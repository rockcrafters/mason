#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""mutate-paths: mutate read/write paths match ground truth (jaccard)."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        exp_map = mutate_map(expected(t))
        if not exp_map:
            return 1.0
        act_map = mutate_map(produced(t))
        exp_paths = set().union(*(mutate_paths(s) for s in exp_map.values()))
        act_paths = set().union(*(mutate_paths(s) for s in act_map.values())) if act_map else set()
        if not exp_paths and not act_paths:
            return 1.0
        union = exp_paths | act_paths
        return len(exp_paths & act_paths) / len(union) if union else 0.0
    return avg(f)

emit(score)
