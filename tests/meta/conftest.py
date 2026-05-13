"""Meta-tests for the eval framework itself. Self-contained; no chisel needed.

Isolated from the slice-skill conftest -- this dir is collected via
`make meta` -> `pytest meta/` which doesn't touch the top-level conftest
chisel checks.
"""
from __future__ import annotations

pytest_plugins = ["pytester"]
