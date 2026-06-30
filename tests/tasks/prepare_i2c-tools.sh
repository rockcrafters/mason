#!/usr/bin/env bash
. "$(dirname "$0")/_lib.sh"

BRANCH=ubuntu-26.04
TARGETS="libi2c0 udev i2c-tools"
prepare_denovo
