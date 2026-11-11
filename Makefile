# OpsDesk for TBO — developer and operator entry points.
.PHONY: help install seed serve test sim bench crawl build docker clean verify

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python and frontend dependencies
	pip install -r requirements.txt
	cd frontend && npm ci

seed: ## Reset and reseed the synthetic dataset (49 tickets, 5 journeys)
	python -m database.seed_data.seed

serve: ## Run the API + SPA on :8000
	uvicorn backend.main:app --host 0.0.0.0 --port 8000

test: ## Full pytest suite (unit + system)
	python -m pytest tests backend/tests -q

sim: ## Run the five seeded journeys end to end
	python -m simulation.run_all

bench: ## Classifier holdout, routing latency and 50k-row export benchmark
	python -m scripts.run_benchmark

crawl: ## Screenshot every workspace with Playwright (needs :8000 running)
	python scripts/ui_crawl.py

build: ## Type-check and build the SPA into backend/static
	cd frontend && npx tsc --noEmit && npm run build

docker: ## Build the container image
	docker build -t opsdesk-tbo:2.1.0 .

verify: test sim ## The gate used before any release: tests + journeys
	@echo "verify: all green"

clean: ## Remove caches and generated exports (keeps the database)
	rm -rf .pytest_cache **/__pycache__ exports/*.csv exports/*.jsonl
