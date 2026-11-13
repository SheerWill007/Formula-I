"""Sandbox tests against every sandbox this host supports.

DockerSandbox needs the image: docker build -t pitwall-sandbox infra/sandbox
NamespaceSandbox needs Linux and root (it is what runs on a Fly machine).
Each test is skipped for a sandbox that is not available here.
"""

import pytest

from backend.analyst.sandbox import DockerSandbox, NamespaceSandbox, Workspace


@pytest.fixture(params=["docker", "namespace"])
def sb(request):
    if request.param == "docker":
        if not DockerSandbox.available():
            pytest.skip("pitwall-sandbox image not available")
        return DockerSandbox()
    if not NamespaceSandbox.available():
        pytest.skip("namespaces not available on this host")
    return NamespaceSandbox()


@pytest.fixture()
def ws():
    workspace = Workspace()
    yield workspace
    workspace.cleanup()


def _run(sb, ws, code, timeout_s=30):
    return sb.run(code, ws, timeout_s=timeout_s)


def test_runs_code_and_returns_stdout(sb, ws):
    result = _run(sb, ws, "print(2 + 2)")
    assert result.ok and result.stdout.strip() == "4"


def test_reads_staged_data_with_helpers(sb, ws):
    ws.write_json("laps.json", [{"lap": 1, "t": 95.0}, {"lap": 2, "t": 94.0}])
    result = _run(sb, ws, "print(df('laps.json')['t'].mean())")
    assert result.ok and result.stdout.strip() == "94.5"


def test_f1lab_is_importable_but_database_code_is_not(sb, ws):
    ok = _run(sb, ws, "from backend.f1lab.pace import fit_degradation\nprint('f1lab ok')")
    assert ok.ok and "f1lab ok" in ok.stdout
    bad = _run(sb, ws, "import backend.f1lab.data")
    assert not bad.ok and "ModuleNotFoundError" in bad.stderr


def test_emit_chart_is_collected(sb, ws):
    result = _run(
        sb, ws, "emit_chart({'series': [{'type': 'line', 'data': [1, 2]}]}, 'Pace')"
    )
    assert result.ok
    assert result.charts == [
        {"title": "Pace", "option": {"series": [{"type": "line", "data": [1, 2]}]}}
    ]


def test_python_errors_are_reported_not_raised(sb, ws):
    result = _run(sb, ws, "1/0")
    assert not result.ok and "ZeroDivisionError" in result.stderr


def test_no_network(sb, ws):
    result = _run(
        sb, ws,
        "import socket\ns = socket.socket()\ns.settimeout(3)\ns.connect(('1.1.1.1', 80))",
    )
    assert not result.ok


def test_scripts_can_save_files_in_data_but_not_elsewhere(sb, ws):
    ws.write_json("x.json", [1])
    saved = _run(sb, ws, "open('notes.json', 'w').write('[2]')\nprint(load('notes.json'))")
    assert saved.ok and saved.stdout.strip() == "[2]"
    assert (ws.data / "notes.json").exists()
    assert not _run(sb, ws, "open('/etc/evil', 'w').write('x')").ok
    assert not _run(sb, ws, "open('/pylib/evil.py', 'w').write('x')").ok


def test_relative_paths_resolve_inside_the_data_dir(sb, ws):
    ws.write_json("laps.json", [{"a": 1}])
    assert _run(sb, ws, "print(len(open('laps.json').read()) > 0)").stdout.strip() == "True"


def test_infinite_loop_times_out(sb, ws):
    result = _run(sb, ws, "while True:\n    pass", timeout_s=3)
    assert result.timed_out and not result.ok


def test_output_is_truncated(sb, ws):
    result = _run(sb, ws, "print('x' * 50000)")
    assert result.ok and len(result.stdout) < 7000 and "truncated" in result.stdout


def test_replayed_earlier_steps_keep_variables_without_repeating_output_or_charts(sb, ws):
    from backend.analyst.tools import ToolBox

    box = ToolBox(ws, sb)
    first = box.call(
        "run_python",
        {"code": "total = 41\nprint('first')\nemit_chart({'series': []}, 'one')"},
    )
    second = box.call("run_python", {"code": "print(total + 1)"})
    assert first.ok and len(first.charts) == 1
    assert second.ok and second.text.count("first") == 0 and "42" in second.text
    assert second.charts == []


def test_environment_secrets_are_not_visible(sb, ws, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@host/db")
    result = _run(
        sb,
        ws,
        "import os\n"
        "print([k for k, v in os.environ.items() if 'should-not-leak' in v or 'secret@host' in v])",
    )
    assert result.ok and result.stdout.strip() == "[]"


def test_cannot_read_the_hosts_environment_through_proc(sb, ws, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    code = (
        "import glob\n"
        "hits = []\n"
        "for f in glob.glob('/proc/[0-9]*/environ'):\n"
        "    try:\n"
        "        if b'sk-should-not-leak' in open(f, 'rb').read():\n"
        "            hits.append(f)\n"
        "    except OSError:\n"
        "        pass\n"
        "print(hits)"
    )
    result = _run(sb, ws, code)
    assert result.ok and result.stdout.strip() == "[]"


def test_namespace_sandbox_runs_as_an_unprivileged_user(ws):
    if not NamespaceSandbox.available():
        pytest.skip("namespaces not available on this host")
    result = NamespaceSandbox().run("import os\nprint(os.getuid())", ws, timeout_s=30)
    assert result.ok and result.stdout.strip() == "65534"
