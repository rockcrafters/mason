#!/usr/bin/env bash
# shared helpers for per-task prepare scripts (tasks/prepare_<id>.sh). sourced,
# not run directly. a task script sets BRANCH (and TARGETS for denovo) then calls
# prepare_knockout or prepare_denovo. the case/package id is $PATS_TASK_ID;
# PATS_WORKDIR (agent cwd) and PATS_OUTPUT_DIR are set by pats.
set -euo pipefail

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # tests/tasks
_repo_root="$(cd "$_here/../.." && pwd)"              # mason repo root (cli.js)
_cases_dir="$_here/../cases"                          # tests/cases

# _clone: chisel-releases@$BRANCH into the workdir (the agent's cwd), record the
# branch so format-version scorers can gate on it.
_clone() {
    git clone --quiet --depth 1 --branch "$BRANCH" \
        https://github.com/canonical/chisel-releases.git "$PATS_WORKDIR"
    cd "$PATS_WORKDIR"
    mkdir -p "$PATS_OUTPUT_DIR"
    printf '%s\n' "$BRANCH" >"$PATS_OUTPUT_DIR/${PATS_TASK_ID}.branch"
}

# _reinit_git: rebuild git history so HEAD no longer carries the removed target
# slice -- otherwise the agent recovers the answer with `git show HEAD:slices/...`
# and the case measures git recall, not authoring. one fresh commit on $BRANCH of
# the current tree (target slice + its spread already deleted by the caller).
# NOTE: nukes history wholesale; fine for an eval sandbox. a history-preserving
# strip (filter-repo) would be the upgrade if real history ever matters here.
_reinit_git() {
    rm -rf .git
    # core.hooksPath=/dev/null: the host's global git hooks (ascii/whitespace/todo
    # gates) would reject upstream chisel-releases' own spread tests. this is a
    # sandbox snapshot of upstream, not our code, so bypass them.
    git init --quiet -b "$BRANCH"
    git -c core.hooksPath=/dev/null -c user.name=pats -c user.email=pats@local \
        add -A
    git -c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.name=pats -c user.email=pats@local \
        commit --quiet -m "chisel-releases base (target slice removed)"
}

# _install: install the skill so claude auto-loads it (-> .claude/skills/).
_install() {
    node "$_repo_root/scripts/cli.js" install --agents claude --target "$PATS_WORKDIR" --force --quiet
}

# prepare_knockout: stash the real slice as ground truth, then remove it + the
# upstream spread test, so the agent must reproduce both.
prepare_knockout() {
    _clone
    local pkg="$PATS_TASK_ID"
    cp "slices/${pkg}.yaml" "$PATS_OUTPUT_DIR/${pkg}.expected.yaml"
    rm "slices/${pkg}.yaml"
    rm -rf "tests/spread/integration/${pkg}"
    _reinit_git
    _install
}

# prepare_denovo: ground truth = the silver files in tests/cases/<case>/. drop
# any stray slice + upstream spread per target so the agent authors from scratch.
prepare_denovo() {
    _clone
    local case_id="$PATS_TASK_ID"
    for t in $TARGETS; do
        cp "$_cases_dir/$case_id/${t}.silver.yaml" "$PATS_OUTPUT_DIR/${t}.expected.yaml"
        rm -f "slices/${t}.yaml"
        rm -rf "tests/spread/integration/${t}"
    done
    rm -rf "tests/spread/integration/${case_id}"
    _reinit_git
    _install
}
