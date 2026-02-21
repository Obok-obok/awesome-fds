import pandas as pd
import numpy as np
from src.config import CFG
from src.io_utils import read_csv, write_csv

def main():
    led = read_csv("out/decision_ledger.csv")
    if led.empty or "exp_group" not in led.columns:
        print("🟨 impact_causal: missing ledger/exp_group")
        return

    led[CFG.paid_col] = pd.to_numeric(led.get(CFG.paid_col), errors="coerce")
    c = led[led["exp_group"]=="CONTROL"][CFG.paid_col].dropna()
    t = led[led["exp_group"]=="TREATMENT"][CFG.paid_col].dropna()
    if len(c)<5 or len(t)<5:
        print("🟨 impact_causal: insufficient samples")
        return

    effect = float(c.mean() - t.mean())
    out = pd.DataFrame([{
        "method": "Unadjusted (Diff-in-Means)",
        "effect_per_claim": effect,
        "n_control": int(len(c)),
        "n_treatment": int(len(t))
    }])
    write_csv(out, "out/impact_causal.csv")
    print("✅ wrote out/impact_causal.csv")

if __name__ == "__main__":
    main()
