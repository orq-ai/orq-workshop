# orq.ai workshop. Every target is one line so it doubles as documentation.
.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= uv
RUN := $(UV) run
MARP ?= $(shell command -v marp 2>/dev/null || echo npx -y @marp-team/marp-cli)
MODULES := $(sort $(notdir $(wildcard modules/*)))

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

setup: ## Install Python deps (uv) and create .env from the example if missing
	$(UV) sync --all-groups --extra langgraph
	@test -f .env || { cp .env.example .env; echo "Created .env. Fill ORQ_API_KEY or run: orq setup --local"; }

doctor: ## orq CLI self-check: auth, endpoints, skills
	orq doctor

smoke: ## One refund turn through the gateway; prints answer + trace id
	$(RUN) python -m app.smoke

test: ## Unit tests for the tools
	$(RUN) pytest -q

seed: ## Create every workshop entity in orq (idempotent, prefixed with WS_PREFIX)
	$(RUN) python -m app.refund_agent.entities seed

traffic: ## Generate 20 mixed good/bad conversations so traces exist for failure analysis
	$(RUN) python -m app.traffic

reset: ## Delete every entity this repo created (by WS_PREFIX)
	$(RUN) python -m app.refund_agent.entities reset

eval: ## Quality regression gate (exit 1 on regression). Used by CI.
	$(RUN) python -m evals.regression

eval-vulnerable: ## Same gate against the vulnerable instructions. Must exit 1.
	$(RUN) python -m evals.regression --instructions app/data/vulnerable_instructions.md --out evals/results/vulnerable.json

redteam-gate: ## Security regression gate with evaluatorq static red team. Used by CI.
	$(RUN) python -m evals.redteam_gate

mcp-server: ## Run the refund MCP server locally on :8000 (module 10)
	$(RUN) python app/mcp_server.py

og-card: ## Regenerate the splash card in docs/assets/og-image.png (README + link unfurls)
	$(UV) run --with "fonttools[woff]" --with pillow python scripts/gen_og_card.py

docs-serve: ## Live docs at http://127.0.0.1:8000
	$(RUN) mkdocs serve

docs-build: ## Strict docs build (fails on broken links)
	$(RUN) mkdocs build --strict

slides: ## Render slides/workshop.md to HTML and PDF with Marp
	$(MARP) slides/workshop.md --theme slides/orq-theme.css -o slides/workshop.html
	$(MARP) slides/workshop.md --theme slides/orq-theme.css --pdf --allow-local-files -o slides/workshop.pdf

modules: ## List modules
	@printf '  %s\n' $(MODULES)

# m00 .. m13: run a module's solution, e.g. `make m01`
m%: ## Run the solution of module NN (e.g. make m03)
	@dir=$$(ls -d modules/$*-* 2>/dev/null | head -1); test -n "$$dir" || { echo "no module $*"; exit 1; }; $(RUN) python $$dir/solution/run.py

.PHONY: help setup doctor smoke test seed traffic reset eval eval-vulnerable redteam-gate mcp-server og-card docs-serve docs-build slides modules
