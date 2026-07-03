# mason

<img src="assets/logo2.png" alt="Mason logo" align="right" width="300">

![WIP](https://img.shields.io/badge/%E2%9A%A0%EF%B8%8F%20work%20in%20progress%20%20%E2%9A%A0%EF%B8%8F-ffffff)

[![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?logo=ubuntu&logoColor=white)](#)
[![rocks](https://img.shields.io/badge/%F0%9F%AA%A8-rocks-E95420)](https://ubuntu.com/server/docs/explanation/virtualisation/about-rock-images/)
[![test](https://github.com/rockcrafters/mason/actions/workflows/test.yml/badge.svg)](https://github.com/rockcrafters/mason/actions/workflows/test.yml)

Tribal knowledge about [`rocks`](https://documentation.ubuntu.com/rockcraft/stable/explanation/rocks/), [`rockcraft`](https://documentation.ubuntu.com/rockcraft/latest/), [`chisel`](https://github.com/canonical/chisel), [`chisel-releases`](https://github.com/canonical/chisel-releases), and slice definition files (SDFs).

Install with:

```
npx github:rockcrafters/mason install ...
```

_(see below for detailed instructions)_

and then, for example, write a new SDF file:

```
git clone https://github.com/canonical/chisel-releases.git && cd chisel-releases
git checkout ubuntu-26.04 && git checkout -b feat/my-new-slice
<in your coding agent>
/mason "please help me write an sdf for foobar"
```

## install

Install the skills into another repo for your agent with `npx`, no clone or npm publish needed:

```
npx github:rockcrafters/mason install --agents claude
```

```
--agents <list>   comma-separated: claude, pi, copilot, opencode, codex (default: auto-detect)
--target <dir>    install into <dir> (default: git root, else cwd)
--dry-run         show what would change, write nothing
--force           clean reinstall: drop each skill dir, then write it anew
--quiet, -q       suppress per-file logs (warnings still print)
--help, -h        show this help
```

The installer copies each self-contained skill tree into the agent's skill-discovery directory
(`.claude/skills/<skill>`, `.pi/skills/<skill>`, `.github/skills/<skill>`, `.opencode/skills/<skill>`, `.codex/skills/<skill>`);
opencode additionally gets a generated `.opencode/command/<skill>.md`. Re-running skips up-to-date
files and leaves locally-modified ones alone; `--force` drops each known skill dir and writes it
fresh (scoped per skill -- foreign skills under the same base survive).

Claude code users can alternatively add it as a plugin via the marketplace (`.claude-plugin/`).

## what's in here

`mason` is an umbrella kit for chisel / rocks work. each capability area is one self-contained skill
under `mason/skills/`; the installer copies each per agent (no committed per-agent adapters). today
there are two: `chisel` (the substance) and `mason` (the `/mason` entry point -- routes a request to the right skill, or prints help).

```
mason/
  skills/
    chisel/                        # a skill -- self-contained, copied verbatim on install
      SKILL.md                     # skill entry + command dispatch
      commands/
        write-slice.md             # author + scaffold tests + self-check + commit
        review-slice.md            # review: deterministic first pass (scripts) + judgement
      shared/CHISEL.md             # shared reference (format, branch model, schema versions, sources of truth)
      scripts/
        orientation                # deterministic orientation: cwd, skill dir, target release + format
        deb-list.py                # inspect .deb contents (files, deps, maintainer scripts); --sdf emits a draft SDF
        try-cut                    # test slices with chisel cut against the current checkout
        scaffold-test.py           # emit a spread task.yaml skeleton (a rootfs per slice, every binary listed)
        check-slice.py             # lint an SDF: sorting, naming, copyright, clutter, arch, version-gated fields
        check-test.py              # report binary test coverage for a slice
        check-diff.py              # append-only regressions (removed SDF / slice / path) vs a base ref
        review-diff.py             # run the three checks over a PR diff -> report + verdict + exit code
      schemas/commands.manifest.yaml  # command index (command -> file)
    mason/                         # umbrella /mason skill -- routes to a skill, or prints usage
      SKILL.md
  .claude-plugin/                  # claude code plugin manifest
scripts/cli.js                     # the npx installer (installs every skill under mason/skills/)
tests/scripts/                     # pytest (script checks) + node --test (installer) -- see makefile
package.json                       # bin: mason -> scripts/cli.js
```

Adding a capability = a new skill directory under `mason/skills/`; the installer picks it up automatically.

## testing

Scripts and the installer are covered by pytest and `node --test` (see makefile). The skills
themselves (prompt-level behaviour) are tested with [pats](https://github.com/lczyk/pats).

## sources of truth

The skill defers to three upstream projects. When in doubt:

**tool behaviour** ([canonical/chisel](https://github.com/canonical/chisel)) > **docs** ([canonical/chisel-docs](https://github.com/canonical/chisel-docs)) > **conventions** ([canonical/chisel-releases](https://github.com/canonical/chisel-releases)) > **this repo**

