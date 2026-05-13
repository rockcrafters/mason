"""Top-level conftest -- intentionally minimal.

Slice-skill scoring lives under tests/slice/ (registers scored plugin).
Meta tests live under tests/meta/ (vanilla pytest, no plugin).
Keeping this file empty avoids leaking fixtures / plugin registration
across both subdirs.
"""
