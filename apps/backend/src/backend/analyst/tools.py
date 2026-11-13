"""Tools the analyst model can call. Read-only; data lands in a per-run workspace."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from backend.analyst.sandbox import Sandbox, Workspace
from backend.f1lab import data, report, sanity

MAX_TOOL_TEXT = 4500
READ_HINT = "Read staged files with load('<file>') (list of dicts) or df('<file>') (DataFrame); not pd.read_json."

# Earlier successful scripts are replayed (output and charts suppressed) before each new one,
# so variables persist between run_python calls, which models assume they do.
_REPLAY = """import contextlib as _cx, io as _io, pitwall as _pw
_pw._state["suppress"] = True
with _cx.redirect_stdout(_io.StringIO()):
    for _src in {sources!r}:
        try:
            exec(compile(_src, "<earlier step>", "exec"), globals())
        except Exception:
            pass
_pw._state["suppress"] = False
del _cx, _io, _pw
"""


def profile_rows(rows: list[dict], max_values: int = 12) -> str:
    """Which values text columns hold and where data is missing, so models need not guess."""
    parts = []
    for column in rows[0]:
        values = [r.get(column) for r in rows]
        present = [v for v in values if v is not None]
        missing = len(values) - len(present)
        if missing:
            parts.append(f"{column} is empty in {missing} of {len(values)} rows")
        counts = Counter(v for v in present if isinstance(v, (str, bool)))
        if counts and len(counts) <= max_values:
            listed = ", ".join(f"{k} x{n}" for k, n in counts.most_common())
            parts.append(f"{column} values: {listed}")
    return "Data profile: " + "; ".join(parts) if parts else ""


@dataclass
class ToolOutput:
    text: str  # what the model sees
    ok: bool = True
    title: str = ""  # short card title for the UI
    preview: str = ""  # code or table excerpt shown on the card
    charts: list[dict] = field(default_factory=list)


def _clip(s: str) -> str:
    return s if len(s) <= MAX_TOOL_TEXT else s[:MAX_TOOL_TEXT] + "\n...[truncated]"


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOL_SCHEMAS: list[dict] = [
    _schema(
        "find_sessions",
        "List stored sessions (with lap and telemetry coverage). Use first to get a session_key.",
        {
            "year": {"type": "integer"},
            "gp": {
                "type": "string",
                "description": "part of the GP name, e.g. 'Singapore'",
            },
            "session_type": {"type": "string", "description": "R race, Q qualifying"},
        },
        [],
    ),
    _schema(
        "race_summary",
        "Facts for a race, one line per driver: final order, tyre compounds, stops with pit "
        "loss and position before each stop, median clean lap, laps in traffic. Call this FIRST "
        "for any question about a race, before loading laps.",
        {"session_key": {"type": "integer"}},
        ["session_key"],
    ),
    _schema(
        "load_laps",
        "Stage lap times (and the drivers table) for a session into /data. Optional driver "
        "(abbreviation, surname or number-free name).",
        {"session_key": {"type": "integer"}, "driver": {"type": "string"}},
        ["session_key"],
    ),
    _schema(
        "load_telemetry",
        "Stage one lap of telemetry samples (distance_m, speed_kmh, brake, gear, drs, x_pos, y_pos) "
        "into /data. There is NO throttle channel.",
        {
            "session_key": {"type": "integer"},
            "driver": {"type": "string"},
            "lap": {"type": "integer"},
        },
        ["session_key", "driver", "lap"],
    ),
    _schema(
        "load_context",
        "Stage results, weather and race-control events for a session into /data.",
        {"session_key": {"type": "integer"}},
        ["session_key"],
    ),
    _schema(
        "run_python",
        "Run Python in an isolated sandbox (pandas, numpy, scipy, backend.f1lab; no network). Variables from earlier successful calls stay available. "
        "Start the code with one comment line describing the step. Read staged files with load()/df(); "
        "print results; publish charts with emit_chart(echarts_option_dict, title). Variables do "
        "not persist between calls.",
        {"code": {"type": "string"}},
        ["code"],
    ),
    _schema(
        "final_answer",
        "Finish with the answer in Markdown. State assumptions and mark estimates as estimates.",
        {"markdown": {"type": "string"}},
        ["markdown"],
    ),
]

ConnFactory = Callable[[], AbstractContextManager[Any]]
TelemetryReader = Callable[[int, int, int], list[dict]]


def _default_conn() -> AbstractContextManager[Any]:
    from backend import extensions

    return extensions.engine.connect()


def _default_telemetry(session_key: int, driver_number: int, lap: int) -> list[dict]:
    from backend.agent import tools as agent_tools
    from backend.agent import types

    found = agent_tools.get_lap_telemetry_artifacts(
        types.GetLapTelemetryArtifactsInput(
            session_key=session_key, driver_number=driver_number, lap_numbers=(lap,)
        )
    )
    if not found.artifacts:
        raise LookupError("no telemetry artifact for that driver/lap")
    return agent_tools._read_artifact_full_channels(found.artifacts[0])


class ToolBox:
    def __init__(
        self,
        workspace: Workspace,
        sandbox: Sandbox,
        *,
        conn_factory: ConnFactory = _default_conn,
        telemetry_reader: TelemetryReader = _default_telemetry,
        sandbox_timeout_s: int = 20,
    ) -> None:
        self.workspace = workspace
        self.sandbox = sandbox
        self.conn_factory = conn_factory
        self.telemetry_reader = telemetry_reader
        self.sandbox_timeout_s = sandbox_timeout_s
        self._history: list[str] = []  # successful scripts, replayed for persistence

    def call(self, name: str, args: dict) -> ToolOutput:
        handlers: dict[str, Callable[..., ToolOutput]] = {
            "find_sessions": self._find_sessions,
            "race_summary": self._race_summary,
            "load_laps": self._load_laps,
            "load_telemetry": self._load_telemetry,
            "load_context": self._load_context,
            "run_python": self._run_python,
        }
        handler = handlers.get(name)
        if handler is None:
            return ToolOutput(f"unknown tool {name!r}", ok=False, title=name)
        try:
            out = handler(**args)
        except TypeError as exc:
            return ToolOutput(f"bad arguments for {name}: {exc}", ok=False, title=name)
        except Exception as exc:  # a failing tool is information for the model
            return ToolOutput(f"{name} failed: {exc}", ok=False, title=name)
        out.text = _clip(out.text)
        return out

    # ── loaders ──────────────────────────────────────────────────────────

    def _find_sessions(
        self,
        year: int | None = None,
        gp: str | None = None,
        session_type: str | None = None,
    ) -> ToolOutput:
        sql = text(
            """
            SELECT s.session_key, s.year, s.gp_name, s.session_type,
              (SELECT count(*) FROM lap_times l WHERE l.session_key = s.session_key) AS laps,
              (SELECT count(*) FROM telemetry_artifacts t WHERE t.session_key = s.session_key) AS telemetry_laps
            FROM sessions s
            WHERE (CAST(:year AS INTEGER) IS NULL OR s.year = CAST(:year AS INTEGER))
              AND (CAST(:gp AS TEXT) IS NULL OR s.gp_name ILIKE CAST(:gp AS TEXT))
              AND (CAST(:st AS TEXT) IS NULL OR s.session_type = CAST(:st AS TEXT))
            ORDER BY s.year DESC, s.session_key DESC
            LIMIT 12
            """
        )
        with self.conn_factory() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    sql,
                    {"year": year, "gp": f"%{gp}%" if gp else None, "st": session_type},
                ).mappings()
            ]
        if not rows:
            return ToolOutput(
                "no matching sessions stored", ok=False, title="Find sessions"
            )
        lines = [
            f"session_key={r['session_key']} {r['year']} {r['gp_name']} [{r['session_type']}] "
            f"laps={r['laps']} telemetry_laps={r['telemetry_laps']}"
            for r in rows
        ]
        return ToolOutput(
            "\n".join(lines),
            title=f"Find sessions · {gp or year or 'all'}",
            preview="\n".join(lines[:4]),
        )

    def _race_summary(self, session_key: int) -> ToolOutput:
        with self.conn_factory() as conn:
            session_type = conn.execute(
                text("SELECT session_type FROM sessions WHERE session_key = :sk"),
                {"sk": session_key},
            ).scalar()
            if session_type != "R":
                return ToolOutput(
                    f"race_summary only works for races; this session is {session_type!r}",
                    ok=False,
                    title="Race summary",
                )
            laps = data.load_laps(conn, session_key, include_deleted=True)
            roster = conn.execute(
                text(
                    "SELECT driver_number, abbreviation, full_name FROM drivers "
                    "WHERE session_key = :sk"
                ),
                {"sk": session_key},
            ).all()
            labels = {row[0]: row[1] for row in roster}
            names = {row[0]: row[2] for row in roster}
        if not laps:
            return ToolOutput(
                "no lap data for that session", ok=False, title="Race summary"
            )
        summary = report.race_summary(laps, labels, names)
        self.workspace.write_json(f"race_summary_{session_key}.json", summary)
        text_out = report.format_race_summary(summary)
        return ToolOutput(
            text_out,
            title=f"Race summary · session {session_key}",
            preview="\n".join(text_out.splitlines()[1:5]),
        )

    def _load_laps(self, session_key: int, driver: str | None = None) -> ToolOutput:
        with self.conn_factory() as conn:
            number = None
            if driver:
                number = data.resolve_driver_number(conn, session_key, driver)
                if number is None:
                    roster = (
                        conn.execute(
                            text(
                                "SELECT abbreviation FROM drivers WHERE session_key = :sk ORDER BY 1"
                            ),
                            {"sk": session_key},
                        )
                        .scalars()
                        .all()
                    )
                    return ToolOutput(
                        f"driver {driver!r} not in session {session_key}. Drivers: {', '.join(roster)}",
                        ok=False,
                        title=f"Laps · {driver}",
                    )
            laps = data.load_laps(conn, session_key, number, include_deleted=True)
            drivers = [
                dict(r)
                for r in conn.execute(
                    text(
                        "SELECT driver_number, abbreviation, full_name, team_name "
                        "FROM drivers WHERE session_key = :sk ORDER BY driver_number"
                    ),
                    {"sk": session_key},
                ).mappings()
            ]
        if not laps:
            return ToolOutput(
                "no lap data for that session/driver", ok=False, title="Laps"
            )
        tag = f"{session_key}" + (f"_{number}" if number else "")
        laps_file, drivers_file = f"laps_{tag}.json", f"drivers_{session_key}.json"
        self.workspace.write_json(laps_file, laps)
        self.workspace.write_json(drivers_file, drivers)
        total = data.race_length(laps)
        summary = (
            f"{laps_file}: {len(laps)} laps, race length {total} laps. Columns: "
            + ", ".join(laps[0].keys())
            + f"\n{drivers_file}: "
            + ", ".join(f"{d['abbreviation']}={d['driver_number']}" for d in drivers)
            + "\nlap_time_ms is milliseconds; track_status is a string of codes "
            "(4=SC, 5=red, 6/7=VSC); pit_in_time_ms is set on the in-lap, pit_out_time_ms on the out-lap."
            f"\n{READ_HINT}"
            f"\n{profile_rows(laps)}"
        )
        return ToolOutput(
            summary,
            title=f"Laps · {driver or 'all drivers'}",
            preview=f"{len(laps)} laps · race length {total}",
        )

    def _load_telemetry(self, session_key: int, driver: str, lap: int) -> ToolOutput:
        with self.conn_factory() as conn:
            number = data.resolve_driver_number(conn, session_key, driver)
        if number is None:
            return ToolOutput(
                f"driver {driver!r} not in session", ok=False, title="Telemetry"
            )
        try:
            samples = self.telemetry_reader(session_key, number, lap)
        except LookupError as exc:
            return ToolOutput(str(exc), ok=False, title=f"Telemetry · {driver} L{lap}")
        name = f"telemetry_{session_key}_{number}_{lap}.json"
        self.workspace.write_json(name, samples)
        issues = sanity.check_telemetry(samples)
        speeds = [s["speed_kmh"] for s in samples if s.get("speed_kmh") is not None]
        summary = (
            f"{name}: {len(samples)} samples, channels: {', '.join(samples[0].keys())}. "
            f"speed {min(speeds):.0f}-{max(speeds):.0f} km/h, lap distance "
            f"{samples[-1]['distance_m']:.0f} m. x_pos/y_pos are in 1/10 m."
        )
        if issues:
            summary += "\nData-quality notes: " + "; ".join(
                f"{i.code}: {i.message}" for i in issues
            )
        summary += f"\n{READ_HINT}"
        return ToolOutput(
            summary,
            title=f"Telemetry · {driver} L{lap}",
            preview=f"{len(samples)} samples",
        )

    def _load_context(self, session_key: int) -> ToolOutput:
        queries = {
            f"results_{session_key}.json": (
                "SELECT driver_number, abbreviation, team_name, grid_position, position, "
                "classified_position, status, points, laps_completed, race_time_ms, q1_ms, q2_ms, q3_ms "
                "FROM session_results WHERE session_key = :sk ORDER BY position NULLS LAST"
            ),
            f"weather_{session_key}.json": (
                "SELECT lap_number, track_temp_c, air_temp_c, humidity_pct, rainfall, wind_speed_ms "
                "FROM weather_events WHERE session_key = :sk ORDER BY timestamp"
            ),
            f"race_control_{session_key}.json": (
                "SELECT lap_number, category, flag, driver_number, message "
                "FROM race_control_events WHERE session_key = :sk ORDER BY recorded_at"
            ),
        }
        lines = []
        with self.conn_factory() as conn:
            for name, sql in queries.items():
                rows = [
                    dict(r)
                    for r in conn.execute(text(sql), {"sk": session_key}).mappings()
                ]
                if rows:
                    self.workspace.write_json(name, rows)
                    sample = json.dumps(rows[0], default=str)[:220]
                    lines.append(
                        f"{name}: {len(rows)} rows. Columns: {', '.join(rows[0])}. First row: {sample}"
                    )
                    profile = profile_rows(rows)
                    if profile:
                        lines.append(profile)
                else:
                    lines.append(f"{name}: NO DATA")
        lines.append(READ_HINT)
        return ToolOutput(
            "\n".join(lines),
            title=f"Context · session {session_key}",
            preview="\n".join(lines),
        )

    # ── compute ──────────────────────────────────────────────────────────

    def _run_python(self, code: str) -> ToolOutput:
        first = code.strip().splitlines()[0] if code.strip() else ""
        title = first.lstrip("# ").strip()[:60] if first.startswith("#") else "Compute"
        script = _REPLAY.format(sources=self._history) + code if self._history else code
        result = self.sandbox.run(
            script, self.workspace, timeout_s=self.sandbox_timeout_s
        )
        if result.ok:
            self._history.append(code)
        parts = [("OK" if result.ok else "ERROR") + f" ({result.duration_s}s)"]
        if result.stdout.strip():
            parts.append("stdout:\n" + result.stdout.strip())
        if result.stderr.strip():
            parts.append("stderr:\n" + result.stderr.strip()[-1500:])
        if not result.ok:
            parts += self._hints(result.stderr)
        elif not result.stdout.strip() and not result.charts:
            parts.append(
                "Note: this script printed nothing, so it produced no result. "
                "Use print() to see values."
            )
        if result.charts:
            parts.append(f"{len(result.charts)} chart(s) published")
        return ToolOutput(
            "\n".join(parts),
            ok=result.ok,
            title=title,
            preview="\n".join(code.strip().splitlines()[:14]),
            charts=result.charts,
        )

    def _hints(self, stderr: str) -> list[str]:
        """Plain-language pointers for the mistakes models make most often."""
        hints = []
        if "read_json" in stderr or "FileNotFoundError" in stderr:
            hints.append(
                f"Hint: {READ_HINT} Staged files: {', '.join(self.workspace.data_files())}."
            )
        if "NameError" in stderr:
            hints.append(
                "Hint: variables from earlier SUCCESSFUL run_python calls are available; "
                "a name that was never defined in one of them is not."
            )
        return hints


def parse_args(raw: str) -> dict:
    """Tool arguments as the model wrote them; {} when they are not valid JSON."""
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def describe_call(name: str, args: dict) -> tuple[str, str]:
    """(card title, preview) for a tool call, known before it runs."""
    if name == "run_python":
        code = str(args.get("code", "")).strip()
        first = code.splitlines()[0] if code else ""
        title = first.lstrip("# ").strip()[:60] if first.startswith("#") else "Compute"
        return title, "\n".join(code.splitlines()[:14])
    if name == "find_sessions":
        label = args.get("gp") or args.get("year") or "all"
        return f"Find sessions · {label}", ""
    if name == "race_summary":
        return f"Race summary · session {args.get('session_key')}", ""
    if name == "load_laps":
        return (
            f"Laps · {args.get('driver') or 'all drivers'}",
            f"session {args.get('session_key')}",
        )
    if name == "load_telemetry":
        return (
            f"Telemetry · {args.get('driver')} L{args.get('lap')}",
            f"session {args.get('session_key')}",
        )
    if name == "load_context":
        return f"Context · session {args.get('session_key')}", ""
    return name, ""
