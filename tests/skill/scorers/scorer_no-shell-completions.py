#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""no-shell-completions: no bash/fish/zsh completion paths."""
from _lib import *  # noqa: F403

def score() -> float:
    pre = ("/usr/share/bash-completion/", "/usr/share/fish/", "/usr/share/zsh/", "/etc/bash_completion.d/")
    return avg(path_penalty(lambda p: any(p.startswith(x) for x in pre)))

emit(score)
