import json
import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split

from src.config import CFG
from src.io_utils import read_csv

def calibrate(model_path: str, out_calibrator_path: str, meta_in: str, meta_out: str, method: str = "isotonic"):
    df = read_csv(CFG.data_claims)
    if df.empty:
        raise SystemExit("Missing data for calibration")

    if CFG.label_col not in df.columns:
        raise SystemExit("No label column for calibration")

    y = pd.to_numeric(df[CFG.label_col], errors="coerce").fillna(0).astype(int).values
    model = load(model_path)

    # Build X using meta feature list if exists
    meta = json.load(open(meta_in,"r",encoding="utf-8")) if os.path.exists(meta_in) else {}
    feat_cols = meta.get("features", [])
    if feat_cols and all(c in df.columns for c in feat_cols):
        X = df[feat_cols]
    else:
        X = df.drop(columns=[c for c in [CFG.id_col, CFG.paid_col, CFG.label_col] if c in df.columns], errors="ignore")
        if X.shape[1] == 0:
            X = df[[CFG.paid_col]].rename(columns={CFG.paid_col: "paid_fallback"})

    s = model.predict_proba(X)[:,1]
    s_train, s_test, y_train, y_test = train_test_split(s, y, test_size=0.2, random_state=42, stratify=y if y.sum()>10 else None)

    if method == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(s_train, y_train)
        dump(iso, out_calibrator_path)
        meta["calibration"] = {"method":"isotonic","path": out_calibrator_path}
        json.dump(meta, open(meta_out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        print("✅ calibrated:", out_calibrator_path)
    else:
        raise SystemExit("Unsupported calibration method")

if __name__ == "__main__":
    import os
    calibrate("models/fraud_lr.joblib", "models/calibrator.joblib", "models/meta.json", "models/meta.json", "isotonic")
