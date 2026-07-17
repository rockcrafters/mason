#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""no-doc-clutter: no doc/lintian clutter under /usr/share/doc.

README, changelog, examples, doc-base and lintian metadata are clutter. Not
clutter, and exempted: the copyright file, upstream legal files (NOTICE /
LICENSE / COPYING / AUTHORS ...), and the package's own doc dir shipped as a
shared-copyright symlink (/usr/share/doc/<pkg>). Mirrors the skill's
check-slice.py so the eval and the linter agree.
"""
from _lib import *  # noqa: F403

_LEGAL = {"COPYRIGHT", "NOTICE", "LICENSE", "LICENCE", "COPYING", "AUTHORS", "THIRDPARTYNOTICES", "THIRD-PARTY-NOTICES"}


def _is_legal(basename: str) -> bool:
    stem = basename
    for suf in (".gz", ".xz", ".bz2", ".txt", ".md", ".rst"):
        if stem.lower().endswith(suf):
            stem = stem[: -len(suf)]
    return stem.upper() in _LEGAL


def score() -> float:
    def allow(path, doc):
        pkg = doc.get("package") if isinstance(doc.get("package"), str) else ""
        if not path.startswith("/usr/share/doc/"):
            return False  # doc-base / lintian are never exempt
        if pkg and path.rstrip("/") == f"/usr/share/doc/{pkg}":
            return True  # doc-dir symlink (shared copyright)
        return _is_legal(path.rstrip("/").rsplit("/", 1)[-1])
    return avg(path_penalty(
        lambda p: p.startswith("/usr/share/doc/") or p.startswith("/usr/share/doc-base/") or p.startswith("/usr/share/lintian/"),
        allow,
    ))

emit(score)
