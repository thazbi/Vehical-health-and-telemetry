PYTHON ?= python

.PHONY: install lint format test typecheck up down logs

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .

test:
	$(PYTHON) -m pytest

typecheck:
	$(PYTHON) -m mypy services

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100
