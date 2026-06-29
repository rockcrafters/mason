# mason

agent kit for working on [`canonical/chisel-releases`](https://github.com/canonical/chisel-releases).

provides two agents:

- **`write-slice`** -- authors + tests + commits chisel slice definition files (SDFs). does not open PRs.
- **`review-slice`** -- read-only review of SDFs against chisel conventions, CI checks, and forward-port rules.

both read `./CHISEL.md` (shared reference: format, branch model, schema versions, sources of truth) and use the helpers in `./scripts/` (`deb-list`, `try-cut`).
