#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""essential-map-format-compat: essential-map only on fmt>=3."""
from _lib import *  # noqa: F403

def score() -> float:
    def uses(d):
        return isinstance(d.get("essential"), dict) or any(isinstance(b.get("essential"), dict) for _, b in iter_bodies(d))
    return fmt_compat(uses, min_ok_fmt=3)

emit(score)
