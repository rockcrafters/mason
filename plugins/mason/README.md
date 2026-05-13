# mason -- codex plugin shim

Codex plugin install root. Skill content is **not duplicated** here -- `skills/` in this dir is a symlink back to repo-root `skills/`, so single source of truth stays at the top level.

## Layout

- `.codex-plugin/plugin.json` -- codex plugin manifest. references `./skills/`.
- `skills/` -- symlink -> `../../skills/`. real files live at repo-root `skills/<name>/SKILL.md`.

## Caveat

Symlink-as-skills-dir relies on git preserving symlinks on checkout. On windows, users may need `git config core.symlinks=true` (or run a posix-y shell) for `skills/` to resolve.
