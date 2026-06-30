#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""target-present: a non-empty <target>.yaml exists per target."""
from _lib import *  # noqa: F403

def score() -> float:
    return avg(lambda t: 1.0 if (OUT / f"{t}.yaml").exists() and (OUT / f"{t}.yaml").stat().st_size > 0 else 0.0)

emit(score)
