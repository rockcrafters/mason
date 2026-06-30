#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""paths-sorted: contents keys sorted within each slice."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        slices = doc.get("slices")
        if not isinstance(slices, dict):
            return 1.0
        for body in slices.values():
            if not isinstance(body, dict):
                continue
            contents = body.get("contents")
            if not isinstance(contents, dict):
                continue
            keys = list(contents.keys())
            if keys != sorted(keys):
                return 0.0
        return 1.0
    return avg(f)

emit(score)
