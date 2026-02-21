# Claim FDS Makefile
# - Local/VM reproducible commands
# - Uses python venv in .venv

PYTHON ?= python
VENV_DIR ?= .venv
PIP := $(VENV_DIR)/bin/pip
PY := $(VENV_DIR)/bin/python

.DEFAULT_GOAL := help

help: ## Show help
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'
	@echo ""

venv: ## Create venv if missing
	@if [ ! -d "$(VENV_DIR)" ]; then \
		$(PYTHON) -m venv $(VENV_DIR); \
	fi

install: venv ## Install requirements
	@$(PIP) -q install --upgrade pip
	@$(PIP) -q install -r requirements.txt

demo: install ## Generate demo artifacts (fast)
	@$(PY) -m src.simulate_production_outputs --scenario GO --days 120 --seed 42

full: install ## Run full pipeline (train->score->impact->stats->guardrails->report)
	@$(PY) -m src.train
	@$(PY) -m src.validate
	@$(PY) -m src.calibrate
	@$(PY) -m src.score_batch_prod
	@$(PY) -m src.score_cc || true
	@$(PY) -m src.experiment
	@$(PY) -m src.impact_causal || true
	@$(PY) -m src.impact_panel
	@$(PY) -m src.stats_impact_scipy
	@$(PY) -m src.segment_alerts
	@$(PY) -m src.guardrails
	@$(PY) -m src.executive_report
	@$(PY) -m src.executive_charts
	@$(PY) -m src.pdf_onepager

dashboard: install ## Run Streamlit dashboard
	@$(VENV_DIR)/bin/streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501

clean: ## Remove venv and out artifacts
	@rm -rf $(VENV_DIR) out/*.png out/*.pdf out/*.csv out/*.md out/*.json out/*.jsonl || true
