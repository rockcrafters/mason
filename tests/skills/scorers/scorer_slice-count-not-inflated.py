#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""slice-count-not-inflated: produced slice count not above ground truth."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        actual, exp = produced(t), expected(t)
        if not isinstance(actual, dict) or not isinstance(exp, dict):
            return 0.0
        a = actual.get("slices") or {}
        e = exp.get("slices") or {}
        if not isinstance(a, dict) or not isinstance(e, dict):
            return 0.0
        na, ne = len(a), len(e)
        if na == 0:
            return 1.0 if ne == 0 else 0.0
        return min(1.0, ne / na)
    return avg(f)

emit(score)
