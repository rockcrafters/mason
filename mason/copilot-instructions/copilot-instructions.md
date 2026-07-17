# Reviewing chisel-releases pull requests

This repository holds chisel slice definition files (SDFs) -- one YAML file per
package under `slices/` -- and their spread tests under
`tests/spread/integration/`. Review PRs against the conventions below. The
detailed format reference (schema versions, canonical slice names, branch
model) is in the `.github/instructions/` files.

Deterministic CI already gates lint, `chisel cut`, removed slices, forward
ports, and hint style -- do not restate what CI reports. Focus comments on the
conventions and judgement calls below.

## Hard gates (flag as blocking)

- Contents paths sorted in bytewise ASCII order within each slice.
- Global `essential:` placed right after `package:`; the `copyright` slice
  placed last in the `slices:` block.
- `package:` matches the filename stem; one package per SDF.
- Architecture names are lowercase Debian names only (`amd64`, `arm64`,
  `armhf`, `i386`, `ppc64el`, `riscv64`, `s390x`) -- never `x86_64` or
  `aarch64`.
- Dependencies come from the deb's `Depends:` only -- never `Recommends:` or
  `Suggests:`.
- Append-only: removing an SDF, a slice, or a content path from a published
  slice is a regression. A slimmer variant means a new slice, not removals.
- Version-gated fields must match `format:` in `chisel.yaml` (`hint:` and
  map-form `essential:` are v3; `prefer:` is v2+).

## Dependencies

- Every direct `Depends:` entry should appear as an `essential:` entry, and
  `bins`/`libs` slices must list every transitive shared-lib provider
  (`libc6_libs`, `libgcc-s1_libs`, ...).
- Don't over-include: a dep or path with no demonstrated need gets pruned --
  if in doubt, leave it out. No speculative slices, no config files for tools
  this repo doesn't slice.
- Slices are use-case-agnostic: describe what a slice ships, never which
  application it exists for.

## Path entry style

- Multiarch lib dirs use the `*-linux-*` glob, not explicit triples.
- No trailing `*` on single-version sonames: `libfoo.so.1:` not
  `libfoo.so.1*:`.
- Version globs pin major.minor only, never the patch level.
- Keep globs narrow -- a path more than one package could own is a red flag.
- No explicit `symlink:` for symlinks the deb already ships; annotate manual
  ones with a comment.

## Testing

- Binaries shipped by a `bins` slice should be exercised in the spread test,
  with functional checks -- `--version` alone is insufficient for
  applications. Untestable means unshippable.
- One fresh rootfs per test; a reused rootfs lets leftover slices mask a
  missing dependency.
- Tests are hermetic: inputs generated inline, no apt-installed extras,
  bounded waits. Only packages whose function is the network path (CA
  bundles, TLS clients) may hit one stable well-known endpoint.

## Patterns to never suggest

Maintainers reject these; do not propose them in review comments or fix
suggestions:

- Inner-spaced flow style: `{ arch: [ amd64 ] }` -- the accepted form is
  `{arch: [amd64]}`.
- Map-form essential entries (`<slice>: {}`) on v1/v2 branches -- the map
  form is v3-only.
- Patch-level version pins in path globs.
- Adding deps to mirror another package's maintainer scripts.
