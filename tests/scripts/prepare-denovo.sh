#!/usr/bin/env bash
# pats prepare for denovo cases: the slice never existed upstream, so ground
# truth is the silver file shipped in tests/cases/<case>/<target>.silver.yaml.
#   $1 = case id, $2 = branch, $3.. = target packages
# env (from pats): PATS_WORKDIR (agent cwd), PATS_OUTPUT_DIR.
set -euo pipefail

case_id="$1"
branch="$2"
shift 2
targets="$*"

here="$(cd "$(dirname "$0")" && pwd)" # tests/scripts
cases_dir="$here/../cases/$case_id"
repo_root="$(cd "$here/../.." && pwd)"

git clone --depth 1 --branch "$branch" \
    https://github.com/canonical/chisel-releases.git "$PATS_WORKDIR"
cd "$PATS_WORKDIR"

mkdir -p "$PATS_OUTPUT_DIR"
printf '%s\n' "$branch" > "$PATS_OUTPUT_DIR/${case_id}.branch"

for t in $targets; do
    # ground truth = silver; the slice should not pre-exist (denovo). drop any
    # stray slice + the upstream spread so the agent authors from scratch.
    cp "$cases_dir/${t}.silver.yaml" "$PATS_OUTPUT_DIR/${t}.expected.yaml"
    rm -f "slices/${t}.yaml"
    rm -rf "tests/spread/integration/${t}"
done
rm -rf "tests/spread/integration/${case_id}"

node "$repo_root/scripts/cli.js" install --agents claude --target "$PATS_WORKDIR" --force
