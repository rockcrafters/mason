#!/usr/bin/env bash
# scorer: 1.0 if the produced slice is valid yaml, else 0.0.
# env (from pats): PATS_OUTPUT_DIR, PATS_TASK (== package == filename stem).
set -euo pipefail

f="$PATS_OUTPUT_DIR/${PATS_TASK}.yaml"
[ -f "$f" ] || { echo "0.0"; exit 0; }

uv run --quiet --with pyyaml python3 - "$f" <<'PY'
import sys, yaml
try:
    yaml.safe_load(open(sys.argv[1]))
    print("1.0")
except Exception:
    print("0.0")
PY
