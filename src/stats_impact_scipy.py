import numpy as np
import pandas as pd
from scipy import stats
from src.config import CFG
from src.io_utils import read_csv, write_csv

def main():
    led = read_csv("out/decision_ledger.csv")
    if led.empty or "exp_group" not in led.columns:
        print("🟨 stats_impact_scipy: missing ledger")
        return

    x = pd.to_numeric(led.get(CFG.paid_col), errors="coerce")
    c = x[led["exp_group"]=="CONTROL"].dropna()
    t = x[led["exp_group"]=="TREATMENT"].dropna()
    if len(c)<5 or len(t)<5:
        print("🟨 insufficient samples")
        return

    effect = float(c.mean() - t.mean())
    tstat, p = stats.ttest_ind(c, t, equal_var=False, nan_policy="omit")

    # CI using t distribution
    se = float(np.sqrt(c.var(ddof=1)/len(c) + t.var(ddof=1)/len(t)))
    df = float((c.var(ddof=1)/len(c) + t.var(ddof=1)/len(t))**2 / ((c.var(ddof=1)/len(c))**2/(len(c)-1) + (t.var(ddof=1)/len(t))**2/(len(t)-1)))
    alpha = 0.05
    crit = stats.t.ppf(1-alpha/2, df)
    ci_lo, ci_hi = effect - crit*se, effect + crit*se

    out = pd.DataFrame([{
        "paid_col_used": CFG.paid_col,
        "n_control": int(len(c)),
        "n_treatment": int(len(t)),
        "effect_per_claim": effect,
        "welch_p_value": float(p),
        "ci95_t_low": float(ci_lo),
        "ci95_t_high": float(ci_hi),
    }])
    write_csv(out, "out/impact_significance_scipy.csv")
    print("✅ wrote out/impact_significance_scipy.csv")

if __name__ == "__main__":
    main()
