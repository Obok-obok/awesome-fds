import pandas as pd
import numpy as np
from scipy import stats
from src.config import CFG
from src.io_utils import read_csv, write_csv

def bh_fdr(pvals, alpha=0.1):
    p = np.array(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order]
    thresh = alpha * (np.arange(1, m+1)/m)
    passed = ranked <= thresh
    k = np.max(np.where(passed)[0]) if passed.any() else -1
    cutoff = ranked[k] if k >= 0 else None
    q = np.empty_like(p)
    # conservative q-values
    q[order] = np.minimum.accumulate((ranked*m/np.arange(1, m+1))[::-1])[::-1]
    return q, cutoff

def main():
    led = read_csv("out/decision_ledger.csv")
    if led.empty:
        print("🟨 segment_alerts: missing ledger")
        return

    # pick some candidate segment cols: low-cardinality object columns
    cand_cols = []
    for c in led.columns:
        if c in [CFG.id_col, CFG.paid_col, "score", "exp_group", "decision", "policy_version", "mode", "control_rate"]:
            continue
        if led[c].dtype == "object":
            nun = led[c].nunique(dropna=True)
            if 2 <= nun <= 30:
                cand_cols.append(c)

    rows = []
    paid = pd.to_numeric(led[CFG.paid_col], errors="coerce")
    for col in cand_cols[:8]:  # cap
        for val, sub in led.groupby(col):
            if len(sub) < 50:
                continue
            c = paid[sub["exp_group"]=="CONTROL"].dropna()
            t = paid[sub["exp_group"]=="TREATMENT"].dropna()
            if len(c) < 20 or len(t) < 20:
                continue
            effect = float(c.mean() - t.mean())
            _, p = stats.ttest_ind(c, t, equal_var=False, nan_policy="omit")
            rows.append({
                "segment_col": col,
                "segment_value": str(val),
                "n_control": int(len(c)),
                "n_treatment": int(len(t)),
                "effect_per_claim": effect,
                "p_value": float(p)
            })

    if not rows:
        print("🟨 no segments")
        return

    df = pd.DataFrame(rows)
    q, _ = bh_fdr(df["p_value"].values, alpha=0.1)
    df["p_fdr"] = q
    # alert if statistically significant negative effect (treatment worse => control - treatment < 0)
    df["is_alert"] = (df["p_fdr"] <= 0.1) & (df["effect_per_claim"] < 0)
    write_csv(df.sort_values(["is_alert","p_fdr"], ascending=[False,True]), "out/segment_alerts.csv")
    print("✅ wrote out/segment_alerts.csv")

if __name__ == "__main__":
    main()
