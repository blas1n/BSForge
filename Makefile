.PHONY: help install-dev dev worker beat test lint format migrate upgrade clean

help:
	@echo "BSForge - Development Commands"
	@echo "=============================="
	@echo "install-dev   - Install with dev dependencies"
	@echo "dev           - Run development server"
	@echo "worker        - Run Celery worker"
	@echo "beat          - Run Celery beat scheduler"
	@echo "test          - Run tests"
	@echo "test-cov      - Run tests with coverage report"
	@echo "lint          - Run linters (ruff, mypy)"
	@echo "format        - Format code (black, ruff)"
	@echo "migrate       - Create migration (use: make migrate msg='description')"
	@echo "upgrade       - Apply migrations"
	@echo "clean         - Clean up generated files"

install-dev:
	uv pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.workers.celery_app worker -l info

beat:
	celery -A app.workers.celery_app beat -l info

flower:
	celery -A app.workers.celery_app flower --port=5555

test:
	pytest

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term-missing

test-unit:
	pytest -m unit

test-integration:
	pytest -m integration

lint:
	ruff check app tests
	mypy app

format:
	black app tests
	ruff check --fix app tests

migrate:
ifndef msg
	$(error msg is not set. Usage: make migrate msg='Add user table')
endif
	alembic revision --autogenerate -m "$(msg)"

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	rm -f .coverage 2>/dev/null || true

db-reset:
	@echo "WARNING: This will drop and recreate the database!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		alembic downgrade base; \
		alembic upgrade head; \
		echo "Database reset complete!"; \
	else \
		echo "Aborted."; \
	fi

pre-commit:
	pre-commit run --all-files

init:
	@echo "Initializing BSForge development environment..."
	uv pip install -e ".[dev]"
	pre-commit install
	@echo "Initialization complete!"
