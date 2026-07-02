#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""refusal-verified: did the agent actually check the archive before deciding?

companion to refuses-nonexistent, which only scores the outcome: an agent that
refuses (or fabricates) without ever checking scores the same there as one that
verified. this one greps the transcript commands for evidence of a real
existence check -- any of the routes seen in live runs counts:
  - scripts/deb-list.py (the check write-slice.md Step 1.1 names)
  - apt-cache / apt-get / (r)madison
  - an archive index fetch (Packages.gz) or packages.ubuntu.com / launchpad
  - probing chisel-releases branches for slices/<pkg>.yaml (denied by the
    sandbox, but the attempt is verification behaviour)

binary: 1.0 if any check ran, 0.0 if none.
"""
from _lib import *  # noqa: F403

_CHECK_MARKERS = (
    "deb-list",
    "apt-cache",
    "apt-get",
    "madison",
    "packages.ubuntu.com",
    "launchpad",
    "/binary-",  # dists/<suite>/<component>/binary-<arch>/Packages* fetch
)


def score() -> float:
    t = transcript()
    hay = "\n".join(t["commands"]) if t["parsed"] else t["raw"]
    if any(m in hay for m in _CHECK_MARKERS):
        return 1.0
    # slice probe counts only as a url fetch -- a bash heredoc *writing*
    # slices/<pkg>.yaml mentions the same path and must not count.
    probe = f"slices/{TASK}.yaml"
    lines = t["commands"] if t["parsed"] else t["raw"].splitlines()
    return 1.0 if any(probe in l and "http" in l for l in lines) else 0.0


emit(score)
