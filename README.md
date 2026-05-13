# mason

wip. agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases) -- skills, agents, prompts, helpers. nothing here is stable yet; expect churn.

## what's in here

- `skills/` -- claude code skills. each `skills/<name>/SKILL.md` is a self-contained briefing the agent loads on demand. current skills:
    - `slice/` -- how to author chisel slice definition files (sdfs). covers `chisel.yaml` schema versions, sdf keys, content path options, `mutate:`/starlark semantics, reviewer conventions, ci checks, forward-port chains, multiarch quirks. stops at local commits -- does not open prs.

more skills + agents to come; see commit history for what's landed.

## why

authoring slices well needs a lot of tribal knowledge that isn't in `CONTRIBUTING.md`: canonical slice names, path-sort rules, arch-list formatting, forward-port chain ordering, common `mutate:` pitfalls, ci check meanings, etc. mason packages that knowledge so an agent can pick it up on demand instead of re-deriving it (or guessing) every session.

## using a skill

drop / symlink the relevant `skills/<name>/` dir into a location claude code picks up (e.g. `~/.claude/skills/<name>/`), or point at it from a project's `.claude/`. the agent loads `SKILL.md` when the trigger phrases in its frontmatter match the user's prompt.

## status

wip. apis / layout / naming all subject to change. if smth here looks half-baked it probably is -- file an issue or just ping me.
