# mason

Agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). Packages the tribal knowledge needed to author and review chisel slice definition files (SDFs) so an AI coding agent can pick it up on demand.

## what's in here

```
skills/
  CHISEL.md                        # shared reference (format, branch model, schema versions, sources of truth)
  write-slice/
    SKILL.md                       # 10-step authoring workflow
    deb-list                       # python script to inspect .deb contents before authoring
  review-slice/
    SKILL.md                       # review checklist (CI checks, style, deps, rejection reasons)
src/plugins/opencode/              # opencode slash-command shims
.claude-plugin/                    # claude code plugin manifest
AGENTS.md                          # agent entrypoint -- references all three skill files
```

### skills

Each `skills/<name>/SKILL.md` is a self-contained briefing an agent loads on demand.

| skill | purpose |
|-------|---------|
| `write-slice` | Author new SDFs: validate target, build dep tree, inspect packages with `deb-list`, design slices, write + format + test + commit. Stops at local commits. After work, proposes a docs-alignment review against [chisel-docs](https://github.com/canonical/chisel-docs). |
| `review-slice` | Review SDFs: CI checks, dependency validation, naming & formatting rules, forward-port requirements, common rejection reasons. |

`CHISEL.md` is shared reference material both skills depend on: SDF format, `chisel.yaml` schema versions (v1/v2/v3), branch model, canonical slice names, multiarch quirks, sources of truth, and external links.

### `deb-list`

Python helper at `skills/write-slice/deb-list`. Inspects a `.deb` package before authoring slices:

```
$ deb-list bash
package: bash  version: 5.3-2ubuntu1  arch: amd64

Depends: base-files (>= 2.1.12), debianutils (>= 5.6-0.1)

files (lexicographic):  [x]=executable  [f]=file  [l]=symlink
  [f] 0644 root/root  /etc/bash.bashrc
  [x] 0755 root/root  /usr/bin/bash
  [l] 0777 root/root  /usr/bin/rbash -> bash
  [f] 0644 root/root  /usr/share/doc/bash/copyright
  ...

maintainer scripts present: postinst  (re-run with --scripts to view)
```

Requires `apt-get` + `dpkg-deb` and a populated apt cache.

### plugin integrations

| client | how |
|--------|-----|
| claude code | `/plugin marketplace add rockcrafters/mason` then `/plugin install mason@mason` |
| opencode | add `"plugin": ["$MASON/src/plugins/opencode"]` to `~/.config/opencode/opencode.json` |
| codex | `ln -s "$MASON/skills/write-slice" ~/.codex/skills/write-slice` |
| copilot cli | `ln -s "$MASON/AGENTS.md" AGENTS.md` in project root |
| gemini cli | `ln -s "$MASON/GEMINI.md" GEMINI.md` in project root |

`$MASON` = wherever you cloned this repo.

## sources of truth

The skills defer to three upstream projects. When in doubt:

**tool behaviour** ([canonical/chisel](https://github.com/canonical/chisel)) > **docs** ([canonical/chisel-docs](https://github.com/canonical/chisel-docs)) > **conventions** ([canonical/chisel-releases](https://github.com/canonical/chisel-releases)) > **this repo**

## status

WIP. Layout and naming subject to change.
