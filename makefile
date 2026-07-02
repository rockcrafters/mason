.SUFFIXES:

help:  ## Show this help
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: test-js test-py  ## Run all test suites

.PHONY: test-js
test-js:  ## Installer tests (node builtin runner, no deps)
	node --test "tests/scripts/**/*.test.js"

.PHONY: test-py
test-py:  ## Script tests (uvx pytest, pyyaml pulled in on the fly)
	uvx --with pyyaml --with pytest pytest tests/scripts/

.PHONY: lint
lint:  ## Lint python (uvx ruff check)
	uvx ruff check scripts/ tests/scripts/

.PHONY: format
format:  ## Format python in place (uvx ruff format)
	uvx ruff format scripts/ tests/scripts/
