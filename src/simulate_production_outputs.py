"""src/simulate_production_outputs.py

운영 대시보드 데모/테스트를 위한 "가짜(시뮬레이션) 생산 결과" 생성기.

왜 필요?
- 실제 운영에서는 KPI/효과/가드레일/차트가 모두 out/ 텔레메트리로 채워짐
- 개발/데모 환경에서는 out/ 파일이 비어있어 대시보드가 NA/—로 보이기 쉬움

생성 산출물 (out/):
- impact_monthly_timeseries.csv   : 일별 절감액/누적
- impact_panel.csv                : 효과 추정 패널(대표 2~3개 방법)
- impact_significance_scipy.csv   : welch_p_value 포함
- guardrails_decision.csv         : GO/HOLD/ROLLBACK
- segment_alerts.csv              : is_alert 포함
- decision_ledger.csv             : 운영 원장(옵션, dashboard fallback)
- executive_summary.md            : 임원 요약(시뮬레이션 문구 포함)

사용 예)
  python -m src.simulate_production_outputs --scenario GO
  python -m src.simulate_production_outputs --scenario HOLD --days 90
  python -m src.simulate_production_outputs --scenario ROLLBACK --seed 13

"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from src.config import CFG


OUT_DIR = "out"


def _ensure_out():
    os.makedirs(OUT_DIR, exist_ok=True)


def _scenario_params(name: str):
    """시나리오별로 KPI 성격을 바꿔서 '운영 느낌'을 강화."""
    n = (name or "GO").upper().strip()

    if n == "GO":
        return {
            "guard": "GO",
            "welch_p": 0.031,
            "effect": 14767,
            "seg_alerts": 0,
            "base_daily": 8_000_000,
        }
    if n == "HOLD":
        return {
            "guard": "HOLD",
            "welch_p": 0.12,
            "effect": 6200,
            "seg_alerts": 2,
            "base_daily": 4_200_000,
        }
    if n == "ROLLBACK":
        return {
            "guard": "ROLLBACK",
            "welch_p": 0.60,
            "effect": -3800,
            "seg_alerts": 4,
            "base_daily": 1_200_000,
        }

    # default
    return {
        "guard": n,
        "welch_p": 0.20,
        "effect": 8000,
        "seg_alerts": 1,
        "base_daily": 5_000_000,
    }


def _make_timeseries(days: int, seed: int, base_daily: int):
    rng = np.random.default_rng(seed)

    end = date.today()
    start = end - timedelta(days=days - 1)
    idx = pd.date_range(start=start, end=end, freq="D")

    # 요일 효과(주말 감소) + 노이즈
    weekday_mult = np.where(idx.weekday < 5, 1.0, 0.65)
    noise = rng.normal(0, base_daily * 0.15, size=len(idx))

    daily = np.maximum(0, (base_daily * weekday_mult + noise)).astype(int)
    cum = np.cumsum(daily).astype(int)

    ts = pd.DataFrame({
        "date": idx.date.astype(str),
        "saving_est_krw": daily,
        "saving_cum_krw": cum,
    })
    return ts


def _kpi_from_ts(ts: pd.DataFrame):
    df = ts.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["saving_est_krw"] = pd.to_numeric(df["saving_est_krw"], errors="coerce")
    df = df.dropna(subset=["date", "saving_est_krw"]).sort_values("date")

    if df.empty:
        return None, None, None, None

    asof = df["date"].max().normalize()

    today = float(df.loc[df["date"].dt.normalize() == asof, "saving_est_krw"].sum())

    m_start = asof.replace(day=1)
    mtd = float(df.loc[(df["date"] >= m_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    q = (asof.month - 1)//3 + 1
    q_start_month = 1 + 3*(q-1)
    q_start = asof.replace(month=q_start_month, day=1)
    qtd = float(df.loc[(df["date"] >= q_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    return asof, int(today), int(mtd), int(qtd)


def _write_csv(df: pd.DataFrame, name: str):
    df.to_csv(os.path.join(OUT_DIR, name), index=False, encoding="utf-8")


def _simulate_decision_ledger(ts: pd.DataFrame, seed: int, control_rate: float, effect_per_claim: int, review_threshold: float):
    """대시보드 fallback/운영 원장용.

    핵심 목표:
    - CONTROL vs TREATMENT 간 유의미한 차이가 "데이터"에서 보이도록 생성
    - 대시보드에서 group-by 차트/테이블로 즉시 확인 가능

    설계:
    - 기본 paid_amount는 동일 분포에서 샘플
    - TREATMENT는 평균적으로 paid_amount가 (effect_per_claim) 만큼 낮도록 shift
    - REVIEW로 분류된 케이스는 추가 감액(추가 절감) 효과를 부여
    """
    rng = np.random.default_rng(seed)
    rows = []

    # Prefer using real-ish claim rows if present.
    # This makes segment HTE, profiling, and explainability much more realistic.
    claims_path = os.path.join("data", "claims.csv")
    claims = pd.DataFrame()
    if os.path.exists(claims_path):
        try:
            claims = pd.read_csv(claims_path)
        except Exception:
            claims = pd.DataFrame()

    dates = pd.to_datetime(ts["date"], errors="coerce").dropna().dt.date.unique()
    if not claims.empty and "claim_id" in claims.columns:
        # Ensure claim_date exists and spans the simulation window.
        if "claim_date" not in claims.columns:
            claims = claims.copy()
            claims["claim_date"] = rng.choice(dates, size=len(claims), replace=True)
        else:
            claims = claims.copy()
            claims["claim_date"] = pd.to_datetime(claims["claim_date"], errors="coerce").dt.date
            mask = claims["claim_date"].isna()
            if mask.any():
                claims.loc[mask, "claim_date"] = rng.choice(dates, size=int(mask.sum()), replace=True)

        # Sample claims per day to create a production-like ledger.
        for d in dates:
            # sample size
            n = int(max(80, rng.normal(240, 40)))
            sample = claims.sample(
                n=min(n, len(claims)),
                replace=(len(claims) < n),
                random_state=int(rng.integers(0, 1_000_000)),
            )

            for _, r in sample.iterrows():
                exp = "CONTROL" if rng.random() < control_rate else "TREATMENT"

                # score from weak signals (realistic monotonic relationships)
                elapsed = float(r.get("elapsed_months", np.nan))
                claim_amt = float(r.get("claim_amount", r.get("paid_amount", 0)) or 0)
                prem = float(r.get("premium_monthly", 1) or 1)
                prior_n = float(r.get("prior_claim_cnt_12m", 0) or 0)
                acct = float(r.get("bank_account_changed_recently", 0) or 0)
                dist = float(r.get("provider_distance_km", 0) or 0)
                docs = float(r.get("doc_uploaded_cnt", 0) or 0)

                risk = 0.0
                if not np.isnan(elapsed):
                    risk += (1.0 if elapsed < 6 else 0.2 if elapsed < 12 else 0.0)
                risk += min(2.0, max(0.0, (claim_amt / max(prem, 1.0)) / 50.0))
                risk += min(1.5, prior_n / 3.0)
                risk += 1.0 * acct
                risk += min(1.0, dist / 50.0)
                risk += 0.4 if docs <= 1 else 0.0

                # map to 0..1
                score = float(1.0 / (1.0 + np.exp(-(risk - 1.2))))
                score = float(np.clip(score + rng.normal(0, 0.06), 0, 1))

                decision = "REVIEW" if (exp == "TREATMENT" and score >= review_threshold) else "PAY"

                paid_raw = float(r.get("paid_amount", max(0, rng.normal(380_000, 220_000))))
                paid = paid_raw
                if exp == "TREATMENT":
                    paid = paid_raw - float(effect_per_claim) + float(rng.normal(0, 12_000))
                    if decision == "REVIEW":
                        paid = paid * float(rng.uniform(0.55, 0.85))

                paid = int(max(0, round(paid)))

                row = {
                    "claim_id": r.get("claim_id"),
                    "claim_date": d.isoformat(),
                    "exp_group": exp,
                    "score": score,
                    "decision": decision,
                    "paid_amount": paid,
                }
                # Keep key segment columns for HTE
                for col in ["channel", "product", "product_line", "region", "hospital_id", "hospital_grade"]:
                    if col in claims.columns:
                        row[col] = r.get(col)
                rows.append(row)

    else:
        # Fallback: purely synthetic ledger
        for d in dates:
            n = int(max(30, rng.normal(120, 25)))
            for i in range(n):
                exp = "CONTROL" if rng.random() < control_rate else "TREATMENT"
                score = float(np.clip(rng.normal(0.35, 0.18), 0, 1))
                decision = "REVIEW" if (exp == "TREATMENT" and score >= review_threshold) else "PAY"
                paid_raw = float(max(0, rng.normal(380_000, 220_000)))
                paid = paid_raw
                if exp == "TREATMENT":
                    paid = paid_raw - float(effect_per_claim) + float(rng.normal(0, 12_000))
                    if decision == "REVIEW":
                        paid = paid * float(rng.uniform(0.55, 0.85))
                paid = int(max(0, round(paid)))
                rows.append({
                    "claim_id": f"SIM{d.strftime('%Y%m%d')}{i:04d}",
                    "claim_date": d.isoformat(),
                    "exp_group": exp,
                    "score": score,
                    "decision": decision,
                    "paid_amount": paid,
                })

    _write_csv(pd.DataFrame(rows), "decision_ledger.csv")


def _simulate_review_cases(seed: int, review_sla_hours: int = 72):
    """Create review processing telemetry for Ops visibility."""
    rng = np.random.default_rng(seed)
    led_path = os.path.join(OUT_DIR, "decision_ledger.csv")
    if not os.path.exists(led_path):
        return
    led = pd.read_csv(led_path)
    if led.empty:
        return
    led["decision"] = led["decision"].astype(str).str.upper()
    q = led[led["decision"] == "REVIEW"].copy()
    if q.empty:
        return

    # Keep latest reviews for realism
    q["claim_date"] = pd.to_datetime(q["claim_date"], errors="coerce")
    q = q.dropna(subset=["claim_date"]).sort_values("claim_date", ascending=False).head(1500)

    now = pd.Timestamp.utcnow()
    status = rng.choice(["PENDING", "APPROVED", "DENIED"], size=len(q), p=[0.35, 0.45, 0.20])
    received = q["claim_date"].dt.tz_localize("UTC") + pd.to_timedelta(rng.integers(0, 18, size=len(q)), unit="h")

    proc_hours = rng.integers(2, review_sla_hours + 36, size=len(q))
    processed = received + pd.to_timedelta(proc_hours, unit="h")
    processed = processed.where(status != "PENDING", pd.NaT)

    out = pd.DataFrame({
        "claim_id": q["claim_id"].astype(str).values,
        "received_time_utc": received.astype(str).values,
        "status": status,
        "processed_time_utc": processed.astype(str).values,
    })
    out["sla_hours"] = review_sla_hours
    out["age_hours"] = ((now - pd.to_datetime(out["received_time_utc"], errors="coerce")) / pd.Timedelta(hours=1)).round(1)
    out["breach_sla"] = (out["status"] == "PENDING") & (out["age_hours"] > review_sla_hours)
    _write_csv(out, "review_cases.csv")


def run(scenario: str, days: int, seed: int, control_rate: float):
    _ensure_out()

    p = _scenario_params(scenario)

    ts = _make_timeseries(days=days, seed=seed, base_daily=p["base_daily"])
    _write_csv(ts, "impact_monthly_timeseries.csv")

    # KPI
    asof, today, mtd, qtd = _kpi_from_ts(ts)

    # Impact panel
    impact_panel = pd.DataFrame([
        {
            "method": "Welch t-test (SciPy)",
            "effect_per_claim": p["effect"],
            "p_value": p["welch_p"],
            "notes": f"Simulated scenario={p['guard']}"
        },
        {
            "method": "Unadjusted (Diff-in-Means)",
            "effect_per_claim": int(round(p["effect"] * 0.9)),
            "p_value": min(0.99, p["welch_p"] * 1.6),
            "notes": "Simulated baseline"
        },
    ])
    _write_csv(impact_panel, "impact_panel.csv")

    sig = pd.DataFrame([{
        "test": "Welch t-test",
        "effect_per_claim": p["effect"],
        "welch_p_value": p["welch_p"],
        "n_control": int(round(600 * control_rate / 0.10)),
        "n_treatment": int(round(6000 * (1 - control_rate) / 0.90)),
    }])
    _write_csv(sig, "impact_significance_scipy.csv")

    # Guardrails
    guard = pd.DataFrame([{
        "decision": p["guard"],
        "reasons": f"Simulated: scenario={p['guard']}, p={p['welch_p']:.3g}, alerts={p['seg_alerts']}"
    }])
    _write_csv(guard, "guardrails_decision.csv")

    # Segment alerts
    seg = []
    for i in range(max(0, p["seg_alerts"])):
        seg.append({
            "segment": f"segment_{i+1}",
            "metric": "FDR",
            "value": float(0.07 + 0.01 * i),
            "threshold": 0.05,
            "is_alert": True,
        })
    # add a couple OK rows for realism
    seg += [
        {"segment": "channel=GA", "metric": "FDR", "value": 0.02, "threshold": 0.05, "is_alert": False},
        {"segment": "product_line=HEALTH", "metric": "FDR", "value": 0.03, "threshold": 0.05, "is_alert": False},
    ]
    _write_csv(pd.DataFrame(seg), "segment_alerts.csv")

    # Decision ledger fallback
    _simulate_decision_ledger(
        ts,
        seed=seed + 1,
        control_rate=control_rate,
        effect_per_claim=int(p["effect"]),
        review_threshold=float(CFG.review_threshold),
    )

    # Review processing telemetry (Ops)
    _simulate_review_cases(seed=seed + 2, review_sla_hours=int(getattr(CFG, "review_sla_hours", 72)))

    # Executive summary
    summary = f"""# Fraud Program Executive Summary

- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- Guardrails decision: **{p['guard']}**
- Best estimate effect per claim (Control – Treatment): **{p['effect']:,}원**
- Welch p-value: **{p['welch_p']:.3g}**
- Segment alerts (FDR): **{p['seg_alerts']}**

## KPI Snapshot (Simulated)

- Saving Today (Est.): **{today:,}원**
- Saving MTD (Est.): **{mtd:,}원** (target: {CFG.target_mtd_saving_krw:,}원)
- Saving QTD (Est.): **{qtd:,}원** (target: {CFG.target_qtd_saving_krw:,}원)

Simulated production telemetry for demonstration.
"""
    with open(os.path.join(OUT_DIR, "executive_summary.md"), "w", encoding="utf-8") as f:
        f.write(summary)

    # Also regenerate charts for consistency
    try:
        from src.executive_charts import main as charts_main
        charts_main()
    except Exception:
        pass


def build_argparser():
    ap = argparse.ArgumentParser(description="Generate simulated production outputs into out/.")
    ap.add_argument("--scenario", default="GO", choices=["GO", "HOLD", "ROLLBACK"], help="Demo scenario")
    ap.add_argument("--days", type=int, default=60, help="Number of days in the timeseries")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    ap.add_argument("--control-rate", type=float, default=CFG.default_control_rate, help="Control group rate (0~1)")
    return ap


def main():
    ap = build_argparser()
    args = ap.parse_args()

    run(
        scenario=args.scenario,
        days=max(7, int(args.days)),
        seed=int(args.seed),
        control_rate=float(args.control_rate),
    )

    print("✅ Simulated outputs generated:")
    for f in [
        "impact_monthly_timeseries.csv",
        "impact_daily_delta.csv",
        "impact_panel.csv",
        "impact_significance_scipy.csv",
        "guardrails_decision.csv",
        "segment_alerts.csv",
        "decision_ledger.csv",
        "executive_summary.md",
        "chart_impact_delta.png",
    ]:
        p = os.path.join(OUT_DIR, f)
        print(" -", p, "(ok)" if os.path.exists(p) else "(missing)")


if __name__ == "__main__":
    main()
