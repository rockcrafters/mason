#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""slice-names-canonical: slice names use canonical vocabulary."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not has_slices(doc):
            return 0.0
        slices = doc["slices"]
        ok = 0
        for name in slices:
            if not isinstance(name, str):
                continue
            if name in CANONICAL:
                ok += 1
                continue
            parts = name.split("-")
            if len(parts) >= 2 and (parts[-1] in CANONICAL or parts[0] in CANONICAL):
                ok += 1
        return ok / len(slices)
    return avg(f)

emit(score)
