#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""mutable-has-text: mutable entries are regular files, not directories.

chisel allows mutable only on a regular file -- a text file or a non-dir copy
(a bare path is an implicit copy from the deb, valid). Real SDFs mark
bare-extracted config files mutable (e.g. libpam-runtime's /etc/pam.d/common-*),
so requiring an explicit text/copy would wrongly penalise them. It is rejected
on a directory (make: true / trailing slash) and on a symlink.
"""
from _lib import *  # noqa: F403

def score() -> float:
    def f(t: str) -> float:
        doc = produced(t)
        if not has_slices(doc):
            return 0.0
        total = bad = 0
        for _, path, entry in iter_contents(doc):
            if not isinstance(entry, dict) or entry.get("mutable") is not True:
                continue
            total += 1
            is_dir = entry.get("make") is True or (isinstance(path, str) and path.endswith("/"))
            if is_dir or isinstance(entry.get("symlink"), str):
                bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return avg(f)

emit(score)
