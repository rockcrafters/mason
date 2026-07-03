#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""mason-stops-clean: did /mason stop after printing, loading nothing else?

the skill is explicit: print the usage block verbatim, then stop -- no other
skill, no scripts, no files. each violation class costs a third:
  - ran the chisel-releases orientation script (its success marker in the raw
    transcript, same detection as scorer_orientation-called)
  - ran chisel itself (a `chisel cut` / `try-cut` bash command)
  - wrote or edited any file
"""
from _lib import *  # noqa: F403

_ORIENTATION_MARKER = "working dir (chisel-releases checkout):"


def score() -> float:
    t = transcript()
    commands = "\n".join(t["commands"]) if t["parsed"] else t["raw"]
    violations = (
        (_ORIENTATION_MARKER in t["raw"])
        + ("chisel cut" in commands or "try-cut" in commands)
        + bool(t["writes"])
    )
    return 1.0 - violations / 3.0


emit(score)
