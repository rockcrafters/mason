# Chisel & chisel-releases Reference

Common knowledge for any agent working with [Chisel](https://github.com/canonical/chisel) and [chisel-releases](https://github.com/canonical/chisel-releases).

## What Chisel Is

[Chisel](https://github.com/canonical/chisel) builds minimal Ubuntu root filesystems by extracting named _slices_ of `.deb` packages instead of whole packages. It is a Go tool that consumes a _chisel release_ (from the chisel-releases repo) as its source of truth.

CLI: `chisel cut --release <ref> --root <dir> <pkg>_<slice> ...`

Docs: <https://documentation.ubuntu.com/chisel/en/latest/>

## Slices

A slice is a named subset of files from a single `.deb` package. Slices are defined in **Slice Definition Files (SDFs)** -- YAML files named `<package>.yaml` stored in the `slices/` directory of a chisel-releases branch.

Addressing: `<package_name>_<slice_name>` (underscore separates package from slice; underscores are not allowed in Debian package names). Used in `essential:` lists and `chisel cut` CLI.

## Branch Model

The [chisel-releases](https://github.com/canonical/chisel-releases) repository has one Git branch per Ubuntu release: `ubuntu-XX.XX` (e.g. `ubuntu-22.04`, `ubuntu-24.04`, `ubuntu-26.04`).

- **`main`** is meta-only: CI, workflows, contributing docs. **No `slices/` or `chisel.yaml` on `main`.** Never commit slice work on `main`.
- **All slice work targets a release branch.** Branch off the target release branch, not `main`.
- **EOL branches are frozen** (read-only). Check `maintenance.end-of-life` in `chisel.yaml`.
- **Branch suffix matches `chisel.yaml`'s `archives.ubuntu.version`**: `ubuntu-24.04` <-> `version: 24.04`.

Per-release branch root layout:

```
chisel.yaml                                    # release manifest
slices/<pkg>.yaml                              # one SDF per package
spread.yaml                                    # spread test config
tests/spread/integration/<pkg>/task.yaml       # integration tests
tests/spread/lib/                              # shared spread helpers
.github/                                       # workflows + CI scripts
```

Active branches grow: 24.04 has ~600 SDFs, 26.04 has ~650.

Live release list: repo [README.md](https://github.com/canonical/chisel-releases/blob/main/README.md).

## `chisel.yaml` Schema Versions

| Version | Branches | Min chisel | Key additions |
|---------|----------|------------|---------------|
| **v1** | `ubuntu-20.04`, `-22.04`, `-24.04` | any | Separate `v2-archives:` for pro/esm |
| **v2** | `ubuntu-25.10` | >= v1.2.0 | Pro archives unified under `archives:` via `pro:` subkey. Adds `prefer:` |
| **v3** | `ubuntu-26.04` | >= v1.4.0 | Adds `hint:` on slices. `essential:` **must** be a map (`<slice>:` / `<slice>: {arch: ...}`) -- the list form is a parse error, and `v3-essential:` is rejected |

(`v3-essential:` -- the arch-gated backport -- is gated by chisel version, >= 1.3.0, not by format; it is valid on v1 and v2 branches alike.)

Key fields: `format:` (gates available features), `archives.ubuntu.suites[0]` (codename, e.g. `noble`), `archives.ubuntu.version` (mirrors branch suffix), `maintenance.end-of-life` (date).

**Always check `format:` in `chisel.yaml` before using version-gated features.** Writing `hint:` against a v1 branch or `prefer:` against a v1 branch produces invalid SDFs.

## SDF Format Reference

### Top-level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `package` | string | Required | Deb package name; **must match filename stem** (`slices/foo.yaml` -> `package: foo`) |
| `archive` | string | Optional | Selects archive from `chisel.yaml`'s `archives:`. Omit for default |
| `essential` | list (v1/v2) / map (v3) of `<pkg>_<slice>` | Optional | Applied to **every** slice in the file. Typically `<pkg>_copyright` |
| `slices` | map name -> body | Required | The slice definitions |

### Per-slice Keys

| Key | Type | Description |
|-----|------|-------------|
| `essential` | list (v1/v2) / map (v3) of `<pkg>_<slice>` | Cross-package dependencies |
| `contents` | map path -> entry options | Paths this slice installs. **Paths must be lexicographically sorted** |
| `mutate` | string (Starlark) | Mutation script run after all slices installed |
| `hint` | string, <= 40 chars | v3+ only. Length + printable-chars enforced by chisel core (parse error since v1.4.0); the noun-phrase _style_ is checked by `validate-hints` CI. Shown in `chisel find`/`info` output |

### Content Path Entry Options

| Key | Type | Description |
|-----|------|-------------|
| _(bare path)_ | -- | Extract from deb at this path |
| `copy` | string | Copy from different source path in deb |
| `make` | bool | Create empty directory; path must end with `/` |
| `mode` | int (octal) | Permission bits, e.g. `0755` |
| `text` | string | Inline literal file contents |
| `symlink` | string | Create symlink to this target |
| `arch` | string or list | Restrict to architectures: `amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x` |
| `mutable` | bool | Path may be modified by `mutate:` |
| `until` | `"mutate"` | Available during install; removed after mutate phase |
| `generate` | `"manifest"` | Path must be a directory glob ending `/**` (no other wildcards, no other options); chisel writes the manifest inside it |
| `prefer` | string, **v2+** | Resolve cross-package path conflicts. Value = name of **another** package in the release that also declares the path (that package wins); not your own package, not usable on globs |

### Wildcard Patterns

- `?` -- any single character except `/`
- `*` -- zero or more characters except `/`
- `**` -- zero or more characters including `/`

Wildcard paths accept only `until:` and `arch:` as entry options -- combining a glob with `copy`/`make`/`text`/`symlink`/`mode`/`mutable`/`prefer` is a parse error. Name the path explicitly instead.

### `mutate:` Semantics

- Written in [Starlark](https://github.com/google/starlark-go) (Google's restricted Python dialect; no imports, no exceptions, restricted stdlib). **Not Python.**
- Runs **once** after all slices in the install set are placed.
- Helpers: `content.list(d)`, `content.read(f)`, `content.write(f, s)`.
- Used for: merging passwd/group, filtering CA certs, splicing apt sources, etc.
- For merging/transforming existing files -- **not synthesis**. If a binary needs file `F`, ship `F` from the deb.
- `until: mutate` partner: file available to the script, deleted post-mutate.

### Arch-gated essentials

Some deps only apply on certain arches. How you express that depends on `format:`:

- **v1 / v2** -- backport via a parallel `v3-essential:` map alongside the flat `essential:` list (needs chisel >= 1.3.0):

  ```yaml
  v3-essential:
    dotnet-sdk-aot-10.0_libs: {arch: [amd64, arm64]}
  ```

- **v3** -- native: `essential:` itself **must** be a map (the list form is a chisel parse error: _"essential expects a map"_). Entries without arch gating are bare map keys; `{arch: ...}` values only where gated. `v3-essential:` is **rejected** on v3 (parse error) -- when forward-porting to a v3 branch, fold its entries into the `essential:` map.

  ```yaml
  essential:
    libc6_libs:
    dotnet-sdk-aot-10.0_libs: {arch: [amd64, arm64]}
  ```

Every SDF on `ubuntu-26.04` uses the map form, arch-gated or not -- there is no list-form `essential:` on a v3 branch.

### `hint:` style (v3+)

Optional one-line description of what a slice provides. Chisel caps it at 40 chars; the `validate-hints` CI check (spaCy) also enforces the style below. A hint is a **noun phrase**, not a sentence:

- sentence case: first letter uppercase.
- no finite verbs -- phrase as a noun fragment, not "Manages X" / "Views Y".
- no leading article (`a` / `an` / `the`).
- allowed chars only: letters, digits, spaces, and `. , ; ( )`. Separate fragments with `;`.
- no trailing punctuation or space; no double spaces.

e.g. `hint: System log viewer` (not `hint: Views system logs`).

### Manifest & Pro Archives

- **Manifest**: convention is `base-files_chisel` declaring `/var/lib/chisel/**: {generate: manifest}`, which makes chisel produce `/var/lib/chisel/manifest.wall`. Only touch when slicing `base-files`.
- **Pro slices**: SDF has `archive: <name>` -> `pro:`-tagged archive in `chisel.yaml` (`fips`, `fips-updates`, `esm-apps`, `esm-infra`).

## Chisel CLI

```bash
chisel cut --release <ref> --root <dir> [--arch <a>] <pkg>_<slice> ...   # materialise rootfs
chisel find <pattern>                                                     # search slices
chisel info <pkg>_<slice>                                                 # inspect slice
chisel debug check-release-archives --release <ref>                       # download all pkgs, report cross-package path conflicts
```

`--release`: `ubuntu-XX.XX` (online branch), a directory path -- anything containing a `/`, e.g. `./` for the current checkout -- or omit (host `/etc/os-release`). On a devel (unstable) or EOL (unmaintained) branch, add `--ignore=unstable` / `--ignore=unmaintained` or `cut` errors out.

## Inspecting the Repo Without a Full Checkout

```bash
# List live release branches
git ls-remote --heads https://github.com/canonical/chisel-releases.git 'ubuntu-*' \
  | awk '{print $2}' | sed 's|refs/heads/||'

# Read release manifest
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/ubuntu-24.04/chisel.yaml

# Read an SDF
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/ubuntu-24.04/slices/bash.yaml

# Sparse clone (slices + chisel.yaml only)
git clone --filter=blob:none --no-checkout --depth 1 \
  -b ubuntu-24.04 https://github.com/canonical/chisel-releases.git /tmp/cr
git -C /tmp/cr sparse-checkout set slices chisel.yaml
git -C /tmp/cr checkout

# Diff slice between releases
git -C <repo> diff ubuntu-22.04:slices/coreutils.yaml ubuntu-24.04:slices/coreutils.yaml
```

## Canonical Slice Names

Names are convention but reviewers enforce them. Use:

| Name | Contents |
|------|----------|
| `bins` | Executables (plural; use `bins` not `bin`). The singular `bin` is essentially only correct in `base-files`, whose `bin` slice builds the `/bin` directory tree, not executables |
| `libs` | Shared libraries (plural; use `libs` not `lib`). Same `base-files` `lib` exception -- it makes the `/lib` tree |
| `config` / `configs` | Configuration files. Break large configs into `<purpose>-config` (e.g. `modprobe-config`, `tmpfiles-config`, `pam-config`) |
| `scripts` | Shell helpers / non-binary executables. Not in `bins` |
| `data` | Static data (locales, templates, fonts) |
| `headers` | `/usr/include/...` |
| `jars` | JVM artefacts |
| `copyright` | Deb copyright file |
| `license` / `notice` | Upstream licence/notice (**not** deb copyright). Depends on `<pkg>_copyright` |
| `core` | Minimum-functional subset. **Not "everything"**. Avoid `all` except a rare umbrella-aggregate slice (e.g. `fonts-ubuntu` ships every font under `all`) |
| `standard` | Fuller-featured above `core` |
| `var` | Directories/files under `/var/` |
| `services` | Systemd service files |
| `modules` | Loadable modules/plugins |
| `locales` | Translation/locale files |
| `tables` | Static data tables (e.g. `dpkg_tables` ships `/usr/share/dpkg/*table`) |
| `chisel` | The generated manifest slice; only on `base-files` (`generate: manifest`) |
| `rules` | udev / polkit rules (e.g. `/usr/lib/udev/rules.d/*.rules`) |
| `dev` | Development files (headers + `.so` dev symlinks) in the by-function layout |

When the deb already names `<pkg>-core` (e.g. `fonts-dejavu-core`), keep the name verbatim.

## Exclude by Default

A `.deb` ships files a minimal rootfs never needs. Do **not** slice these unless a concrete runtime need is proven -- reviewers reject them, and `check-slice.py` (and the eval) flag them:

| Excluded | Paths | Notes |
|----------|-------|-------|
| **man pages** | `/usr/share/man/`, `/usr/man/` | never shipped |
| **shell completions** | `/usr/share/bash-completion/`, `/usr/share/fish/`, `/usr/share/zsh/`, `/etc/bash_completion.d/` | never shipped |
| **docs / changelogs** | `/usr/share/doc/**` | **except** the legal files below |
| **doc-base / lintian** | `/usr/share/doc-base/`, `/usr/share/lintian/` | packaging metadata, not runtime |
| **examples** | `/usr/share/doc/*/examples/`, `.../example*` | covered by the doc rule above |

Under `/usr/share/doc/<pkg>/`, ship only legal files: `copyright` always, and the upstream legal notices (`NOTICE`, `LICENSE`, `COPYING`, `AUTHORS`, with `.txt`/`.gz` variants) where the package carries them for licence compliance -- apache2, aspnetcore, and libaprutil1t64 do. Everything else there (README, changelog, NEWS, examples) is clutter. Shared-copyright packages instead ship `/usr/share/doc/<pkg>` itself as a symlink to another package's doc dir (gcc/cpp/binutils families); that bare entry is also fine.

## Debian Architecture Names

Always use Debian arch names in `arch:` fields: `amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x`. **Not** `x86_64`/`aarch64`.

## Multiarch Quirks

- **`binutils-common` per-arch** despite `Architecture: all`-looking contents. Don't assume one SDF covers all arches without checking.
- **Cross-toolchain packages** (`<tool>-<triple>-linux-gnu`, e.g. `binutils-aarch64-linux-gnu`) ship prefixed binaries (`aarch64-linux-gnu-ld`). Unprefixed symlinks (`/usr/bin/ld -> aarch64-linux-gnu-ld`) are **not** in the cross deb -- consumers create them. Convention: arch-specific SDFs leave them out; top-level `binutils` SDF carries the unprefixed name with a `# Symlink to ${ARCH_TRIPLET}-ld` comment.
- **`/proc/self/exe` workaround** for chroot Java tests (chroot breaks `/proc/self/exe`, which the JVM launcher reads): inside the rootfs, `mkdir -p "${rootfs}/proc/self" && ln -sf <path-to-java-binary> "${rootfs}/proc/self/exe"` -- see the openjdk `task.yaml` files for the convention.

## Cross-Release Differences

SDFs for the same package differ across Ubuntu release branches. Forward-porting is **adaptation, not copy-paste**. Always run `deb-list.py` against each target release and verify actual `.deb` contents.

| Category | Example | What changes |
|----------|---------|-------------|
| **usrmerge** | `/bin/bash` -> `/usr/bin/bash` | Ubuntu 24.04+ moved binaries from `/bin/` to `/usr/bin/`. Update `contents` paths per release |
| **t64 transition** | `libssl3` -> `libssl3t64` | Ubuntu 24.04+ renamed libraries for 64-bit `time_t`. Update `essential` deps and copyright refs |
| **Package splits/renames** | Transitional packages, new soname packages | May need entirely different SDF structure or filename |
| **Soname bumps** | `librocksdb9.11` -> `librocksdb10` | Old SDF deleted (archive no longer carries it); new SDF with new filename |
| **Essential syntax** | List (`- foo_bar`) vs map (`foo_bar:`) | v3 branches **must** use map syntax in `essential:` (list form is a parse error); v1/v2 use the list |
| **Slice granularity** | `bashbug` inline in `bins` (24.04) vs separate `bashbug` slice (26.04) | Newer releases may demand finer-grained decomposition |
| **New/removed files** | New config files, removed scripts | `.deb` contents change between releases. Some paths exist in one release but not another |
| **Dependency changes** | New deps added, old deps dropped | `Depends:` may differ. Always re-check with `deb-list.py` or `apt-cache depends` |

## Spread Test Infrastructure

Integration tests in chisel-releases use [spread](https://github.com/canonical/spread) to validate slices inside ephemeral containers.

### Layout

```
spread.yaml                                         # project config (backends, global prepare)
tests/spread/integration/<pkg>/task.yaml            # per-package test
tests/spread/lib/                                   # shared helpers (on PATH via spread.yaml)
```

### `install-slices` helper

Located at `tests/spread/lib/install-slices`. Added to `PATH` by `spread.yaml`. Usage:

```bash
rootfs="$(install-slices <pkg>_<slice> [<pkg2>_<slice2> ...])"
```

What it does:
1. Creates a temporary directory for the rootfs.
2. Runs `chisel cut --ignore=unstable --ignore=unmaintained --release "$PROJECT_PATH" --root "$rootfs" $slices` -- validates against the **local checkout**.
3. Automatically appends `base-files_chisel` to every cut (for manifest generation). You do not need to include it.
4. Retries on transient archive fetch failures (up to 3 attempts).
5. Prints the rootfs path to stdout.

NOTE: the `--ignore` flags mean install-slices succeeds on devel/EOL branches where a bare manual `chisel cut` errors -- pass them yourself when testing manually on such a branch.

### Two-layer testing model

- **Layer 1 -- installability**: `chisel cut` succeeds. The SDF parses, dependencies resolve, files extract. This is what the `install-slices` CI check validates.
- **Layer 2 -- functionality**: `chroot` + commands prove the sliced rootfs actually works. This is what spread tests validate.

Both layers are required. A slice that installs but doesn't function is rejected.

### Chroot environment patterns

Sliced rootfs is minimal. Tests that need more than bare files must set up the chroot:

| Need | Pattern |
|------|---------|
| Network (DNS) | `cp /etc/resolv.conf "${rootfs}/etc/"` |
| `/dev/null` | `mkdir -p "${rootfs}/dev" && touch "${rootfs}/dev/null"` |
| `/bin/sh` | `ln "${rootfs}/bin/bash" "${rootfs}/bin/sh"` (or whichever shell is available) |
| `/proc/self/exe` (Java) | `mkdir -p "${rootfs}/proc/self" && ln -sf <java-binary> "${rootfs}/proc/self/exe"` (see openjdk task.yaml) |

### Backends

`spread.yaml` configures two backends:

- **lxd** -- default for local development. Ephemeral LXC containers.
- **docker** -- used in CI for multi-arch testing: `amd64`, `arm64`, `armhf`, `ppc64el`, `s390x`, `riscv64`.

## Sources of Truth

The knowledge in this file and the associated skills is derived from three upstream projects. When in doubt, **always defer to these sources** over anything written here.

### 1. `canonical/chisel` (tool behaviour)

The Go source code defines what chisel actually does: how it parses SDFs, resolves dependencies, extracts files, runs mutate scripts, handles wildcards, and validates fields. The tool's behaviour is the ultimate arbiter of what is valid.

- Repo: <https://github.com/canonical/chisel>
- Key paths: `internal/setup/` (SDF parsing), `internal/slicer/` (slice cutting logic)

### 2. `canonical/chisel-docs` (official documentation)

The documentation source renders to <https://documentation.ubuntu.com/chisel/en/latest/>. It is the authoritative reference for SDF format, CLI usage, and slicing workflows.

- Repo: <https://github.com/canonical/chisel-docs>
- Raw page access pattern: `https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/<path>.md`; rendered at `https://documentation.ubuntu.com/chisel/latest/<path>/`
- Key pages:
  - `how-to/slice-a-package.md` -- canonical slicing workflow
  - `reference/chisel-releases/slice-definitions.md` -- SDF format specification
  - `reference/chisel-releases/chisel.yaml.md` -- release config schema (format versions, archives, maintenance)
  - `explanation/slice-design-approaches.md` -- grouping-by-content vs grouping-by-function
  - `explanation/slices.md` -- conceptual overview of slices
  - `reference/cmd/cut.md` -- `chisel cut` CLI reference
  - `reference/manifest.md` -- manifest format
  - `how-to/install-pro-package-slices.md` -- pro slices

### 3. `canonical/chisel-releases` (existing slices & conventions)

The collection of published SDFs is the ground truth for conventions, naming patterns, and reviewer expectations. Studying real SDFs is more reliable than any written convention doc.

- Repo: <https://github.com/canonical/chisel-releases>
- Key files on each release branch: `chisel.yaml`, `slices/bash.yaml`, `slices/base-files.yaml`, `CONTRIBUTING.md`
- `README.md` on `main` carries the live release-branch list
- CI workflows in `.github/` define the automated checks

Also: chisel-releases navigator <https://canonical.github.io/chisel-releases-navigator/>; Ubuntu release schedule <https://wiki.ubuntu.com/Releases>.

### Precedence

When sources conflict: **tool behaviour > chisel-docs > chisel-releases conventions > this file**.

---

When this document disagrees with the repo, trust the repo. When in doubt, read `slices/bash.yaml` or `slices/base-files.yaml` on the target release branch.
