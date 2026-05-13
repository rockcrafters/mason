.SUFFIXES:

# run from inside tests/ -- all paths relative to here
CACHE := .cache
UV ?= uv
UVX ?= uvx

# Overridable knobs:
#   make run MODEL=haiku CASE=hello FORCE=1
#   make test MODEL=haiku
MODEL := $(or $(MODEL),)
CASE := $(or $(CASE),)
FORCE := $(or $(FORCE),)
JOBS := $(or $(JOBS),4)
KFILTER := $(strip $(MODEL) $(CASE))
ifeq ($(KFILTER),)
  PYTEST_K :=
else
  PYTEST_K := -k "$(KFILTER)"
endif

RUN_ARGS :=
ifneq ($(MODEL),)
  RUN_ARGS += --model $(MODEL)
endif
ifneq ($(CASE),)
  RUN_ARGS += --case $(CASE)
endif
ifneq ($(FORCE),)
  RUN_ARGS += --force
endif
ifneq ($(JOBS),)
  RUN_ARGS += -j $(JOBS)
endif

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "} {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: run
run:  ## Run every model on every case (writes .cache/runs/<model>/<case>/)
	$(UV) run python -m framework.runner $(RUN_ARGS)

.PHONY: test
test:  ## Score cached runs in .cache/runs/ (does not invoke agents)
	$(UV) run pytest slice/ $(PYTEST_K) --scored-report=$(CACHE)/report.json

.PHONY: meta
meta:  ## Self-tests for the eval framework (no agent runs, no chisel)
	$(UV) run pytest meta/ -v

.PHONY: report
report:  ## Re-render last report.json as bar table
	@if [ ! -f $(CACHE)/report.json ]; then echo "no report at $(CACHE)/report.json; run 'make test' first"; exit 1; fi
	@$(UV) run python -c "import json; \
d=json.load(open('$(CACHE)/report.json')); \
w=10; bar=lambda s: '['+'#'*int(round(s*w))+'-'*(w-int(round(s*w)))+']'; \
[print(f\"{t['id'][:60]:60}  {t['score']:5.2f}  {bar(t['score'])}\") for t in d['tests']]; \
print('---'); \
[print(f\"  {axis}={v:24} avg {x['avg']:5.2f} (n={x['n']})  {bar(x['avg'])}\") for axis,vals in d['groups'].items() for v,x in vals.items()]; \
print('---'); \
o=d['overall']; print(f\"  overall avg {o['avg']:5.2f} (n={o['n']})  {bar(o['avg'])}\")"

.PHONY: lint
lint:  ## ruff check
	$(UVX) ruff check .

.PHONY: format
format:  ## ruff format + ruff check --fix
	$(UVX) ruff format .
	$(UVX) ruff check --fix .

.PHONY: verify
verify: lint test  ## Aggregate gate: lint + score

.PHONY: show-diff
show-diff:  ## Diff expected vs actual for a cached run (fzf picker if no spec)
	@$(UV) run python -m tools.show_diff $(filter-out $@,$(MAKECMDGOALS))

.PHONY: show-logs
show-logs:  ## View run/stdout/stderr/prompt/meta for a cached run (WHICH=run|stdout|stderr|prompt|meta)
	@$(UV) run python -m tools.show_logs $(if $(WHICH),--which $(WHICH)) $(filter-out $@,$(MAKECMDGOALS))

%:
	@:

.PHONY: clean
clean:  ## Nuke .cache (clones, runs, reports)
	rm -rf $(CACHE)

.PHONY: clean-runs
clean-runs:  ## Nuke only .cache/runs (keep chisel-releases clone)
	rm -rf $(CACHE)/runs
