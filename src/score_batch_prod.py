import os, json
import pandas as pd
import numpy as np
from joblib import load

from src.config import CFG
from src.io_utils import ensure_dirs, read_csv, write_csv
from src.policy_registry import ensure_policy_registry, load_policy
from src.experiment import assign_group

def _get_X(df, meta_path):
    meta = json.load(open(meta_path,"r",encoding="utf-8")) if os.path.exists(meta_path) else {}
    feat_cols = meta.get("features", [])
    if feat_cols and all(c in df.columns for c in feat_cols):
        return df[feat_cols]
    X = df.drop(columns=[c for c in [CFG.id_col, CFG.paid_col, CFG.label_col] if c in df.columns], errors="ignore")
    if X.shape[1] == 0:
        X = df[[CFG.paid_col]].rename(columns={CFG.paid_col:"paid_fallback"})
    return X

def main():
    ensure_dirs(CFG.out_dir, CFG.model_dir)
    ensure_policy_registry(CFG.default_control_rate)
    pol = load_policy()["current"]
    control_rate = float(pol["control_rate"])
    policy_version = pol.get("policy_version","P?")
    mode = pol.get("mode","EXPERIMENT")

    df = read_csv(CFG.data_claims)
    if df.empty:
        raise SystemExit("Missing claims data")

    # load champion + optional calibrator
    model = load("models/champion.joblib") if os.path.exists("models/champion.joblib") else load("models/fraud_lr.joblib")
    meta_path = "models/meta_champion.json" if os.path.exists("models/meta_champion.json") else "models/meta.json"
    calibrator_path = "models/calibrator.joblib"
    calibrator = load(calibrator_path) if os.path.exists(calibrator_path) else None

    X = _get_X(df, meta_path)
    raw = model.predict_proba(X)[:,1]
    if calibrator is not None:
        try:
            score = calibrator.predict(raw)
        except Exception:
            score = raw
    else:
        score = raw

    out = df[[c for c in [CFG.id_col, CFG.paid_col] if c in df.columns]].copy()
    out["score"] = score
    out["exp_group"] = out[CFG.id_col].astype(str).apply(lambda cid: assign_group(cid, CFG.experiment_salt, control_rate))

    # Decision policy: review queue for treatment only unless baseline-only
    if mode == "BASELINE_ONLY":
        out["decision"] = "PAY"
    else:
        out["decision"] = np.where((out["exp_group"]=="TREATMENT") & (out["score"] >= CFG.review_threshold), "REVIEW", "PAY")

    # review queue (cap)
    rq = out[out["decision"]=="REVIEW"].sort_values("score", ascending=False).head(CFG.max_daily_reviews).copy()
    write_csv(rq, "out/review_queue.csv")

    # ledger (audit)
    out_ledger = out.copy()
    out_ledger["policy_version"] = policy_version
    out_ledger["mode"] = mode
    out_ledger["control_rate"] = control_rate
    write_csv(out_ledger, "out/decision_ledger.csv")

    print("✅ wrote out/review_queue.csv and out/decision_ledger.csv")

if __name__ == "__main__":
    main()
