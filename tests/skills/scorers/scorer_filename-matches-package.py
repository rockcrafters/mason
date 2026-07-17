#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""filename-matches-package: doc.package == target stem."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        return 1.0 if isinstance(doc, dict) and doc.get("package") == t else 0.0
    return avg(f)

emit(score)
