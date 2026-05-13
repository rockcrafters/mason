# mason

wip. agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases) -- skills, agents, prompts, helpers. nothing here is stable yet; expect churn.

## what's in here

- `skills/` -- claude code skills. each `skills/<name>/SKILL.md` is a self-contained briefing the agent loads on demand. current skills:
    - `slice/` -- how to author chisel slice definition files (sdfs). covers `chisel.yaml` schema versions, sdf keys, content path options, `mutate:`/starlark semantics, reviewer conventions, ci checks, forward-port chains, multiarch quirks. stops at local commits -- does not open prs.

more skills + agents to come; see commit history for what's landed.

## why

authoring slices well needs a lot of tribal knowledge that isn't in `CONTRIBUTING.md`: canonical slice names, path-sort rules, arch-list formatting, forward-port chain ordering, common `mutate:` pitfalls, ci check meanings, etc. mason packages that knowledge so an agent can pick it up on demand instead of re-deriving it (or guessing) every session.

## install

primary targets: claude code + opencode -- native plugin install. others: clone + reference.

clone path referenced as `$MASON` below.

```
git clone https://github.com/rockcrafters/mason.git ~/git/mason
```

| client | how |
|---|---|
| claude code | `/plugin marketplace add rockcrafters/mason` then `/plugin install mason@mason` |
| opencode | add `"plugin": ["$MASON/src/plugins/opencode"]` to `~/.config/opencode/opencode.json` |
| codex | `ln -s "$MASON/skills/slice" ~/.codex/skills/slice` (codex plugins layout still wip; verify path) |
| copilot cli | in your project root: `ln -s "$MASON/AGENTS.md" AGENTS.md` (picks up all mason skills; or `@`-include from existing `AGENTS.md`) |
| gemini cli | in your project root: `ln -s "$MASON/GEMINI.md" GEMINI.md` (picks up all mason skills; or `@`-include from existing `GEMINI.md`) |

## status

wip. apis / layout / naming all subject to change. if smth here looks half-baked it probably is -- file an issue or just ping me.
