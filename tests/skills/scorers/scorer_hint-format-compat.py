#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""hint-format-compat: hint only on fmt>=3."""
from _lib import *  # noqa: F403

def score() -> float:
    return fmt_compat(lambda d: any("hint" in b for _, b in iter_bodies(d)), min_ok_fmt=3)

emit(score)
