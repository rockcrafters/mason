#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""chisel-cut: did the agent validate its slices by running `chisel cut`?

reads the run transcript and correlates each `chisel cut` / `try-cut` invocation
to its result:
  0.0  never ran chisel cut (no validation attempted)
  0.5  ran it but no invocation succeeded (every cut errored)
  1.0  ran it and at least one cut exited cleanly

two transcript formats, tried in order:
  - claude (stdout.log, ndjson stream-json): tool_use/tool_result correlation.
  - opencode (stderr.log, plain ANSI text): `$ <command>` blocks, scanned for
    failure markers in their output. used whenever stdout.log has no parseable
    stream-json (i.e. non-claude harnesses).
"""
from _lib import *  # noqa: F403
import json
import re

# substrings in chisel-cut output that mean the cut failed (case-insensitive).
_FAIL = ("error:", "no content at", "cannot find", "not found", "panic", "usage:")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _is_cut_cmd(cmd: str) -> bool:
    return "chisel cut" in cmd or "try-cut" in cmd


def _score_claude() -> float | None:
    """stream-json tool_use/tool_result correlation. None if stdout.log has no
    parseable json (-> not a claude transcript)."""
    log = OUT / "stdout.log"
    if not log.exists():
        return None

    cut_ids: dict[str, str] = {}
    results: dict[str, tuple[bool, str]] = {}
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
                cmd = str((c.get("input") or {}).get("command", ""))
                if _is_cut_cmd(cmd):
                    cut_ids[c.get("id")] = cmd
            elif c.get("type") == "tool_result":
                cont = c.get("content")
                if isinstance(cont, list):
                    text = " ".join(b.get("text", "") for b in cont if isinstance(b, dict))
                else:
                    text = str(cont or "")
                results[c.get("tool_use_id")] = (bool(c.get("is_error")), text)

    if not saw_json:
        return None  # not a stream-json transcript -- let the text scorer try
    if not cut_ids:
        return 0.0
    for tid in cut_ids:
        r = results.get(tid)
        if r is None:
            continue
        is_err, text = r
        if not is_err and not any(m in text.lower() for m in _FAIL):
            return 1.0
    return 0.5


def _score_text() -> float:
    """plain-text transcript (e.g. opencode): scan `$ <command>` blocks for
    chisel-cut/try-cut invocations and check their output for failure markers."""
    chunks = []
    for name in ("stderr.log", "stdout.log"):
        p = OUT / name
        if p.exists():
            chunks.append(_ANSI.sub("", p.read_text(encoding="utf-8", errors="replace")))
    text = "\n".join(chunks)
    if not text.strip():
        return 0.0

    # split into command blocks: a block starts at a line beginning with "$ "
    # (a bash tool invocation) and runs until the next such line.
    lines = text.splitlines()
    blocks: list[tuple[str, list[str]]] = []
    cur_cmd: str | None = None
    cur_out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("$ "):
            if cur_cmd is not None:
                blocks.append((cur_cmd, cur_out))
            cur_cmd = stripped[2:]
            cur_out = []
        elif cur_cmd is not None:
            cur_out.append(line)
    if cur_cmd is not None:
        blocks.append((cur_cmd, cur_out))

    cut_blocks = [(cmd, out) for cmd, out in blocks if _is_cut_cmd(cmd)]
    if not cut_blocks:
        return 0.0
    for _, out in cut_blocks:
        out_text = "\n".join(out).lower()
        if not any(m in out_text for m in _FAIL):
            return 1.0
    return 0.5


def score() -> float:
    claude_score = _score_claude()
    if claude_score is not None:
        return claude_score
    return _score_text()


emit(score)
