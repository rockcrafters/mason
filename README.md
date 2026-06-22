# mason

![WIP](https://img.shields.io/badge/%E2%9A%A0%EF%B8%8F%20work%20in%20progress%20%20%E2%9A%A0%EF%B8%8F-ffffff)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?logo=ubuntu&logoColor=white)](#)
[![rocks](https://img.shields.io/badge/%F0%9F%AA%A8-rocks-E95420)](https://ubuntu.com/server/docs/explanation/virtualisation/about-rock-images/)

WIP. Layout and naming subject to change.

<p align="center">
  <img src="assets/logo.png" alt="Mason logo">
</p>

Agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). Packages the tribal knowledge needed to author and review chisel slice definition files (SDFs) so an AI coding agent can pick it up on demand.

## what's in here

```
mason/
  skills/
    CHISEL.md                      # shared reference (format, branch model, schema versions, sources of truth)
    write-slice/
      SKILL.md                     # 10-step authoring workflow
      scripts/deb-list             # python script to inspect .deb contents before authoring
      scripts/try-cut              # bash script to test slices against the current checkout
    review-slice/
      SKILL.md                     # review checklist (CI checks, style, deps, rejection reasons)
.claude-plugin/                    # claude code plugin manifest
```

## sources of truth

The skills defer to three upstream projects. When in doubt:

**tool behaviour** ([canonical/chisel](https://github.com/canonical/chisel)) > **docs** ([canonical/chisel-docs](https://github.com/canonical/chisel-docs)) > **conventions** ([canonical/chisel-releases](https://github.com/canonical/chisel-releases)) > **this repo**

