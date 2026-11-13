"""Helpers pre-imported into every sandboxed run (`from pitwall import *`).

Runs INSIDE the sandbox container. Data is mounted read-only at /data and the
only writable place is /out. No network, no secrets.
"""

import json
import os

import pandas as pd  # type: ignore[import-untyped]

DATA_DIR = "/data"
OUT_DIR = "/out"
_state = {"suppress": False}  # set while earlier steps are replayed


def load(name):
    """Read a JSON file the loaders staged in /data (list of dicts or dict)."""
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def df(name):
    """Same as load() but as a pandas DataFrame."""
    return pd.DataFrame(load(name))


def emit_chart(option, title="chart"):
    """Publish an ECharts option (a plain dict) as a chart in the answer."""
    if _state["suppress"]:
        return
    n = len([f for f in os.listdir(OUT_DIR) if f.startswith("chart_")])
    with open(os.path.join(OUT_DIR, f"chart_{n:02d}.json"), "w") as f:
        json.dump({"title": title, "option": option}, f)
    print(f"[chart published: {title}]")


__all__ = ["load", "df", "emit_chart", "pd"]
