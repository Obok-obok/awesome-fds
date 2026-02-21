import json
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from src.config import CFG
from src.io_utils import ensure_dirs, read_csv
from src.features import build_preprocessor

def main():
    ensure_dirs(CFG.model_dir, CFG.out_dir)
    df = read_csv(CFG.data_claims)
    if df.empty:
        raise SystemExit("Missing claims dataset")

    # label might be missing -> create weak label (placeholder) from heuristics (paid extreme)
    if CFG.label_col not in df.columns:
        q = pd.to_numeric(df[CFG.paid_col], errors="coerce").fillna(0)
        df[CFG.label_col] = (q > q.quantile(0.98)).astype(int)

    y = pd.to_numeric(df[CFG.label_col], errors="coerce").fillna(0).astype(int).values

    pre, feat_cols, num_cols, cat_cols = build_preprocessor(df, CFG.id_col, CFG.paid_col, CFG.label_col)

    clf = LogisticRegression(max_iter=200, n_jobs=1)
    pipe = Pipeline([("pre", pre), ("clf", clf)])

    X = df[feat_cols] if feat_cols else df[[CFG.paid_col]].copy()  # fallback
    if not feat_cols:
        X = X.rename(columns={CFG.paid_col: "paid_fallback"})
        pre2, *_ = build_preprocessor(pd.concat([df[[CFG.id_col, CFG.paid_col, CFG.label_col]], X], axis=1),
                                      CFG.id_col, CFG.paid_col, CFG.label_col)
        pipe = Pipeline([("pre", pre2), ("clf", clf)])

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y if y.sum()>10 else None)
    pipe.fit(X_train, y_train)

    p = pipe.predict_proba(X_test)[:,1]
    auc = roc_auc_score(y_test, p) if len(np.unique(y_test))>1 else float("nan")
    ap = average_precision_score(y_test, p) if len(np.unique(y_test))>1 else float("nan")

    dump(pipe, "models/fraud_lr.joblib")

    meta = {
        "model_name": "fraud_lr",
        "features": feat_cols,
        "num_cols": num_cols,
        "cat_cols": cat_cols,
        "metrics": {"roc_auc": auc, "avg_precision": ap},
    }
    json.dump(meta, open("models/meta.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✅ trained models/fraud_lr.joblib", meta["metrics"])

if __name__ == "__main__":
    main()
