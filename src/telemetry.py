"""Telemetry & KPI computations.

This module centralizes operational KPI calculations used by the Streamlit
executive dashboard and the PDF one-pager.

Design goals (big-tech style):
- Prefer aggregated telemetry (timeseries) as source of truth.
- Fall back to raw ledgers when needed.
- Be resilient to missing/dirty data (never crash the dashboard).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SavingKPI:
    asof_date: Optional[pd.Timestamp]
    saving_today: Optional[float]
    saving_mtd: Optional[float]
    saving_qtd: Optional[float]
    dod_pct: Optional[float]
    ma7: Optional[float]
    target_mtd: Optional[float]
    target_qtd: Optional[float]
    mtd_progress: Optional[float]
    qtd_progress: Optional[float]


@dataclass(frozen=True)
class OpsKPI:
    asof_date: Optional[pd.Timestamp]
    claims_today: Optional[int]
    treatment_rate_today: Optional[float]
    review_rate_today: Optional[float]
    avg_score_today: Optional[float]
    control_rate_observed: Optional[float]


def _safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        if np.isnan(v):
            return None
        return v
    except Exception:
        return None


def compute_savings_from_timeseries(ts: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], Optional[float], Optional[float], Optional[float]]:
    """Compute Today/MTD/QTD from out/impact_monthly_timeseries.csv.

    Expected columns:
      - date (YYYY-MM-DD)
      - saving_est_krw (numeric)

    Returns: (asof_date, today, mtd, qtd)
    """
    if ts is None or ts.empty:
        return (None, None, None, None)

    if "date" not in ts.columns or "saving_est_krw" not in ts.columns:
        return (None, None, None, None)

    df = ts.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["saving_est_krw"] = pd.to_numeric(df["saving_est_krw"], errors="coerce")
    df = df.dropna(subset=["date", "saving_est_krw"]).sort_values("date")
    if df.empty:
        return (None, None, None, None)

    asof = df["date"].max().normalize()

    # TODAY
    today_val = float(df.loc[df["date"].dt.normalize() == asof, "saving_est_krw"].sum())

    # MTD
    m_start = asof.replace(day=1)
    mtd_val = float(df.loc[(df["date"] >= m_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    # QTD
    q = (asof.month - 1) // 3 + 1
    q_start_month = 1 + 3 * (q - 1)
    q_start = asof.replace(month=q_start_month, day=1)
    qtd_val = float(df.loc[(df["date"] >= q_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    return (asof, today_val, mtd_val, qtd_val)


def compute_savings_from_ledger(effect_per_claim: float, ledger: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], Optional[float], Optional[float], Optional[float]]:
    """Compute Today/MTD/QTD from raw decision ledger.

    - Uses effect_per_claim (KRW per claim)
    - Multiplies by number of TREATMENT claims in each period.

    Expected columns:
      - claim_date (date)
      - exp_group (CONTROL/TREATMENT)

    Returns: (asof_date, today, mtd, qtd)
    """
    eff = _safe_float(effect_per_claim)
    if eff is None:
        return (None, None, None, None)

    if ledger is None or ledger.empty:
        return (None, None, None, None)

    # tolerant aliasing
    df = ledger.copy()
    if "claim_date" not in df.columns and "date" in df.columns:
        df["claim_date"] = df["date"]
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]

    if "claim_date" not in df.columns or "exp_group" not in df.columns:
        return (None, None, None, None)

    df["claim_date"] = pd.to_datetime(df["claim_date"], errors="coerce")
    df = df.dropna(subset=["claim_date"])
    if df.empty:
        return (None, None, None, None)

    asof = df["claim_date"].max().normalize()
    t = df[df["exp_group"].astype(str).str.upper().eq("TREATMENT")]
    if t.empty:
        return (asof, 0.0, 0.0, 0.0)

    # TODAY
    n_today = (t["claim_date"].dt.normalize() == asof).sum()
    saving_today = eff * float(n_today)

    # MTD
    m_start = asof.replace(day=1)
    n_mtd = ((t["claim_date"] >= m_start) & (t["claim_date"] < asof + pd.Timedelta(days=1))).sum()
    saving_mtd = eff * float(n_mtd)

    # QTD
    q = (asof.month - 1) // 3 + 1
    q_start_month = 1 + 3 * (q - 1)
    q_start = asof.replace(month=q_start_month, day=1)
    n_qtd = ((t["claim_date"] >= q_start) & (t["claim_date"] < asof + pd.Timedelta(days=1))).sum()
    saving_qtd = eff * float(n_qtd)

    return (asof, saving_today, saving_mtd, saving_qtd)


def compute_saving_kpis(
    ts: Optional[pd.DataFrame],
    effect_per_claim: Optional[float],
    ledger: Optional[pd.DataFrame],
    target_mtd: float,
    target_qtd: float,
) -> SavingKPI:
    """Compute a full KPI bundle, preferring timeseries then ledger."""

    asof, today, mtd, qtd = compute_savings_from_timeseries(ts if ts is not None else pd.DataFrame())

    if asof is None:
        asof, today, mtd, qtd = compute_savings_from_ledger(effect_per_claim or np.nan, ledger if ledger is not None else pd.DataFrame())

    dod_pct = None
    ma7 = None

    if ts is not None and (asof is not None) and (not ts.empty) and ("date" in ts.columns) and ("saving_est_krw" in ts.columns):
        df = ts.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["saving_est_krw"] = pd.to_numeric(df["saving_est_krw"], errors="coerce")
        df = df.dropna(subset=["date", "saving_est_krw"]).sort_values("date")

        prev = asof - pd.Timedelta(days=1)
        prev_val = float(df.loc[df["date"].dt.normalize() == prev, "saving_est_krw"].sum())
        if prev_val > 0 and today is not None:
            dod_pct = (float(today) - prev_val) / prev_val

        last7 = df[df["date"] >= (asof - pd.Timedelta(days=6))]
        if len(last7):
            ma7 = float(last7["saving_est_krw"].mean())

    mtd_progress = None
    qtd_progress = None
    if mtd is not None and target_mtd > 0:
        mtd_progress = float(mtd) / float(target_mtd)
    if qtd is not None and target_qtd > 0:
        qtd_progress = float(qtd) / float(target_qtd)

    return SavingKPI(
        asof_date=asof,
        saving_today=today,
        saving_mtd=mtd,
        saving_qtd=qtd,
        dod_pct=dod_pct,
        ma7=ma7,
        target_mtd=target_mtd,
        target_qtd=target_qtd,
        mtd_progress=mtd_progress,
        qtd_progress=qtd_progress,
    )


def compute_ops_kpis(ledger: Optional[pd.DataFrame]) -> OpsKPI:
    """Compute operational KPIs from decision ledger.

    Expected columns (aliases supported):
      - claim_date / date
      - exp_group / group
      - decision (PAY/REVIEW)
      - score (0..1)

    Returns None fields if ledger is missing/invalid.
    """
    if ledger is None or ledger.empty:
        return OpsKPI(None, None, None, None, None, None)

    df = ledger.copy()
    if "claim_date" not in df.columns and "date" in df.columns:
        df["claim_date"] = df["date"]
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]

    if "claim_date" not in df.columns:
        return OpsKPI(None, None, None, None, None, None)

    df["claim_date"] = pd.to_datetime(df["claim_date"], errors="coerce")
    df = df.dropna(subset=["claim_date"])
    if df.empty:
        return OpsKPI(None, None, None, None, None, None)

    asof = df["claim_date"].max().normalize()
    d0 = df[df["claim_date"].dt.normalize() == asof]
    if d0.empty:
        return OpsKPI(asof, 0, None, None, None, None)

    n = int(len(d0))

    # observed control rate (full window)
    control_rate = None
    if "exp_group" in df.columns:
        g = df["exp_group"].astype(str).str.upper()
        if len(g):
            control_rate = float((g == "CONTROL").mean())

    # today treatment share
    treat_rate = None
    if "exp_group" in d0.columns:
        g0 = d0["exp_group"].astype(str).str.upper()
        if len(g0):
            treat_rate = float((g0 == "TREATMENT").mean())

    # today review rate
    review_rate = None
    if "decision" in d0.columns:
        dec = d0["decision"].astype(str).str.upper()
        if len(dec):
            review_rate = float((dec == "REVIEW").mean())

    # today avg score
    avg_score = None
    if "score" in d0.columns:
        s = pd.to_numeric(d0["score"], errors="coerce")
        if s.notna().any():
            avg_score = float(s.mean())

    return OpsKPI(asof, n, treat_rate, review_rate, avg_score, control_rate)
