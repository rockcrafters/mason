#!/usr/bin/env sh
# shared pats scorer wrapper: every slice scorer points its `file:` here and is
# dispatched by id via $PATS_SCORER. trampolines to python (pyyaml via uv).
exec uv run --quiet --with pyyaml python3 "$(dirname "$0")/slice_scorers.py" "$PATS_SCORER"
