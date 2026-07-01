# mason

agent kit for chisel / rocks work. a cross-agent skill bundle, portable across claude code, pi, opencode, copilot, and codex.

each capability area is its own skill under `mason/skills/`. today there is one:

## chisel-releases

working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). command-per-file; commands:

- **`write-slice`** -- authors + tests + commits chisel slice definition files (SDFs). does not open PRs.
- **`review-slice`** -- read-only review of SDFs against chisel conventions, CI checks, and forward-port rules.

@./mason/skills/chisel-releases/SKILL.md

self-contained under `./mason/skills/chisel-releases/`: `commands/`, shared reference `shared/CHISEL.md`, helpers `scripts/` (`orientation`, `deb-list.py`, `try-cut`, `check-slice.py`, `check-test.py`, `check-diff.py`), command index `schemas/commands.manifest.yaml`. paths inside command files are relative to the skill's own directory (or, for repo paths like `slices/`, to the chisel-releases checkout being worked on).

three deterministic checkers are the backbone, so the commands don't rely on the agent remembering conventions:
- `check-slice.py` -- static SDF linter: sorting, naming, absolute paths, copyright presence, clutter exclusion, arch names, version-gated fields.
- `check-test.py` -- reports any binary an SDF ships that its spread test never exercises (a top rejection reason).
- `check-diff.py` -- append-only regressions between two SDF versions (removed SDF / slice / path), the `removed-slices` CI gate; works file-pair or `--base <ref>` via git.
- `review-diff.py --base <ref>` -- the assembled entrypoint: finds the changed SDFs in a diff, runs the three checkers over them, prints findings by severity with a verdict, exits non-zero on any `block`. this is the CI-callable PR-review bot; it needs no agent.

`write-slice` self-checks with the three checkers before commit; `review-slice` leads with `review-diff.py`; together they're the engine for a future chisel-releases PR-review bot. static-check rule sets are kept in sync with the eval scorers under `tests/scorers/` (shared vocab like the canonical slice-name set lives in both). the checkers have their own regression net at `tests/test_checks.py` (assert-based, run with `uv run tests/test_checks.py`); they're load-bearing, so keep it green when editing them. all checkers stay empirically clean against the real merged corpus on `ubuntu-24.04` (v1) and `ubuntu-26.04` (v3) -- 0 false-positive blocks.

## install

`npx github:rockcrafters/mason install` copies all skills into the target agent's discovery dirs (see README). adding a capability = a new skill dir under `mason/skills/`.
