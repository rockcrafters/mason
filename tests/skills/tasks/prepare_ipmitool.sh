#!/usr/bin/env bash
. "$(dirname "$0")/_lib.sh"

BRANCH=ubuntu-26.04
TARGETS="freeipmi-common libfreeipmi17 ipmitool"
prepare_denovo
