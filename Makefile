# Zuzu developer commands (Windows: use scripts\dev.ps1 / scripts\check.ps1)
PY ?= python

.PHONY: install test lint typecheck fmt check run-api run-web backup help

help:
	@echo "make install    - install backend + dev deps"
	@echo "make test       - run backend test suite"
	@echo "make lint       - ruff check"
	@echo "make fmt        - ruff format"
	@echo "make typecheck  - mypy"
	@echo "make check      - lint + typecheck + test"
	@echo "make run-api    - run API with migrations"
	@echo "make run-web    - run web dev server"

install:
	$(PY) -m pip install -e ".[dev]"
	cd apps/web && npm install

test:
	$(PY) -m pytest tests -q

lint:
	$(PY) -m ruff check apps/api/src tests migrations scripts

fmt:
	$(PY) -m ruff format apps/api/src tests migrations scripts

typecheck:
	$(PY) -m mypy apps/api/src

check: lint typecheck test

run-api:
	$(PY) -m alembic upgrade head
	$(PY) -m uvicorn zuzu.main:app --host 127.0.0.1 --port 8000

run-web:
	cd apps/web && npm run dev

backup:
	bash scripts/backup.sh
