from __future__ import annotations
import textwrap
from dataclasses import dataclass
from backend.agent import llm as llm_client

SYSTEM_PROMPT = (
    "You are an F1 Data Analyst. Write a secure Pandas script to answer the query "
    "using the provided data. You must only print the final statistical result to "
    "standard output. Do not include markdown formatting or markdown code blocks in "
    "your response — output pure Python code only."
)

TIMEOUT_SECONDS = 10


@dataclass
class ComputeInput:
    query: str
    data_csv: str
    error_feedback: str = ""


@dataclass
class ComputeOutput:
    script: str
    result: str
    success: bool


def run(inp: ComputeInput) -> ComputeOutput:
    """Generate and execute the pandas script to answer the query"""
    prompt = _build_prompt(inp)
    script = llm_client.complete(prompt, system=SYSTEM_PROMPT)
    result, success = _execute(script, inp.data_csv)

    return ComputeOutput(script=script, result=result, success=success)


def _build_prompt(inp: ComputeInput) -> str:
    parts = [
        f"Query : {inp.query}",
        "",
        "The CSV data is already loaded into a pandas DataFrame called `df`.",
        "Write a Python script using `df` to answer the query. Print only the answer.",
    ]
    if inp.error_feedback:
        parts += ["", f"PREVIOUS ERROR — fix this: {inp.error_feedback}"]
    return "\n".join(parts)


def _execute(script: str, data_csv: str) -> tuple[str, bool]:
    """Run the model's script in the Docker sandbox (no network, no secrets)."""
    from backend.analyst.sandbox import Workspace, default_sandbox

    sandbox = default_sandbox()
    if sandbox is None:
        return "Error: analysis sandbox is unavailable.", False

    workspace = Workspace()
    try:
        (workspace.data / "data.csv").write_text(data_csv)
        code = "df = pd.read_csv('/data/data.csv')\n" + textwrap.dedent(script)
        result = sandbox.run(code, workspace, timeout_s=TIMEOUT_SECONDS)
    finally:
        workspace.cleanup()

    if result.timed_out:
        return "Error: script exceeded 10-second timeout.", False
    if not result.ok:
        return f"Script error: {result.stderr[:500]}", False
    return result.stdout.strip(), True
