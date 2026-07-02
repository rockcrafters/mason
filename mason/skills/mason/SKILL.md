---
name: mason
description: >-
  Usage / help for the mason agent kit. Print available skills and how to invoke them.
  Use when user runs /mason, says "mason help", "what can mason do", or types /mason with no
  clear target -- treat as a --help request.
argument-hint: "(no args -- prints usage)"
---

# mason

Agent kit for chisel / rocks work -- a cross-agent skill bundle, portable across
claude code, pi, opencode, copilot, and codex.

`/mason` has no actions of its own. Print the usage block below verbatim, then stop.
Do not load or run anything else.

```
mason -- agent kit for chisel / rocks work

skills:
  /chisel-releases           author + review chisel slice definition files (SDFs)
                             against canonical/chisel-releases.
    write-slice <pkg>        author + test + commit an SDF (no PR)
    review-slice <sdf>       read-only review of an SDF

usage:
  /chisel-releases write-slice <pkg>
  /chisel-releases review-slice slices/<pkg>.yaml
  or plain language: "write a slice for <pkg>", "review slices/foo.yaml"

docs: https://github.com/rockcrafters/mason
```
