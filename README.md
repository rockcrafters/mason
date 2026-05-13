# mason

wip. agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases) -- skills, agents, prompts, helpers. nothing here is stable yet; expect churn.

## what's in here

- `skills/` -- claude code skills. each `skills/<name>/SKILL.md` is a self-contained briefing the agent loads on demand. current skills:
    - `slice/` -- how to author chisel slice definition files (sdfs). covers `chisel.yaml` schema versions, sdf keys, content path options, `mutate:`/starlark semantics, reviewer conventions, ci checks, forward-port chains, multiarch quirks. stops at local commits -- does not open prs.

more skills + agents to come; see commit history for what's landed.

## why

authoring slices well needs a lot of tribal knowledge that isn't in `CONTRIBUTING.md`: canonical slice names, path-sort rules, arch-list formatting, forward-port chain ordering, common `mutate:` pitfalls, ci check meanings, etc. mason packages that knowledge so an agent can pick it up on demand instead of re-deriving it (or guessing) every session.

## supported clients

source of truth: repo-root `skills/<name>/SKILL.md`. each client below picks the skill up via a thin shim, no content duplication.

| client | install path / shim |
|---|---|
| claude code | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`. install via `/plugin marketplace add rockcrafters/mason` then `/plugin install mason@mason`. skills auto-discovered from `skills/` |
| opencode | `src/plugins/opencode/` -- `commands/<name>.md` shims `@`-include the matching SKILL.md |
| codex | `plugins/mason/.codex-plugin/plugin.json` w/ `plugins/mason/skills` symlinked to repo-root `skills/` |
| copilot cli | `AGENTS.md` at repo root -- `@`-includes `skills/<name>/SKILL.md` so copilot picks it up as project memory when run inside a mason checkout |
| gemini cli | `GEMINI.md` -- same shape as `AGENTS.md` |

for single-user no-install use: symlink `skills/<name>/` -> `~/.claude/skills/<name>/` (or equivalent for other clients).

## status

wip. apis / layout / naming all subject to change. if smth here looks half-baked it probably is -- file an issue or just ping me.
