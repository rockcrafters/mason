---
name: mason
description: >-
  Entry point for the mason agent kit. Routes a plain-language request to the right mason
  skill, or prints usage when the intent is unclear. Use when user runs /mason (with a request
  or bare), says "mason help", or "what can mason do".
argument-hint: "[request]  (no args -- prints usage)"
---

# mason

Agent kit for chisel / rocks work -- a cross-agent skill bundle, portable across
claude code, pi, opencode, copilot, and codex.

`/mason` has no actions of its own -- it either routes or prints usage:

- **route** -- if the request clearly maps to a skill below (writing / authoring an SDF or
  slice, reviewing an SDF -> `chisel`), load that skill's `SKILL.md` from its
  sibling directory (`../chisel/SKILL.md` relative to this file) and follow its
  dispatch, passing the request through as plain language.
  e.g. `/mason "please help me write an sdf for foobar"` -> `chisel` write-slice, foobar.
- **usage** -- no args, "help", or intent not obviously covered by a skill below: print the
  usage block below verbatim, then stop. Do not load or run anything else -- never guess.

```
mason -- agent kit for chisel / rocks work

skills:
  /chisel                    author + review chisel slice definition files (SDFs)
                             against canonical/chisel-releases.
    write-slice <pkg>        author + test + commit an SDF (no PR)
    review-slice <sdf>       read-only review of an SDF

usage:
  /chisel write-slice <pkg>
  /chisel review-slice slices/<pkg>.yaml
  or plain language: "write a slice for <pkg>", "review slices/foo.yaml"

docs: https://github.com/rockcrafters/mason
```
