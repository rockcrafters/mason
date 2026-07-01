#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""mutable-has-text: mutable entries carry text (or symlink/copy)."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not has_slices(doc):
            return 0.0
        total = bad = 0
        for _, _, entry in iter_contents(doc):
            if not isinstance(entry, dict) or entry.get("mutable") is not True:
                continue
            total += 1
            text = entry.get("text")
            if isinstance(text, str) and text != "":
                continue
            if isinstance(entry.get("symlink"), str) or isinstance(entry.get("copy"), str):
                continue
            bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return avg(f)

emit(score)
