# mason

![WIP](https://img.shields.io/badge/%E2%9A%A0%EF%B8%8F%20work%20in%20progress%20%20%E2%9A%A0%EF%B8%8F-ffffff)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?logo=ubuntu&logoColor=white)](#)
[![rocks](https://img.shields.io/badge/%F0%9F%AA%A8-rocks-E95420)](https://ubuntu.com/server/docs/explanation/virtualisation/about-rock-images/)

WIP. Layout and naming subject to change.

<p align="center">
  <img src="assets/logo.png" alt="Mason logo">
</p>

Agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). Packages the tribal knowledge needed to author and review chisel slice definition files (SDFs) so an AI coding agent can pick it up on demand.

## install

Install the skills into another repo for your agent with `npx`, no clone or npm publish needed:

```
npx github:rockcrafters/mason install --agents claude
```

```
--agents <list>   comma-separated: claude, pi, copilot, opencode, codex (default: auto-detect)
--target <dir>    install into <dir> (default: git root, else cwd)
--dry-run         show what would change, write nothing
--force           overwrite files that differ from the skill source
--quiet, -q       suppress per-file logs (warnings still print)
--help, -h        show this help
```

The installer copies each self-contained skill tree into the agent's skill-discovery directory
(`.claude/skills/<skill>`, `.pi/skills/<skill>`, `.github/skills/<skill>`, `.opencode/skills/<skill>`, `.codex/skills/<skill>`);
opencode additionally gets a generated `.opencode/command/<skill>.md`. Re-running skips up-to-date
files and leaves locally-modified ones alone unless `--force` is set.

Claude code users can alternatively add it as a plugin via the marketplace (`.claude-plugin/`).

## what's in here

`mason` is an umbrella kit for chisel / rocks work. each capability area is one self-contained skill
under `mason/skills/`; the installer copies each per agent (no committed per-agent adapters). today
there is one skill, `chisel-releases`.

```
mason/
  skills/
    chisel-releases/               # a skill -- self-contained, copied verbatim on install
      SKILL.md                     # skill entry + command dispatch + ${MASON_ROOT} convention
      commands/
        write-slice.md             # author + test + commit (10-step authoring workflow)
        review-slice.md            # review checklist (CI checks, style, deps, rejection reasons)
      shared/CHISEL.md             # shared reference (format, branch model, schema versions, sources of truth)
      scripts/
        orientation                # deterministic orientation: cwd, skill dir, target release + format
        deb-list.py                # python script to inspect .deb contents before authoring
        try-cut                    # bash script to test slices against the current checkout
      schemas/commands.manifest.yaml  # command index (command -> file)
  .claude-plugin/                  # claude code plugin manifest
scripts/cli.js                     # the npx installer (installs every skill under mason/skills/)
package.json                       # bin: mason -> scripts/cli.js
```

Adding a capability = a new skill directory under `mason/skills/`; the installer picks it up automatically.

## sources of truth

The skill defers to three upstream projects. When in doubt:

**tool behaviour** ([canonical/chisel](https://github.com/canonical/chisel)) > **docs** ([canonical/chisel-docs](https://github.com/canonical/chisel-docs)) > **conventions** ([canonical/chisel-releases](https://github.com/canonical/chisel-releases)) > **this repo**

