#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""mutate-present: expected mutate slices are present."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        exp = mutate_map(expected(t))
        if not exp:
            return 1.0
        act = mutate_map(produced(t))
        return sum(1 for name in exp if name in act) / len(exp)
    return avg(f)

emit(score)
