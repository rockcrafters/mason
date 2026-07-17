#!/usr/bin/env bash
# mason-help: no repo, no knockout -- an empty workdir with the skill installed.
# /mason must print the usage block and stop; scorers read the transcript only,
# so there is nothing to collect.
. "$(dirname "$0")/_lib.sh"

mkdir -p "$PATS_WORKDIR" "$PATS_OUTPUT_DIR"
_install
