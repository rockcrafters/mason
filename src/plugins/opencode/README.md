# mason -- opencode plugin

Thin opencode shim. Surfaces mason skills as slash commands.

Source of truth for skill content stays in repo-root `skills/<name>/SKILL.md`. Each `commands/<name>.md` here is a one-line wrapper that `@`-includes the matching SKILL.md so the briefing loads in opencode w/out duplication.

## Layout

- `package.json` -- ESM marker so bun loads the dir correctly.
- `commands/<name>.md` -- slash command shims. frontmatter `description:` only; body is a single `@skills/<name>/SKILL.md` reference.

## What it does NOT do

- no hooks, no state, no flag files. mason skills are declarative -- no mode toggling like caveman.
- no separate npm package. ships in-repo alongside the claude-code plugin.
