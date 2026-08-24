.DEFAULT_GOAL := help
.PHONY: help install check format test cov build clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install:  ## Sync the dev environment and install hooks
	uv sync --all-extras
	uv run pre-commit install

check:  ## Run every static check, exactly as CI does
	uv run pre-commit run --all-files

format:  ## Apply formatting and safe fixes
	uv run ruff check --fix .
	uv run ruff format .

test:  ## Run the test suite
	uv run pytest

cov:  ## Run the test suite with a coverage report
	uv run pytest --cov=restraint --cov-report=term-missing --cov-report=xml

build:  ## Build the sdist and wheel
	uv build

clean:  ## Remove build and test artefacts
	@rm -rf build/ dist/ .tox/ .eggs/ .pytest_cache/ .ruff_cache/ .mypy_cache/ \
		*.egg-info *.egg coverage.xml results.xml .coverage
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} +
