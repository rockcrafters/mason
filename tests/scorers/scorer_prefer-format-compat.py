#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""prefer-format-compat: prefer only on fmt>=2."""
from _lib import *  # noqa: F403

def score() -> float:
    def uses(d):
        for _, body in iter_bodies(d):
            contents = body.get("contents")
            if isinstance(contents, dict) and any(isinstance(o, dict) and "prefer" in o for o in contents.values()):
                return True
        return False
    return fmt_compat(uses, min_ok_fmt=2)

emit(score)
