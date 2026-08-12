# RFHound — common tasks. Run `make help` for the list.
.DEFAULT_GOAL := help
PY ?= python3

.PHONY: help install dev test lint run dashboard demo build clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install RFHound (runtime only)
	pip install -e .

dev:  ## Install RFHound + test/lint tools
	pip install -e ".[dev]"

test:  ## Run the test suite
	pytest -q

lint:  ## Run flake8 (rules in .flake8, same as CI)
	flake8 rfhound tests

run:  ## Launch the guided menu
	rfhound

dashboard:  ## Launch the web dashboard in simulate mode
	rfhound --simulate web --open

demo:  ## Run a full recon survey with no hardware
	rfhound --simulate recon

build:  ## Build a wheel
	$(PY) -m build --wheel

clean:  ## Remove build/test artifacts
	rm -rf build dist *.egg-info .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
