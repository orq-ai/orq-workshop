# orq.ai workshop. Every target is one line so it doubles as documentation.
.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= uv
RUN := $(UV) run
MARP ?= $(shell command -v marp 2>/dev/null || echo npx -y @marp-team/marp-cli)
MODULES := $(sort $(notdir $(wildcard modules/*)))

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-28s\033[0m %s\n",$$1,$$2}'

setup: ## Install Python deps (uv) and create .env from the example if missing
	$(UV) sync --all-groups --extra langgraph
	@test -f .env || { cp .env.example .env; echo "Created .env. Fill ORQ_API_KEY or run: orq setup --local"; }

orq-doctor: ## orq CLI self-check: auth, endpoints, skills
	orq doctor

gateway-check: ## One refund turn through the gateway; prints answer + trace id
	$(RUN) python -m app.gateway_check

test: ## Unit tests for the tools
	$(RUN) pytest -q

seed-workspace: ## Create every workshop entity in orq (idempotent, prefixed with WS_PREFIX)
	$(RUN) python -m app.refund_agent.entities seed

seed-insurance: ## Create the insurance claims demo (agents, evaluators, 15 test cases) for the chat's Insurance demo
	$(RUN) python -m app.insurance

generate-traffic: ## Generate 20 mixed good/bad conversations so traces exist for failure analysis
	$(RUN) python -m app.traffic

reset-workspace: ## Delete every entity this repo created (by WS_PREFIX)
	$(RUN) python -m app.refund_agent.entities reset

regression-eval: ## Quality regression gate (exit 1 on regression). Used by CI.
	$(RUN) python -m evals.regression

regression-eval-vulnerable: ## Same gate against the vulnerable instructions. The gate must exit 1; this target succeeds when it does.
	@$(RUN) python -m evals.regression --instructions app/data/vulnerable_instructions.md --out evals/results/vulnerable.json; ec=$$?; \
	  echo "gate exit code: $$ec (expected 1)"; test $$ec -eq 1

evaluatorq-dashboard: ## Simulation and red-team results in the browser (eq dashboard), with the key from .env
	@test -f .env || { echo "No .env yet: run make setup and fill ORQ_API_KEY."; exit 1; }
	@set -a; source .env; set +a; $(RUN) eq dashboard $(if $(PORT),--port $(PORT))

redteam-gate: ## Security regression gate with evaluatorq static red team. Used by CI.
	$(RUN) python -m evals.redteam_gate

mcp-server: ## Run the refund MCP server locally on :8000 (module 10)
	$(RUN) python app/mcp_server.py

edge: ## Run app/edge.py on :8001 (module 09 external KB + module 14 webhook receiver); expose it, put the public URL in WS_EDGE_URL
	$(RUN) python -m app.edge

edge-docker: ## The same as a container (what the instructor hosts for the room)
	docker build -t orq-edge . && docker run --rm -p 8001:8001 -e WS_WEBHOOK_SECRET=$$WS_WEBHOOK_SECRET orq-edge

agent-chat-ui: ## Run the refund agent chat UI on :8002
	$(RUN) python -m app.web

og-card: ## Regenerate the splash card in docs/assets/og-image.png (README + link unfurls)
	$(UV) run --with "fonttools[woff]" --with pillow python scripts/gen_og_card.py

diagrams: ## Re-export the diagram SVGs (modules/*/assets, docs/assets/diagrams) to PNG
	$(UV) run --with playwright python scripts/export_diagrams.py

# Solutions written in Jupytext percent format (`# %%` cells) double as notebook sources.
NB_SOURCES := $(shell grep -l "^\# %%" modules/*/run.py 2>/dev/null)

notebooks: ## Generate modules/NN-*/notebook.ipynb from every percent-format run.py (on the solution branch)
	@for src in $(NB_SOURCES); do dir=$${src%/run.py}; $(RUN) jupytext --quiet --to ipynb -o $$dir/notebook.ipynb $$src && echo "  $$dir/notebook.ipynb"; done

lab: notebooks ## Generate the notebooks and open JupyterLab at the repo root
	$(RUN) jupyter lab

docs-serve: ## Live docs at http://127.0.0.1:8000
	$(RUN) --group docs mkdocs serve

docs-build: ## Strict docs build (fails on broken links)
	$(RUN) --group docs mkdocs build --strict

S ?= workshop
session: ## Build sessions/$(S): run-of-show.md, docs page and slides/deck.html (marp). Commit the output.
	$(RUN) python scripts/build_session.py $(S)
	$(MARP) sessions/$(S)/slides/deck.md --theme slides/orq-theme.css --allow-local-files -o sessions/$(S)/slides/deck.html
	$(RUN) python scripts/build_session.py $(S) --inline

session-pdf: ## Optional PDF of sessions/$(S)/slides/deck.md (not part of `make session`; gives up after 60 s)
	$(MARP) sessions/$(S)/slides/deck.md --theme slides/orq-theme.css --pdf --allow-local-files --browser-timeout 60 -o sessions/$(S)/slides/deck.pdf

deck: ## Serve a reveal.js deck: make deck [D=kickstart|october-insurance] [PORT=8000], then open http://localhost:8000/#/5 (add ?code=XXXX to show the login code)
	python3 -m http.server $(or $(PORT),8000) -d slides/$(or $(D),kickstart)

handout: ## Build slides/handout.html (QR codes, commands; A4, white) and open it to print
	uvx --with segno python slides/handout.py && open slides/handout.html

modules: ## List modules by name, with what each leaves you with
	@for d in modules/*/; do n=$$(basename $$d); printf '  %-28s %s\n' "$$n" "$$(grep -m1 -A1 '^!!! abstract' $$d/README.md | tail -1 | sed 's/^ *//' | cut -c1-90)"; done

module: ## Run modules/$(M)/run.py (starter on main, finished file on the solution branch), e.g. make module M=tracing
	@test -n "$(M)" -a -d "modules/$(M)" || { echo "no module '$(M)'. make modules lists them"; exit 1; }
	@echo "Source file: modules/$(M)/run.py"; echo "Full command: $(RUN) python modules/$(M)/run.py"; echo
	$(RUN) python modules/$(M)/run.py

# ponytail: the old numbered names (make m07) stay as aliases because printed handouts and private
# run-of-shows use them. Drop after the next client run.
OLD_NUMBERS := 00=setup 01=gateway 02=tracing 03=smart-routing 04=guardrails 05=budgets-and-keys 06=orqi 07=failure-analysis 08=managed-agents 09=knowledge-base 10=mcp-gateway 11=simulation 12=evals-in-ci 13=coding-agents 14=alerts-and-webhooks 15=advisor-and-sidekick 16=red-teaming 17=annotation-queues 18=trace-insights
m%:
	@slug=$$(echo "$(OLD_NUMBERS)" | tr ' ' '\n' | sed -n 's/^$*=//p'); test -n "$$slug" || { echo "no module $*"; exit 1; }; \
	echo "make m$* is now: make module M=$$slug"; $(MAKE) --no-print-directory module M=$$slug

.PHONY: evaluatorq-dashboard help setup orq-doctor gateway-check test seed-workspace seed-insurance generate-traffic reset-workspace regression-eval regression-eval-vulnerable redteam-gate mcp-server edge edge-docker agent-chat-ui og-card diagrams docs-serve docs-build session session-pdf deck handout modules module

# ponytail: old target names, kept because private run-of-shows and printed handouts still say them.
# Drop after the next client run. Hidden from `make help` (no `##`).
smoke: gateway-check
doctor: orq-doctor
seed: seed-workspace
reset: reset-workspace
eval: regression-eval
eval-vulnerable: regression-eval-vulnerable
chat: agent-chat-ui
traffic: generate-traffic
