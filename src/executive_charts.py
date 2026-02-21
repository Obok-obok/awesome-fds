# src/executive_charts.py (BCG minimal)
"""Generate only charts that directly support program decisions.

Outputs:
- out/impact_daily_delta.csv  (daily Control−Treatment delta paid)
- out/chart_impact_delta.png  (trend chart used by dashboard + PDF)

This intentionally removes decorative 'monthly/cumulative saving' charts.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OUT_DIR = "out"
LEDGER_PATH = os.path.join(OUT_DIR, "decision_ledger.csv")

DAILY_DELTA_CSV = os.path.join(OUT_DIR, "impact_daily_delta.csv")
DELTA_PNG = os.path.join(OUT_DIR, "chart_impact_delta.png")


def _daily_group_metrics(ledger: pd.DataFrame) -> pd.DataFrame:
    df = ledger.copy()

    # tolerate schema drift
    if "claim_date" not in df.columns and "date" in df.columns:
        df["claim_date"] = df["date"]

    df["claim_date"] = pd.to_datetime(df.get("claim_date"), errors="coerce")

    # paid amount
    if "paid_amount" not in df.columns and "paid" in df.columns:
        df["paid_amount"] = df["paid"]
    df["paid_amount"] = pd.to_numeric(df.get("paid_amount"), errors="coerce")

    # exp group
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]
    df["exp_group"] = df.get("exp_group").astype(str).str.upper()

    # decision
    if "decision" not in df.columns:
        df["decision"] = "PAY"

    df = df.dropna(subset=["claim_date", "paid_amount"])
    if df.empty:
        return pd.DataFrame()

    df["date"] = df["claim_date"].dt.normalize()

    def _review_rate(s: pd.Series) -> float:
        ss = s.astype(str).str.upper()
        return float((ss == "REVIEW").mean()) if len(ss) else 0.0

    g = df.groupby(["date", "exp_group"], as_index=False).agg(
        n=("paid_amount", "size"),
        avg_paid=("paid_amount", "mean"),
        review_rate=("decision", _review_rate),
    )
    return g


def _build_daily_delta(g: pd.DataFrame) -> pd.DataFrame:
    if g is None or g.empty:
        return pd.DataFrame()

    c = g[g["exp_group"] == "CONTROL"][
        ["date", "avg_paid", "n", "review_rate"]
    ].rename(columns={"avg_paid": "avg_paid_c", "n": "n_c", "review_rate": "review_rate_c"})

    t = g[g["exp_group"] == "TREATMENT"][
        ["date", "avg_paid", "n", "review_rate"]
    ].rename(columns={"avg_paid": "avg_paid_t", "n": "n_t", "review_rate": "review_rate_t"})

    m = c.merge(t, on="date", how="inner")
    if m.empty:
        return m

    m["delta_paid_c_minus_t"] = m["avg_paid_c"] - m["avg_paid_t"]
    return m.sort_values("date")


def _plot_delta(m: pd.DataFrame):
    if m is None or m.empty:
        return

    df = m.tail(60)

    fig, ax = plt.subplots(figsize=(10.24, 4.0), dpi=140)
    ax.plot(df["date"], df["delta_paid_c_minus_t"], linewidth=2)
    ax.axhline(0, linestyle="--", linewidth=1)

    ax.set_title("Daily Δ Paid (Control − Treatment)", loc="left", fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", linewidth=0.4, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{int(x):,}"))
    fig.tight_layout()

    os.makedirs(OUT_DIR, exist_ok=True)
    fig.savefig(DELTA_PNG)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not os.path.exists(LEDGER_PATH):
        print("Missing ledger:", LEDGER_PATH)
        return

    ledger = pd.read_csv(LEDGER_PATH)
    if ledger.empty:
        print("Empty ledger")
        return

    g = _daily_group_metrics(ledger)
    m = _build_daily_delta(g)

    if m.empty:
        print("Not enough CONTROL/TREATMENT overlap to compute daily delta")
        return

    m.to_csv(DAILY_DELTA_CSV, index=False, encoding="utf-8")
    _plot_delta(m)

    print("Wrote:", DAILY_DELTA_CSV)
    print("Wrote:", DELTA_PNG)


if __name__ == "__main__":
    main()
