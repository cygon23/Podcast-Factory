.PHONY: test run status validate cost-report lint

VENV ?= .venv/bin

test:
	$(VENV)/python -m pytest tests/ -v

lint:
	$(VENV)/python -m ruff check dorosak_factory tests
	$(VENV)/python -m black --check dorosak_factory tests

run:
	$(VENV)/python -m dorosak_factory run

status:
	$(VENV)/python -m dorosak_factory status

validate:
	$(VENV)/python -m dorosak_factory validate

cost-report:
	$(VENV)/python -m dorosak_factory cost-report
