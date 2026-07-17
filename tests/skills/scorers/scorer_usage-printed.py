#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""usage-printed: did /mason print the usage block?

exact-verbatim matching would be brittle (harnesses re-wrap and re-indent), so
the score is the fraction of key usage-block phrases present in the agent's own
output text. tool results are excluded on parsed transcripts -- the agent
reading SKILL.md (which contains the block) must not count as printing it. on
the plain-text fallback that distinction is lost; accepted, it only affects old
opencode runs predating --format json.
"""
from _lib import *  # noqa: F403

# one phrase per load-bearing line of the usage block in
# mason/skills/mason/SKILL.md; drift there should fail here.
_MARKERS = (
    "agent kit for chisel / rocks work",
    "/chisel-releases",
    "write-slice <pkg>",
    "review-slice",
    "slices/<pkg>.yaml",
    "github.com/rockcrafters/mason",
)


def score() -> float:
    t = transcript()
    hay = "\n".join(t["texts"]) if t["parsed"] else t["raw"]
    return sum(m in hay for m in _MARKERS) / len(_MARKERS)


emit(score)
