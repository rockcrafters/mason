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

## Path convention

`${MASON_ROOT}` is this skill's own directory (the one containing this `SKILL.md`).

- claude code plugin: `${MASON_ROOT}` is `${CLAUDE_PLUGIN_ROOT}/skills/chisel-releases`.
- npx-installed (`.claude/skills/chisel-releases`, `.pi/skills/chisel-releases`, ...): `${MASON_ROOT}` is that install directory.

All paths below are written relative to `${MASON_ROOT}`.

## Layout

- `commands/` -- one command definition per file, loaded on demand
- `shared/CHISEL.md` -- shared reference (format, branch model, schema versions, naming, sources of truth)
- `scripts/` -- helpers (`deb-list`, `try-cut`)
- `schemas/commands.manifest.yaml` -- command index (name -> file)

## Shared reference

Before any command, read `${MASON_ROOT}/shared/CHISEL.md`.

## Commands

`write-slice` and `review-slice` are **not** standalone slash commands -- only `/chisel-releases` is registered. select a command from the invocation:

- `/chisel-releases write-slice <pkg>` (the first arg names the command), or
- plain language: "write a slice for `<pkg>`", "review `slices/foo.yaml`".

dispatch: take the first token of the args as the command name; if it matches a command below, load that file and treat the rest as its input. no match (or no args) -> ask which command, or infer from the request.

- `write-slice` -> `commands/write-slice.md` -- author + test + commit SDFs. does not open PRs.
- `review-slice` -> `commands/review-slice.md` -- read-only review of SDFs.
