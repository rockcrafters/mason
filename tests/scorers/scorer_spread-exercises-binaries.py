#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""spread-exercises-binaries: spread bundle references the sliced binaries."""
from _lib import *  # noqa: F403

def score() -> float:
    bins: set[str] = set()
    for t in targets():
        bins |= declared_binaries(produced(t))
    if not bins:
        return 1.0
    bundle_path = OUT / f"{TASK}.spread.txt"
    bundle = bundle_path.read_text(encoding="utf-8") if bundle_path.exists() else ""
    if not bundle:
        return 0.0
    return sum(1 for b in bins if b in bundle) / len(bins)

emit(score)
