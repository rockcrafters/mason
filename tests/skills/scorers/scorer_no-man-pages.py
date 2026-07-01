#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""no-man-pages: no man-page paths shipped."""
from _lib import *  # noqa: F403

def score() -> float:
    return avg(path_penalty(lambda p: p.startswith("/usr/share/man/") or p.startswith("/usr/man/")))

emit(score)
