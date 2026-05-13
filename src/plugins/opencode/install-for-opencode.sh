#!/usr/bin/env bash
# install-for-opencode.sh
#
# FOR OPENCODE AGENTS ONLY.
# Wires mason skills into OpenCode's global skill directory so they are
# discoverable via the `skill` tool in every future OpenCode session.
#
# Safe to run multiple times (idempotent).
#
# Usage (from any directory):
#   bash /path/to/mason/src/plugins/opencode/install-for-opencode.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASON_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SKILLS_SRC="$MASON_ROOT/skills"
SKILLS_DST="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills"

link_skill() {
  local name="$1"
  local src="$SKILLS_SRC/$name"
  local dst="$SKILLS_DST/$name"

  if [ ! -d "$src" ]; then
    echo "ERROR: skill source not found: $src" >&2
    return 1
  fi

  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "  already linked: $dst -> $src"
    return 0
  fi

  if [ -e "$dst" ]; then
    echo "  replacing existing entry: $dst"
    rm -rf "$dst"
  fi

  ln -s "$src" "$dst"
  echo "  linked: $dst -> $src"
}

echo "mason: installing OpenCode skills"
echo "  source: $SKILLS_SRC"
echo "  target: $SKILLS_DST"
echo ""

mkdir -p "$SKILLS_DST"

link_skill "write-slice"
link_skill "review-slice"

echo ""
echo "Done. Skills available in all OpenCode sessions:"
echo "  write-slice  -- author chisel SDF files"
echo "  review-slice -- review chisel SDF files"
