#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""v3-essential-format-compat: v3-essential is a v1/v2 backport, obsolete on v3."""
from _lib import *  # noqa: F403

def score() -> float:
    f_ = fmt()
    if f_ is None:
        raise NA

    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        used = any("v3-essential" in b for _, b in iter_bodies(doc))
        return 0.0 if (used and f_ >= 3) else 1.0
    return avg(f)

emit(score)
