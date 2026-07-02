#!/usr/bin/env bash
# pats collect: gather the agent's output to score. uniform across tasks -- the
# case id is $PATS_TASK_ID, the rest is data-driven (loops the staged
# *.expected.yaml). env: PATS_WORKDIR (agent cwd), PATS_OUTPUT_DIR.
set -eu

case_id="$PATS_TASK_ID"
mkdir -p "$PATS_OUTPUT_DIR"

# copy the produced slice for every target with a ground-truth file (single-
# target cases have one; multi-target denovo have several).
for exp in "$PATS_OUTPUT_DIR"/*.expected.yaml; do
    [ -e "$exp" ] || continue
    stem="$(basename "$exp" .expected.yaml)"
    if [ -f "$PATS_WORKDIR/slices/${stem}.yaml" ]; then
        cp "$PATS_WORKDIR/slices/${stem}.yaml" "$PATS_OUTPUT_DIR/${stem}.yaml"
    fi
done

# spread tests are case-level: the task.yaml + a concatenated bundle of the whole
# integration/<case>/ dir (scorers grep the bundle for binary names).
spread_dir="$PATS_WORKDIR/tests/spread/integration/${case_id}"
if [ -f "$spread_dir/task.yaml" ]; then
    cp "$spread_dir/task.yaml" "$PATS_OUTPUT_DIR/${case_id}.task.yaml"
fi
if [ -d "$spread_dir" ]; then
    find "$spread_dir" -type f -exec cat {} + >"$PATS_OUTPUT_DIR/${case_id}.spread.txt" 2>/dev/null || true
fi
