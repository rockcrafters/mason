#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""essential-list-on-v1: on v1 branches, essential is a string list. NA otherwise."""
from _lib import *  # noqa: F403

def score() -> float:
    f_ = fmt()
    if f_ is None or f_ != 1:
        raise NA

    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        for _, body in iter_bodies(doc):
            ess = body.get("essential")
            if ess is None:
                continue
            if not isinstance(ess, list) or not all(isinstance(x, str) for x in ess):
                return 0.0
        return 1.0
    return avg(f)

emit(score)
