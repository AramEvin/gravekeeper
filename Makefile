.PHONY: help dev test lint format templates demo-up seed demo-run demo-down build clean

help:            ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-12s %s\n", $$1, $$2}'

dev:             ## Install for development (editable + dev tools + git hooks)
	pip install -e ".[dev]"
	pre-commit install

test:            ## Run the tests
	pytest -q

lint:            ## Lint and check formatting
	ruff check .
	ruff format --check .

format:          ## Auto-format the code
	ruff check --fix .
	ruff format .

templates:       ## Rebuild the DOCX templates
	python -m gravekeeper.build_templates

demo-up:         ## Start the demo stack (Grafana, Prometheus, Loki, Alloy)
	docker compose -f demo/docker-compose.yml up -d

seed:            ## Seed demo dashboards and print a token
	python demo/seed.py

demo-run:        ## Scan the demo Grafana (needs GRAFANA_TOKEN)
	gravekeeper run -c demo/gravekeeper.demo.yaml

demo-down:       ## Stop the demo stack and delete its data
	docker compose -f demo/docker-compose.yml down -v

build:           ## Build wheel and source archive into dist/
	python -m build

clean:           ## Remove build and output files
	rm -rf dist build out *.egg-info .pytest_cache .ruff_cache
