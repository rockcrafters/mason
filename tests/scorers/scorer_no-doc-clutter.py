#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""no-doc-clutter: no doc/lintian clutter (copyright allowed)."""
from _lib import *  # noqa: F403

def score() -> float:
    def allow(path, doc):
        pkg = doc.get("package") if isinstance(doc.get("package"), str) else ""
        return path == f"/usr/share/doc/{pkg}/copyright"
    return avg(path_penalty(
        lambda p: p.startswith("/usr/share/doc/") or p.startswith("/usr/share/doc-base/") or p.startswith("/usr/share/lintian/"),
        allow,
    ))

emit(score)
