#!/usr/bin/env bash
# pats prepare: seed the sandbox workdir for a knockout slice eval.
#   $1 = package, $2 = chisel-releases branch
# env (from pats): PATS_WORKDIR (becomes the agent's cwd), PATS_OUTPUT_DIR.
set -euo pipefail

pkg="$1"
branch="$2"
repo_root="$(cd "$(dirname "$0")/../.." && pwd)" # mason repo root (cli.js lives here)

# the workdir IS the chisel-releases checkout -- agent runs with cwd here.
git clone --depth 1 --branch "$branch" \
    https://github.com/canonical/chisel-releases.git "$PATS_WORKDIR"

cd "$PATS_WORKDIR"

# knockout: stash the real slice as ground truth, then remove it -- along with
# the upstream spread test, so the agent must produce its own (else the spread
# scorers measure the existing upstream test, not the agent's work).
mkdir -p "$PATS_OUTPUT_DIR"
cp "slices/${pkg}.yaml" "$PATS_OUTPUT_DIR/${pkg}.expected.yaml"
rm "slices/${pkg}.yaml"
rm -rf "tests/spread/integration/${pkg}"

# record the branch so format-version scorers can gate on it.
printf '%s\n' "$branch" > "$PATS_OUTPUT_DIR/${pkg}.branch"

# install the skill so claude auto-loads it (-> .claude/skills/chisel-releases/).
node "$repo_root/scripts/cli.js" install --agents claude --target "$PATS_WORKDIR" --force
