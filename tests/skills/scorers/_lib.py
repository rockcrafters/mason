"""shared helpers for mason's pats scorers. not a scorer itself (no exec bit, no
shebang) -- imported by each scorer_<id>.py via `from _lib import *`.

a scorer receives the whole run output dir (env PATS_OUTPUT_DIR) and scores
whatever's there. the dir holds, per *target* (a sliced package):

    <target>.yaml           the slice the agent produced
    <target>.expected.yaml  ground truth (knockout snapshot or denovo silver)

plus per *case* (env PATS_TASK_ID):

    <case>.task.yaml        the spread test task.yaml the agent wrote (if any)
    <case>.spread.txt       concatenated spread-test bundle text (if any)
    <case>.branch           the chisel-releases branch (recorded at clone time)
    <case>.format           the branch's manifest format (version-gated checks)

the *targets* are the stems of the `*.expected.yaml` files. single-target cases
have exactly one; multi-target (denovo) cases have several. per-target scorers
average across targets, so single-target is just the N=1 case.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml

__all__ = [
    "OUT", "TASK", "NA", "emit", "avg", "produced", "expected",
    "fmt", "iter_contents", "iter_bodies", "mutate_map",
    "mutate_paths", "content_paths", "declared_binaries", "path_penalty",
    "targets", "fmt_compat", "CANONICAL", "has_slices", "transcript",
]

OUT = Path(os.environ["PATS_OUTPUT_DIR"])
TASK = os.environ["PATS_TASK_ID"]  # the case id (also the single-target package)

_EXP_SUFFIX = ".expected.yaml"


class NA(Exception):
    """raised by a scorer that does not apply to this case -> prints 'na'."""


def emit(fn: Callable[[], float]) -> None:
    """run a scorer and print its verdict: a [0,1] float, or 'na' on NA."""
    try:
        print(f"{fn():.4f}")
    except NA:
        print("na")


def targets() -> list[str]:
    """stems with a ground-truth file -- the set of packages that should exist."""
    ts = sorted(p.name[: -len(_EXP_SUFFIX)] for p in OUT.glob("*" + _EXP_SUFFIX))
    return ts or [TASK]  # fallback so a missing-expected run still scores (-> 0s)


def avg(fn: Callable[[str], float]) -> float:
    ts = targets()
    vals = [fn(t) for t in ts]
    return sum(vals) / len(vals) if vals else 1.0


def load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def produced(t: str) -> Any:
    return load(OUT / f"{t}.yaml")


def expected(t: str) -> Any:
    return load(OUT / f"{t}{_EXP_SUFFIX}")


def fmt() -> int | None:
    """Manifest format of the case's branch, captured at fixture time (tasks/_lib.sh
    writes <case>.format from the freshly-cloned chisel.yaml). Derived from the real
    branch, so it's release-agnostic -- no hardcoded branch->format table to rot."""
    f = OUT / f"{TASK}.format"
    if not f.exists():
        return None
    m = re.search(r"\d+", f.read_text(encoding="utf-8"))
    return int(m.group()) if m else None


CANONICAL = {
    "bins", "libs", "config", "configs", "data", "scripts", "copyright",
    "core", "standard", "var", "headers", "jars", "license", "notice",
    "locales", "services", "modules", "tables", "chisel", "rules", "dev",
}
BIN_DIRS = ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/usr/libexec/")


def iter_contents(doc: Any):
    if not isinstance(doc, dict):
        return
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return
    for sname, body in slices.items():
        if not isinstance(body, dict):
            continue
        contents = body.get("contents")
        if not isinstance(contents, dict):
            continue
        for path, entry in contents.items():
            yield sname, path, entry


def iter_bodies(doc: Any):
    if not isinstance(doc, dict):
        return
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return
    for name, body in slices.items():
        if isinstance(body, dict):
            yield name, body


def mutate_map(doc: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, body in iter_bodies(doc):
        m = body.get("mutate")
        if isinstance(m, str) and m.strip():
            out[name] = m
    return out


def mutate_paths(script: str) -> set[str]:
    return set(re.findall(r'content\.(?:read|write)\s*\(\s*["\']([^"\']+)["\']', script))


def content_paths(doc: Any) -> set[str]:
    return {str(p).lower() for _, p, _ in iter_contents(doc)}


def has_slices(doc: Any) -> bool:
    """doc has a non-empty slices: dict -- i.e. is shaped like a real SDF, not
    some other invented schema. compliance scorers (no forbidden path, sorted
    keys, ...) gate on this: absence of slices is not evidence of compliance."""
    return isinstance(doc, dict) and isinstance(doc.get("slices"), dict) and bool(doc["slices"])


def declared_binaries(doc: Any) -> set[str]:
    out: set[str] = set()
    for _, path, _ in iter_contents(doc):
        if not any(path.startswith(d) for d in BIN_DIRS):
            continue
        if path.endswith("/") or "*" in path or "?" in path:
            continue
        out.add(path.rsplit("/", 1)[-1])
    return out


def path_penalty(matches: Callable[[str], bool], allow: Callable[[str, Any], bool] = lambda p, d: False) -> Callable[[str], float]:
    def f(t: str) -> float:
        doc = produced(t)
        if not has_slices(doc):
            return 0.0
        total = bad = 0
        for _, path, _ in iter_contents(doc):
            total += 1
            if allow(path, doc):
                continue
            if matches(path):
                bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return f


# --- transcript parsing ------------------------------------------------------
# shared by scorers that read the agent's event stream rather than its files.
# scorer_orientation-called.py and scorer_chisel-cut.py predate this helper and
# carry their own copies of the same format detection.

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_WRITE_TOOLS = {"write", "edit", "multiedit", "notebookedit", "patch"}
_PATH_KEYS = ("file_path", "filePath", "path", "notebook_path")


def _jsonl(path: Path):
    """yield parsed json objects from a jsonl file, skipping non-json lines."""
    import json
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def transcript() -> dict:
    """parse the run transcript (stdout.log) into what the agent said and did.

        texts     assistant-visible output text (NOT tool results -- a scorer
                  grepping for skill phrases must not match the skill file the
                  agent read)
        commands  bash commands the agent ran
        writes    file paths touched via write/edit-style tools
        parsed    True when a structured format matched; False -> plain-text
                  fallback, only `raw` is meaningful
        raw       ansi-stripped stdout+stderr, all formats

    formats tried in order: claude stream-json (lines carry "message" /
    "session_id"), opencode --format json (lines carry a "part" object).
    """
    texts: list[str] = []
    commands: list[str] = []
    writes: list[str] = []
    saw_claude = saw_oc = False

    for ev in _jsonl(OUT / "stdout.log"):
        if "message" in ev or "session_id" in ev:
            saw_claude = True
        msg = ev.get("message") or {}
        for c in (msg.get("content") or []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and msg.get("role") == "assistant":
                texts.append(str(c.get("text", "")))
            elif c.get("type") == "tool_use":
                inp = c.get("input") or {}
                name = str(c.get("name", "")).lower()
                if name == "bash":
                    commands.append(str(inp.get("command", "")))
                elif name in _WRITE_TOOLS:
                    writes.extend(str(inp[k]) for k in _PATH_KEYS if k in inp)

        part = ev.get("part")
        if not isinstance(part, dict):
            continue
        saw_oc = True
        if ev.get("type") == "text":
            texts.append(str(part.get("text", "")))
        elif ev.get("type") == "tool_use":
            state = part.get("state") or {}
            inp = state.get("input") or {}
            tool = str(part.get("tool", "")).lower()
            if "command" in inp:
                commands.append(str(inp.get("command", "")))
            elif tool in _WRITE_TOOLS:
                # NOTE: gate on the tool name only -- a bare path-key check
                # counted opencode reads (read has file_path too) as writes.
                writes.extend(str(inp[k]) for k in _PATH_KEYS if k in inp)

    chunks = []
    for name in ("stdout.log", "stderr.log"):
        p = OUT / name
        if p.exists():
            chunks.append(_ANSI.sub("", p.read_text(encoding="utf-8", errors="replace")))
    return {
        "texts": texts,
        "commands": commands,
        "writes": writes,
        "parsed": saw_claude or saw_oc,
        "raw": "\n".join(chunks),
    }


def fmt_compat(uses: Callable[[Any], bool], min_ok_fmt: int, exact_ok: int | None = None) -> float:
    """branch-gated per-target compat. NA when the branch is unknown."""
    f_ = fmt()
    if f_ is None:
        raise NA

    def f(t: str) -> float:
        doc = produced(t)
        if not isinstance(doc, dict):
            return 0.0
        if f_ >= min_ok_fmt or (exact_ok is not None and f_ == exact_ok):
            return 1.0
        return 0.0 if uses(doc) else 1.0
    return avg(f)
