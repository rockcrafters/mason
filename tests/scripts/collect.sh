#!/usr/bin/env bash
# pats collect: gather the agent's output to score.
#   $1 = case id (used for the case-level spread bundle)
# env (from pats): PATS_WORKDIR (agent cwd), PATS_OUTPUT_DIR.
#
# generic over targets: copies the produced slice for every target that has a
# ground-truth file (<target>.expected.yaml staged by prepare). single-target
# cases have one; multi-target (denovo) have several.
set -eu

case_id="$1"
mkdir -p "$PATS_OUTPUT_DIR"

for exp in "$PATS_OUTPUT_DIR"/*.expected.yaml; do
    [ -e "$exp" ] || continue
    stem="$(basename "$exp" .expected.yaml)"
    if [ -f "$PATS_WORKDIR/slices/${stem}.yaml" ]; then
        cp "$PATS_WORKDIR/slices/${stem}.yaml" "$PATS_OUTPUT_DIR/${stem}.yaml"
    fi
done

# spread tests are case-level: the task.yaml + a concatenated bundle of the
# whole integration/<case>/ dir (scorers grep the bundle for binary names).
spread_dir="$PATS_WORKDIR/tests/spread/integration/${case_id}"
if [ -f "$spread_dir/task.yaml" ]; then
    cp "$spread_dir/task.yaml" "$PATS_OUTPUT_DIR/${case_id}.task.yaml"
fi
if [ -d "$spread_dir" ]; then
    find "$spread_dir" -type f -exec cat {} + > "$PATS_OUTPUT_DIR/${case_id}.spread.txt" 2>/dev/null || true
fi
