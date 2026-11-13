"""Run model-written Python in an isolated container.

The model never gets a shell, the network, secrets or the database: it only
sees files the loaders staged into a per-run workspace. The Sandbox protocol
is the seam where a runner plugs in. Two exist:

- DockerSandbox: one container per run (local development, CI, any Docker host).
- NamespaceSandbox: for hosts without Docker, such as a Fly machine. It runs
  the script in new network/pid/mount namespaces as an unprivileged user with
  an empty environment and resource limits.

default_sandbox() picks whichever works on the current host.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
import functools
from functools import lru_cache
from pathlib import Path
from typing import Protocol

IMAGE = "pitwall-sandbox"
MAX_OUTPUT_CHARS = 6000
_F1LAB_SRC = Path(__file__).resolve().parents[1] / "f1lab"
_LIB_SRC = Path(__file__).parent / "sandbox_lib"
# data.py needs SQLAlchemy and the database: never ship it into the sandbox
_F1LAB_EXCLUDE = {"data.py", "__pycache__"}


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    charts: list[dict] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


class Sandbox(Protocol):
    def run(
        self, code: str, workspace: "Workspace", *, timeout_s: int = 20
    ) -> SandboxResult: ...


class Workspace:
    """Per-run directory: data/ (loaders write it, scripts may add files), out/ (charts)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(tempfile.mkdtemp(prefix="pitwall-run-"))
        self.data = self.root / "data"
        self.out = self.root / "out"
        self.code = self.root / "code"
        for d in (self.data, self.out, self.code):
            d.mkdir(parents=True, exist_ok=True)
        # the container runs as an unprivileged user and may save intermediate files in data/
        self.out.chmod(0o777)
        self.data.chmod(0o777)

    def write_json(self, name: str, obj: object) -> Path:
        import json

        if "/" in name or name.startswith("."):
            raise ValueError(f"bad data file name: {name!r}")
        path = self.data / name
        path.write_text(json.dumps(obj, default=str))
        return path

    def data_files(self) -> list[str]:
        return sorted(p.name for p in self.data.iterdir())

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


@lru_cache(maxsize=1)
def _lib_dir() -> Path:
    """Build the read-only lib mounted at /pylib: pitwall.py + f1lab (no DB code)."""
    lib = Path(tempfile.mkdtemp(prefix="pitwall-lib-"))
    shutil.copy(_LIB_SRC / "pitwall.py", lib / "pitwall.py")
    pkg = lib / "backend"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")  # stub: the real one imports Flask
    shutil.copytree(
        _F1LAB_SRC, pkg / "f1lab", ignore=shutil.ignore_patterns(*_F1LAB_EXCLUDE)
    )
    return lib


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        text[:MAX_OUTPUT_CHARS]
        + f"\n... [truncated {len(text) - MAX_OUTPUT_CHARS} chars]"
    )


def _collect(workspace: "Workspace", before: set) -> tuple[list[dict], list[str]]:
    """Charts (chart_*.json) and other files a run wrote to out/."""
    import json

    charts, files = [], []
    for path in sorted(set(workspace.out.iterdir()) - before):
        if path.name.startswith("chart_") and path.suffix == ".json":
            try:
                charts.append(json.loads(path.read_text()))
            except ValueError:
                pass
        else:
            files.append(path.name)
    return charts, files


class DockerSandbox:
    def __init__(
        self, image: str = IMAGE, memory: str = "512m", cpus: str = "1"
    ) -> None:
        self.image = image
        self.memory = memory
        self.cpus = cpus

    @staticmethod
    def available(image: str = IMAGE) -> bool:
        """True when docker is reachable and the sandbox image exists."""
        try:
            done = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                timeout=10,
            )
            return done.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def run(
        self, code: str, workspace: Workspace, *, timeout_s: int = 20
    ) -> SandboxResult:
        script = workspace.code / f"run_{uuid.uuid4().hex[:8]}.py"
        script.write_text("from pitwall import *\n" + code)
        name = f"pw-sandbox-{uuid.uuid4().hex[:10]}"
        cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none",
            "--memory", self.memory, "--cpus", self.cpus, "--pids-limit", "128",
            "--read-only", "--tmpfs", "/tmp:size=64m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            "-v", f"{workspace.data}:/data",
            "-v", f"{workspace.out}:/out",
            "-v", f"{script.parent}:/code:ro",
            "-v", f"{_lib_dir()}:/pylib:ro",
            "-e", "PYTHONPATH=/pylib",
            "-w", "/data",
            self.image, "python", f"/code/{script.name}",
        ]  # fmt: skip
        import time

        started = time.perf_counter()
        before = set(workspace.out.iterdir())
        try:
            done = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s
            )
            timed_out, stdout, stderr, ok = (
                False,
                done.stdout,
                done.stderr,
                done.returncode == 0,
            )
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker", "kill", name], capture_output=True)
            timed_out, ok = True, False
            stdout = (
                (exc.stdout or b"").decode()
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            )
            stderr = f"timed out after {timeout_s}s"
        duration = round(time.perf_counter() - started, 2)

        charts, files = _collect(workspace, before)
        return SandboxResult(
            ok, _clip(stdout), _clip(stderr), duration, timed_out, charts, files
        )


_UNPRIVILEGED_ID = "65534"  # nobody


class NamespaceSandbox:
    """Run model-written Python without Docker, inside the current (Linux) host.

    Needs root (or CAP_SYS_ADMIN) to create namespaces, which a Fly machine
    has. Isolation per run:
    - new network namespace: no network at all
    - new pid + mount-proc namespace: it cannot see or signal other processes,
      and /proc/<pid>/environ of the API is not reachable
    - runs as uid/gid 65534 with no extra groups and no_new_privs
    - an EMPTY environment: no API keys, database URL or tokens are inherited
    - RLIMITs on memory, processes, CPU time and file size
    Weaker than a container (the filesystem is the host's, read-only for this
    user), so it never gets secrets: the only thing worth reading is public data.
    """

    def __init__(
        self, memory_bytes: int = 1_500_000_000, max_procs: int = 128
    ) -> None:
        self.memory_bytes = memory_bytes
        self.max_procs = max_procs

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def available() -> bool:
        """True when this host can create the namespaces (Linux, enough privilege)."""
        if not sys.platform.startswith("linux"):
            return False
        for tool in ("unshare", "setpriv", "prlimit"):
            if shutil.which(tool) is None:
                return False
        try:
            done = subprocess.run(
                ["unshare", "--net", "--pid", "--fork", "--mount", "--mount-proc", "true"],
                capture_output=True,
                timeout=10,
            )
            return done.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _make_readable(self, workspace: "Workspace") -> None:
        """The run executes as another user: let it traverse to, and read, its inputs."""
        workspace.root.chmod(0o711)  # traverse only, no listing
        workspace.code.chmod(0o755)
        for path in workspace.code.iterdir():
            path.chmod(0o644)
        for path in workspace.data.iterdir():
            path.chmod(0o666)
        lib = _lib_dir()
        for dirpath, dirnames, filenames in os.walk(lib):
            os.chmod(dirpath, 0o755)
            for name in filenames:
                os.chmod(os.path.join(dirpath, name), 0o644)

    def run(
        self, code: str, workspace: Workspace, *, timeout_s: int = 20
    ) -> SandboxResult:
        import time

        script = workspace.code / f"run_{uuid.uuid4().hex[:8]}.py"
        script.write_text("from pitwall import *\n" + code)
        self._make_readable(workspace)

        # The helper library expects /data and /out (the Docker mount points).
        # Bind the run's workspace there inside the private mount namespace; on
        # Fly this also hides the real /data volume from the sandboxed code.
        mount_and_exec = (
            'mkdir -p /data /out && mount --bind "$1" /data && mount --bind "$2" /out'
            ' && shift 2 && cd /data && exec "$@"'
        )
        cmd = [
            "unshare", "--net", "--pid", "--fork", "--mount", "--mount-proc",
            "--kill-child",
            "sh", "-c", mount_and_exec, "sandbox", str(workspace.data), str(workspace.out),
            "setpriv", f"--reuid={_UNPRIVILEGED_ID}", f"--regid={_UNPRIVILEGED_ID}",
            "--clear-groups", "--no-new-privs",
            "prlimit",
            f"--as={self.memory_bytes}", f"--nproc={self.max_procs}",
            f"--cpu={timeout_s + 5}", "--fsize=67108864", "--nofile=256",
            sys.executable, str(script),
        ]  # fmt: skip
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONPATH": str(_lib_dir()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "HOME": "/tmp",
            "MPLCONFIGDIR": "/tmp",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        }
        started = time.perf_counter()
        before = set(workspace.out.iterdir())
        proc = subprocess.Popen(
            cmd,
            cwd=workspace.data,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
            timed_out, ok = False, proc.returncode == 0
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, _ = proc.communicate()
            timed_out, ok = True, False
            stderr = f"timed out after {timeout_s}s"
        duration = round(time.perf_counter() - started, 2)

        charts, files = _collect(workspace, before)
        return SandboxResult(
            ok, _clip(stdout or ""), _clip(stderr or ""), duration, timed_out, charts, files
        )


def default_sandbox() -> Sandbox | None:
    """The sandbox to use on this host, or None when nothing safe is available."""
    if DockerSandbox.available():
        return DockerSandbox()
    if NamespaceSandbox.available():
        return NamespaceSandbox()
    return None
