# mason

agent kit for chisel / rocks work. a cross-agent skill bundle, portable across claude code, pi, opencode, copilot, and codex.

each capability area is its own skill under `mason/skills/`. today there is one:

## chisel

working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). command-per-file; commands:

- **`write-slice`** -- authors + tests + commits chisel slice definition files (SDFs). does not open PRs.
- **`review-slice`** -- read-only review of SDFs against chisel conventions, CI checks, and forward-port rules.

@./mason/skills/chisel/SKILL.md

self-contained under `./mason/skills/chisel/`: `commands/`, shared reference `shared/CHISEL.md`, helpers under `scripts/`, command index `schemas/commands.manifest.yaml`. paths inside command files are relative to the skill's own directory (or, for repo paths like `slices/`, to the chisel-releases checkout being worked on).

the deterministic scripts are the backbone, so the commands don't rely on the agent remembering conventions or hand-rolling boilerplate:

- **inspect / author**: `orientation` (where am i, which release/format, which tools are available), `deb-list.py` (files + deps inside a .deb; `--sdf` groups them into a draft SDF -- bins/libs/config/headers/var/copyright, clutter dropped, multiarch dirs globbed, copyright wired (incl. shared-copyright doc-dir symlinks), sorted, ambiguous files left as unplaced comments -- as a deterministic starting point the author refines), `try-cut` (chisel cut into a temp root), `scaffold-test.py` (emit a spread `task.yaml` skeleton -- one fresh rootfs per binary-bearing slice, a chroot line per declared binary, so the author fills real functional checks not boilerplate).
- **check**: `check-slice.py` (static conventions: sorting, naming, absolute paths, copyright presence, clutter exclusion, arch names, version-gated fields, hint length/style), `check-test.py` (binary test coverage: warns on no test or a test exercising none of the binaries, else an info summary of untested binaries), `check-diff.py` (append-only regressions -- removed SDF / slice / path -- the `removed-slices` CI gate; file-pair or `--base <ref>` via git).
- **assemble**: `review-diff.py --base <ref>` finds the changed SDFs in a diff, runs the three checkers, prints findings by severity with a verdict, exits non-zero on any `block`. this is the CI-callable PR-review bot; it needs no agent.

`write-slice` drafts the SDF and its tests then self-checks with the checkers before commit; `review-slice` leads with `review-diff.py`; together they're the engine for a future chisel-releases PR-review bot. the generators round-trip with the checkers by construction -- a fresh `deb-list.py --sdf` passes `check-slice.py`, a fresh `scaffold-test.py` reports full coverage under `check-test.py`. static-check rule sets are kept in sync with the eval scorers under `tests/skills/scorers/` (shared vocab like the canonical slice-name set lives in both). the scripts have a pytest regression net at `tests/scripts/test_checks.py` (`uv run --with pyyaml --with pytest pytest tests/scripts/`); they're load-bearing, so keep it green. the checkers stay empirically clean against the real merged corpus on `ubuntu-24.04` (v1) and `ubuntu-26.04` (v3) -- 0 false-positive blocks.

`tests/` splits by what's under test: `tests/skills/` is the pats eval (agents run through the skill in docker, scored by the `scorers/`); `tests/scripts/` is pytest unit tests of the scripts that ship with the skill.

## install

`npx github:rockcrafters/mason install` copies all skills into the target agent's discovery dirs (see README). adding a capability = a new skill dir under `mason/skills/`.
