# mason

agent kit for chisel / rocks work. a cross-agent skill bundle, portable across claude code, pi, opencode, copilot, and codex.

each capability area is its own skill under `mason/skills/`. today there is one:

## chisel-releases

working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). command-per-file; commands:

- **`write-slice`** -- authors + tests + commits chisel slice definition files (SDFs). does not open PRs.
- **`review-slice`** -- read-only review of SDFs against chisel conventions, CI checks, and forward-port rules.

@./mason/skills/chisel-releases/SKILL.md

self-contained under `./mason/skills/chisel-releases/`: `commands/`, shared reference `shared/CHISEL.md`, helpers `scripts/` (`orientation`, `deb-list.py`, `try-cut`), command index `schemas/commands.manifest.yaml`. paths inside command files are relative to the skill's own directory (or, for repo paths like `slices/`, to the chisel-releases checkout being worked on).

## install

`npx github:rockcrafters/mason install` copies all skills into the target agent's discovery dirs (see README). adding a capability = a new skill dir under `mason/skills/`.
