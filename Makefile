.PHONY: install dev test lint format clean help

## ─── Setup ────────────────────────────────────────────────────────────────────

install: ## Install all dependencies and pre-commit hooks
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

## ─── Development ──────────────────────────────────────────────────────────────

dev: ## Start local development server (hot reload)
	docker-compose up -d db cache
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

dev-full: ## Start all services via Docker Compose
	docker-compose up --build

## ─── Quality ──────────────────────────────────────────────────────────────────

test: ## Run unit and integration tests with coverage
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=xml

lint: ## Run linter and type checker
	ruff check . && mypy src/

format: ## Auto-format code
	ruff format .

## ─── Maintenance ──────────────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "coverage.xml" -delete 2>/dev/null || true

## ─── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
