"""src/explainability.py

Big-tech style explainability utilities for the Fraud/FDS demo.

Goals
- Provide **human readable** reasons why a claim looks risky.
- Offer **model-based** explanations when a linear model is available.
- Produce **profiles** comparing high-risk vs low-risk populations.

Notes
- This is designed to work offline on a small VM.
- For production, replace rule reasons with curated fraud typologies and
  use a governed explainer (e.g., SHAP + monitoring + approvals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ----------------------------
# Rule-based (always-available) reasons
# ----------------------------


@dataclass(frozen=True)
class RiskRule:
    key: str
    title: str
    weight: float


RULES: List[RiskRule] = [
    RiskRule("short_tenure", "가입 경과가 짧음(초기 청구)", 1.2),
    RiskRule("high_ratio", "청구금액/월보험료 비율이 비정상적으로 큼", 1.1),
    RiskRule("many_prior", "최근 12개월 청구 이력이 많음", 1.0),
    RiskRule("acct_change", "최근 계좌 변경(수령 계좌) 발생", 0.9),
    RiskRule("far_provider", "병원 거리/이동이 과도함", 0.7),
    RiskRule("low_docs", "제출 서류가 부족/미흡", 0.6),
]


def _num(x: Any, default: float = np.nan) -> float:
    try:
        v = float(x)
        return v
    except Exception:
        return default


def risk_rule_flags(row: Dict[str, Any]) -> Dict[str, Tuple[bool, float, str]]:
    """Return flags for each rule: (triggered, score, short evidence)."""
    elapsed = _num(row.get("elapsed_months"), np.nan)
    claim_amt = _num(row.get("claim_amount", row.get("paid_amount", 0)), 0.0)
    prem = max(_num(row.get("premium_monthly"), 1.0), 1.0)
    prior_n = _num(row.get("prior_claim_cnt_12m"), 0.0)
    acct = _num(row.get("bank_account_changed_recently"), 0.0)
    dist = _num(row.get("provider_distance_km"), 0.0)
    docs = _num(row.get("doc_uploaded_cnt"), 0.0)

    ratio = claim_amt / prem

    flags: Dict[str, Tuple[bool, float, str]] = {}
    flags["short_tenure"] = (
        (not np.isnan(elapsed) and elapsed < 6),
        float(6 - elapsed) if not np.isnan(elapsed) else 0.0,
        f"elapsed_months={elapsed:.0f}" if not np.isnan(elapsed) else "elapsed_months=NA",
    )
    flags["high_ratio"] = (
        ratio >= 50,
        float(min(5.0, ratio / 50.0)),
        f"claim/premium={ratio:.1f}",
    )
    flags["many_prior"] = (
        prior_n >= 2,
        float(prior_n),
        f"prior_claim_cnt_12m={prior_n:.0f}",
    )
    flags["acct_change"] = (
        acct >= 1,
        float(acct),
        f"bank_account_changed_recently={acct:.0f}",
    )
    flags["far_provider"] = (
        dist >= 30,
        float(dist),
        f"provider_distance_km={dist:.1f}",
    )
    flags["low_docs"] = (
        docs <= 1,
        float(max(0.0, 2 - docs)),
        f"doc_uploaded_cnt={docs:.0f}",
    )
    return flags


def summarize_rule_reasons(row: Dict[str, Any], topk: int = 3) -> Tuple[str, List[Dict[str, Any]]]:
    flags = risk_rule_flags(row)
    scored = []
    for rr in RULES:
        trig, mag, ev = flags.get(rr.key, (False, 0.0, ""))
        if trig:
            scored.append({
                "reason": rr.title,
                "rule": rr.key,
                "weight": rr.weight,
                "magnitude": float(mag),
                "evidence": ev,
                "score": float(rr.weight * (1.0 + mag)),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:topk]
    short = "; ".join([f"{t['reason']} ({t['evidence']})" for t in top]) if top else "—"
    return short, top


# ----------------------------
# Profile comparison utilities
# ----------------------------


def compare_profiles(df: pd.DataFrame, score_col: str = "score") -> Dict[str, pd.DataFrame]:
    """Compare high-risk vs low-risk groups.

    Returns a dict with tables:
    - numeric: mean/median differences for numeric columns
    - categorical: top category share differences for selected categorical columns
    """
    if df is None or df.empty or score_col not in df.columns:
        return {"numeric": pd.DataFrame(), "categorical": pd.DataFrame()}

    d = df.copy()
    d[score_col] = pd.to_numeric(d[score_col], errors="coerce")
    d = d.dropna(subset=[score_col])
    if d.empty:
        return {"numeric": pd.DataFrame(), "categorical": pd.DataFrame()}

    hi = d[d[score_col] >= d[score_col].quantile(0.9)].copy()
    lo = d[d[score_col] <= d[score_col].quantile(0.1)].copy()
    if hi.empty or lo.empty:
        return {"numeric": pd.DataFrame(), "categorical": pd.DataFrame()}

    num_cols = [c for c in [
        "elapsed_months", "claim_amount", "premium_monthly", "prior_claim_cnt_12m",
        "provider_distance_km", "doc_uploaded_cnt", "age",
    ] if c in d.columns]

    out_num = []
    for c in num_cols:
        hi_v = pd.to_numeric(hi[c], errors="coerce")
        lo_v = pd.to_numeric(lo[c], errors="coerce")
        out_num.append({
            "feature": c,
            "high_mean": float(hi_v.mean()),
            "low_mean": float(lo_v.mean()),
            "mean_diff": float(hi_v.mean() - lo_v.mean()),
            "high_median": float(hi_v.median()),
            "low_median": float(lo_v.median()),
        })
    num_tbl = pd.DataFrame(out_num).sort_values("mean_diff", key=lambda s: s.abs(), ascending=False)

    cat_cols = [c for c in ["channel", "product_line", "product", "region", "hospital_grade"] if c in d.columns]
    out_cat = []
    for c in cat_cols:
        hi_share = hi[c].astype(str).value_counts(normalize=True).head(5)
        lo_share = lo[c].astype(str).value_counts(normalize=True).head(5)
        keys = sorted(set(hi_share.index.tolist() + lo_share.index.tolist()))
        for k in keys:
            out_cat.append({
                "feature": c,
                "category": k,
                "high_share": float(hi_share.get(k, 0.0)),
                "low_share": float(lo_share.get(k, 0.0)),
                "share_diff": float(hi_share.get(k, 0.0) - lo_share.get(k, 0.0)),
            })
    cat_tbl = pd.DataFrame(out_cat)
    if not cat_tbl.empty:
        cat_tbl = cat_tbl.sort_values("share_diff", key=lambda s: s.abs(), ascending=False).head(30)

    return {"numeric": num_tbl, "categorical": cat_tbl}


# ----------------------------
# Model-based explanations (best-effort)
# ----------------------------


def linear_model_contributions(pipeline: Any, X: pd.DataFrame, topk: int = 5) -> List[List[Dict[str, Any]]]:
    """Best-effort contributions for linear models inside a sklearn Pipeline.

    Works for:
    - Pipeline(preprocess -> LogisticRegression)

    Returns per-row list of top positive contributors.
    If introspection fails, returns empty lists.
    """
    try:
        # Locate steps
        if hasattr(pipeline, "named_steps"):
            steps = pipeline.named_steps
            # heuristics
            pre = None
            clf = None
            for k, v in steps.items():
                if "pre" in k or "prep" in k or "transform" in k or "ct" in k:
                    pre = v
                if "log" in k or "clf" in k or "model" in k:
                    clf = v
            if pre is None:
                # fallback: first step
                pre = list(steps.values())[0]
            if clf is None:
                clf = list(steps.values())[-1]
        else:
            return [[] for _ in range(len(X))]

        Xt = pre.transform(X)
        if hasattr(pre, "get_feature_names_out"):
            names = pre.get_feature_names_out()
        else:
            names = np.array([f"f{i}" for i in range(Xt.shape[1])])

        coef = getattr(clf, "coef_", None)
        if coef is None:
            return [[] for _ in range(len(X))]
        w = np.asarray(coef).reshape(-1)

        # contributions = x_i * w
        out: List[List[Dict[str, Any]]] = []
        for i in range(Xt.shape[0]):
            row = Xt[i]
            if hasattr(row, "toarray"):
                row = row.toarray().reshape(-1)
            else:
                row = np.asarray(row).reshape(-1)
            contrib = row * w
            idx = np.argsort(contrib)[::-1]
            top = []
            for j in idx[: topk * 3]:
                if contrib[j] <= 0:
                    continue
                top.append({"feature": str(names[j]), "contrib": float(contrib[j])})
                if len(top) >= topk:
                    break
            out.append(top)
        return out
    except Exception:
        return [[] for _ in range(len(X))]
