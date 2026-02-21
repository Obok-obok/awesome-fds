import pandas as pd
from src.config import CFG
from src.io_utils import read_csv, write_csv

def main():
    claims = read_csv(CFG.data_claims)
    fb = read_csv(CFG.data_labels_feedback)
    if claims.empty or fb.empty:
        print("🟨 skip update_labels: missing data")
        return

    if CFG.id_col not in fb.columns or "label" not in fb.columns:
        print("🟨 labels_feedback.csv missing required columns: claim_id,label")
        return

    fb = fb[[CFG.id_col, "label"]].dropna()
    fb["label"] = pd.to_numeric(fb["label"], errors="coerce").fillna(0).astype(int)

    out = claims.merge(fb, on=CFG.id_col, how="left", suffixes=("", "_fb"))
    if CFG.label_col in out.columns:
        # prefer feedback if present
        out[CFG.label_col] = out["label_fb"].where(out["label_fb"].notna(), out[CFG.label_col] if CFG.label_col in claims.columns else 0)
    else:
        out[CFG.label_col] = out["label_fb"].fillna(0)

    out = out.drop(columns=[c for c in ["label_fb"] if c in out.columns])
    write_csv(out, CFG.data_claims)
    print("✅ labels updated into", CFG.data_claims)

if __name__ == "__main__":
    main()
