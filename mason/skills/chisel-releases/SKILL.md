---
name: chisel-releases
description: >-
  Author and review chisel slice definition files (SDFs) against canonical/chisel-releases.
  Command-per-file architecture, portable across claude code, pi, opencode, copilot, and codex.
  Commands: write-slice (author + test + commit), review-slice (read-only review).
argument-hint: "[write-slice|review-slice] <pkg-or-sdf>"
---

# chisel-releases

Cross-agent skill for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases).
Self-contained: the same skill directory drives claude code, pi, opencode, copilot, and codex.

## Where things live

You work inside a checkout of `canonical/chisel-releases` -- your current working
directory. Every repo path you read or write -- `slices/<pkg>.yaml`,
`tests/spread/...`, `chisel.yaml`, sibling SDFs -- is relative to this checkout,
exactly as written.

Paths below (`commands/`, `shared/`, `scripts/`, `schemas/`) are relative to this
skill's own directory instead -- the one holding this `SKILL.md`. They are
read-only.

## Layout

- `commands/` -- command workflows: markdown to read and follow, not executable scripts
- `shared/CHISEL.md` -- reference (format, branch model, schema versions, naming, sources of truth)
- `scripts/` -- runnable helpers: `orientation`, `deb-list.py`, `try-cut`, `check-slice.py` (deterministic SDF linter), `check-test.py` (binary test-coverage check), `check-diff.py` (append-only regression check)
- `schemas/commands.manifest.yaml` -- command index (name -> file)

## Orient first

Before anything else, run `scripts/orientation [<package>]`. It prints --
deterministically -- your working dir, this skill's own dir, and the target
release + manifest format parsed from `chisel.yaml`. Treat its output as ground
truth; don't infer any of it. Then read `shared/CHISEL.md` for format and
conventions.

## Commands

`write-slice` and `review-slice` are **not** standalone slash commands -- only `/chisel-releases` is registered. select a command from the invocation:

- `/chisel-releases write-slice <pkg>` (the first arg names the command), or
- plain language: "write a slice for `<pkg>`", "review `slices/foo.yaml`".

dispatch: take the first token of the args as the command name; if it matches a command below, read that file and follow its steps, treating the rest of the args as its input. on no match, or no args at all, print the numbered list below and wait for the user's reply before loading anything -- never guess.

1. `write-slice` -> `commands/write-slice.md` -- author + test + commit SDFs. does not open PRs.
2. `review-slice` -> `commands/review-slice.md` -- read-only review of SDFs.
