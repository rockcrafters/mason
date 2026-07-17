#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""copyright-path-present: copyright slice ships the copyright file."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        pkg = doc.get("package") if isinstance(doc.get("package"), str) else t
        slices = doc.get("slices")
        if not isinstance(slices, dict):
            return 0.0
        cp = slices.get("copyright")
        if not isinstance(cp, dict):
            return 0.0
        contents = cp.get("contents")
        if not isinstance(contents, dict):
            return 0.0
        return 1.0 if f"/usr/share/doc/{pkg}/copyright" in contents else 0.0
    return avg(f)

emit(score)
