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

three transcript formats, tried in order:
  - claude (stdout.log, ndjson stream-json): tool_use/tool_result correlation
    (claude lines carry "message"/"session_id" keys).
  - opencode (stdout.log, `--format json` events): each tool_use event carries
    both the command and its result (part.state), no correlation needed
    (opencode lines carry a "part" object + camel-case "sessionID").
  - plain text (stderr.log/stdout.log, ANSI): `$ <command>` blocks scanned for
    failure markers. fallback for old opencode runs predating --format json.
"""
from _lib import *  # noqa: F403
import json
import re

# substrings in chisel-cut output that mean the cut failed (case-insensitive).
_FAIL = ("error:", "no content at", "cannot find", "not found", "panic", "usage:")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _is_cut_cmd(cmd: str) -> bool:
    return "chisel cut" in cmd or "try-cut" in cmd


def _jsonl(path):
    """yield parsed json objects from a jsonl file, skipping non-json lines."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _score_claude() -> float | None:
    """stream-json tool_use/tool_result correlation. None if stdout.log has no
    claude-shaped events."""
    cut_ids: dict[str, str] = {}
    results: dict[str, tuple[bool, str]] = {}
    saw_claude = False

    for ev in _jsonl(OUT / "stdout.log"):
        if "message" in ev or "session_id" in ev:
            saw_claude = True
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

    if not saw_claude:
        return None
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


def _score_opencode() -> float | None:
    """opencode --format json: a tool_use event is self-contained -- the part's
    state carries input.command, output/error, and status. None if stdout.log
    has no opencode-shaped events."""
    saw_oc = False
    cuts: list[tuple[bool, str]] = []  # (is_err, output)

    for ev in _jsonl(OUT / "stdout.log"):
        part = ev.get("part")
        if not isinstance(part, dict):
            continue
        saw_oc = True
        if ev.get("type") != "tool_use":
            continue
        state = part.get("state") or {}
        cmd = str((state.get("input") or {}).get("command", ""))
        if not _is_cut_cmd(cmd):
            continue
        out = str(state.get("output") or state.get("error") or "")
        cuts.append((state.get("status") == "error", out))

    if not saw_oc:
        return None
    if not cuts:
        return 0.0
    for is_err, text in cuts:
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
    for s in (_score_claude(), _score_opencode()):
        if s is not None:
            return s
    return _score_text()


emit(score)
