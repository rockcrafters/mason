#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""structural-distance: produced vs expected content paths (jaccard)."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        actual, exp = produced(t), expected(t)
        if actual is None or exp is None:
            return 0.0
        a, e = content_paths(actual), content_paths(exp)
        if not a and not e:
            return 1.0
        union = a | e
        return len(a & e) / len(union) if union else 0.0
    return avg(f)

emit(score)
