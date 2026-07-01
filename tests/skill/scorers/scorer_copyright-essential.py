#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""copyright-essential: copyright slice is marked essential."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        pkg = doc.get("package")
        essential = doc.get("essential")
        if not isinstance(essential, list) or not isinstance(pkg, str):
            slices = doc.get("slices") or {}
            return 1.0 if isinstance(slices, dict) and "copyright" in slices else 0.0
        return 1.0 if f"{pkg}_copyright" in essential else 0.0
    return avg(f)

emit(score)
