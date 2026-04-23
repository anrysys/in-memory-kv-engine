.DEFAULT_GOAL := help
PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PORT ?= 9888
HOST ?= 127.0.0.1
IMAGE ?= ember-cache:latest

.PHONY: help venv install lint format test run client \
        docker-build docker-run docker-stop compose-up compose-down \
        smoke clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

venv: ## Create a local virtualenv at .venv
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv ## Install package + dev dependencies into .venv
	$(BIN)/pip install -e ".[dev]"

lint: ## Run ruff and black --check
	$(BIN)/ruff check .
	$(BIN)/black --check .

format: ## Auto-fix with ruff and black
	$(BIN)/ruff check --fix .
	$(BIN)/black .

test: ## Run the pytest e2e suite
	$(BIN)/pytest -v

run: ## Run the server locally on $(HOST):$(PORT)
	HOST=$(HOST) PORT=$(PORT) $(BIN)/python -m ember_cache

client: ## Open the interactive CLI client against $(HOST):$(PORT)
	$(BIN)/python -m ember_cache.client --host $(HOST) --port $(PORT)

docker-build: ## Build the Docker image
	docker build -t $(IMAGE) .

docker-run: ## Run the container, exposing port 9888
	docker run --rm --name ember-cache -p $(PORT):9888 $(IMAGE)

docker-stop: ## Stop the running ember-cache container
	-docker stop ember-cache

compose-up: ## Start via docker compose (detached)
	docker compose up -d --build

compose-down: ## Stop the docker compose stack
	docker compose down

smoke: ## Reproduce the spec example sequence against a running server
	@echo "Smoke testing $(HOST):$(PORT) ..."
	@$(BIN)/python scripts/smoke.py --host $(HOST) --port $(PORT)

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
