#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""v3-essential-format-compat: no v3-essential on incompatible branches."""
from _lib import *  # noqa: F403

def score() -> float:
    return fmt_compat(lambda d: any("v3-essential" in b for _, b in iter_bodies(d)), min_ok_fmt=99, exact_ok=2)

emit(score)
