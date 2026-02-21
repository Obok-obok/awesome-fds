import pandas as pd
from src.io_utils import read_csv, write_csv

def main():
    rows = []
    for f in ["out/impact_causal.csv"]:
        df = read_csv(f)
        if not df.empty:
            rows.append(df)
    # add welch row from significance
    sig = read_csv("out/impact_significance_scipy.csv")
    if not sig.empty:
        rows.append(pd.DataFrame([{
            "method":"Welch t-test (SciPy)",
            "effect_per_claim": float(sig["effect_per_claim"].iloc[0]),
            "p_value": float(sig["welch_p_value"].iloc[0]),
            "n_control": int(sig["n_control"].iloc[0]),
            "n_treatment": int(sig["n_treatment"].iloc[0]),
        }]))
    if rows:
        out = pd.concat(rows, ignore_index=True)
        write_csv(out, "out/impact_panel.csv")
        print("✅ wrote out/impact_panel.csv")
    else:
        print("🟨 no impact rows")

if __name__ == "__main__":
    main()
