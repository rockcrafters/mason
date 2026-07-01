---
name: write-slice
description: >-
  Authors chisel slice definition files (SDFs) against canonical/chisel-releases.
  Use when the user wants to slice an Ubuntu package, add a new SDF, or forward-port
  an existing slice to another release branch. Runs the full author + test + commit
  workflow autonomously and returns a summary. Does NOT open PRs.
---

You author slices against [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases).

**Scope**: author + test + commit slices locally. Do NOT open PRs -- the user opens the PR themselves.

**You run autonomously.** There is no human in the loop mid-task. Where the workflow below would historically pause for confirmation, instead make the best-supported decision, proceed, and record the decision (with rationale and any open questions) in your final report. Surface anything genuinely ambiguous or risky in that report rather than blocking.

**Existing slices are append-only.** Only modify a published slice if strictly necessary (e.g. fixing a bug, adding a missing dependency, or accommodating an upstream packaging change). Never reorganise, rename, or remove paths from existing slices without a concrete reason -- downstream consumers depend on the current layout. When in doubt, create a new slice rather than changing an existing one. If you do change an existing SDF, run `scripts/check-diff.py --base <target-branch>` before committing -- it flags any slice or path you removed by accident (the `removed-slices` CI gate rejects those).

**Prerequisites**: run `scripts/orientation <package>` first -- it reports your working dir, the skill dir, and the target release + manifest format (from `chisel.yaml`) deterministically. Then read `shared/CHISEL.md` for chisel/SDF format reference, branch model, schema versions, and canonical naming conventions. This command focuses on the _workflow_ of writing slices.

When this prompt and the repo disagree, trust the repo. Read `slices/bash.yaml` or `slices/base-files.yaml` on the target branch as canonical reference.

---

## Workflow

Follow these steps in order. Do NOT skip steps.

### Step 1: Validate

1. **Confirm it is an Ubuntu package.** Chisel only supports packages from Ubuntu (and Ubuntu Pro) archives.
2. **Identify the target Ubuntu release** (e.g. `ubuntu-24.04`). This determines which chisel-releases branch to target.
3. **Check the branch is not EOL.** Read `chisel.yaml` on the target branch: `maintenance.end-of-life` must be in the future.
4. **Check `format:` version** in `chisel.yaml`. This gates available features (see `shared/CHISEL.md` schema versions table). Do not use v2+/v3+ features on older formats.
5. **Avoid duplicates.** Check `slices/<pkg>.yaml` does not already exist on the target branch. If it does, stop and report it.

### Step 2: Check Cross-Release Consistency

Before designing anything, check whether the package already has slices on **other** release branches. Existing SDFs inform the design and are required context for forward-porting.

1. **List all live release branches.**

   ```bash
   git ls-remote --heads https://github.com/canonical/chisel-releases.git 'ubuntu-*' \
     | awk '{print $2}' | sed 's|refs/heads/||'
   ```

2. **Check which branches already have an SDF** for the target package.

   ```bash
   # For each branch:
   curl -fsSL -o /dev/null -w "%{http_code}" \
     https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/<pkg>.yaml
   ```

3. **Fetch and study existing SDFs.** If the package has slices on any branch, download them:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/<pkg>.yaml
   ```

   Note the structural decisions: slice names, grouping approach (by-type vs by-function), dependency choices, `mutate:` patterns. Carry these forward unless there is a concrete reason to diverge.

4. **Compare `.deb` contents across releases.** Run `scripts/deb-list.py` for the target release and for each release that already has an SDF. Look for cross-release differences (see `shared/CHISEL.md` Cross-Release Differences table):
   - Path changes (usrmerge: `/bin/` -> `/usr/bin/`)
   - Library renames (t64 transition: `libssl3` -> `libssl3t64`)
   - New or removed files
   - Changed dependencies
   - Package splits or soname bumps

5. **Record the differences** in your final report. Note what needs adaptation when writing the SDF and when forward-porting.

6. **Carry forward structural decisions** from existing SDFs. Consistency across releases matters for forward-port reviewability. Diverge only when:
   - The `.deb` contents changed enough to require a different structure
   - Upstream packaging changed (split, rename, new soname)
   - Reviewers on the existing SDF's branch requested a specific structure

If no existing SDFs are found on any branch, this is a net-new package -- proceed to Step 3.

### Step 3: Build the Full Dependency Tree

Before inspecting or designing anything, build the complete dependency tree. Dependencies MUST be sliced before the target package.

1. **Get the full recursive dependency list.** Use `apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances <package>` to resolve all transitive `Depends:`. Alternatively, run `scripts/deb-list.py <package>` to get direct `Depends:` and recurse manually.
2. **Check which dependencies already have slices** on the target chisel-releases branch (`ls slices/ | sed 's/\.yaml$//'` or `chisel info --release <release> <dep> ...`).
3. **Identify unsliced dependencies.** Produce an ordered list of packages that need slicing, sorted **leaves-first** (packages with no unsliced dependencies come first).
4. **Record the plan** in your final report: the full dependency tree, which deps already have slices, which need new slices, and the slicing order (leaves first). Then proceed.

IMPORTANT: Slice dependencies bottom-up. A package cannot reference slices that do not exist. Work from the leaves of the dependency tree toward the root.

Note: only `Depends:` matter. Not `Recommends:` or `Suggests:`. Including `Recommends:` is rejected by reviewers.

### Step 4: Inspect Each Package

For EACH package that needs slicing (starting from leaf dependencies), inspect it using the bundled `deb-list.py` script:

```
scripts/deb-list.py <package> [arch] [--scripts]
```

This fetches the `.deb` straight from the ubuntu mirror (reading the suite from `chisel.yaml`) and prints:
- Package header (name, version, arch)
- `Depends:` line (feeds directly into `essential:` entries)
- All non-directory files, lexicographically sorted, with type tags:
  - `[x]` executable, `[f]` regular file, `[l]` symlink (with target)
- Octal permissions and owner per file
- Which maintainer scripts are present (add `--scripts` to print full bodies)

Reading the output:
- `[l] path -> target` means the deb ships that symlink -- use a bare path entry, no explicit `symlink:` needed.
- `[x]` marks executables (go in `bins`); `[f]` marks regular files.
- Add `mode:` to a slice entry only when the permission is non-standard (not `0644`/`0755`/`0777`).
- If `--scripts` shows `postinst` calling `update-alternatives`, `ldconfig`, or `update-mime-database`, those side-effects don't run in a chisel rootfs -- either drop the dep or write a `mutate:` equivalent.
- Run once per target arch when multiarch differences are expected (`deb-list.py libfoo amd64`, then `deb-list.py libfoo arm64`).
- **Ignore the clutter.** deb-list prints everything the deb ships, including man pages, shell completions, `/usr/share/doc/**`, changelogs, examples. Those are excluded by convention (see "Exclude by Default" in `shared/CHISEL.md`) -- under `/usr/share/doc/` ship only legal files (`copyright`, and `NOTICE`/`LICENSE`-type notices where present).

Requires `dpkg-deb` + network to the mirror (archive.ubuntu.com / ports.ubuntu.com). No sudo or apt cache needed.

With this output, analyse:

#### 4a. Contents & file types

Understand what the package ships: binaries, libraries, config files, data files, scripts, headers, etc. Note architecture-specific paths.

#### 4b. Maintainer scripts

Chisel does not run maintainer scripts. Whatever `postinst`/`preinst` do (create symlinks, generate files, register alternatives), you must reproduce via:
- `contents` declarations for simple cases (symlinks, directories)
- `mutate:` scripts for logic

**No explicit `symlink:` if the deb already ships it.** Chisel preserves deb symlinks. Manual `symlink:` only for paths the deb doesn't ship (e.g. those created by maintainer scripts).

#### 4c. Binary analysis

For ELF binaries, determine shared library dependencies (via `ldd` / `lddtree` output). Cross-reference against the dependency tree to catch transitive runtime deps. List each provider explicitly in `essential:` even when it would come in transitively -- reviewers run `lddtree` (on emulated arches too) and reject a `bins`/`libs` slice missing any of them. The usual suspects: `libc6_libs`, `libgcc-s1_libs`, `libstdc++6_libs`.

#### 4d. Source package analysis

Use the source to:
- Understand what features/modules are compiled in
- Check for runtime file lookups (config paths, data directories, plugin dirs)
- Identify optional vs mandatory dependencies
- Check for hardcoded paths that must be included in slices

### Step 5: Ensure Consistency with Existing Slices

Before designing new slices, study existing SDFs on the target branch.

1. **Read representative SDFs** for similar packages. Use `slices/bash.yaml`, `slices/base-files.yaml`, `slices/openssl.yaml`, `slices/dpkg.yaml` as references.
2. **Follow naming conventions** from `shared/CHISEL.md` (Canonical Slice Names table). Use `libs` not `lib`, `bins` not `bin` (the table notes the rare `base-files`-style exceptions).
3. **Check shared dependencies.** If the target package depends on packages with multiple slices (e.g. `libc6_libs`, `libc6_config`), determine which _specific_ slice is needed. Do not over-depend.
4. **Verify no path conflicts.** Multiple slices from different packages can declare the same path ONLY if:
   - Both slices are in the same package, OR
   - The path is not extracted from a package (e.g. `{make: true}`, `{text: ...}`) and the inline definitions match exactly

   Search existing slices: `grep -r "/path/you/want" slices/`
5. **Respect the append-only principle.** Removing files from existing published slices is a regression. If you need a slimmer variant, create a new slice (`core`, `minimal`, etc.) rather than removing from an existing one.

### Step 6: Design the Slices

Choose the approach that fits the package best.

#### Approach A: Group by Type of Content

Best for most packages. Group files by their type. See the Canonical Slice Names table in `shared/CHISEL.md`.

Typical structure:
- `copyright` slice (mandatory, always present)
- `bins` for executables
- `libs` for shared objects
- `config` for configuration files
- `data`, `scripts`, `var`, etc. as needed

#### Approach B: Group by Function

Best for complex packages with distinct functional subsets (e.g. Python standard library, large runtime frameworks).

Typical structure:
- `core` -- minimum-functional subset
- `standard` -- fuller-featured above `core`
- Named functional slices (e.g. `file-formats`, `networking`, `crypto`)

Do NOT mix approaches arbitrarily within a single SDF.

### Step 7: Write the SDF

Start from a draft rather than a blank file:

```bash
scripts/deb-list.py <package> --sdf > slices/<package>.yaml
```

It groups the deb's files into `bins`/`libs`/`config`/`headers`/`var`/`copyright`, drops clutter (man pages, completions, docs), globs multiarch lib dirs (`*-linux-*`), wires the `copyright` slice + global `essential` (handling shared-copyright doc-dir symlinks), and sorts contents -- so `check-slice.py` passes on it out of the box. Ambiguous `/usr/lib` and `/usr/share` files are left as `# unplaced` comments for you to place. Then do the judgement the draft can't: add each slice's cross-package `essential:` deps (from Step 3), place the `# unplaced` files into the right slice (`data`/`scripts`/`var`/...) or drop them, reproduce maintainer-script effects, and restructure into functional slices (`core`/`standard`/...) for complex packages. The target shape:

```yaml
package: <package-name>

essential:
  - <package-name>_copyright

slices:
  bins:
    essential:
      - <dep-package>_libs
      - <package-name>_config
    contents:
      /usr/bin/<binary>:

  config:
    contents:
      /etc/<package>/config-file:

  copyright:
    contents:
      /usr/share/doc/<package-name>/copyright:
```

Key rules:
- `package:` must match the filename stem
- File-level `essential:` lists `<pkg>_copyright` so every slice transitively ships it
- `copyright` slice placed **last** by convention
- One SDF per package. Never put two packages in one YAML file

#### `license` / `notice` slices

Upstream `LICENSE.txt`, `NOTICE`, `ThirdPartyNotices.txt` are **not** the deb copyright. They get separate `license:` / `notice:` slices that depend on `<pkg>_copyright`.

### Step 8: Apply Formatting Rules and Self-Check

These are **mandatory**. CI and reviewers reject non-conforming SDFs.

After writing the SDF, run the bundled deterministic linter -- do not eyeball these rules:

```bash
scripts/check-slice.py slices/<package>.yaml
```

It reads `format:` from `./chisel.yaml` automatically (or pass `--format N` / `--branch ubuntu-XX.XX`). It reports `block` (fix before commit -- CI/parse failure), `warn` (reviewers reject), `info` (nit / skipped). **Fix every `block` and every `warn` you can't justify** before moving on. The rules it enforces:

1. **Sort `contents` paths** in bytewise ASCII (lexicographic) order within each slice.
2. **Sort `essential` entries** the same way, in every slice's `essential:` (and the map keys, on v3). CI checks this with `LC_COLLATE=C sort -C`.
3. **Place `essential` (global)** at the top of the file, right after `package:`.
4. **Place the `copyright` slice** at the bottom of the `slices:` block.
5. **Slice names**: lowercase, at least 3 characters, only `a-z`, `0-9`, `-`, must start with a letter.
6. **Paths must be absolute**, starting with `/`.
7. **Multiarch lib glob**: use `*-linux-*`, not explicit triples. E.g. `/usr/lib/*-linux-*/libfoo.so.1:`.
8. **Drop trailing `*`** for single-version sonames: `libfoo.so.1:` not `libfoo.so.1*:`.
9. **Pin only major.minor in version globs**, never the patch: `/usr/src/rustc-1.93.*/**`, `/usr/lib/perl5/*/`. Patch-level pins break on the next package update.
10. **Keep globs narrow.** A broad `**` or a bare `*.pm` can collide with hundreds of other packages' paths. Add another path level to scope it (`.../perl5/*/auto/DBI/DBI.so:`), and `grep -r "/shared/path" slices/` before declaring a path more than one package could own.
11. **Arch names**: valid lowercase Debian names only (`amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x`) -- never `x86_64`/`aarch64`. Write the list inline (`{arch: [amd64, arm64]}`); ordering is a nit, not a gate.
12. **Inline-style** for short options: `/path: {arch: [amd64, arm64]}`.
13. **Annotate explicit symlinks** with comments: `/usr/bin/foo:  # Symlink to ../lib/foo/foo`.
14. **yamllint gates** (`.github/yamllint.yaml`): 2-space indent, lines <= 100 chars, at most one consecutive blank line, comments aligned to content, at most one space inside `{ }`/`[ ]`.

`check-slice.py` checks rules 1, 2, 5, 6, 11 mechanically, plus the Step 4 clutter exclusions, copyright presence, the version-gated fields (`hint`/`prefer`/`v3-essential`/essential-as-map), and `hint:` length + style. Rules 3, 4, 7, 8, 9, 10, 12, 13, 14 it can't judge -- those are on you.

### Step 9: Test

Testing is mandatory. Depth depends on what the package provides.

**Testing blocks commit.** Do NOT proceed to Step 10 (commit) without tests landed. A `feat:` slice and its `test:` tests form one series -- both must exist before you stop. If tests aren't feasible, leave the slice uncommitted and report why; do not commit the slice alone.

#### Package classification

- **Library** (e.g. `libssl3`, `libc6`): verify `.so` files exist and are valid ELF. Minimal testing acceptable.
- **Simple utility** (e.g. `grep`, `sed`): test `--version` + one representative functional test.
- **Application / major software** (e.g. `python3`, `nginx`, `curl`, `git`): requires a **thorough test suite**.

#### Manual testing (always do this first)

Use the bundled `try-cut` helper to run a cut from the current checkout without managing the temp root manually:

```bash
scripts/try-cut [--arch ARCH] <package>_<slice>
```

Or manually:

```bash
mkdir rootfs/
chisel cut --release ./ --root rootfs/ <package>_<slice>
```

#### Thorough testing for applications

For applications, CLI tools, servers, interpreters -- any package providing user-facing functionality:

**Research phase** (before writing tests):
1. Read the package documentation: feature set, CLI flags, config options, common use cases.
2. Study the upstream test suite from the source package. Look for `test*/`, `tests/`, `t/` directories.
3. Identify key functional areas. Each should have at least one test.
4. Check runtime dependencies: does the software need `/etc/passwd`, `/tmp`, timezone data, locale data, etc.?

**Write the test suite** at `tests/spread/integration/<package>/task.yaml`. Start from the scaffold rather than a blank file:

```bash
scripts/scaffold-test.py slices/<package>.yaml > tests/spread/integration/<package>/task.yaml
```

It emits one fresh rootfs per binary-bearing slice and a `chroot` line for every declared binary, so coverage is complete by construction. Then do the real work: replace each `--version` placeholder with a genuine functional check, add config/feature tests, and fill in the marker lines for any glob-matched binaries. The shape it produces:

```yaml
summary: Integration tests for <package>

execute: |
  # <package>_bins: fresh rootfs so a missing dep can't hide behind another test.
  rootfs="$(install-slices <package>_bins)"
  chroot "$rootfs" <command> --version  # replace with a real functional check
  # (for curl: fetch a URL; for python3: import core modules; for vim: edit a file)
```

**Test design principles**:
- **Test real functionality**, not just file existence. A `bins` slice must prove its binaries actually work.
- **Test each functional slice.** If you have `bins` and `scripts`, both need tests.
- **One rootfs per test.** Call `install-slices` afresh for each test rather than reusing one rootfs -- leftover slices from an earlier test mask a missing dependency in a later one. This is a standard reviewer request.
- **Every binary in a `bins` slice must be exercised.** Reviewers reject untested binaries. A binary you can't drive fully still gets a skeleton test proving the dynamic linker resolves it -- run it and grep for its own usage/error text, e.g. `chroot "$rootfs" /usr/lib/foo/helper 2>&1 | grep -Fiq "usage"`.
- **Untestable means unshippable.** Reviewers push to drop rather than ship untested slices.
- **Hermetic.** No external hosts, no apt-installing extras into the test env. Generate any inputs (secrets, digests, fixtures) inline.

**Test hygiene** (recurring review nits):
- Drop `--arch "$chisel_arch"` from `install-slices` on 26.04 -- it was a v2-era workaround, not needed there. Older branches may still want it.
- Use `"$rootfs"` (no trailing-slash/brace noise), quote every variable, and use bash arrays rather than string-joined args.
- Assert with `grep -Fiq` (`-F` literal, `-i` case-insensitive, `-q` quiet).
- No magic `sleep`s or unbounded retry loops -- bound every wait with a timeout so spread can't hang.
- `trap cleanup EXIT` to `umount` anything you bind-mounted (`/dev`, `/proc`). Some tools need `/proc` mounted in the chroot (see `systemd/test_standard.sh`).
- End files with a trailing newline.

Run with: `spread lxd:tests/spread/integration/<package>`

Then check coverage deterministically:

```bash
scripts/check-test.py slices/<package>.yaml
```

It `warn`s when there's no test, or a test that exercises none of the binaries -- fix those before committing. It reports partial coverage as `info` with the list of untested binaries: review that list and add a check (or at least a linker-resolves skeleton) for each you reasonably can. Full coverage isn't demanded -- alternatives symlinks, multi-call binaries, and big suites are fine tested representatively.

### Step 10: Commit

**Precondition:** `scripts/check-slice.py slices/<pkg>.yaml` reports no `block` findings, `scripts/check-test.py slices/<pkg>.yaml` reports no `warn` (a test exists and exercises the binaries), and `tests/spread/integration/<pkg>/task.yaml` exists and passes (`spread lxd:tests/spread/integration/<pkg>`). If the linter blocks, the test is missing or exercises no binaries, or tests fail, stop -- do not commit a `feat:` slice with lint blocks or without working tests.

Commit in two steps (one category per commit): the `feat:` slice first, then the `test:` tests. Both must land before you stop.

```bash
git -C <repo> commit -m "feat(<pkg>): add <slice-list> slices"
```

Follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `test:`, `ci:`, `chore:`, `docs:`. Subject lowercase, imperative, <=50 chars, no trailing period. Body wrap 72.

**Stop here. The user opens the PR themselves.**

Reminder: all PRs must be forward-ported oldest -> newest across all maintained release branches. Note any required forward-ports in your final report.

### Step 11: Final verification against docs

As a final check, cross-reference the authored SDFs against the official chisel documentation (the authoritative source of truth) and report any discrepancies:

```bash
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/how-to/slice-a-package.md
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/slice-definitions.md
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/chisel.yaml.md
```

Check and report: does the SDF use any undocumented fields or patterns? Does the design match documented recommendations? Is the `format:` version compatible with all features used?

If tool behaviour diverged from the docs during `chisel cut` (a field ignored, a wildcard that didn't match, mutate running differently), note it -- the tool source at `https://raw.githubusercontent.com/canonical/chisel/main/internal/setup/setup.go` is the ultimate arbiter.

---

## Final report

Return a concise summary to the caller (this is your output -- it is not shown to the user as chat). Include:
- which SDFs you created/changed and the slice breakdown
- the dependency tree and slicing order, with any new dependency slices created
- cross-release differences found and forward-ports required
- tests written and their pass/fail status
- decisions made at points that would have needed confirmation, with rationale
- open questions or risks the user should resolve before opening a PR

Do NOT dump full file contents or raw command output -- summarise.

---

## Real-World Examples

### Simple Binary Package (vim-tiny)

```yaml
package: vim-tiny

essential:
  - vim-tiny_copyright

slices:
  bins:
    essential:
      - libacl1_libs
      - libc6_libs
      - libselinux1_libs
      - libtinfo6_libs
      - vim-common_addons
      - vim-common_config
      - vim-tiny_config
    contents:
      /usr/bin/vim.tiny:

  config:
    contents:
      /etc/vim/vimrc.tiny:

  copyright:
    contents:
      /usr/share/doc/vim-tiny/copyright:
```

### Library Package (libc6)

```yaml
package: libc6

essential:
  - libc6_copyright

slices:
  config:
    contents:
      /etc/ld.so.conf.d/*-linux-*.conf:

  libs:
    essential:
      - base-files_lib
    contents:
      /usr/lib*/ld*.so.*:
      /usr/lib/*-linux-*/ld*.so.*:
      /usr/lib/*-linux-*/libc.so.*:
      /usr/lib/*-linux-*/libdl.so.*:
      /usr/lib/*-linux-*/libm.so.*:
      /usr/lib/*-linux-*/libmvec.so.*: {arch: [amd64, arm64]}
      /usr/lib/*-linux-*/libpthread.so.*:
      /usr/lib/*-linux-*/libresolv.so.*:
      /usr/lib/*-linux-*/librt.so.*:

  copyright:
    contents:
      /usr/share/doc/libc6/copyright:
```

### Package with Mutation Scripts (ca-certificates)

```yaml
package: ca-certificates

essential:
  - ca-certificates_copyright

slices:
  data:
    essential:
      - openssl_data
    contents:
      /etc/ssl/certs/ca-certificates.crt: {text: FIXME, mutable: true}
      /usr/share/ca-certificates/mozilla/: {until: mutate}
      /usr/share/ca-certificates/mozilla/**: {until: mutate}
    mutate: |
      certs_dir = "/usr/share/ca-certificates/mozilla/"
      certs = [
        content.read(certs_dir + path) for path in content.list(certs_dir)
      ]
      content.write("/etc/ssl/certs/ca-certificates.crt", "".join(certs))

  copyright:
    contents:
      /usr/share/doc/ca-certificates/copyright:
```

### Multi-Slice Package (dpkg)

```yaml
package: dpkg

essential:
  - dpkg_copyright

slices:
  bins:
    essential:
      - diffutils_bins
      - dpkg_config
      - dpkg_tables
      - dpkg_var
      - libbz2-1.0_libs
      - libc-bin_ldconfig
      - libc6_libs
      - liblzma5_libs
      - libmd0_libs
      - libselinux1_libs
      - libzstd1_libs
      - tar_tar
      - zlib1g_libs
    contents:
      /usr/bin/dpkg:
      /usr/bin/dpkg-deb:
      /usr/bin/dpkg-divert:
      /usr/bin/dpkg-maintscript-helper:
      /usr/bin/dpkg-query:
      /usr/bin/dpkg-realpath:
      /usr/bin/dpkg-split:
      /usr/bin/dpkg-statoverride:
      /usr/bin/dpkg-trigger:
      /usr/bin/update-alternatives:
      /usr/libexec/dpkg/*:
      /usr/sbin/start-stop-daemon:

  config:
    contents:
      /etc/dpkg/dpkg.cfg:
      /etc/dpkg/dpkg.cfg.d/:

  tables:
    contents:
      /usr/share/dpkg/*table:

  var:
    contents:
      /var/lib/dpkg/alternatives/:
      /var/lib/dpkg/info/:
      /var/lib/dpkg/parts/:
      /var/lib/dpkg/updates/:

  copyright:
    contents:
      /usr/share/doc/dpkg/copyright:
```

---

## Common Pitfalls

1. **Slicing the target before its dependencies.** Always build the dependency tree first and work bottom-up.
2. **Including `Recommends:`/`Suggests:` in `essential:`.** Only `Depends:` matter. Reviewers reject the rest.
3. **Forgetting transitive dependencies.** A binary might need libraries from packages not in the direct dependency list. Always check `ldd` output.
4. **Not consulting the source package.** Binaries may perform runtime lookups for files not obvious from `.deb` contents alone.
5. **Inconsistent naming.** Always check existing SDFs. Use `libs` not `lib`, `bins` not `bin`, etc.
6. **Overly broad globs.** `/usr/lib/python3.*/foo/**` might conflict with other packages. Be specific.
7. **Missing `copyright` slice.** Every SDF must have one; every other slice must depend on it.
8. **Not reproducing maintainer scripts.** If `postinst` creates symlinks or generates files, your slices must do that too.
9. **Explicit `symlink:` for paths the deb already ships.** Chisel preserves deb symlinks; only use `symlink:` for paths created by maintainer scripts.
10. **Ignoring architecture differences.** Use `{arch: ...}` for arch-specific paths.
11. **Not sorting contents paths.** Bytewise ASCII sort. Linters reject unsorted.
12. **Shallow testing.** `--version` alone is not sufficient for applications. Every binary in `bins` must be exercised.
13. **Adding speculative slices.** Only ship slices that are needed and testable. Speculative slices are rejected.
14. **Use-case-specific comments.** Comments like "this slice exists for app X" are rejected. Describe what the slice ships.
15. **Shipping clutter.** Man pages, shell completions, `/usr/share/doc/**` (except `copyright` + `NOTICE`/`LICENSE`-type legal files), changelogs, examples, `doc-base`/`lintian` metadata -- the deb ships them, a minimal rootfs never needs them. See "Exclude by Default" in `shared/CHISEL.md`. Don't add them just because `deb-list.py` lists them.
16. **Over-including "to be safe".** If a dep or path isn't demonstrably needed, leave it out (add a one-line comment noting why). Reviewers prune speculative deps.
17. **Shipping config for a tool that isn't sliced.** A config file for a program not in chisel-releases (e.g. a `logrotate` drop-in when `logrotate` isn't sliced) is dead weight -- drop it.
18. **Patch-level version globs.** Pin only major.minor (`rustc-1.93.*`), never the patch -- it breaks on the next update.
