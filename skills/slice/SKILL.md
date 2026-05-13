---
name: slice
description: >
  Author chisel slice definition files (sdfs) for canonical/chisel-releases.
  Covers branch model, chisel.yaml schema versions (v1/v2/v3), sdf keys,
  content path options, mutate/starlark semantics, reviewer conventions,
  ci checks, forward-port chains, and multiarch quirks. Does NOT open PRs --
  stops at local commits; user opens PR themselves.
  Use when user says "add slice", "chisel slice", "slice <pkg>",
  or works inside a `canonical/chisel-releases` checkout.
---

Briefing for authoring slices against [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases). **Scope: author + commit slices locally. Do NOT open PRs -- user opens PR themselves.** When this doc and the repo disagree, trust the repo. Read `slices/bash.yaml` / `slices/base-files.yaml` on target branch as canonical reference.

## What chisel is

[chisel](https://github.com/canonical/chisel) builds minimal ubuntu rootfs by extracting named _slices_ of debs instead of whole packages. Go tool. Consumes _chisel release_ (this repo) as source of truth. CLI: `chisel cut --release <ref> --root <dir> <pkg>_<slice> ...`. Docs: <https://documentation.ubuntu.com/chisel/en/latest/>.

## Branch model

One git branch per ubuntu release: `ubuntu-XX.XX` (`ubuntu-22.04`, `-24.04`, `-25.10`, `-26.04`). `main` meta-only -- ci, workflows, contributing docs; **no `slices/` or `chisel.yaml` on `main`**. All slice work targets release branch. EOL branches frozen. Active branches grow: 24.04 ~600 sdfs, 26.04 ~650.

Per-release branch root:

- `chisel.yaml` -- release manifest.
- `slices/<pkg>.yaml` -- one per debian source package.
- `spread.yaml` + `tests/spread/integration/<pkg>/{task.yaml,smoke.sh}` -- integration tests.
- `tests/spread/lib/` -- shared spread helpers.
- `.github/` -- workflows + ci scripts (synced from `main`).

Live release list: repo `README.md`.

## `chisel.yaml` schema versions

- **v1** -- `ubuntu-20.04`, `-22.04`, `-24.04`. Separate `v2-archives:` block for pro/esm.
- **v2** -- `ubuntu-25.10`. Needs chisel >= `v1.2.0`. Pro archives unified under `archives:` via `pro:` subkey. Adds `prefer:`.
- **v3** -- `ubuntu-26.04`. Needs chisel >= `v1.4.0`. Adds `hint:` on slices + `v3-essential:` block.

Key fields: `format:` (gates features), `archives.ubuntu.suites[0]` (codename, e.g. `noble`), `archives.ubuntu.version` (mirrors branch suffix), `maintenance.end-of-life` (date; eol = read-only).

## SDF top-level keys

- `package` -- required, string. Deb package name; **must match filename stem**.
- `archive` -- optional. Selects archive from `chisel.yaml`'s `archives:`. Omit for default.
- `essential` -- optional, list of `<pkg>_<slice>` applied to **every** slice in file. Typically `<pkg>_copyright`.
- `slices` -- required, map name -> body.

## Per-slice keys

- `essential` -- list of `<pkg>_<slice>` deps (cross-package ok).
- `contents` -- map path -> entry options. **Paths lexicographically sorted.**
- `mutate` -- starlark script run after every slice installed.
- `hint` -- v3+ only, max 40 chars, validated by `validate-hints` ci.

## Content path entry options

| key | type | meaning |
|---|---|---|
| (bare path) | -- | copy from deb at this path |
| `copy` | string | copy from different source path in deb |
| `make` | bool | create empty dir; requires trailing `/` |
| `mode` | int (octal) | permission bits, e.g. `0755` |
| `text` | string | inline literal file contents |
| `symlink` | string | create symlink to this target |
| `arch` | string or list | restrict to `amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x` |
| `mutable` | bool | path may be modified by `mutate:` |
| `until` | `"mutate"` | available during install; chisel removes after mutate phase |
| `generate` | `"manifest"` | chisel writes manifest at this path |
| `prefer` | string, **v2+** | resolve cross-package path conflicts |

## `mutate:` semantics

- Starlark (google's restricted python dialect; no imports, no exceptions, restricted stdlib).
- Runs **once** after all slices in install set placed. Not per-slice. Don't assume execution order.
- Helpers: `content.list(d)`, `content.read(f)`, `content.write(f, s)`.
- Use: merge passwd/group, filter ca certs, splice apt sources, etc.
- For merging / transforming files that exist -- **not synthesis**. If binary needs `F`, ship `F` from deb.
- `until: mutate` partner: file available to script, deleted post-mutate. Collision: if needed at runtime too, can't drop -- use two paths or restructure.

## Addressing & conventions

- **`<pkg>_<slice>`** -- canonical full id. Used in `essential:` and `chisel cut` cli.
- **`copyright` slice** -- nearly every pkg has one. Ships `/usr/share/doc/<pkg>/copyright`. Listed in file-level `essential:` so all slices transitively ship it. **Upstream `LICENSE.txt` / `NOTICE` / `ThirdPartyNotices.txt` != copyright** -- separate `license:` / `notice:` slice depending on `<pkg>_copyright`.
- **Filename rule** -- `slices/<pkg>.yaml` stem == `package:` field.
- **Path sort** -- bytewise ascii sort in `contents:`. Reviewers reject unsorted.
- **Slice design** -- group by content type (`bins`, `config`, `libs`) OR by functional use case. Don't mix arbitrarily.

## Canonical slice names (reviewer preference)

Names are convention but reviewers re-classify aggressively. Use:

- `bins` -- executables (plural; never `bin`).
- `libs` -- shared libs (plural; never `lib`).
- `headers` -- `/usr/include/...`.
- `config` / `configs` -- conf files. Break large `config` into `<purpose>-config`: `modprobe-config`, `tmpfiles-config`, `pam-config`, `kernel-parameters`, `system-users`.
- `scripts` -- shell helpers / non-binary executables. Not in `bins`.
- `data` -- static data (locales, templates, fonts).
- `jars` -- jvm artefacts.
- `copyright` -- deb copyright file.
- `license` / `notice` -- upstream licence/notice (not deb copyright).
- `core` -- minimum-functional subset. **Not "everything"**. Avoid `all` (rejected).
- `standard` -- fuller-featured above `core`.
- When deb already names `<pkg>-core` (e.g. `git-core`), keep verbatim.

## Dependency rules

- **Stay true to deb's declared deps.** List each direct apt `Depends:` as `essential:`. Reviewers cross-check via `pkg-deps` ci.
- **`Depends:` only** -- not `Recommends:`/`Suggests:`. Including `Recommends:` rejected.
- **Maintainer postinst not mirrored.** If upstream postinst invokes another pkg's tool (e.g. `update-mime-database`), either drop dep or write `mutate:` equivalent.
- **Only slices we need.** Speculative slices rejected.
- **Published slices append-only in spirit.** Removing files from existing slice = regression. Create variant (`<existing>-only`, stricter `core`).
- **Use-case-agnostic.** Comments like _"this slice exists for app X"_ rejected. Describe what it ships.

## Path entry style nits

- **Multiarch lib glob**: `*-linux-*`, not explicit triple. e.g. `/usr/lib/*-linux-*/libnghttp2.so.14*:`.
- **Drop trailing `*` if one version**: `libfoo.so.1:` not `libfoo.so.1*:`.
- **No explicit `symlink:` if deb ships it.** Chisel preserves deb symlinks. Manual `symlink:` only for paths deb doesn't ship.
- **Annotate explicit symlinks**: `/usr/bin/dotnet:  # Symlink to ../lib/dotnet/dotnet`.
- **Inline-style for short options**: `/path: {arch: [amd64, arm64]}`.
- **Arch list formatting rigid**: lowercase, alphabetical, no inner spaces. `[amd64, arm64, ppc64el, riscv64, s390x]` -- single space after commas, no padding. `[ amd64, ... s390x ]` rejected.

## `v3-essential:` (v3+)

Parallel map alongside `essential:`. Arch-gated cross-package deps:

```yaml
v3-essential:
  dotnet-sdk-aot-10.0_libs: {arch: [amd64, arm64]}
```

Regular `essential:` stays flat string list. Only `v3-essential:` accepts per-entry options (currently just `arch:`).

Historical bug: malformed `essential:` entries (typoed id) silently dropped. Patched upstream; older chisel may misbehave.

## Chisel cli

- `chisel cut --release <ref> --root <dir> [--arch <a>] <pkg>_<slice> ...` -- materialise rootfs.
- `chisel find <pattern>` -- search slices.
- `chisel info <pkg>_<slice>` -- inspect slice.

`--release`: `ubuntu-XX.XX` (online branch), absolute path (local checkout), or omit (host `/etc/os-release`).

## Manifest, pro archives

- **Manifest** -- emit at any path declared `generate: manifest`. Convention: `base-files_chisel` writes `/var/lib/chisel/manifest.wall` (jsonwall, zstd). Touch only when slicing `base-files`.
- **Pro slices** -- sdf has `archive: <name>` -> `pro:`-tagged archive in `chisel.yaml` (`fips`, `fips-updates`, `esm-apps`, `esm-infra`). Most lts branches wired; `ubuntu-26.04` not yet.

## Contribution rules

Defer to [`CONTRIBUTING.md` on `main`](https://github.com/canonical/chisel-releases/blob/main/CONTRIBUTING.md). Key points:

- **Branch off target release branch, not `main`.** PRs into `main` wrong.
- **Conventional commits**: `feat:`, `fix:`, `test:`, `ci:`, `chore:`, `docs:`, `refactor:`. Subject lowercase, imperative, <=50 chars, no trailing period. Body wrap 72.
- **Two maintainer approvals**, cla signed, green ci before review, no force-push after review comments, one cohesive change per pr.

Extras not in CONTRIBUTING:

- **Forward-port to every newer live release.** PR chain oldest -> newest. `forward-port-missing` ci auto-labels prs missing this. Exception: pkg gone from newer archive -- auto-ignored.
- **Two-approval exception**: trivial forward-port prs (cherry-picks of approved breaking changes) sometimes land on one approval. Don't rely on it for substantive work.
- Non-forward-port prs: mark with `### Forward porting\nn/a` in description.

## CI checks

| check | failure means |
|---|---|
| `lint` | yaml syntax/formatting issue in sdf |
| `install-slices` | slice can't `chisel cut`, or pkg not in archive for some arch |
| `removed-slices` | sdf deleted -- breaking unless pkg gone from archive |
| `forward-port-missing` | new slice in branch but not in newer live releases |
| `pkg-deps` | informational diff declared deps vs `apt depends`; non-blocking |
| `validate-hints` | `hint:` text fails nlp style check (v3+) |
| `spread` | smoke test failed inside lxd test container |
| `cla-check` | cla unsigned |

Heads-up: github copilot auto-reviews and proposes patterns reviewers reject (inner-spaced arch lists, `: {}` on essentials). Don't follow blindly.

## Multiarch quirks

- **`binutils-common` per-arch** despite `Architecture: all`-looking contents. Don't assume one sdf covers all arches.
- **Cross-toolchain pkgs** (`<tool>-<triple>-linux-gnu`, e.g. `binutils-aarch64-linux-gnu`) ship prefixed binaries (`aarch64-linux-gnu-ld`). Unprefixed symlinks (`/usr/bin/ld -> aarch64-linux-gnu-ld`) **not** in cross deb -- consumers create them. Convention: arch-specific sdfs leave them out; top-level `binutils` sdf carries unprefixed name with `# -> ${ARCH_TRIPLET}-ld` comment.
- **`/proc/self/exe` linker workaround** for chroot java tests: `tests/spread/lib/link-proc`. Needed because chroot breaks `/proc/self/exe`.

## Testing model

Local:

1. Checkout release branch.
2. Install `chisel` cli (binary or `go install github.com/canonical/chisel/cmd/chisel@latest`).
3. `chisel cut --release . --root /tmp/test-rootfs <pkg>_<slice>`.
4. Exercise: `chroot /tmp/test-rootfs <cmd> --version` etc.

Integration tests: `tests/spread/integration/<pkg>/` with `task.yaml` (spread task: `summary`, `prepare`, `execute`) + `smoke.sh`. Run under spread with lxd backend (`spread.yaml`). Ephemeral `ubuntu:<release>` containers. **Don't run spread locally without lxd configured** -- allocates cloud-style resources.

Rules:

- **Every binary in `bins` slice exercised in spread.** "please test every binary being delivered" is recurring rejection.
- **Untestable means unshippable.** Reviewers push to drop rather than ship untested.
- **80%-ish coverage** soft target in pr coverage comments. Not hard gate but watched.
- **Spread runs against `distro-info --latest`** for newest release; sometimes lxd image lags -- fallback to `ubuntu-daily:` channel ([pr#1001](https://github.com/canonical/chisel-releases/pull/1001)).

## Gotchas to internalise

- **Never commit on `main`.** Slice work on release branches.
- **Branch suffix matches `chisel.yaml` `archives.ubuntu.version`** -- `ubuntu-24.04` <-> `version: 24.04`.
- **EOL releases read-only.** Check `maintenance.end-of-life` vs today.
- **Forward-port not optional**, auto-ignored when pkg version gone from newer archive (e.g. `librocksdb9.11.yaml` deleted because newer ships `librocksdb10`). Heart of [#1000](https://github.com/canonical/chisel-releases/issues/1000).
- **Slice file == package 1:1.** Don't put two packages in one yaml.
- **`<pkg>_<slice>` addressing primitive** for cross-slice refs.
- **Debian arches in gating**: `amd64`, `arm64`, `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x`. Not `x86_64`/`aarch64`.
- **`copyright` slice conventional** -- almost every pkg has one. In file-level `essential:`.
- **`chisel <cmd> --release ubuntu-XX.XX`** -> matching git branch (online); `--release <path>` -> local; no flag -> host `/etc/os-release`.
- **`format:` gates schema**: v1/v2/v3 differ -- `hint:` v3-only, `prefer:` v2+, `pro:` under `archives:` in v2+ but `v2-archives:` in v1.
- **Starlark not python** in mutate.
- **Path sort** lexicographic in `contents:`.
- **`copyright` mandatory for functional slices.**
- **Forward-port chain order**: oldest -> newest. Cross-link prs in descriptions.
- **Slice rename across releases** (e.g. `bins` -> `scripts`): breaking pr in oldest, then ff prs into newer with `n/a` forward-port marker.
- **Versioned soname pkgs** (`librocksdb9.11`) deleted when upstream rolls new soname (`librocksdb10`). `removed-slices` ci ignores if old pkg gone from archive.

## Inspecting a deb package

Use `skills/slice/deb-list <package> [arch]` to inspect a deb before authoring slices.

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

Add `--scripts` to print the full bodies of all present maintainer scripts.

- `Depends:` feeds directly into `essential:` entries -- filter to direct deps only, skip `Recommends:`.
- `[l] path -> target` means the deb ships that symlink -- use a bare path entry, no explicit `symlink:` needed.
- `[x]` marks executables (go in `bins`); `[f]` marks regular files.
- Octal permissions and owner are shown per file. Add `mode:` to a slice entry only when the value is non-standard (not `0644`/`0755`/`0777`).
- If `--scripts` shows the postinst calling tools like `update-alternatives`, `ldconfig`, or `update-mime-database`, those side-effects do not run in a chisel rootfs -- either drop the dep or write a `mutate:` equivalent.
- Run once per target arch when multiarch differences are expected (`deb-list libfoo amd64`, then `arm64`, etc.).

Requires `apt-get` + `dpkg-deb` and a populated apt cache (`sudo apt-get update`).

## Inspecting repo without full checkout

Prefer `git` + `curl` over `gh` -- more commonly available, no auth needed for public reads.

```bash
# list live release branches
git ls-remote --heads https://github.com/canonical/chisel-releases.git 'ubuntu-*' \
  | awk '{print $2}' | sed 's|refs/heads/||'

# read release manifest (raw.githubusercontent.com serves blobs by ref)
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/ubuntu-24.04/chisel.yaml

# read sdf
curl -fsSL https://raw.githubusercontent.com/canonical/chisel-releases/ubuntu-24.04/slices/bash.yaml

# list slices on a branch w/out full clone -- sparse / partial fetch
git clone --filter=blob:none --no-checkout --depth 1 \
  -b ubuntu-24.04 https://github.com/canonical/chisel-releases.git /tmp/cr
git -C /tmp/cr sparse-checkout set slices chisel.yaml
git -C /tmp/cr checkout

# diff slice between releases (needs clone)
git -C <chisel-releases-repo> diff ubuntu-22.04:slices/coreutils.yaml ubuntu-24.04:slices/coreutils.yaml
```

Contribution flow:

```bash
git -C <repo> fetch origin ubuntu-24.04
git -C <repo> checkout -b add-mypkg-slices ubuntu-24.04
# add slices/mypkg.yaml + tests/spread/integration/mypkg/{task.yaml,smoke.sh}
git -C <repo> commit -m "feat(mypkg): add core, bins, libs, copyright slices"
# STOP here. User opens pr against ubuntu-24.04 and chains forward-ports through 25.10 -> 26.04.
```

## External references

- Chisel source: <https://github.com/canonical/chisel>
- Chisel docs: <https://documentation.ubuntu.com/chisel/latest/>
  - How-to slice a package: <https://documentation.ubuntu.com/chisel/latest/how-to/slice-a-package/>
  - SDF reference: <https://documentation.ubuntu.com/chisel/latest/reference/chisel-releases/slice-definitions/>
  - `chisel.yaml` reference: <https://documentation.ubuntu.com/chisel/latest/reference/chisel-releases/chisel.yaml/>
  - Manifest reference: <https://documentation.ubuntu.com/chisel/latest/reference/manifest/>
  - `cut` cli reference: <https://documentation.ubuntu.com/chisel/latest/reference/cmd/cut/>
  - Pro slices how-to: <https://documentation.ubuntu.com/chisel/latest/how-to/install-pro-package-slices/>
- chisel-releases repo: <https://github.com/canonical/chisel-releases>
  - `CONTRIBUTING.md` (authoritative): <https://github.com/canonical/chisel-releases/blob/main/CONTRIBUTING.md>
  - `README.md` (live release list): <https://github.com/canonical/chisel-releases/blob/main/README.md>
- chisel-releases navigator: <https://canonical.github.io/chisel-releases-navigator/>
- Ubuntu release schedule (codenames + eol): <https://wiki.ubuntu.com/Releases>

---

When this doc disagrees with repo, trust repo. When in doubt, read `slices/bash.yaml` or `slices/base-files.yaml` on target release branch.
