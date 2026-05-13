---
name: reviewer
description: >
  Review chisel slice definition files (SDFs) for canonical/chisel-releases.
  Covers CI checks, reviewer conventions, style enforcement, dependency
  validation, formatting rules, forward-port requirements, and common
  rejection reasons. Use when reviewing a PR, validating an SDF, or
  checking slice quality before submission.
---

Skill for reviewing slices in [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases).

**Prerequisites**: read `@./CHISEL.md` for chisel/SDF format reference, branch model, schema versions, and canonical naming conventions. This skill focuses on _what to check_ when reviewing.

---

## CI Checks

These automated checks run on every PR. Understand what each one validates:

| Check | Failure means |
|-------|---------------|
| `lint` | YAML syntax/formatting issue in SDF |
| `install-slices` | Slice can't `chisel cut`, or package not in archive for some arch |
| `removed-slices` | SDF deleted -- breaking unless package is gone from the archive |
| `forward-port-missing` | New slice in branch but not in newer live releases |
| `pkg-deps` | Informational diff of declared deps vs `apt depends`; non-blocking but reviewer signal |
| `validate-hints` | `hint:` text fails NLP style check (v3+ only) |
| `spread` | Integration test failed inside LXD test container |
| `cla-check` | CLA unsigned |

All checks must be green before review. `pkg-deps` is non-blocking but reviewers use it to cross-check dependency accuracy.

## Dependency Validation

- **`Depends:` only.** Not `Recommends:` or `Suggests:`. Including `Recommends:` is an immediate rejection.
- **Stay true to deb's declared deps.** Each direct `apt Depends:` should appear as an `essential:` entry. Cross-check via `pkg-deps` CI output.
- **Maintainer postinst is not mirrored.** If upstream `postinst` invokes another package's tool (e.g. `update-mime-database`), either drop the dep or write a `mutate:` equivalent. Do not pull in the tool's package as a dependency.
- **Only slices we need.** Speculative slices (slices added "just in case") are rejected.
- **Use-case-agnostic.** Comments like "this slice exists for app X" are rejected. Describe what the slice ships, not who it's for.

## Append-Only Principle

Published slices are **append-only in spirit**. Removing files from an existing slice is a regression for downstream consumers. If a slimmer variant is needed, create a new slice (`core`, `minimal`, or a more specific name) rather than removing from an existing one.

## Naming Conventions

Verify against the Canonical Slice Names table in `@./CHISEL.md`:

- `bins` (never `bin`) for executables
- `libs` (never `lib`) for shared libraries
- `config` for configuration files; break large configs into `<purpose>-config`
- `scripts` for non-binary executables (not in `bins`)
- `copyright` for deb copyright (mandatory)
- `license` / `notice` for upstream licence/notice (separate from `copyright`)
- `core` for minimum-functional subset (never `all` -- rejected)
- When deb already names `<pkg>-core`, keep verbatim

Slice names must: be lowercase, >= 3 characters, only `a-z 0-9 -`, start with a letter.

## Formatting Rules

These are hard gates. Reject if violated:

1. **Contents paths sorted** in bytewise ASCII (lexicographic) order within each slice.
2. **Global `essential:`** placed at top of file, right after `package:`.
3. **`copyright` slice** placed last in the `slices:` block.
4. **`package:` matches filename stem.** `slices/foo.yaml` -> `package: foo`.
5. **One SDF per package.** Never two packages in one YAML.

## Path Entry Style

- **Multiarch lib glob**: `*-linux-*`, not explicit triples. E.g. `/usr/lib/*-linux-*/libnghttp2.so.14*:`.
- **Drop trailing `*` for single-version sonames**: `libfoo.so.1:` not `libfoo.so.1*:`.
- **No explicit `symlink:` if deb ships it.** Chisel preserves deb symlinks. Manual `symlink:` only for paths the deb doesn't ship (e.g. created by maintainer scripts).
- **Annotate explicit symlinks**: `/usr/bin/dotnet:  # Symlink to ../lib/dotnet/dotnet`.
- **Inline-style for short options**: `/path: {arch: [amd64, arm64]}`.
- **Arch list formatting**: lowercase, alphabetical, single space after commas, no inner padding.
  - Correct: `{arch: [amd64, arm64]}`
  - Rejected: `{arch: [ amd64, arm64 ]}` or `{arch: [arm64, amd64]}`

## Schema Version Compliance

Check `format:` in `chisel.yaml` on the target branch:

- `hint:` is **v3+ only**. Reject if used on v1/v2 branches.
- `prefer:` is **v2+ only**. Reject if used on v1 branches.
- `v3-essential:` (arch-gated deps map) is **v3+ only**.
- `pro:` under `archives:` is v2+ unified. v1 uses separate `v2-archives:` block.

## Testing Requirements

- **Every binary in a `bins` slice must be exercised** in spread tests. "Please test every binary being delivered" is a recurring rejection reason.
- **Untestable means unshippable.** Push to drop rather than ship untested.
- **~80% coverage** is a soft target mentioned in PR coverage comments. Not a hard gate but actively watched.
- **Functional slices need functional tests.** `--version` alone is insufficient for applications. Test actual functionality.
- Tests live at `tests/spread/integration/<pkg>/task.yaml`.

## Forward-Port Requirements

- **All PRs must be forward-ported** to every newer live release branch. PR chain goes oldest -> newest.
- `forward-port-missing` CI auto-labels PRs that lack this.
- Exception: package gone from the newer archive -- auto-ignored.
- Cross-link forward-port PRs in descriptions.
- Non-forward-port PRs: mark with `### Forward porting\nn/a` in description.
- Trivial forward-port PRs (cherry-picks of approved changes) sometimes land on one approval. Do not rely on it for substantive work.

## Contribution Process

Defer to [`CONTRIBUTING.md`](https://github.com/canonical/chisel-releases/blob/main/CONTRIBUTING.md). Key points:

- **Branch off the target release branch**, not `main`. PRs into `main` are wrong.
- **Conventional commits**: `feat:`, `fix:`, `test:`, `ci:`, `chore:`, `docs:`, `refactor:`. Subject lowercase, imperative, <=50 chars, no trailing period. Body wrap 72.
- **Two maintainer approvals** required, CLA signed, green CI before review.
- **No force-push** after review comments.
- **One cohesive change per PR.** Don't mix unrelated slice definitions.

## Common Rejection Reasons

1. Unsorted `contents` paths
2. Missing `copyright` slice or not in global `essential:`
3. `Recommends:`/`Suggests:` included as dependencies
4. Speculative slices with no demonstrated need
5. Use-case-specific comments ("for app X")
6. `bin`/`lib` instead of `bins`/`libs`
7. Explicit `symlink:` for paths the deb already ships
8. Missing tests for binaries in `bins` slice
9. Arch list with wrong formatting (inner spaces, wrong order)
10. v3 features (`hint:`) used on v1/v2 branches
11. Missing forward-port PRs for newer release branches
12. Files removed from existing published slice (regression)
13. `package:` field doesn't match YAML filename stem

## Copilot Warning

GitHub Copilot auto-reviews and proposes patterns that reviewers reject:
- Inner-spaced arch lists: `{ arch: [ amd64 ] }` (wrong)
- `: {}` on essential entries (wrong for v1/v2)

Do not follow Copilot suggestions blindly.

---

## Post-Review Reflection

After completing a review, perform a reflection pass to verify your review criteria against the sources of truth and improve this skill for next time.

### Validate review criteria against upstream

Fetch the current documentation and compare the review criteria used:

```bash
# SDF format reference (field validity, format version rules)
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/slice-definitions.md

# chisel.yaml reference (schema versions, what format gates what)
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/chisel.yaml.md

# Contribution rules
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/main/CONTRIBUTING.md

# Canonical reference SDFs on the target branch
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/bash.yaml
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/base-files.yaml
```

Check:
- Are there new CI checks not listed in the CI Checks table above?
- Have formatting or naming conventions evolved in recent SDFs?
- Are there new SDF fields or content path options that require new review rules?
- Has `CONTRIBUTING.md` added new requirements (e.g. new commit conventions, changed approval process)?
- Have schema version boundaries changed (new format version, new branches)?

### Validate against chisel tool behaviour

If the review flagged something as invalid but `chisel cut` accepted it (or vice versa), check the tool source:

```bash
curl -fsSL https://raw.githubusercontent.com/canonical/chisel/main/internal/setup/setup.go
```

The tool's actual behaviour overrides any written convention.

### Update the skill files

If discrepancies were found:
- **Review criteria changes** (new CI checks, changed style rules, new rejection reasons) -> update this file (`reviewer/SKILL.md`)
- **Factual corrections** (format versions, field names, valid values) -> update `@./CHISEL.md`
- **Workflow changes** (new steps, changed recommendations) -> update `slice/SKILL.md`

Principles:
- Be specific: add exact rules, not vague guidance.
- Add context: explain _why_ a rule exists if non-obvious.
- Preserve structure: add to existing sections.
- Remove stale content: don't leave contradictory information.
