#!/usr/bin/env bash
set -euo pipefail

python3 -m src.validate

if [ -f data/labels_feedback.csv ]; then
  python3 -m src.update_labels || true
fi

python3 -m src.train

# init champion if needed
PYTHONPATH=. python3 -c "from src.registry import init_champion_if_missing; init_champion_if_missing()"

# set challenger from latest model
cp models/fraud_lr.joblib models/challenger.joblib
cp models/meta.json models/meta_challenger.json

python3 -m src.score_cc || true
python3 -m src.promote_if_better || true

python3 -m src.score_batch_prod
python3 -m src.impact_causal || true
python3 -m src.stats_impact_scipy || true
python3 -m src.impact_panel || true
python3 -m src.segment_alerts || true
python3 -m src.guardrails || true
python3 -m src.rollout_controller || true

python3 -m src.executive_report || true
python3 -m src.executive_charts || true

# Build one-page pdf automatically (optional)
PYTHONPATH=. python3 - <<'PY'
import os, json
import pandas as pd
from src.pdf_onepager import export_onepager_pdf, _pick_highlights
ci = json.load(open("assets/ci.json","r",encoding="utf-8"))
md = open("out/executive_summary.md","r",encoding="utf-8").read() if os.path.exists("out/executive_summary.md") else ""
hi = _pick_highlights(md, 10)
panel = pd.read_csv("out/impact_panel.csv") if os.path.exists("out/impact_panel.csv") else pd.DataFrame()
ms=[]
if not panel.empty:
    if "p_value" not in panel.columns: panel["p_value"]=""
    for _,r in panel.head(3).iterrows():
        ms.append({"method":str(r.get("method","NA")),"effect_per_claim":f"{int(round(float(r.get('effect_per_claim',0)))):,}원","p_value":str(r.get("p_value","—"))})
kpis={"policy_ver":"NA","policy_mode":"NA","control_rate":"NA","effect_per_claim":"NA","saving_today":"NA","saving_mtd":"NA","saving_qtd":"NA","p_value":"NA","guardrails_badge":"NA","red_flag":False}
export_onepager_pdf("out/executive_onepager.pdf", ci, kpis, hi, "out/chart_impact_delta.png", None, ms)
print("✅ built out/executive_onepager.pdf")
PY

echo "✅ self-healing pipeline done"
