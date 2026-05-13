# mason -- opencode plugin

Surfaces mason skills in OpenCode via two mechanisms.

Source of truth for skill content stays in repo-root `skills/<name>/SKILL.md`.

---

## Native skills (recommended)

OpenCode's `skill` tool discovers skills placed in `~/.config/opencode/skills/`.
Run the install script once to symlink mason skills globally:

```bash
bash src/plugins/opencode/install-for-opencode.sh
```

After this, any OpenCode session can load skills on demand:
- `write-slice` — author chisel SDF files
- `review-slice` — review chisel SDF files

The script is idempotent and resolves paths relative to itself, so it works from any working directory.

**This is the preferred path for OpenCode agents.** It uses the native `skill` tool rather than slash commands and requires no `opencode.json` config changes.

---

## Slash commands (legacy)

The `commands/` directory exposes skills as `/`-commands via an opencode plugin entry. Requires adding the plugin to `opencode.json`:

```json
{ "plugin": ["$MASON/src/plugins/opencode"] }
```

## Layout

- `package.json` -- ESM marker so bun loads the dir correctly.
- `commands/<name>.md` -- slash command shims. frontmatter `description:` only; body is a single `@skills/<name>/SKILL.md` reference.
- `install-for-opencode.sh` -- installs native skills via symlinks into `~/.config/opencode/skills/`.

## What it does NOT do

- no hooks, no state, no flag files. mason skills are declarative -- no mode toggling like caveman.
- no separate npm package. ships in-repo alongside the claude-code plugin.
