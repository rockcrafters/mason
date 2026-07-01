#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""arch-format: arch: lists are sorted, lowercase, tidy."""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        p = OUT / f"{t}.yaml"
        if not has_slices(produced(t)):
            return 0.0
        bad = total = 0
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("arch:"):
                continue
            total += 1
            value = line[len("arch:"):].strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                if inner != inner.strip():
                    bad += 1
                    continue
                parts = [x.strip() for x in inner.split(",")]
                if parts != sorted(parts) or any(x != x.lower() for x in parts):
                    bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return avg(f)

emit(score)
