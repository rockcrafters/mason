#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""orientation-called: did the agent run scripts/orientation before anything else?

reads the run transcript and checks for orientation's own success marker
("working dir (chisel-releases checkout):"), the same way scorer_chisel-cut.py
reads claude's stream-json (stdout.log) or opencode's plain ANSI text (stderr.log):
  0.0  orientation never ran (no invocation attempt found)
  0.5  invocation attempted but failed (e.g. wrong path -- no success marker)
  1.0  ran successfully, before the first write to a slice file
"""
from _lib import *  # noqa: F403
import json
import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SUCCESS_MARKER = "working dir (chisel-releases checkout):"
_ATTEMPT_MARKERS = ("orientation",)


def _claude_events():
    """yield (kind, text) for each stream-json event in stdout.log, in order.
    kind is 'tool_use' (text = the bash command) or 'text' (assistant/tool output).
    None if stdout.log has no parseable json (-> not a claude transcript)."""
    log = OUT / "stdout.log"
    if not log.exists():
        return None
    events = []
    saw_json = False
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        saw_json = True
        for c in ((ev.get("message") or {}).get("content") or []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") == "Bash":
                events.append(str((c.get("input") or {}).get("command", "")))
            elif c.get("type") == "tool_result":
                cont = c.get("content")
                text = " ".join(b.get("text", "") for b in cont if isinstance(b, dict)) if isinstance(cont, list) else str(cont or "")
                events.append(text)
    return events if saw_json else None


def _score_claude() -> float | None:
    events = _claude_events()
    if events is None:
        return None
    joined = "\n".join(events)
    if not any(m in joined for m in _ATTEMPT_MARKERS):
        return 0.0
    return 1.0 if _SUCCESS_MARKER in joined else 0.5


def _score_text() -> float:
    chunks = []
    for name in ("stderr.log", "stdout.log"):
        p = OUT / name
        if p.exists():
            chunks.append(_ANSI.sub("", p.read_text(encoding="utf-8", errors="replace")))
    text = "\n".join(chunks)
    if not any(m in text for m in _ATTEMPT_MARKERS):
        return 0.0
    return 1.0 if _SUCCESS_MARKER in text else 0.5


def score() -> float:
    claude_score = _score_claude()
    if claude_score is not None:
        return claude_score
    return _score_text()


emit(score)
