#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# Claim FDS: one-shot reproducible run script
# - creates/uses venv
# - installs requirements
# - generates out/ artifacts (demo by default)
# - runs Streamlit dashboard
#
# Usage:
#   bash scripts/run_all.sh demo
#   bash scripts/run_all.sh full
#
# Notes:
# - 'demo' uses src.simulate_production_outputs to generate artifacts quickly
# - 'full' runs training->scoring->impact->stats->guardrails->report pipeline
# ------------------------------------------------------------

MODE="${1:-demo}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "[1/6] Create venv if missing"
if [ ! -d ".venv" ]; then
  ${PYTHON_BIN} -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/6] Install requirements"
pip -q install --upgrade pip
pip -q install -r requirements.txt

mkdir -p out

if [ "${MODE}" = "demo" ]; then
  echo "[3/6] Generate demo artifacts (simulate_production_outputs)"
  python -m src.simulate_production_outputs --scenario GO --days 120 --seed 42
else
  echo "[3/6] Run full pipeline (train->score->impact->stats->guardrails->report)"
  python -m src.train
  python -m src.validate
  python -m src.calibrate

  python -m src.score_batch_prod
  # Optional: champion/challenger comparison
  python -m src.score_cc || true

  python -m src.experiment
  python -m src.impact_causal || true
  python -m src.impact_panel
  python -m src.stats_impact_scipy
  python -m src.segment_alerts
  python -m src.guardrails

  python -m src.executive_report
  python -m src.executive_charts
  python -m src.pdf_onepager
fi

echo "[4/6] Quick check outputs"
ls -1 out | head -n 50 || true

echo "[5/6] Launch dashboard"
echo "  - URL: http://<YOUR_VM_EXTERNAL_IP>:8501"
streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501
