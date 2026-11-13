"""Load qualifying results and turn them into a clean, comparable target.

Target
------
``gap`` is a driver's Q1 lap as a percentage slower than the fastest Q1 lap of the
same session: ``100 * (t / t_min - 1)``. Q1 is the one segment every driver enters,
so unlike Q2/Q3 it is not censored by knockout (slow cars never reach Q3, which
would bias any model fitted on Q3 times).

Cleaning
--------
* 2006+ only: knockout qualifying, and a comparable single-lap-per-segment format.
* A driver with no Q1 time is *missing* (crash, withdrawn, no lap).
* A gap above ``OUTLIER_PCT`` is a lap that was not representative (red flag,
  traffic, a spin). It is recorded as an outlier and treated as missing.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

FIRST_YEAR = 2006
OUTLIER_PCT = 7.0

_TIME = re.compile(r"^(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parse_laptime(text: str | None) -> float:
    """'1:27.470' -> 87.47 seconds. Anything unparseable is NaN."""
    if not text:
        return np.nan
    m = _TIME.match(text.strip())
    if not m:
        return np.nan
    minutes = int(m.group(1)) if m.group(1) else 0
    return minutes * 60 + float(m.group(2))


def load_quali(conn) -> pd.DataFrame:
    """Raw qualifying rows from ``historical_results`` (kind 'Q')."""
    sql = """
        select year, round, race_name, driver_id, driver_name, constructor_id, q1
        from historical_results
        where kind = 'Q' and year >= %s
        order by year, round, driver_id
    """
    cur = conn.execute(sql, (FIRST_YEAR,))
    cols = [d.name for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def build_gaps(raw: pd.DataFrame, outlier_pct: float = OUTLIER_PCT) -> pd.DataFrame:
    """Add ``session``, ``team_season``, ``t`` (seconds), ``gap`` and ``status``.

    status: 'ok' | 'missing' (no Q1 time) | 'outlier' (gap above the cap).
    ``gap`` is NaN unless status is 'ok'; ``raw_gap`` keeps the uncleaned value.
    """
    df = raw.copy()
    df["t"] = df["q1"].map(parse_laptime)
    df["session"] = df["year"].astype(str) + "-" + df["round"].astype(str).str.zfill(2)
    df["team_season"] = df["constructor_id"] + ":" + df["year"].astype(str)
    fastest = df.groupby("session")["t"].transform("min")
    raw_gap = 100.0 * (df["t"] / fastest - 1.0)
    df["raw_gap"] = raw_gap
    df["status"] = np.where(df["t"].isna(), "missing", np.where(raw_gap > outlier_pct, "outlier", "ok"))
    df["gap"] = raw_gap.where(df["status"] == "ok")
    return df


def sessions_in_order(df: pd.DataFrame) -> list[str]:
    return sorted(df["session"].unique())


def fill_from_session_results(df: pd.DataFrame, conn, session: str, session_key: int) -> pd.DataFrame:
    """Jolpica can lag a few days behind a race weekend. Fill a session's Q1 times from our own
    ``session_results`` (ingested via OpenF1) when Jolpica has the rows but no times."""
    cur = conn.execute("select abbreviation, q1_ms from session_results where session_key = %s", (session_key,))
    own = {a: q / 1000.0 for a, q in cur.fetchall() if q}
    codes = conn.execute(
        "select distinct on (driver_code) driver_code, driver_id from historical_results where kind='Q' and year=%s and driver_code is not null order by driver_code, round desc",
        (int(session.split("-")[0]),),
    ).fetchall()
    code_to_id = {c: i for c, i in codes}
    times = {code_to_id[a]: t for a, t in own.items() if a in code_to_id}
    out = df.copy()
    m = out["session"] == session
    out.loc[m, "t"] = out.loc[m, "driver_id"].map(times)
    fastest = out.loc[m, "t"].min()
    raw = 100.0 * (out.loc[m, "t"] / fastest - 1.0)
    out.loc[m, "raw_gap"] = raw
    status = np.where(out.loc[m, "t"].isna(), "missing", np.where(raw > OUTLIER_PCT, "outlier", "ok"))
    out.loc[m, "status"] = status
    out.loc[m, "gap"] = raw.where(status == "ok")
    return out
