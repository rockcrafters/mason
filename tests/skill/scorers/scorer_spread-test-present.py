#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""spread-test-present: the agent wrote a spread task.yaml."""
from _lib import *  # noqa: F403

def score() -> float:
    p = OUT / f"{TASK}.task.yaml"
    return 1.0 if p.exists() and p.stat().st_size > 0 else 0.0

emit(score)
