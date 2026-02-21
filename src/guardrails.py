import os
import pandas as pd
from src.io_utils import read_csv, write_csv

def main():
    panel = read_csv("out/impact_panel.csv")
    sig = read_csv("out/impact_significance_scipy.csv")
    seg = read_csv("out/segment_alerts.csv")

    decision = "HOLD"
    reasons = []

    effect = None
    if not panel.empty and "effect_per_claim" in panel.columns:
        # prefer Welch if present
        hit = panel[panel["method"]=="Welch t-test (SciPy)"]
        if len(hit):
            effect = float(hit["effect_per_claim"].iloc[0])
            reasons.append("effect_source=Welch")
        else:
            effect = float(panel["effect_per_claim"].iloc[0])
            reasons.append("effect_source=panel_first")
    if effect is None:
        reasons.append("missing_effect")
        return _emit("HOLD", reasons)

    if effect <= 0:
        reasons.append(f"effect_non_positive={effect:.2f}")
        return _emit("ROLLBACK", reasons)

    if sig.empty or "welch_p_value" not in sig.columns:
        reasons.append("missing_significance")
        return _emit("HOLD", reasons)

    p = float(sig["welch_p_value"].iloc[0])
    ci_lo = float(sig["ci95_t_low"].iloc[0]) if "ci95_t_low" in sig.columns else None
    if not (p < 0.05 or (ci_lo is not None and ci_lo > 0)):
        reasons.append(f"not_significant(p={p:.4g}, ci_lo={ci_lo})")
        return _emit("HOLD", reasons)
    reasons.append(f"significant(p={p:.4g})")

    if not seg.empty and "is_alert" in seg.columns:
        n_alert = int(seg["is_alert"].fillna(False).astype(bool).sum())
        if n_alert > 0:
            reasons.append(f"segment_alerts={n_alert}")
            return _emit("ROLLBACK", reasons)
        reasons.append("segment_alerts=0")

    return _emit("GO", reasons)

def _emit(decision, reasons):
    out = pd.DataFrame([{"decision": decision, "reasons": " | ".join(reasons)}])
    write_csv(out, "out/guardrails_decision.csv")
    print("✅ wrote out/guardrails_decision.csv:", decision)
    return decision

if __name__ == "__main__":
    main()
