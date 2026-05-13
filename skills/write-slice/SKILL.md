---
name: write-slice
description: >
  Author chisel slice definition files (SDFs) for canonical/chisel-releases.
  Covers dependency-tree-first workflow, package inspection via deb-list,
  slice design, SDF authoring, formatting, and testing. Stops at local
  commits; user opens PR themselves.
  Use when user says "add slice", "chisel slice", "slice <pkg>",
  or works inside a `canonical/chisel-releases` checkout.
---

Skill for authoring slices against [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases).

**Scope**: author + test + commit slices locally. Do NOT open PRs -- user opens PR themselves.

**Existing slices are append-only.** Only modify a published slice if strictly necessary (e.g. fixing a bug, adding a missing dependency, or accommodating an upstream packaging change). Never reorganise, rename, or remove paths from existing slices without a concrete reason -- downstream consumers depend on the current layout. When in doubt, create a new slice rather than changing an existing one.

**Prerequisites**: read `@./CHISEL.md` for chisel/SDF format reference, branch model, schema versions, and canonical naming conventions. This skill focuses on the _workflow_ of writing slices.

When this skill and the repo disagree, trust the repo. Read `slices/bash.yaml` or `slices/base-files.yaml` on the target branch as canonical reference.

---

## Workflow

Follow these steps in order. Do NOT skip steps.

### Step 1: Validate

1. **Confirm it is an Ubuntu package.** Chisel only supports packages from Ubuntu (and Ubuntu Pro) archives.
2. **Identify the target Ubuntu release** (e.g. `ubuntu-24.04`). This determines which chisel-releases branch to target.
3. **Check the branch is not EOL.** Read `chisel.yaml` on the target branch: `maintenance.end-of-life` must be in the future.
4. **Check `format:` version** in `chisel.yaml`. This gates available features (see `@./CHISEL.md` schema versions table). Do not use v2+/v3+ features on older formats.
5. **Avoid duplicates.** Check `slices/<pkg>.yaml` does not already exist on the target branch. If it does, stop and inform the user.

### Step 2: Build the Full Dependency Tree

Before inspecting or designing anything, build the complete dependency tree. Dependencies MUST be sliced before the target package.

1. **Get the full recursive dependency list.** Use `apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances <package>` to resolve all transitive `Depends:`. Alternatively, run `deb-list <package>` to get direct `Depends:` and recurse manually.
2. **Check which dependencies already have slices** on the target chisel-releases branch (`ls slices/ | sed 's/\.yaml$//'` or `chisel info --release <release> <dep> ...`).
3. **Identify unsliced dependencies.** Produce an ordered list of packages that need slicing, sorted **leaves-first** (packages with no unsliced dependencies come first).
4. **Present the plan to the user.** Show:
   - The full dependency tree
   - Which dependencies already have slices
   - Which dependencies need new slices
   - The proposed slicing order (leaves first)

   Get confirmation before proceeding.

IMPORTANT: Slice dependencies bottom-up. A package cannot reference slices that do not exist. Work from the leaves of the dependency tree toward the root.

Note: only `Depends:` matter. Not `Recommends:` or `Suggests:`. Including `Recommends:` is rejected by reviewers.

### Step 3: Inspect Each Package

For EACH package that needs slicing (starting from leaf dependencies), inspect it using the bundled `deb-list` script:

```
deb-list <package> [arch] [--scripts]
```

This downloads the `.deb` from the local apt cache and prints:
- Package header (name, version, arch)
- `Depends:` line (feeds directly into `essential:` entries)
- All non-directory files, lexicographically sorted, with type tags:
  - `[x]` executable, `[f]` regular file, `[l]` symlink (with target)
- Octal permissions and owner per file
- Which maintainer scripts are present (add `--scripts` to print full bodies)

Example:

```
$ deb-list bash
package: bash  version: 5.3-2ubuntu1  arch: amd64

Depends: base-files (>= 2.1.12), debianutils (>= 5.6-0.1)

files (lexicographic):  [x]=executable  [f]=file  [l]=symlink
  [f] 0644 root/root  /etc/bash.bashrc
  [f] 0644 root/root  /etc/skel/.bash_logout
  ...
  [x] 0755 root/root  /usr/bin/bash
  [l] 0777 root/root  /usr/bin/rbash -> bash
  [f] 0644 root/root  /usr/share/doc/bash/copyright
  ...

maintainer scripts present: postinst  (re-run with --scripts to view)
```

Reading the output:
- `[l] path -> target` means the deb ships that symlink -- use a bare path entry, no explicit `symlink:` needed.
- `[x]` marks executables (go in `bins`); `[f]` marks regular files.
- Add `mode:` to a slice entry only when the permission is non-standard (not `0644`/`0755`/`0777`).
- If `--scripts` shows `postinst` calling `update-alternatives`, `ldconfig`, or `update-mime-database`, those side-effects don't run in a chisel rootfs -- either drop the dep or write a `mutate:` equivalent.
- Run once per target arch when multiarch differences are expected (`deb-list libfoo amd64`, then `deb-list libfoo arm64`).

Requires `apt-get` + `dpkg-deb` and a populated apt cache (`sudo apt-get update`).

With this output, analyse:

#### 3a. Contents & file types

Understand what the package ships: binaries, libraries, config files, data files, scripts, headers, etc. Note architecture-specific paths.

#### 3b. Maintainer scripts

Chisel does not run maintainer scripts. Whatever `postinst`/`preinst` do (create symlinks, generate files, register alternatives), you must reproduce via:
- `contents` declarations for simple cases (symlinks, directories)
- `mutate:` scripts for logic

**No explicit `symlink:` if the deb already ships it.** Chisel preserves deb symlinks. Manual `symlink:` only for paths the deb doesn't ship (e.g. those created by maintainer scripts).

#### 3c. Binary analysis

For ELF binaries, determine shared library dependencies (via `ldd` output from the script). Cross-reference against the dependency tree to catch transitive runtime deps.

#### 3d. Source package analysis

Use the source to:
- Understand what features/modules are compiled in
- Check for runtime file lookups (config paths, data directories, plugin dirs)
- Identify optional vs mandatory dependencies
- Check for hardcoded paths that must be included in slices

### Step 4: Ensure Consistency with Existing Slices

Before designing new slices, study existing SDFs on the target branch.

1. **Read representative SDFs** for similar packages. Use `slices/bash.yaml`, `slices/base-files.yaml`, `slices/openssl.yaml`, `slices/dpkg.yaml` as references.
2. **Follow naming conventions** from `@./CHISEL.md` (Canonical Slice Names table). Use `libs` never `lib`, `bins` never `bin`, etc.
3. **Check shared dependencies.** If the target package depends on packages with multiple slices (e.g. `libc6_libs`, `libc6_config`), determine which _specific_ slice is needed. Do not over-depend.
4. **Verify no path conflicts.** Multiple slices from different packages can declare the same path ONLY if:
   - Both slices are in the same package, OR
   - The path is not extracted from a package (e.g. `{make: true}`, `{text: ...}`) and the inline definitions match exactly

   Search existing slices: `grep -r "/path/you/want" slices/`
5. **Respect the append-only principle.** Removing files from existing published slices is a regression. If you need a slimmer variant, create a new slice (`core`, `minimal`, etc.) rather than removing from an existing one.

### Step 5: Design the Slices

Choose the approach that fits the package best.

#### Approach A: Group by Type of Content

Best for most packages. Group files by their type. See the Canonical Slice Names table in `@./CHISEL.md`.

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

### Step 6: Write the SDF

Create `slices/<package>.yaml`:

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

### Step 7: Apply Formatting Rules

These are **mandatory**. CI and reviewers reject non-conforming SDFs.

1. **Sort `contents` paths** in bytewise ASCII (lexicographic) order within each slice.
2. **Place `essential` (global)** at the top of the file, right after `package:`.
3. **Place the `copyright` slice** at the bottom of the `slices:` block.
4. **Slice names**: lowercase, at least 3 characters, only `a-z`, `0-9`, `-`, must start with a letter.
5. **Paths must be absolute**, starting with `/`.
6. **Multiarch lib glob**: use `*-linux-*`, not explicit triples. E.g. `/usr/lib/*-linux-*/libfoo.so.1:`.
7. **Drop trailing `*`** for single-version sonames: `libfoo.so.1:` not `libfoo.so.1*:`.
8. **Arch list formatting**: lowercase, alphabetical, single space after commas, no inner padding. `{arch: [amd64, arm64]}` -- not `{arch: [ amd64, arm64 ]}`.
9. **Inline-style** for short options: `/path: {arch: [amd64, arm64]}`.
10. **Annotate explicit symlinks** with comments: `/usr/bin/foo:  # Symlink to ../lib/foo/foo`.

### Step 8: Test

Testing is mandatory. Depth depends on what the package provides.

#### Package classification

- **Library** (e.g. `libssl3`, `libc6`): verify `.so` files exist and are valid ELF. Minimal testing acceptable.
- **Simple utility** (e.g. `grep`, `sed`): test `--version` + one representative functional test.
- **Application / major software** (e.g. `python3`, `nginx`, `curl`, `git`): requires a **thorough test suite**.

#### Manual testing (always do this first)

Use the bundled `try-cut` helper to run a cut from the current checkout without managing the temp root manually:

```bash
try-cut [--arch ARCH] <package>_<slice>
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

**Write the test suite** at `tests/spread/integration/<package>/task.yaml`:

```yaml
summary: Integration tests for <package>

execute: |
  # Test 1: Basic invocation
  rootfs="$(install-slices <package>_bins)"
  chroot "${rootfs}/" <command> --version

  # Test 2: Core functionality
  # (for curl: fetch a URL; for python3: import core modules; for vim: edit a file)

  # Test 3: Configuration
  # (verify config files are picked up)

  # Test 4: Key features
  # (test primary use cases)
```

**Test design principles**:
- **Test real functionality**, not just file existence. A `bins` slice must prove its binaries actually work.
- **Test each functional slice.** If you have `bins` and `scripts`, both need tests.
- **Test in isolation.** Each test works with only the slices it declares -- no reliance on the host.
- **Every binary in a `bins` slice must be exercised.** Reviewers reject untested binaries.
- **Untestable means unshippable.** Reviewers push to drop rather than ship untested slices.

Run with: `spread lxd:tests/spread/integration/<package>`

### Step 9: Commit

```bash
git -C <repo> commit -m "feat(<pkg>): add <slice-list> slices"
```

Follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `test:`, `ci:`, `chore:`, `docs:`. Subject lowercase, imperative, <=50 chars, no trailing period. Body wrap 72.

**Stop here. User opens PR themselves.**

Reminder: all PRs must be forward-ported oldest -> newest across all maintained release branches.

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

---

## Step 10: Propose a Docs-Alignment Review

After the work is fully complete (SDFs written, tests passing, commit made), **propose to the user** that they review the result against the official chisel documentation. The [chisel-docs](https://github.com/canonical/chisel-docs) are the authoritative source of truth on how to write slices.

Present this to the user:

> The slices are committed. Before opening a PR, I'd recommend we check the result against the official chisel documentation to make sure everything aligns. Want me to fetch the current docs and compare?

If the user accepts, perform the following checks:

### 10a. Validate against chisel-docs (source of truth)

Fetch the current upstream documentation and compare the authored SDFs against it:

```bash
# The authoritative slicing guide
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/how-to/slice-a-package.md

# SDF format reference
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/slice-definitions.md

# chisel.yaml reference (schema version rules)
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/reference/chisel-releases/chisel.yaml.md

# Slice design approaches
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/explanation/slice-design-approaches.md
```

Check and report to the user:
- Does the SDF use any fields or patterns not documented in the official reference?
- Does the slice design approach match documented recommendations?
- Are there new SDF fields, content path options, or `mutate:` functions in the docs that could improve the result?
- Is the `format:` version on the target branch compatible with all features used?

### 10b. Cross-check against existing slices

Compare the output against canonical reference SDFs on the target branch:

```bash
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/bash.yaml
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/<branch>/slices/base-files.yaml
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/main/CONTRIBUTING.md
```

Check and report:
- Does the formatting match established patterns?
- Are naming conventions consistent with existing SDFs?
- Have contribution rules changed since this skill was last updated?

### 10c. Check tool behaviour (if issues arose)

If anything behaved unexpectedly during `chisel cut` (a field was ignored, a wildcard didn't match, mutate ran differently than documented):

```bash
curl -fsSL https://raw.githubusercontent.com/canonical/chisel/main/internal/setup/setup.go
```

The tool's actual behaviour overrides any written convention.

### 10d. Update skill files if needed

If the review found discrepancies between the docs and this skill's guidance, update the relevant file:

- **Factual corrections** (format versions, field names, CLI syntax, arch names) -> update `@./CHISEL.md`
- **Workflow changes** (new inspection steps, changed design recommendations, new testing requirements) -> update this file (`write-slice/SKILL.md`)
- **Review criteria changes** (new CI checks, changed rejection reasons, new style rules) -> update `review-slice/SKILL.md`

When updating, follow these principles:
- **Be specific.** Add the exact rule, the exact field name, the exact formatting.
- **Add context.** Explain _why_ if non-obvious (e.g. "Chisel v1.4.0 added `hint:` validation; using it on v1 branches causes a parse error").
- **Preserve structure.** Add to existing sections; don't create new top-level sections unless the topic is genuinely new.
- **Remove stale content.** Don't leave contradictory information.
