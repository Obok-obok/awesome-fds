import os
import pandas as pd
from datetime import datetime
from src.io_utils import read_csv, write_text

def main():
    os.makedirs("out", exist_ok=True)
    panel = read_csv("out/impact_panel.csv")
    guard = read_csv("out/guardrails_decision.csv")
    seg = read_csv("out/segment_alerts.csv")
    sig = read_csv("out/impact_significance_scipy.csv")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    effect = "NA"
    if not panel.empty and "effect_per_claim" in panel.columns:
        effect = f"{int(round(float(panel['effect_per_claim'].iloc[0]))):,}원"

    decision = guard["decision"].iloc[0] if (not guard.empty and "decision" in guard.columns) else "NA"
    n_alert = int(seg["is_alert"].fillna(False).astype(bool).sum()) if (not seg.empty and "is_alert" in seg.columns) else 0
    pval = f"{float(sig['welch_p_value'].iloc[0]):.4g}" if (not sig.empty and "welch_p_value" in sig.columns) else "NA"

    md = f"""# Fraud Program Executive Summary

- Generated: {ts}
- Guardrails decision: **{decision}**
- Best estimate effect per claim (Control − Treatment): **{effect}**
- Welch p-value: **{pval}**
- Segment alerts (FDR): **{n_alert}**

## What happened
- Treatment group applies the fraud review policy; Control group follows baseline.
- Estimated savings are computed as (Control mean paid − Treatment mean paid).

## What we do next
- If Guardrails is GO: continue rollout.
- If HOLD: keep current stage and monitor.
- If ROLLBACK: revert rollout stage and investigate alert segments.

## Notes
- This is an automated report generated from the latest batch run artifacts in `out/`.
"""
    write_text(md, "out/executive_summary.md")
    print("✅ wrote out/executive_summary.md")

if __name__ == "__main__":
    main()
