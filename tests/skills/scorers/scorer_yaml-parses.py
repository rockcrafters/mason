#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""yaml-parses: each produced <target>.yaml parses."""
from _lib import *  # noqa: F403

def score() -> float:
    return avg(lambda t: 1.0 if produced(t) is not None else 0.0)

emit(score)
