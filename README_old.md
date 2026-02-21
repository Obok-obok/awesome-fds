# Ultimate Executive-Grade Fraud Program Demo

This repository is a **single-command** demo of an enterprise Fraud Detection Program:

- Model training + champion/challenger registry
- Batch scoring with review queue
- Control/Treatment experiment (hash-stable assignment)
- Causal-ish impact reporting (diff-in-means + Welch test)
- Guardrails (GO / HOLD / ROLLBACK)
- **Executive Streamlit dashboard + one-page PDF export**
- **Demo telemetry generator** (GO/HOLD/ROLLBACK scenarios) for realistic dashboard fills

## Quick start (GCP free-vm / Ubuntu)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Option A — Run the real pipeline

```bash
bash src/run_self_healing.sh
```

Then launch the dashboard:

```bash
streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

## Option B — Fill the dashboard with realistic demo telemetry

This creates `out/` artifacts such as impact panel, p-values, guardrails, charts and a decision ledger.

```bash
python -m src.simulate_production_outputs --scenario GO --days 60 --seed 42
python -m src.executive_charts
```

Then launch the dashboard:

```bash
streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

## Executive dashboard controls

In the left sidebar:
- **Demo Telemetry**: pick `GO/HOLD/ROLLBACK` and click **Generate / Refresh Demo Data**.
  - This regenerates `out/` telemetry and charts, and refreshes the UI.

## Important folders

- `src/` : pipeline modules
- `data/` : input datasets (`claims.csv`) and optional label feedback
- `models/` : champion/challenger models + policy registry
- `out/` : executive artifacts (panels, guardrails, charts, onepager pdf)

