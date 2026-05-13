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
| **v3** | `ubuntu-26.04` | >= v1.4.0 | Adds `hint:` on slices + `v3-essential:` for arch-gated deps |

Key fields: `format:` (gates available features), `archives.ubuntu.suites[0]` (codename, e.g. `noble`), `archives.ubuntu.version` (mirrors branch suffix), `maintenance.end-of-life` (date).

**Always check `format:` in `chisel.yaml` before using version-gated features.** Writing `hint:` against a v1 branch or `prefer:` against a v1 branch produces invalid SDFs.

## SDF Format Reference

### Top-level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `package` | string | Required | Deb package name; **must match filename stem** (`slices/foo.yaml` -> `package: foo`) |
| `archive` | string | Optional | Selects archive from `chisel.yaml`'s `archives:`. Omit for default |
| `essential` | list of `<pkg>_<slice>` | Optional | Applied to **every** slice in the file. Typically `<pkg>_copyright` |
| `slices` | map name -> body | Required | The slice definitions |

### Per-slice Keys

| Key | Type | Description |
|-----|------|-------------|
| `essential` | list of `<pkg>_<slice>` | Cross-package dependencies |
| `contents` | map path -> entry options | Paths this slice installs. **Paths must be lexicographically sorted** |
| `mutate` | string (Starlark) | Mutation script run after all slices installed |
| `hint` | string, max 40 chars | v3+ only. Validated by `validate-hints` CI |

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
| `generate` | `"manifest"` | Chisel writes manifest at this path |
| `prefer` | string, **v2+** | Resolve cross-package path conflicts |

### Wildcard Patterns

- `?` -- any single character except `/`
- `*` -- zero or more characters except `/`
- `**` -- zero or more characters including `/`

### `mutate:` Semantics

- Written in [Starlark](https://github.com/google/starlark-go) (Google's restricted Python dialect; no imports, no exceptions, restricted stdlib). **Not Python.**
- Runs **once** after all slices in the install set are placed.
- Helpers: `content.list(d)`, `content.read(f)`, `content.write(f, s)`.
- Used for: merging passwd/group, filtering CA certs, splicing apt sources, etc.
- For merging/transforming existing files -- **not synthesis**. If a binary needs file `F`, ship `F` from the deb.
- `until: mutate` partner: file available to the script, deleted post-mutate.

### `v3-essential:` (v3+ only)

Parallel map alongside `essential:`. Provides arch-gated cross-package deps:

```yaml
v3-essential:
  dotnet-sdk-aot-10.0_libs: {arch: [amd64, arm64]}
```

Regular `essential:` stays a flat string list. Only `v3-essential:` accepts per-entry options (currently just `arch:`).

### Manifest & Pro Archives

- **Manifest**: emit at any path declared `generate: manifest`. Convention: `base-files_chisel` writes `/var/lib/chisel/manifest.wall`. Only touch when slicing `base-files`.
- **Pro slices**: SDF has `archive: <name>` -> `pro:`-tagged archive in `chisel.yaml` (`fips`, `fips-updates`, `esm-apps`, `esm-infra`).

## Chisel CLI

```bash
chisel cut --release <ref> --root <dir> [--arch <a>] <pkg>_<slice> ...   # materialise rootfs
chisel find <pattern>                                                     # search slices
chisel info <pkg>_<slice>                                                 # inspect slice
```

`--release`: `ubuntu-XX.XX` (online branch), absolute path (local checkout), or omit (host `/etc/os-release`).

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
| `bins` | Executables (plural; **never** `bin`) |
| `libs` | Shared libraries (plural; **never** `lib`) |
| `config` / `configs` | Configuration files. Break large configs into `<purpose>-config` (e.g. `modprobe-config`, `tmpfiles-config`, `pam-config`) |
| `scripts` | Shell helpers / non-binary executables. Not in `bins` |
| `data` | Static data (locales, templates, fonts) |
| `headers` | `/usr/include/...` |
| `jars` | JVM artefacts |
| `copyright` | Deb copyright file |
| `license` / `notice` | Upstream licence/notice (**not** deb copyright). Depends on `<pkg>_copyright` |
| `core` | Minimum-functional subset. **Not "everything"**. Avoid `all` (rejected) |
| `standard` | Fuller-featured above `core` |
| `var` | Directories/files under `/var/` |
| `services` | Systemd service files |
| `modules` | Loadable modules/plugins |
| `locales` | Translation/locale files |

When the deb already names `<pkg>-core` (e.g. `git-core`), keep the name verbatim.

## Debian Architecture Names

Always use Debian arch names in `arch:` fields: `amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x`. **Not** `x86_64`/`aarch64`.

## Multiarch Quirks

- **`binutils-common` per-arch** despite `Architecture: all`-looking contents. Don't assume one SDF covers all arches without checking.
- **Cross-toolchain packages** (`<tool>-<triple>-linux-gnu`, e.g. `binutils-aarch64-linux-gnu`) ship prefixed binaries (`aarch64-linux-gnu-ld`). Unprefixed symlinks (`/usr/bin/ld -> aarch64-linux-gnu-ld`) are **not** in the cross deb -- consumers create them. Convention: arch-specific SDFs leave them out; top-level `binutils` SDF carries the unprefixed name with a `# -> ${ARCH_TRIPLET}-ld` comment.
- **`/proc/self/exe` linker workaround** for chroot Java tests: `tests/spread/lib/link-proc`. Needed because chroot breaks `/proc/self/exe`.

## Sources of Truth

The knowledge in this file and the associated skills is derived from three upstream projects. When in doubt, **always defer to these sources** over anything written here.

### 1. `canonical/chisel` (tool behaviour)

The Go source code defines what chisel actually does: how it parses SDFs, resolves dependencies, extracts files, runs mutate scripts, handles wildcards, and validates fields. The tool's behaviour is the ultimate arbiter of what is valid.

- Repo: <https://github.com/canonical/chisel>
- Key paths: `internal/setup/` (SDF parsing), `internal/slicer/` (slice cutting logic)

### 2. `canonical/chisel-docs` (official documentation)

The documentation source renders to <https://documentation.ubuntu.com/chisel/en/latest/>. It is the authoritative reference for SDF format, CLI usage, and slicing workflows.

- Repo: <https://github.com/canonical/chisel-docs>
- Raw page access pattern: `https://raw.githubusercontent.com/canonical/chisel-docs/main/docs/<path>.md`
- Key pages:
  - `how-to/slice-a-package.md` -- canonical slicing workflow
  - `reference/chisel-releases/slice-definitions.md` -- SDF format specification
  - `reference/chisel-releases/chisel.yaml.md` -- release config schema (format versions, archives, maintenance)
  - `explanation/slice-design-approaches.md` -- grouping-by-content vs grouping-by-function
  - `explanation/slices.md` -- conceptual overview of slices
  - `reference/cmd/cut.md` -- `chisel cut` CLI reference

### 3. `canonical/chisel-releases` (existing slices & conventions)

The collection of published SDFs is the ground truth for conventions, naming patterns, and reviewer expectations. Studying real SDFs is more reliable than any written convention doc.

- Repo: <https://github.com/canonical/chisel-releases>
- Key files on each release branch: `chisel.yaml`, `slices/bash.yaml`, `slices/base-files.yaml`, `CONTRIBUTING.md`
- CI workflows in `.github/` define the automated checks

### Precedence

When sources conflict: **tool behaviour > chisel-docs > chisel-releases conventions > this file**.

## External References

- Chisel source: <https://github.com/canonical/chisel>
- Chisel docs: <https://documentation.ubuntu.com/chisel/latest/>
  - How-to slice a package: <https://documentation.ubuntu.com/chisel/latest/how-to/slice-a-package/>
  - SDF reference: <https://documentation.ubuntu.com/chisel/latest/reference/chisel-releases/slice-definitions/>
  - `chisel.yaml` reference: <https://documentation.ubuntu.com/chisel/latest/reference/chisel-releases/chisel.yaml/>
  - Manifest reference: <https://documentation.ubuntu.com/chisel/latest/reference/manifest/>
  - `cut` CLI reference: <https://documentation.ubuntu.com/chisel/latest/reference/cmd/cut/>
  - Pro slices how-to: <https://documentation.ubuntu.com/chisel/latest/how-to/install-pro-package-slices/>
- chisel-releases repo: <https://github.com/canonical/chisel-releases>
  - `CONTRIBUTING.md`: <https://github.com/canonical/chisel-releases/blob/main/CONTRIBUTING.md>
  - `README.md` (live release list): <https://github.com/canonical/chisel-releases/blob/main/README.md>
- chisel-releases navigator: <https://canonical.github.io/chisel-releases-navigator/>
- Ubuntu release schedule: <https://wiki.ubuntu.com/Releases>

---

When this document disagrees with the repo, trust the repo. When in doubt, read `slices/bash.yaml` or `slices/base-files.yaml` on the target release branch.
