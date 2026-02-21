import json
import numpy as np
import pandas as pd
from joblib import load
from sklearn.metrics import roc_auc_score, average_precision_score

from src.config import CFG
from src.io_utils import read_csv, write_csv
from src.registry import init_champion_if_missing, CHAMPION, CHALLENGER, META_CHAMP, META_CHALL

def _get_X(df, meta_path):
    meta = json.load(open(meta_path,"r",encoding="utf-8")) if meta_path and os.path.exists(meta_path) else {}
    feat_cols = meta.get("features", [])
    if feat_cols and all(c in df.columns for c in feat_cols):
        return df[feat_cols]
    X = df.drop(columns=[c for c in [CFG.id_col, CFG.paid_col, CFG.label_col] if c in df.columns], errors="ignore")
    if X.shape[1] == 0:
        X = df[[CFG.paid_col]].rename(columns={CFG.paid_col:"paid_fallback"})
    return X

def main():
    init_champion_if_missing()
    df = read_csv(CFG.data_claims)
    if df.empty or CFG.label_col not in df.columns:
        print("🟨 score_cc: missing label, skip")
        return

    y = pd.to_numeric(df[CFG.label_col], errors="coerce").fillna(0).astype(int).values

    champ = load(CHAMPION)
    chall = load(CHALLENGER) if os.path.exists(CHALLENGER) else None

    Xc = _get_X(df, META_CHAMP)
    pc = champ.predict_proba(Xc)[:,1]

    out = {"model":"champion", "roc_auc": float("nan"), "avg_precision": float("nan")}
    if len(np.unique(y))>1:
        out["roc_auc"] = roc_auc_score(y, pc)
        out["avg_precision"] = average_precision_score(y, pc)

    rows = [out]

    if chall is not None and os.path.exists(META_CHALL):
        Xh = _get_X(df, META_CHALL)
        ph = chall.predict_proba(Xh)[:,1]
        out2 = {"model":"challenger", "roc_auc": float("nan"), "avg_precision": float("nan")}
        if len(np.unique(y))>1:
            out2["roc_auc"] = roc_auc_score(y, ph)
            out2["avg_precision"] = average_precision_score(y, ph)
        rows.append(out2)

    res = pd.DataFrame(rows)
    write_csv(res, "out/cc_metrics.csv")
    print("✅ wrote out/cc_metrics.csv")

if __name__ == "__main__":
    import os
    main()
