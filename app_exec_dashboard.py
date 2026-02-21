import os, json, html
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st
import joblib

from src.pdf_onepager import export_onepager_pdf, _pick_highlights
from src.config import CFG
from src.telemetry import compute_saving_kpis, compute_ops_kpis
from src.simulate_production_outputs import run as simulate_run
from src.explainability import summarize_rule_reasons, compare_profiles, linear_model_contributions

OUT="out"
CI_PATH="assets/ci.json"
POLICY_REGISTRY="models/policy_registry.json"

def exists(p): return os.path.exists(p)
def path_out(*p): return os.path.join(OUT,*p)
def mtime(p): return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S") if exists(p) else "NA"
def read_text(p): return open(p,"r",encoding="utf-8").read() if exists(p) else ""
def read_csv(p):
    if not exists(p): return pd.DataFrame()
    try: return pd.read_csv(p)
    except: return pd.DataFrame()
def read_json(p):
    if not exists(p): return {}
    try: return json.load(open(p,"r",encoding="utf-8"))
    except: return {}

def krw(x):
    try:
        v=float(x)
        if np.isnan(v): return "NA"
        return f"{int(round(v)):,}원"
    except: return "NA"


def safe_ratio(num, den):
    """Return num/den or None when invalid."""
    try:
        num = float(num)
        den = float(den)
        if den == 0 or np.isnan(den) or np.isnan(num):
            return None
        return num / den
    except Exception:
        return None

def pvalue(x):
    try:
        v=float(x)
        if np.isnan(v): return "NA"
        return f"{v:.2e}" if v<1e-4 else f"{v:.4g}"
    except: return "NA"


# -----------------------------
# Report period helpers
# -----------------------------

def _to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def available_months(ts: pd.DataFrame, ledger: pd.DataFrame) -> list[str]:
    """Return available months as 'YY.M월' strings (e.g., '25.1월')."""
    months = set()
    if ts is not None and (not ts.empty) and "date" in ts.columns:
        d = _to_datetime(ts["date"]).dropna()
        for x in d.dt.to_period("M").astype(str).tolist():
            months.add(x)
    if ledger is not None and (not ledger.empty):
        col = "claim_date" if "claim_date" in ledger.columns else ("date" if "date" in ledger.columns else None)
        if col:
            d = _to_datetime(ledger[col]).dropna()
            for x in d.dt.to_period("M").astype(str).tolist():
                months.add(x)

    # sort
    out = sorted(list(months))

    def fmt(ym: str) -> str:
        # ym: 'YYYY-MM'
        try:
            y, m = ym.split("-")
            return f"{y[-2:]}.{int(m)}월"
        except Exception:
            return ym

    return [fmt(x) for x in out]


def _parse_month_label(label: str) -> str:
    """Convert '25.1월' -> '2025-01' (best-effort)."""
    try:
        y2, rest = label.split(".")
        m = rest.replace("월", "")
        y = int(y2)
        y = 2000 + y if y < 70 else 1900 + y
        return f"{y:04d}-{int(m):02d}"
    except Exception:
        return label


def filter_to_month(df: pd.DataFrame, date_col: str, month_ym: str) -> pd.DataFrame:
    """Filter dataframe to a given month (month_ym='YYYY-MM')."""
    if df is None or df.empty or date_col not in df.columns:
        return df
    d = df.copy()
    d[date_col] = _to_datetime(d[date_col])
    d = d.dropna(subset=[date_col])
    if d.empty:
        return d
    start = pd.Timestamp(f"{month_ym}-01")
    end = (start + pd.offsets.MonthBegin(1))
    return d[(d[date_col] >= start) & (d[date_col] < end)].copy()


def compute_period_ops_summary(ledger: pd.DataFrame) -> dict:
    """Period-level operational summary (used for 월간 drill-down)."""
    if ledger is None or ledger.empty:
        return {"n": None, "review_rate": None, "treat_rate": None, "avg_score": None, "control_rate": None}
    df = ledger.copy()
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]
    if "decision" not in df.columns:
        df["decision"] = ""
    if "score" not in df.columns:
        df["score"] = np.nan

    n = len(df)
    dec = df["decision"].astype(str).str.upper()
    review_rate = float((dec == "REVIEW").mean()) if n else None
    grp = df["exp_group"].astype(str).str.upper()
    treat_rate = float((grp == "TREATMENT").mean()) if n else None
    control_rate = float((grp == "CONTROL").mean()) if n else None
    s = pd.to_numeric(df["score"], errors="coerce")
    avg_score = float(s.mean()) if s.notna().any() else None

    return {
        "n": n,
        "review_rate": review_rate,
        "treat_rate": treat_rate,
        "avg_score": avg_score,
        "control_rate": control_rate,
    }

# -----------------------------
# Formatting helpers (BCG-style tables)
# -----------------------------
DIM_LABELS = {
    "channel": "유입채널",
    "product_line": "상품군",
    "product": "상품",
    "region": "지역",
    "hospital_grade": "의료기관 등급",
}

def fmt_int(x):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        return f"{int(round(float(x))):,}"
    except Exception:
        return "—"

def fmt_krw(x):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        return f"{int(round(float(x))):,}원"
    except Exception:
        return "—"

def fmt_pct(x, digits=1):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        return f"{float(x) * 100:.{digits}f}%"
    except Exception:
        return "—"

def fmt_score(x, digits=3):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        return f"{float(x):.{digits}f}"
    except Exception:
        return "—"



# ----------------------------
# Business label dictionaries (deck-friendly)
# ----------------------------

FEATURE_LABELS = {
    "claim_amount": "청구금액(원)",
    "paid_amount": "지급금액(원)",
    "premium_monthly": "월 보험료(원)",
    "elapsed_months": "가입 경과(개월)",
    "provider_distance_km": "의료기관 거리(km)",
    "prior_claim_cnt_12m": "최근 12개월 청구건수",
    "age": "연령(세)",
    "doc_uploaded_cnt": "제출 서류 수(건)",
    "hospital_grade": "의료기관 등급",
    "hospital_id": "의료기관",
    "channel": "유입채널",
    "product_line": "상품군",
    "product": "상품",
    "region": "지역",
}

# --- Risk driver taxonomy (consulting-style categories) ---
RULE_CATEGORY_MAP = {
    # rule_code : business category
    "many_prior": "과거 청구 이력",
    "acct_change": "계정/수령계좌 변경",
    "high_ratio": "비정상 청구 패턴",
    "short_tenure": "초기 계약 리스크",
    "far_provider": "원거리 의료기관",
    "doc_missing": "서류 미비/불충분",
}

RULE_CATEGORY_KEYWORDS = [
    ("과거 청구 이력", ["다빈도", "최근 12개월", "기존 청구", "이력", "prior"]),
    ("계정/수령계좌 변경", ["계정", "계좌", "변경", "수정", "acct"]),
    ("비정상 청구 패턴", ["비정상", "비율", "패턴", "high ratio", "ratio"]),
    ("초기 계약 리스크", ["초기", "가입 경과", "단기", "tenure", "short"]),
    ("원거리 의료기관", ["원거리", "거리", "km", "distance"]),
    ("서류 미비/불충분", ["서류", "미비", "누락", "doc", "upload"]),
]

# Common column rename map for display (across tabs)
DISPLAY_COLS = {
    # Impact / causal
    "n": "표본수",
    "n_total": "표본수",
    "n_control": "통제군",
    "n_treatment": "처리군",
    "avg_paid_control": "평균 지급액(통제)",
    "avg_paid_treatment": "평균 지급액(처리)",
    "delta_paid_c_minus_t": "지급액 개선(통제-처리)",
    "review_rate_control": "검토율(통제)",
    "review_rate_treatment": "검토율(처리)",
    "delta_review_rate_t_minus_c": "검토율 변화(처리-통제)",
    "segment_col": "구분",
    "segment": "세그먼트",
    # Ops queue
    "claim_date": "청구일",
    "submitted_at": "접수일시",
    "age_hours": "대기시간(시간)",
    "sla_hours": "SLA(시간)",
    "breach_sla": "SLA 위반",
    "status": "상태",
    "decision": "처리",
    "score": "리스크 점수",
    "risk_reasons": "의심 사유(요약)",
    "paid_amount": "지급액",
    "claim_id": "청구 ID",
}

def _maybe_parse_listlike(x):
    """Parse list-like strings: JSON / python literal / already list."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, (tuple, set)):
        return list(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return []
        # try json then python literal
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else []
        except Exception:
            pass
        try:
            import ast
            v = ast.literal_eval(s)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return []

def apply_business_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known columns & feature names consistently across the deck."""
    d = df.copy()
    d = d.rename(columns={k: v for k, v in DISPLAY_COLS.items() if k in d.columns})
    # if a feature/variable name column exists, map it
    for col in ["feature", "지표", "변수", "항목"]:
        if col in d.columns:
            d[col] = d[col].map(lambda x: FEATURE_LABELS.get(str(x), str(x)))
    return d

def insight_box(title: str, bullets: list[str], tone: str = "neutral"):
    """Consulting-style message box (Key message)."""
    if not bullets:
        return
    b = "".join([f"<li>{html.escape(x)}</li>" for x in bullets if x])
    tone_cls = "success" if tone == "success" else "warn" if tone == "warn" else "danger" if tone == "danger" else ""
    st.markdown(
        f"""
        <div class="card" style="padding:16px 18px;">
          <div style="display:flex; align-items:center; gap:10px;">
            {badge(html.escape(title), tone_cls) if tone_cls else f'<span class="badge">{html.escape(title)}</span>'}
            <div style="font-weight:900; color:var(--fg);">{html.escape(title)}</div>
          </div>
          <div style="height:8px"></div>
          <ul style="margin:0 0 0 18px; color:var(--fg);">{b}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _rule_to_category(item: dict) -> str:
    rule = str(item.get("rule", "") or "").strip()
    if rule and rule in RULE_CATEGORY_MAP:
        return RULE_CATEGORY_MAP[rule]
    reason = str(item.get("reason") or item.get("title") or "").strip()
    low = reason.lower()
    for cat, kws in RULE_CATEGORY_KEYWORDS:
        for kw in kws:
            if kw.lower() in low:
                return cat
    return "기타"

def build_driver_category_table(df_top: pd.DataFrame) -> pd.DataFrame:
    """Aggregate risk reasons into business categories."""
    if df_top is None or df_top.empty or "risk_reason_details" not in df_top.columns:
        return pd.DataFrame()
    rows = []
    for _, r in df_top.iterrows():
        score = r.get("score")
        items = _maybe_parse_listlike(r.get("risk_reason_details"))
        cats = set()
        for it in items:
            if isinstance(it, dict):
                cats.add(_rule_to_category(it))
        for c in cats:
            rows.append({"리스크 카테고리": c, "리스크 점수": score})
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    g = d.groupby("리스크 카테고리", as_index=False).agg(
        발생건수=("리스크 점수", "size"),
        평균_점수=("리스크 점수", "mean"),
    ).sort_values(["발생건수", "평균_점수"], ascending=[False, False])
    total = float(g["발생건수"].sum()) if len(g) else 0.0
    if total > 0:
        g["발생 비중"] = g["발생건수"].map(lambda v: v / total)
    else:
        g["발생 비중"] = 0.0

    out = g[["리스크 카테고리", "발생 비중", "평균_점수", "발생건수"]].copy()
    out = out.rename(columns={"평균_점수": "평균 리스크 점수", "발생건수": "건수"})
    out["발생 비중"] = out["발생 비중"].map(lambda v: fmt_pct(v, 1))
    out["평균 리스크 점수"] = out["평균 리스크 점수"].map(lambda v: fmt_score(v, 3))
    out["건수"] = out["건수"].map(fmt_int)
    return out

def profile_table_with_interpretation(prof_num: pd.DataFrame) -> pd.DataFrame:
    if prof_num is None or prof_num.empty:
        return pd.DataFrame()
    d = prof_num.copy()
    rename_map = {
        "feature": "지표",
        "high_mean": "고위험 평균",
        "low_mean": "저위험 평균",
        "mean_diff": "평균 차이",
        "high_median": "고위험 중앙값",
        "low_median": "저위험 중앙값",
    }
    d = d.rename(columns={k: v for k, v in rename_map.items() if k in d.columns})
    if "지표" in d.columns:
        d["지표"] = d["지표"].map(lambda x: FEATURE_LABELS.get(str(x), str(x)))

    # interpretation
    if "평균 차이" in d.columns:
        def _interp(v):
            try:
                v = float(v)
            except Exception:
                return "—"
            if v > 0:
                return "고위험군이 더 높음"
            if v < 0:
                return "고위험군이 더 낮음"
            return "유사"
        d["해석"] = d["평균 차이"].map(_interp)

    # money detection
    money_idx = set()
    if "지표" in d.columns:
        for i, v in enumerate(d["지표"].astype(str).tolist()):
            if "(원)" in v or "금액" in v:
                money_idx.add(i)
    value_cols = [c for c in d.columns if c not in ["지표", "해석"]]
    for c in value_cols:
        formatted = []
        for i, v in enumerate(d[c].tolist()):
            formatted.append(fmt_krw(v) if i in money_idx else fmt_int(v))
        d[c] = formatted
    return d

def generate_key_messages(hte_df: pd.DataFrame, driver_cat: pd.DataFrame, prof_df: pd.DataFrame) -> list[str]:
    bullets = []
    if hte_df is not None and not hte_df.empty and "delta_paid_c_minus_t" in hte_df.columns:
        best = hte_df.sort_values("delta_paid_c_minus_t", ascending=False).iloc[0]
        seg = str(best.get("segment", ""))
        dim = DIM_LABELS.get(str(best.get("segment_col", "")), str(best.get("segment_col", "")))
        bullets.append(f"효과가 가장 큰 구간: {dim}={seg} (건당 {fmt_krw(best.get('delta_paid_c_minus_t'))} 개선)")
    if driver_cat is not None and not driver_cat.empty:
        top = driver_cat.iloc[0]
        bullets.append(f"주요 의심 요인: {top['리스크 카테고리']} (비중 {top['발생 비중']})")
    if prof_df is not None and not prof_df.empty and "평균 차이" in prof_df.columns and "지표" in prof_df.columns:
        tmp = prof_df.copy()
        # pick largest absolute diff among numeric values
        try:
            tmp["abs_diff"] = pd.to_numeric(tmp["평균 차이"], errors="coerce").abs()
            row = tmp.sort_values("abs_diff", ascending=False).iloc[0]
            bullets.append(f"고위험군 프로파일: {row['지표']} 차이가 큼 ({row.get('해석','')})")
        except Exception:
            pass
    return bullets[:3]

def generate_actions(hte_df: pd.DataFrame, driver_cat: pd.DataFrame) -> list[str]:
    actions = []
    if hte_df is not None and not hte_df.empty and "delta_paid_c_minus_t" in hte_df.columns:
        best = hte_df.sort_values("delta_paid_c_minus_t", ascending=False).iloc[0]
        dim = DIM_LABELS.get(str(best.get("segment_col", "")), str(best.get("segment_col", "")))
        seg = str(best.get("segment", ""))
        actions.append(f"'{dim}={seg}' 구간에 대해 자동 검토 대상(리뷰) 커버리지를 우선 확대")
    if driver_cat is not None and not driver_cat.empty:
        cat = str(driver_cat.iloc[0]["리스크 카테고리"])
        if "계정" in cat:
            actions.append("수령계좌/연락처 변경 발생 시 추가 증빙(계좌확인, 위임장 등) 필수화")
        elif "서류" in cat:
            actions.append("서류 미비 케이스는 자동 보완요청 워크플로우로 전환(누락 서류 체크리스트 제공)")
        elif "과거" in cat:
            actions.append("최근 12개월 다빈도 청구 고객군은 임계치(Threshold)를 보수적으로 설정")
        else:
            actions.append(f"'{cat}' 카테고리 룰을 중심으로 룰 설명/감사 로그를 표준화")
    actions.append("운영 KPI(검토율·SLA·절감액)를 주간 단위로 트래킹하고, 효과가 낮은 구간은 정책을 재조정")
    return actions[:3]

def fill_from_claim_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Merge 이후 segment 컬럼이 None/NaN이면 claims 원본 컬럼(<col>_claim)로 보정."""
    d = df.copy()
    for c in cols:
        c2 = f"{c}_claim"
        if c in d.columns and c2 in d.columns:
            d[c] = d[c].where(d[c].notna(), d[c2])
    return d

def hte_table_for_display(hte: pd.DataFrame) -> pd.DataFrame:
    if hte is None or hte.empty:
        return pd.DataFrame()
    d = hte.copy()
    d["segment"] = d["segment"].fillna("기타").astype(str).replace({"nan": "기타", "None": "기타"})
    out = d[[
        "segment_col", "segment", "n_total", "n_control", "n_treatment",
        "avg_paid_control", "avg_paid_treatment", "delta_paid_c_minus_t",
        "review_rate_control", "review_rate_treatment", "delta_review_rate_t_minus_c",
    ]].copy()
    out = out.rename(columns={
        "segment_col": "구분",
        "segment": "세그먼트",
        "n_total": "표본수",
        "n_control": "통제군",
        "n_treatment": "처리군",
        "avg_paid_control": "평균 지급액(통제)",
        "avg_paid_treatment": "평균 지급액(처리)",
        "delta_paid_c_minus_t": "지급액 개선(통제-처리)",
        "review_rate_control": "검토율(통제)",
        "review_rate_treatment": "검토율(처리)",
        "delta_review_rate_t_minus_c": "검토율 변화(처리-통제)",
    })
    out["구분"] = out["구분"].map(lambda x: DIM_LABELS.get(x, str(x)))
    for c in ["표본수", "통제군", "처리군"]:
        out[c] = out[c].map(fmt_int)
    for c in ["평균 지급액(통제)", "평균 지급액(처리)", "지급액 개선(통제-처리)"]:
        out[c] = out[c].map(fmt_krw)
    for c in ["검토율(통제)", "검토율(처리)", "검토율 변화(처리-통제)"]:
        out[c] = out[c].map(lambda v: fmt_pct(v, 2))
    return out

def hte_top_table_for_display(hte: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if hte is None or hte.empty:
        return pd.DataFrame()
    d = hte.copy().head(top_n)
    d["segment"] = d["segment"].fillna("기타").astype(str).replace({"nan": "기타", "None": "기타"})
    out = d[["segment_col", "segment", "n_total", "delta_paid_c_minus_t", "delta_review_rate_t_minus_c"]].copy()
    out = out.rename(columns={
        "segment_col": "구분",
        "segment": "세그먼트",
        "n_total": "표본수",
        "delta_paid_c_minus_t": "지급액 개선(통제-처리)",
        "delta_review_rate_t_minus_c": "검토율 변화(처리-통제)",
    })
    out["구분"] = out["구분"].map(lambda x: DIM_LABELS.get(x, str(x)))
    out["표본수"] = out["표본수"].map(fmt_int)
    out["지급액 개선(통제-처리)"] = out["지급액 개선(통제-처리)"].map(fmt_krw)
    out["검토율 변화(처리-통제)"] = out["검토율 변화(처리-통제)"].map(lambda v: fmt_pct(v, 2))
    return out


def load_ci():
    ci=read_json(CI_PATH)
    ci.setdefault("company_name","YOUR COMPANY")
    ci.setdefault("report_title","Fraud Detection Program — Executive Report")
    ci.setdefault("logo_path","assets/company_logo.png")
    ci.setdefault("accent_color","#0B3B8C")
    ci.setdefault("neutral_bg","#FFFFFF")
    ci.setdefault("soft_bg","#F9FAFB")
    return ci

def css(ci):
    accent=ci.get("accent_color","#0B3B8C")
    st.markdown(f"""
<style>
html, body, [class*='css'] {{ font-family: 'Pretendard','Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif; }}
.block-container {{ padding-top: 1.35rem; padding-bottom: 2.8rem; max-width: 1240px; }}
/* BCG-style breathing room */
div[data-testid="stHorizontalBlock"] {{ gap: 1.55rem; }}
div[data-testid="stVerticalBlock"] {{ gap: 1.20rem; }}
div[data-testid="stMetric"] {{ margin-bottom: 0.25rem; }}
:root {{
  --fg:#111827; --muted:#6b7280; --line:#e5e7eb;
  --bg:{ci.get("neutral_bg","#FFFFFF")}; --soft:{ci.get("soft_bg","#F9FAFB")}; --accent:{accent};
  --success:#065f46; --success_bg:#d1fae5; --success_bd:#a7f3d0;
  --warn:#92400e; --warn_bg:#fffbeb; --warn_bd:#fde68a;
  --danger:#991b1b; --danger_bg:#fef2f2; --danger_bd:#fecaca;
}}
.card {{ border:1.5px solid #d1d5db; background:var(--bg); border-radius:14px; padding:14px 16px; box-shadow: 0 6px 18px rgba(17,24,39,0.08); }}
/* KPI cards: allow content to breathe (avoid clipping small text) */
.kpi-card {{ min-height:118px; height:auto; display:flex; flex-direction:column; justify-content:space-between; }}
/* Compact variant for short labels (e.g., guardrails, progress) */
.kpi-card-compact {{ min-height:86px; height:auto; display:flex; flex-direction:column; justify-content:space-between; padding:12px 14px; }}
.kpi-card-compact .card-title {{ margin-bottom:4px; }}
.kpi-card-compact .card-sub {{ -webkit-line-clamp:2; }}
.card-title {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.10em; margin-bottom:6px; }}
.card-value {{ font-size:22px; color:var(--fg); font-weight:900; line-height:1.08; }}
/* Make small text readable; keep it concise but visible */
.card-sub {{ font-size:13px; color:#4b5563; margin-top:6px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; }}
.section-h {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.12em; margin: 4px 0 8px 0; }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:900; border:1px solid var(--line); background:var(--soft); color:var(--fg); }}
.badge.success{{ color:var(--success); background:var(--success_bg); border-color:var(--success_bd); }}
.badge.warn{{ color:var(--warn); background:var(--warn_bg); border-color:var(--warn_bd); }}
.badge.danger{{ color:var(--danger); background:var(--danger_bg); border-color:var(--danger_bd); }}
.mono {{ font-family: ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size:12px; color:#374151; }}
.accent-line {{ height:3px; width:100%; background: var(--accent); border-radius:999px; margin-top:8px; }}
/* compact pill buttons for segmented controls */
div.stButton > button {{ border-radius: 999px; padding: 0.35rem 0.8rem; font-weight: 800; }}
/* compact badge row */
.badge-row {{ display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }}
/* mini progress block (deck-style) */
.mini-wrap {{ border: 1.5px solid #d1d5db; box-shadow: 0 6px 18px rgba(17,24,39,0.08); border-radius: 18px; padding: 10px 12px; background:#fff; }}
.mini-title {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.10em; font-weight:900; }}
.mini-value {{ font-size:14px; color:var(--fg); font-weight:900; margin-top:2px; }}
.mini-sub {{ font-size:12px; color:var(--muted); margin-top:4px; }}
.stProgress > div > div {{ height: 8px; border-radius: 999px; }}
/* Tabs -> deck-style pills */
div[data-testid="stTabs"] button {{
  border-radius: 999px !important;
  padding: 0.30rem 0.75rem !important;
  font-weight: 900 !important;
  border: 1.5px solid #d1d5db !important;
  margin-right: 0.45rem !important;
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{
  border-color: var(--accent) !important;
}}
div[data-testid="stTabs"] div[role="tablist"] {{
  gap: 0.25rem !important;
}}
</style>
""", unsafe_allow_html=True)


def segmented_choice(label: str, options: list[str], key: str, default: str | None = None) -> str:
    """Pill-style segmented control using buttons (no wide radio)."""
    if default is None:
        default = options[0]
    if key not in st.session_state:
        st.session_state[key] = default

    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        is_active = (st.session_state[key] == opt)
        btn_type = "primary" if is_active else "secondary"
        if cols[i].button(opt, key=f"{key}__{i}", use_container_width=True, type=btn_type):
            st.session_state[key] = opt

    if label:
        st.caption(label)
    return st.session_state[key]

def card(t, v, s="", variant: str = "kpi"):
    """Render a KPI card.

    variant:
      - "kpi"     : standard fixed-height card
      - "compact" : shorter card for small content (e.g., guardrails, progress)
    """
    cls = "kpi-card" if variant == "kpi" else "kpi-card-compact"
    st.markdown(
        f"""<div class="card {cls}"><div class="card-title">{t}</div><div class="card-value">{v}</div><div class="card-sub">{s}</div></div>""",
        unsafe_allow_html=True,
    )

def badge(label,tone="neutral"):
    cls="badge"
    if tone=="success": cls+=" success"
    elif tone=="warn": cls+=" warn"
    elif tone=="danger": cls+=" danger"
    return f'<span class="{cls}">{label}</span>'

def badge_row(items: list[tuple[str,str]], align: str = "left"):
    """items: [(label, tone), ...]. align: left|right|center"""
    style = ""
    if align == "right":
        style = ' style="justify-content:flex-end;"'
    elif align == "center":
        style = ' style="justify-content:center;"'
    html = f'<div class="badge-row"{style}>' + "".join([badge(l,t) for l,t in items]) + '</div>'
    st.markdown(html, unsafe_allow_html=True)

def mini_progress(title: str, ratio: float | None, subtitle: str):
    r = 0.0 if ratio is None else float(max(0.0, min(1.0, ratio)))
    st.markdown(
        f'<div class="mini-wrap"><div class="mini-title">{title}</div>'
        f'<div class="mini-value">{r*100:.0f}%</div><div class="mini-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )
    st.progress(r)

def guardrail():
    g=read_csv(path_out("guardrails_decision.csv"))
    if g.empty or "decision" not in g.columns: return ("UNKNOWN","neutral","")
    d=str(g["decision"].iloc[0]).upper()
    r=str(g["reasons"].iloc[0]) if "reasons" in g.columns else ""
    if d=="GO": return ("GO","success",r)
    if d=="HOLD": return ("HOLD","warn",r)
    if d=="ROLLBACK": return ("ROLLBACK","danger",r)
    return (d,"neutral",r)

def policy_stage():
    p=read_json(POLICY_REGISTRY)
    cur=(p or {}).get("current",{})
    if not cur: return ("NOT CONFIGURED","NOT CONFIGURED","NA")
    return (str(cur.get("policy_version","NA")), str(cur.get("mode","NA")), str(cur.get("control_rate","NA")))

def best_effect():
    panel=read_csv(path_out("impact_panel.csv"))
    if panel.empty or "method" not in panel.columns or "effect_per_claim" not in panel.columns: return (None,"NA",panel)
    pr=["Welch t-test (SciPy)","Unadjusted (Diff-in-Means)"]
    for m in pr:
        hit=panel[panel["method"]==m]
        if len(hit): return (hit["effect_per_claim"].iloc[0], m, panel)
    return (panel["effect_per_claim"].iloc[0], str(panel["method"].iloc[0]), panel)

def methods_summary(panel):
    if panel is None or panel.empty: return []
    if "p_value" not in panel.columns: panel=panel.assign(p_value="")
    pr=["Welch t-test (SciPy)","Unadjusted (Diff-in-Means)"]
    picked=[]
    used=set()
    for m in pr:
        hit=panel[panel["method"]==m]
        if len(hit):
            picked.append(hit.iloc[0].to_dict()); used.add(m)
    if len(picked)<3:
        rest=panel[~panel["method"].isin(list(used))].head(3-len(picked))
        for _,r in rest.iterrows(): picked.append(r.to_dict())
    out=[]
    for r in picked[:3]:
        pv=str(r.get("p_value","")).strip()
        out.append({"method":str(r.get("method","NA")),"effect_per_claim":krw(r.get("effect_per_claim")),"p_value":pvalue(pv) if pv else "—"})
    return out

def compute_savings_from_ledger(effect_per_claim, ledger: pd.DataFrame):
    """
    운영형 방식:
    - effect_per_claim(원/건) * (TREATMENT 건수)
    - Today / MTD / QTD 를 decision_ledger.csv의 claim_date 기준으로 계산
    """
    try:
        eff = float(effect_per_claim)
        if np.isnan(eff):
            return (None, None, None, None)
    except:
        return (None, None, None, None)

    if ledger is None or ledger.empty:
        return (None, None, None, None)

    # 필수 컬럼 체크
    if "claim_date" not in ledger.columns or "exp_group" not in ledger.columns:
        return (None, None, None, None)

    df = ledger.copy()

    # claim_date 파싱
    df["claim_date"] = pd.to_datetime(df["claim_date"], errors="coerce")
    df = df.dropna(subset=["claim_date"])

    if df.empty:
        return (None, None, None, None)

    # "오늘"은 운영 데이터에서 가장 최신 날짜로 잡는게 현실적
    today = df["claim_date"].max().normalize()

    # 그룹 필터
    t = df[df["exp_group"].astype(str).str.upper().eq("TREATMENT")]

    if t.empty:
        return (today, 0.0, 0.0, 0.0)

    # TODAY
    n_today = (t["claim_date"].dt.normalize() == today).sum()
    saving_today = eff * n_today

    # MTD
    m_start = today.replace(day=1)
    n_mtd = ((t["claim_date"] >= m_start) & (t["claim_date"] < (today + pd.Timedelta(days=1)))).sum()
    saving_mtd = eff * n_mtd

    # QTD
    q = (today.month - 1)//3 + 1
    q_start_month = 1 + 3*(q-1)
    q_start = today.replace(month=q_start_month, day=1)
    n_qtd = ((t["claim_date"] >= q_start) & (t["claim_date"] < (today + pd.Timedelta(days=1)))).sum()
    saving_qtd = eff * n_qtd

    return (today, saving_today, saving_mtd, saving_qtd)

def compute_savings_from_timeseries(ts: pd.DataFrame):
    """
    out/impact_monthly_timeseries.csv 기반:
    - date, saving_est_krw를 사용해 Today/MTD/QTD 계산
    """
    if ts is None or ts.empty:
        return (None, None, None, None)

    if "date" not in ts.columns or "saving_est_krw" not in ts.columns:
        return (None, None, None, None)

    df = ts.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["saving_est_krw"] = pd.to_numeric(df["saving_est_krw"], errors="coerce")
    df = df.dropna(subset=["date", "saving_est_krw"])
    if df.empty:
        return (None, None, None, None)

    asof = df["date"].max().normalize()

    # TODAY
    saving_today = float(df.loc[df["date"].dt.normalize() == asof, "saving_est_krw"].sum())

    # MTD
    m_start = asof.replace(day=1)
    saving_mtd = float(df.loc[(df["date"] >= m_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    # QTD
    q = (asof.month - 1)//3 + 1
    q_start_month = 1 + 3*(q-1)
    q_start = asof.replace(month=q_start_month, day=1)
    saving_qtd = float(df.loc[(df["date"] >= q_start) & (df["date"] < asof + pd.Timedelta(days=1)), "saving_est_krw"].sum())

    return (asof, saving_today, saving_mtd, saving_qtd)

def compute_savings_kpi_bundle(ts: pd.DataFrame, target_mtd_krw: float = 200_000_000):
    """
    returns:
      asof, today, mtd, qtd, dod_pct, ma7, target_mtd, target_progress
    """
    asof, today, mtd, qtd = compute_savings_from_timeseries(ts)
    if asof is None:
        return (None, None, None, None, None, None, target_mtd_krw, None)

    df = ts.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["saving_est_krw"] = pd.to_numeric(df["saving_est_krw"], errors="coerce")
    df = df.dropna(subset=["date","saving_est_krw"]).sort_values("date")

    # 전일 대비
    prev_day = asof - pd.Timedelta(days=1)
    prev_val = float(df.loc[df["date"].dt.normalize()==prev_day, "saving_est_krw"].sum())
    dod_pct = None if prev_val <= 0 else (today - prev_val) / prev_val

    # 7일 이동평균(최근 7일)
    last7 = df[df["date"] >= (asof - pd.Timedelta(days=6))]
    ma7 = float(last7["saving_est_krw"].mean()) if len(last7) else None

    # 목표 대비
    target_progress = None if target_mtd_krw <= 0 else (mtd / target_mtd_krw)

    return (asof, today, mtd, qtd, dod_pct, ma7, target_mtd_krw, target_progress) 


def compute_experiment_daily(ledger: pd.DataFrame) -> pd.DataFrame:
    """Build daily CONTROL vs TREATMENT telemetry from decision ledger.

    Returns a tidy dataframe with:
      date, exp_group, n, avg_paid, median_paid, review_rate, avg_score
    """
    if ledger is None or ledger.empty:
        return pd.DataFrame()

    df = ledger.copy()
    if "claim_date" not in df.columns and "date" in df.columns:
        df["claim_date"] = df["date"]
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]

    need = {"claim_date", "exp_group"}
    if not need.issubset(set(df.columns)):
        return pd.DataFrame()

    df["claim_date"] = pd.to_datetime(df["claim_date"], errors="coerce")
    df = df.dropna(subset=["claim_date"])
    if df.empty:
        return pd.DataFrame()

    df["date"] = df["claim_date"].dt.normalize()
    df["exp_group"] = df["exp_group"].astype(str).str.upper()
    df = df[df["exp_group"].isin(["CONTROL", "TREATMENT"])]
    if df.empty:
        return pd.DataFrame()

    if "paid_amount" in df.columns:
        df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce")
    else:
        df["paid_amount"] = np.nan
    if "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
    else:
        df["score"] = np.nan
    if "decision" in df.columns:
        df["is_review"] = df["decision"].astype(str).str.upper().eq("REVIEW")
    else:
        df["is_review"] = False

    g = df.groupby(["date", "exp_group"], dropna=False)
    out = g.agg(
        n=("claim_id", "count") if "claim_id" in df.columns else ("paid_amount", "size"),
        avg_paid=("paid_amount", "mean"),
        median_paid=("paid_amount", "median"),
        review_rate=("is_review", "mean"),
        avg_score=("score", "mean"),
    ).reset_index()

    # fill missing paid/score
    for c in ["avg_paid", "median_paid", "avg_score"]:
        if c in out.columns:
            out[c] = out[c].astype(float)
    out["review_rate"] = out["review_rate"].astype(float)
    out["n"] = out["n"].astype(int)
    return out.sort_values(["date", "exp_group"]).reset_index(drop=True)


def compute_experiment_summary(ledger: pd.DataFrame) -> dict:
    """High-level A/B summary for executive consumption."""
    if ledger is None or ledger.empty:
        return {}
    d = compute_experiment_daily(ledger)
    if d.empty:
        return {}

    # whole-window summary
    df = ledger.copy()
    if "claim_date" not in df.columns and "date" in df.columns:
        df["claim_date"] = df["date"]
    if "exp_group" not in df.columns and "group" in df.columns:
        df["exp_group"] = df["group"]
    df["exp_group"] = df["exp_group"].astype(str).str.upper()
    df = df[df["exp_group"].isin(["CONTROL", "TREATMENT"])]
    if df.empty:
        return {}

    df["paid_amount"] = pd.to_numeric(df.get("paid_amount"), errors="coerce")
    df["score"] = pd.to_numeric(df.get("score"), errors="coerce")
    df["is_review"] = df.get("decision", "").astype(str).str.upper().eq("REVIEW")

    def pack(gdf: pd.DataFrame):
        return {
            "n": int(len(gdf)),
            "avg_paid": float(gdf["paid_amount"].mean()) if len(gdf) else None,
            "median_paid": float(gdf["paid_amount"].median()) if len(gdf) else None,
            "review_rate": float(gdf["is_review"].mean()) if len(gdf) else None,
            "avg_score": float(gdf["score"].mean()) if len(gdf) else None,
        }

    c = pack(df[df["exp_group"] == "CONTROL"])
    t = pack(df[df["exp_group"] == "TREATMENT"])
    effect_obs = None
    if c.get("avg_paid") is not None and t.get("avg_paid") is not None:
        effect_obs = float(c["avg_paid"] - t["avg_paid"])

    return {"control": c, "treatment": t, "effect_obs": effect_obs, "asof": d["date"].max()}


def compute_hte(ledger: pd.DataFrame, seg_cols: list[str], min_n: int = 200) -> pd.DataFrame:
    """Heterogeneous Treatment Effect: segment-wise (Control − Treatment) paid delta."""
    if ledger is None or ledger.empty:
        return pd.DataFrame()
    df = ledger.copy()
    df["exp_group"] = df.get("exp_group", df.get("group", "")).astype(str).str.upper()
    df = df[df["exp_group"].isin(["CONTROL", "TREATMENT"])].copy()
    if df.empty:
        return pd.DataFrame()

    df["paid_amount"] = pd.to_numeric(df.get("paid_amount"), errors="coerce")
    df["score"] = pd.to_numeric(df.get("score"), errors="coerce")
    df["is_review"] = df.get("decision", "").astype(str).str.upper().eq("REVIEW")

    out = []
    for col in seg_cols:
        if col not in df.columns:
            continue
        g = df.groupby([col, "exp_group"], dropna=False)
        agg = g.agg(
            n=("paid_amount", "size"),
            avg_paid=("paid_amount", "mean"),
            review_rate=("is_review", "mean"),
            avg_score=("score", "mean"),
        ).reset_index()

        # pivot to compute deltas
        piv = agg.pivot(index=col, columns="exp_group", values=["n", "avg_paid", "review_rate", "avg_score"])
        piv.columns = [f"{a}_{b.lower()}" for a, b in piv.columns]
        piv = piv.reset_index()
        # min sample rule
        piv["n_total"] = piv.get("n_control", 0).fillna(0) + piv.get("n_treatment", 0).fillna(0)
        piv = piv[piv["n_total"] >= min_n].copy()
        if piv.empty:
            continue
        if "avg_paid_control" in piv.columns and "avg_paid_treatment" in piv.columns:
            piv["delta_paid_c_minus_t"] = piv["avg_paid_control"] - piv["avg_paid_treatment"]
        if "review_rate_control" in piv.columns and "review_rate_treatment" in piv.columns:
            piv["delta_review_rate_t_minus_c"] = piv["review_rate_treatment"] - piv["review_rate_control"]
        piv["segment_col"] = col
        piv = piv.rename(columns={col: "segment"})
        out.append(piv)

    if not out:
        return pd.DataFrame()

    res = pd.concat(out, ignore_index=True)
    # rank by absolute effect
    if "delta_paid_c_minus_t" in res.columns:
        res = res.sort_values("delta_paid_c_minus_t", key=lambda s: s.abs(), ascending=False)
    return res


def attach_rule_reasons(df: pd.DataFrame) -> pd.DataFrame:
    """Attach rule-based reasons to a dataframe of claims."""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    shorts = []
    tops = []
    for _, r in d.iterrows():
        s, top = summarize_rule_reasons(r.to_dict(), topk=3)
        shorts.append(s)
        tops.append(top)
    d["risk_reasons"] = shorts
    d["risk_reason_details"] = tops
    return d


def try_load_model():
    """Best-effort load champion model for explanations/accuracy."""
    for p in ["models/champion.joblib", "models/fraud_lr.joblib", "models/challenger.joblib"]:
        if exists(p):
            try:
                return joblib.load(p)
            except Exception:
                continue
    return None

# App
ci=load_ci()
st.set_page_config(page_title=ci["report_title"], layout="wide")
css(ci)

# Load telemetry early (used by report-period selector)
ts_raw = read_csv(path_out("impact_monthly_timeseries.csv"))
ledger_raw = read_csv(path_out("decision_ledger.csv"))

with st.sidebar:
    st.markdown("### Executive Controls")
    if st.button("Refresh"): st.rerun()
    st.markdown("---")
    st.caption("KRW standard · Fixed layout · One-page PDF export")

    st.markdown("#### 리포트 기준")
    period_mode = st.selectbox("집계 단위", ["최신(일간)", "월간"], index=0)
    month_label = None
    month_ym = None
    if period_mode == "월간":
        ms = available_months(ts_raw, ledger_raw)
        if len(ms) == 0:
            st.caption("월간 선택을 위한 데이터가 없습니다.")
        else:
            month_label = st.selectbox("월 선택", ms, index=max(0, len(ms)-1))
            month_ym = _parse_month_label(month_label)
    st.markdown("---")

    st.markdown("#### Demo Telemetry")
    demo_scn = st.selectbox("Scenario", ["GO","HOLD","ROLLBACK"], index=0)
    demo_days = st.slider("History window (days)", 30, 180, 60, step=10)
    demo_seed = st.number_input("Seed", min_value=1, max_value=10_000, value=42, step=1)
    if st.button("Generate / Refresh Demo Data", use_container_width=True):
        simulate_run(scenario=demo_scn, days=int(demo_days), seed=int(demo_seed), control_rate=CFG.default_control_rate)
        # regenerate charts to keep one-pager consistent
        try:
            from src.executive_charts import main as charts_main
            charts_main()
        except Exception:
            pass
        st.rerun()

pv, pm, cr = policy_stage()
g_label, g_tone, g_reasons = guardrail()
effect, effect_src, panel = best_effect()
sig=read_csv(path_out("impact_significance_scipy.csv"))
pval = sig["welch_p_value"].iloc[0] if (not sig.empty and "welch_p_value" in sig.columns) else None
seg=read_csv(path_out("segment_alerts.csv"))
seg_n = int(seg["is_alert"].fillna(False).astype(bool).sum()) if (not seg.empty and "is_alert" in seg.columns) else 0
red_flag = (seg_n>0) or (g_label=="ROLLBACK")

ts = ts_raw
ledger = ledger_raw

# Apply report period filter
period_caption = ""
if 'period_mode' in globals() and period_mode == "월간" and month_ym:
    if ts is not None and not ts.empty and "date" in ts.columns:
        ts = filter_to_month(ts, "date", month_ym)
    if ledger is not None and not ledger.empty:
        dcol = "claim_date" if "claim_date" in ledger.columns else ("date" if "date" in ledger.columns else None)
        if dcol:
            ledger = filter_to_month(ledger, dcol, month_ym)
    period_caption = f"(월간 기준: {month_label})"
else:
    period_caption = "(최신 일간 기준)"
kpi = compute_saving_kpis(
    ts=ts if not ts.empty else None,
    effect_per_claim=effect,
    ledger=ledger if not ledger.empty else None,
    target_mtd=float(CFG.target_mtd_saving_krw),
    target_qtd=float(CFG.target_qtd_saving_krw),
)

ops = compute_ops_kpis(ledger if not ledger.empty else None)

asof_date = kpi.asof_date
saving_today = kpi.saving_today
saving_mtd = kpi.saving_mtd
saving_qtd = kpi.saving_qtd
dod_pct = kpi.dod_pct
ma7 = kpi.ma7
target_mtd = kpi.target_mtd
prog = kpi.mtd_progress
qprog = kpi.qtd_progress

h1,h2=st.columns([1.2,1.0])
with h1:
    lp=ci.get("logo_path","")
    if lp and exists(lp): st.image(lp, width=160)
    st.markdown(f"""
<div style="margin-top:6px; font-size:12px; color:#6b7280; letter-spacing:0.12em; text-transform:uppercase;">
{ci["company_name"]} · 임원 보고 표준
</div>
<div style="font-size:30px; font-weight:900; color:#111827; letter-spacing:-0.02em;">
{ci["report_title"]}
</div>
<div class="accent-line"></div>
<div style="margin-top:8px; color:#6b7280; font-size:13px;">
정책: <span class="mono">{pv}</span> · 모드: <span class="mono">{pm}</span> · 통제 비중: <span class="mono">{cr}</span>
</div>
""", unsafe_allow_html=True)
with h2:
    st.markdown(f"""
<div style="text-align:right;">
  <div style="font-size:12px; color:#6b7280;">Last updated</div>
  <div class="mono">{mtime(path_out("executive_summary.md"))}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ---- KPI (Deck: 한 장 요약) ----
st.markdown('<div class="section-h">핵심 지표</div>', unsafe_allow_html=True)

if 'period_mode' in globals() and period_mode == "월간" and month_label:
    sub_asof = f"기준월: {month_label}"
else:
    sub_asof = f"기준일: {asof_date.strftime('%Y-%m-%d')}" if asof_date is not None else ""

ops_period = compute_period_ops_summary(ledger if ledger is not None else pd.DataFrame())

# 1) 한 줄 요약 KPI (덱 스타일: 컴팩트)
k1, k2, k3 = st.columns([1.2, 1.0, 0.8])
with k1:
    title = "월 절감(추정)" if ('period_mode' in globals() and period_mode == "월간") else "MTD 절감(추정)"
    val = krw(saving_mtd) if saving_mtd is not None else "—"
    card(title, val, sub_asof, variant="compact")
with k2:
    if ('period_mode' in globals() and period_mode == "월간"):
        v = fmt_int(ops_period.get("n"))
        card("기간 청구 건수", v, sub_asof, variant="compact")
    else:
        v = f"{ops.claims_today:,}" if ops.claims_today is not None else "—"
        card("금일 청구 건수", v, sub_asof, variant="compact")
with k3:
    # 가드레일/품질은 배지로만 표시(면적 최소)
    badge_row([
        (f"{g_label}", g_tone),
        (f"p={pvalue(pval)}", "neutral"),
        (f"경보 {seg_n}건", "neutral" if seg_n == 0 else "warn"),
    ], align="right")

with st.expander("세부 지표 보기", expanded=False):
    tabs_kpi = st.tabs(["재무 성과", "운영 지표", "품질·가드레일"])

    with tabs_kpi[0]:
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            card("건당 지급 개선액", krw(effect) if effect is not None else "—", f"통제−처리 · {effect_src}")
        with d2:
            title = "월 절감(추정)" if ('period_mode' in globals() and period_mode == "월간") else "오늘 절감(추정)"
            v = krw(saving_mtd) if ('period_mode' in globals() and period_mode == "월간") else (krw(saving_today) if saving_today is not None else "—")
            sub=[]
            if sub_asof:
                sub.append(sub_asof)
            if dod_pct is not None and ('period_mode' in globals() and period_mode != "월간"):
                sub.append(f"전일 대비: {dod_pct*100:+.1f}%")
            if ma7 is not None and ('period_mode' in globals() and period_mode != "월간"):
                sub.append(f"7일 평균: {krw(ma7)}")
            card(title, v, " · ".join(sub))
        with d3:
            v = krw(saving_qtd) if saving_qtd is not None else "—"
            card("분기 누적 절감(추정)", v, f"{sub_asof}")
        with d4:
            # 월 목표는 얇은 진행바 + 한 줄 설명(덱 스타일)
            prog_any = prog if (prog is not None) else safe_ratio(saving_mtd, target_mtd)
            if target_mtd is not None and saving_mtd is not None:
                sub = f"누적 {krw(saving_mtd)} / 목표 {krw(target_mtd)}"
            elif target_mtd is not None:
                sub = f"목표 {krw(target_mtd)}"
            else:
                sub = "월 목표 미설정"
            mini_progress("월 목표 달성률", prog_any, sub)

    with tabs_kpi[1]:
        d1, d2, d3, d4 = st.columns(4)
        if ('period_mode' in globals() and period_mode == "월간"):
            rr = ops_period.get("review_rate")
            tr = ops_period.get("treat_rate")
            cr_obs = ops_period.get("control_rate")
            sc = ops_period.get("avg_score")
            with d1:
                card("총 청구 건수", fmt_int(ops_period.get("n")), f"{sub_asof} · 기간 합산")
            with d2:
                card("검토 전환율", fmt_pct(rr, digits=1) if rr is not None else "—", f"{sub_asof} · 기간 평균")
            with d3:
                sub = f"관측 통제 비중 {fmt_pct(cr_obs, digits=1)}" if cr_obs is not None else ""
                card("처리 비중", fmt_pct(tr, digits=1) if tr is not None else "—", sub)
            with d4:
                card("평균 리스크 점수", fmt_score(sc, digits=3) if sc is not None else "—", "0~1 (높을수록 위험)")
        else:
            with d1:
                v = f"{ops.claims_today:,}" if ops.claims_today is not None else "—"
                card("금일 청구 건수", v, sub_asof)
            with d2:
                v = fmt_pct(ops.review_rate_today, digits=1) if ops.review_rate_today is not None else "—"
                card("검토 전환율", v, sub_asof)
            with d3:
                v = fmt_pct(ops.treatment_rate_today, digits=1) if ops.treatment_rate_today is not None else "—"
                sub = fmt_pct(ops.control_rate_observed, digits=1)
                card("처리 비중", v, f"관측 통제 비중 {sub}" if sub != "—" else "")
            with d4:
                v = fmt_score(ops.avg_score_today, digits=3) if ops.avg_score_today is not None else "—"
                card("평균 리스크 점수", v, "0~1 (높을수록 위험)")

    with tabs_kpi[2]:
        q1, q2, q3 = st.columns(3)
        with q1:
            card("가드레일 상태", g_label, sub_asof, variant="compact")
        with q2:
            card("유의확률(p)", pvalue(pval), "통제 vs 처리", variant="compact")
        with q3:
            card("세그먼트 경보", fmt_int(seg_n), "모니터링 룰", variant="compact")
        with st.expander("가드레일 상세 기준", expanded=False):
            st.markdown(
                "- **가드레일(GO/HOLD/ROLLBACK)**: 핵심 지표가 기준 범위 내인지 점검합니다.\n"
                "- **p-value**: 통제 vs 처리 차이의 유의성(참고 지표)입니다.\n"
                "- **세그먼트 경보**: 특정 세그먼트에 리스크 패턴이 집중되는지 감시합니다.\n"
            )

st.caption(f"{period_caption} · 가드레일 {g_label} · p={pvalue(pval)} · 세그먼트 경보 {seg_n}건")

tabs=st.tabs(["임원 요약", "효과 분석", "세그먼트·요인", "운영", "근거"])

# -----------------------------
# TAB 0 — Executive — One-page deck
# -----------------------------
with tabs[0]:
    st.markdown('<div class="section-h">임원 요약</div>', unsafe_allow_html=True)

    st.markdown("### 핵심 메시지")
    km=[]
    km.append(f"가드레일 판단은 **{g_label}** 입니다.")
    if effect is not None:
        km.append(f"건당 지급액은 **{krw(effect)} 개선**되었습니다(통제−처리).")
    if saving_mtd is not None:
        km.append(f"월 누적 절감은 **{krw(saving_mtd)}(추정)** 입니다.")
    insight_box("핵심 메시지", km, tone=g_tone)

    st.markdown("### 근거")
    st.caption("*건당 지급 개선액=통제군 평균 지급액 − 처리군 평균 지급액")

    # 핵심 세그먼트 5개만 노출 (상세는 접기)
    if ledger is None or ledger.empty:
        st.info("원장(out/decision_ledger.csv)이 없습니다. 파이프라인 실행 또는 데모 생성이 필요합니다.")
    else:
        claims = read_csv("data/claims.csv")
        led = ledger.copy()
        if not claims.empty and "claim_id" in claims.columns and "claim_id" in led.columns:
            cols = [c for c in claims.columns if c not in ["paid_amount"]]
            led = led.merge(claims[cols], on="claim_id", how="left", suffixes=("", "_claim"))
        led = fill_from_claim_cols(led, ["channel","product_line","product","region","hospital_grade","hospital_id"])
        hte = compute_hte(led, seg_cols=["channel","product_line","region"], min_n=150)
        if hte is not None and not hte.empty:
            top5 = hte.sort_values("delta_paid_c_minus_t", ascending=False).head(5)
            st.dataframe(hte_top_table_for_display(top5, top_n=5), use_container_width=True, hide_index=True, height=240)
        else:
            st.caption("세그먼트별 효과(HTE)를 계산할 데이터가 부족합니다.")

    # 1개 핵심 차트만 유지
    st.markdown("#### 효과 추세")
    trend = read_csv(path_out("impact_daily_delta.csv"))
    if trend is None or trend.empty:
        st.caption("일별 효과 추세 데이터가 없습니다.")
    else:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
        df = trend.copy()
        df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
        df["delta_paid_c_minus_t"] = pd.to_numeric(df.get("delta_paid_c_minus_t"), errors="coerce")
        df = df.dropna(subset=["date", "delta_paid_c_minus_t"]).sort_values("date").tail(60)
        fig, ax = plt.subplots(figsize=(9.8, 3.0), dpi=150)
        ax.plot(df["date"], df["delta_paid_c_minus_t"], linewidth=2)
        ax.axhline(0, linestyle="--", linewidth=1)
        ax.set_title("일별 지급액 개선(통제−처리)", loc="left", fontsize=12, fontweight="bold")
        ax.grid(True, axis="y", linewidth=0.4, alpha=0.25)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{int(x):,}"))
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)

    st.markdown("### 실행 권고")
    if g_label == "GO":
        st.markdown("""- 효과가 큰 세그먼트를 우선 대상으로 **단계적 확대 적용**을 권고합니다.
- 운영 부하(SLA·대기)를 일 단위로 모니터링하고, 필요 시 **검토 배정 비율 상한**을 조정합니다.
- 월간 리포트에 **가드레일 사유·세그먼트 경보**를 고정 포함합니다.""")
    elif g_label == "HOLD":
        st.markdown("""- 확대 적용은 보류하고, **세그먼트별 효과·경보 원인**을 우선 점검합니다.
- 데이터 결측(세그먼트·룰)과 실험 설정(통제 비율)을 교정합니다.
- 보정 후 재실험 결과를 기준으로 **재의사결정**합니다.""")
    else:
        st.markdown("""- 정책을 기준선으로 복귀하고, 부정 신호(경보·역효과) 원인을 분석합니다.
- 운영·정책·모델 가드레일을 강화한 뒤 **재출시**를 검토합니다.""")

    st.markdown('<div class="section-h">내보내기</div>', unsafe_allow_html=True)
    cbtn, cn = st.columns([1, 3])
    with cbtn:
        if st.button("📄 임원 원페이지 PDF 생성", use_container_width=True):
            md = read_text(path_out("executive_summary.md"))
            hi = _pick_highlights(md, max_lines=10)
            ms = methods_summary(panel)
            kpis = {
                "policy_ver": pv, "policy_mode": pm, "control_rate": cr,
                "effect_per_claim": krw(effect),
                "saving_today": krw(saving_today) if saving_today is not None else "—",
                "saving_mtd": krw(saving_mtd) if saving_mtd is not None else "—",
                "saving_qtd": krw(saving_qtd) if saving_qtd is not None else "—",
                "p_value": pvalue(pval),
                "guardrails_badge": g_label,
                "red_flag": bool(red_flag),
            }
            export_onepager_pdf(
                output_pdf=path_out("executive_onepager.pdf"),
                ci=ci, kpis=kpis, highlights=hi,
                chart_left=path_out("chart_impact_delta.png"),
                chart_right=None,
                methods_summary=ms,
            )
            st.success("out/executive_onepager.pdf 생성 완료")
    with cn:
        st.caption("임원 보고용 1장(PDF): KPI · 핵심 메시지 · 추세 · 방법 요약")

    pdfp = path_out("executive_onepager.pdf")
    if exists(pdfp):
        with open(pdfp, "rb") as f:
            st.download_button(
                "⬇️ executive_onepager.pdf 다운로드",
                data=f.read(),
                file_name="executive_onepager.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

# -----------------------------
# TAB 1 — Impact — One-page deck
# -----------------------------
with tabs[1]:
    st.markdown('<div class="section-h">영향 측정</div>', unsafe_allow_html=True)

    st.markdown("### 핵심 메시지")
    if ledger is None or ledger.empty:
        st.info("영향 측정을 위한 원장(out/decision_ledger.csv)이 없습니다.")
    else:
        claims = read_csv("data/claims.csv")
        led = ledger.copy()
        if not claims.empty and "claim_id" in claims.columns and "claim_id" in led.columns:
            cols = [c for c in claims.columns if c not in ["paid_amount"]]
            led = led.merge(claims[cols], on="claim_id", how="left", suffixes=("", "_claim"))
        led = fill_from_claim_cols(led, ["channel","product_line","product","region","hospital_grade","hospital_id"])

        summ = compute_experiment_summary(led)
        daily = compute_experiment_daily(led)
        if not summ or daily.empty:
            st.info("실험 지표를 계산할 데이터가 부족합니다.")
        else:
            c = summ["control"]; t = summ["treatment"]
            eff = summ.get("effect_obs")
            rr = t.get("review_rate")

            km=[]
            if eff is not None:
                km.append(f"관측 결과, **건당 지급액이 {krw(eff)} 개선**되었습니다(통제−처리).")
            if rr is not None:
                km.append(f"처리군 검토 전환율은 **{rr*100:.1f}%** 입니다.")
            km.append("효과 추세는 단기 변동이 있으나, 개선 구간이 지속적으로 관찰됩니다.")
            insight_box("핵심 메시지", km, tone="success")

            st.markdown("### 근거")
            a,b,c2 = st.columns(3)
            with a: card("통제군 표본수", f"{int(c.get('n',0)):,}", "기간 합산")
            with b: card("처리군 표본수", f"{int(t.get('n',0)):,}", "기간 합산")
            with c2: card("관측 효과(건당)", krw(eff) if eff is not None else "—", "통제−처리")
            st.caption("*관측 효과(건당)=통제군 평균 지급액 − 처리군 평균 지급액")

            st.markdown("#### 추세(일별)")
            wide = daily.pivot_table(index="date", columns="exp_group", values=["avg_paid"], aggfunc="first")
            wide.columns = [f"{a}_{b.lower()}" for a,b in wide.columns]
            wide = wide.reset_index().sort_values("date")
            if "avg_paid_control" in wide.columns and "avg_paid_treatment" in wide.columns:
                wide["delta_paid_c_minus_t"] = wide["avg_paid_control"] - wide["avg_paid_treatment"]
                import matplotlib.pyplot as plt
                from matplotlib.ticker import FuncFormatter
                dfx = wide.dropna(subset=["delta_paid_c_minus_t"]).tail(60)
                fig, ax = plt.subplots(figsize=(9.8, 3.0), dpi=150)
                ax.plot(pd.to_datetime(dfx["date"]), dfx["delta_paid_c_minus_t"], linewidth=2)
                ax.axhline(0, linestyle="--", linewidth=1)
                ax.set_title("일별 지급액 개선(통제−처리)", loc="left", fontsize=12, fontweight="bold")
                ax.grid(True, axis="y", linewidth=0.4, alpha=0.25)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{int(x):,}"))
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)

            # ---- Strategy 2x2 (Effect vs Review Lift) ----
            # Minimal, message-first summary; details in expander.
            if led is not None and not led.empty:
                hte2 = compute_hte(led, seg_cols=["channel", "product_line", "region"], min_n=150)
            else:
                hte2 = pd.DataFrame()

            if hte2 is not None and not hte2.empty:
                tmp = hte2.copy()
                tmp["effect"] = pd.to_numeric(tmp.get("delta_paid_c_minus_t"), errors="coerce")
                tmp["lift"] = pd.to_numeric(tmp.get("delta_review_rate_t_minus_c"), errors="coerce")
                tmp = tmp.dropna(subset=["effect", "lift"]).copy()

                # cutoffs: 0 (directional) for one-page exec view
                tmp["zone"] = np.where(
                    (tmp["effect"] > 0) & (tmp["lift"] >= 0), "확대", \
                    np.where((tmp["effect"] > 0) & (tmp["lift"] < 0), "유지", \
                             np.where((tmp["effect"] <= 0) & (tmp["lift"] >= 0), "재설계", "중단"))
                )

                st.markdown("#### 전략 매트릭스 요약")
                zc = tmp["zone"].value_counts().to_dict()
                st.caption(
                    f"효과(지급 개선)와 검토 전환율 변화를 기준으로 세그먼트를 4개 구역으로 분류했습니다. "
                    f"확대 {fmt_int(zc.get('확대',0))} · 유지 {fmt_int(zc.get('유지',0))} · "
                    f"재설계 {fmt_int(zc.get('재설계',0))} · 중단 {fmt_int(zc.get('중단',0))}"
                )

                with st.expander("세그먼트 분류 상세(Top)", expanded=False):
                    view = tmp.sort_values(["zone", "effect"], ascending=[True, False]).head(20)
                    out = view[["segment_col", "segment", "n_total", "effect", "lift", "zone"]].copy()
                    out = out.rename(columns={
                        "segment_col": "구분",
                        "segment": "세그먼트",
                        "n_total": "표본수",
                        "effect": "건당 지급 개선액",
                        "lift": "검토율 변화",
                        "zone": "권고",
                    })
                    out["표본수"] = out["표본수"].map(fmt_int)
                    out["건당 지급 개선액"] = out["건당 지급 개선액"].map(fmt_krw)
                    out["검토율 변화"] = out["검토율 변화"].map(lambda v: fmt_pct(v, 2))
                    st.dataframe(out, use_container_width=True, hide_index=True)

            st.markdown("### 실행 권고")
            acts=[]
            if eff is not None and float(eff) > 0:
                acts.append("효과가 확인된 현 정책을 유지하되, 확대 적용은 단계적으로 진행합니다.")
            else:
                acts.append("효과가 제한적이므로, 세그먼트 기반 재설계 후보를 선별합니다.")
            acts.append("통제 비율·세그먼트 결측을 점검하여 추정 안정성을 확보합니다.")
            acts.append("월간 리포트에 유의확률·가드레일을 고정 포함합니다.")
            st.markdown("\n".join([f"- {x}" for x in acts]))

            with st.expander("상세 지표(표)", expanded=False):
                df = pd.DataFrame([
                    {"구분":"통제군","표본수":c.get("n"),"평균 지급액":c.get("avg_paid"),"검토 전환율":c.get("review_rate")},
                    {"구분":"처리군","표본수":t.get("n"),"평균 지급액":t.get("avg_paid"),"검토 전환율":t.get("review_rate")},
                ])
                df["표본수"] = df["표본수"].map(fmt_int)
                df["평균 지급액"] = df["평균 지급액"].map(fmt_krw)
                df["검토 전환율"] = df["검토 전환율"].map(lambda v: fmt_pct(v,1))
                st.dataframe(df, use_container_width=True, hide_index=True)

# -----------------------------
# TAB 2 — Segments & Drivers (BCG)
# -----------------------------
with tabs[2]:
    st.markdown('<div class="section-h">Segments & drivers</div>', unsafe_allow_html=True)
    st.caption("구성: 핵심 메시지 → 근거 → 실행 권고")

    if ledger is None or ledger.empty:
        st.info("Missing out/decision_ledger.csv — run pipeline or generate demo telemetry.")
    else:
        claims = read_csv("data/claims.csv")
        led = ledger.copy()
        if not claims.empty and "claim_id" in claims.columns and "claim_id" in led.columns:
            cols = [c for c in claims.columns if c not in ["paid_amount"]]
            led = led.merge(claims[cols], on="claim_id", how="left", suffixes=("", "_claim"))
        led = fill_from_claim_cols(led, ["channel","product_line","product","region","hospital_grade","hospital_id"])

        # -----------------------------
        # Build artifacts
        # -----------------------------
        dims = ["channel","product_line","product","region","hospital_grade"]
        hte_all = []
        for d0 in dims:
            tmp = compute_hte(led, seg_cols=[d0], min_n=150)
            if tmp is not None and not tmp.empty:
                hte_all.append(tmp)
        hte_all = pd.concat(hte_all, ignore_index=True) if hte_all else pd.DataFrame()

        dd = led.copy()
        dd["score"] = pd.to_numeric(dd.get("score"), errors="coerce")
        dd = dd.dropna(subset=["score"]).sort_values("score", ascending=False)
        top = attach_rule_reasons(dd.head(300).copy())
        top["risk_reasons"] = top.get("risk_reasons", "").astype(str)
        driver_cat = build_driver_category_table(top)
        prof = compare_profiles(dd, score_col="score")
        prof_num_raw = prof.get("numeric") if isinstance(prof, dict) else pd.DataFrame()
        prof_num = profile_table_with_interpretation(prof_num_raw)

        # -----------------------------
        # KEY MESSAGE
        # -----------------------------
        st.markdown("### 핵심 메시지")
        km = generate_key_messages(hte_all, driver_cat, prof_num_raw)
        if km:
            insight_box("핵심 메시지", km, tone="success")
        else:
            st.info("핵심 메시지를 생성할 데이터가 부족합니다. 데모 텔레메트리를 생성하거나 파이프라인을 실행하세요.")

        # -----------------------------
        # SUPPORTING EVIDENCE
        # -----------------------------
        st.markdown("### 근거")
        left, right = st.columns([1, 1], gap="large")

        with left:
            st.markdown("#### HTE — 효과가 큰 구간 Top 5")
            if hte_all.empty:
                st.caption("HTE not available (insufficient segment attributes or sample size).")
            else:
                top5_raw = hte_all.sort_values("delta_paid_c_minus_t", ascending=False).head(5).copy()
                show = hte_top_table_for_display(top5_raw, top_n=5)
                # 시사점 컬럼 추가 (원본 수치 기반)
                imp = []
                for v in top5_raw["delta_paid_c_minus_t"].tolist():
                    try:
                        vv = float(v)
                    except Exception:
                        vv = 0.0
                    imp.append("확대 적용 권장" if vv > 0 else "효과 제한")
                show["시사점"] = imp
                st.dataframe(show, use_container_width=True, hide_index=True, height=240)

            with st.expander("세그먼트 차원별 상세(HTE)", expanded=False):
                dim = st.selectbox("세그먼트 차원", dims, index=0)
                hte_dim = compute_hte(led, seg_cols=[dim], min_n=150)
                if hte_dim is None or hte_dim.empty:
                    st.caption("선택한 차원에서 HTE를 계산할 수 없습니다.")
                else:
                    st.dataframe(hte_table_for_display(hte_dim).head(20), use_container_width=True, hide_index=True)

        with right:
            st.markdown("#### 리스크 드라이버 — 카테고리 요약")
            if driver_cat.empty:
                st.caption("의심 사유(룰) 데이터가 없습니다.")
            else:
                st.dataframe(driver_cat.head(8), use_container_width=True, hide_index=True, height=240)

            st.markdown("#### 고위험 vs 저위험 프로파일")
            if prof_num.empty:
                st.caption("프로파일 비교 결과가 없습니다.")
            else:
                # 차이가 큰 지표 우선 노출
                tmp = prof_num.copy()
                if "평균 차이" in tmp.columns:
                    # '평균 차이'는 아직 원본 numeric 값일 수 있음 → prof_num_raw 기준으로 정렬
                    try:
                        raw = prof_num_raw.copy()
                        raw["abs_diff"] = pd.to_numeric(raw.get("mean_diff"), errors="coerce").abs()
                        order = raw.sort_values("abs_diff", ascending=False)["feature"].head(7).tolist()
                        tmp = tmp[tmp["지표"].isin([FEATURE_LABELS.get(x, x) for x in order])]
                    except Exception:
                        tmp = tmp.head(7)
                st.dataframe(tmp.head(7), use_container_width=True, hide_index=True, height=320)

        st.divider()
        st.markdown("### 실행 권고")
        actions = generate_actions(hte_all, driver_cat)
        if actions:
            st.markdown("\n".join([f"- {a}" for a in actions]))
        else:
            st.caption("Actions를 생성할 데이터가 부족합니다.")


        # Keep detailed review table (evidence) in expander to keep deck layout clean
        with st.expander("검토 대상 Top 고위험 청구 (Evidence)", expanded=False):
            keep = [c for c in [
                "claim_date", "claim_id", "score", "decision", "paid_amount",
                "channel", "product_line", "product", "region", "hospital_grade", "risk_reasons"
            ] if c in top.columns]
            top_show = top[keep].head(25).copy()
            top_show = apply_business_labels(top_show)
            if "리스크 점수" in top_show.columns:
                top_show["리스크 점수"] = top_show["리스크 점수"].map(lambda v: fmt_score(v, 3))
            if "지급액" in top_show.columns:
                top_show["지급액"] = top_show["지급액"].map(fmt_krw)
            st.dataframe(top_show, use_container_width=True, hide_index=True, height=520)

# -----------------------------
# TAB 3 — 운영 — One-page deck
# -----------------------------
with tabs[3]:
    st.markdown('<div class="section-h">운영 현황</div>', unsafe_allow_html=True)

    st.markdown("### 핵심 메시지")
    rq = read_csv(path_out("review_cases.csv"))
    if rq.empty:
        st.info("운영 데이터(out/review_cases.csv)가 없습니다.")
    else:
        rq["status"] = rq["status"].astype(str).str.upper()
        pending = rq[rq["status"]=="PENDING"].copy()
        breach = int(rq.get("breach_sla", False).astype(bool).sum()) if "breach_sla" in rq.columns else 0
        sla = int(pd.to_numeric(rq.get("sla_hours"), errors="coerce").dropna().iloc[0]) if "sla_hours" in rq.columns and rq["sla_hours"].notna().any() else None

        km=[]
        km.append(f"현재 **대기 {len(pending):,}건**, SLA 위반 **{breach:,}건**입니다.")
        if sla is not None:
            km.append(f"운영 기준 SLA는 **{sla}시간**입니다.")
        km.append("운영 안정성(SLA)은 확대 적용보다 우선입니다.")
        insight_box("핵심 메시지", km, tone="warn" if breach>0 else "success")

        st.markdown("### 근거")
        a,b,c2 = st.columns(3)
        with a: card("대기 건수", f"{len(pending):,}", "리뷰 큐")
        with b: card("SLA 위반", f"{breach:,}", "누적")
        with c2: card("처리 완료", f"{int((rq['status']!='PENDING').sum()):,}", "승인+거절")
        st.caption("*SLA 위반=대기시간이 SLA 기준을 초과한 건")

        st.markdown("### 실행 권고")
        acts=[]
        if breach>0:
            acts.append("SLA 안정화를 위해 검토 배정 비율 상한을 일시 조정합니다.")
            acts.append("고위험 상위 구간 우선 처리로 효율을 유지합니다.")
        else:
            acts.append("운영이 안정적이면, 효과가 큰 세그먼트 중심으로 단계적 확대를 검토합니다.")
        acts.append("대기·위반 지표를 일 단위로 상단 KPI에 고정 노출합니다.")
        st.markdown("\n".join([f"- {x}" for x in acts]))

        with st.expander("큐 상세(표)", expanded=False):
            show = rq.sort_values(["status","age_hours"], ascending=[True, False]).head(200).copy()
            show = apply_business_labels(show)
            if "대기시간(시간)" in show.columns:
                show["대기시간(시간)"] = show["대기시간(시간)"].map(fmt_int)
            if "SLA(시간)" in show.columns:
                show["SLA(시간)"] = show["SLA(시간)"].map(fmt_int)
            if "SLA 위반" in show.columns:
                show["SLA 위반"] = show["SLA 위반"].map(lambda v: "Y" if bool(v) else "N")
            if "리스크 점수" in show.columns:
                show["리스크 점수"] = show["리스크 점수"].map(lambda v: fmt_score(v, 3))
            if "지급액" in show.columns:
                show["지급액"] = show["지급액"].map(fmt_krw)
            st.dataframe(show, use_container_width=True, hide_index=True)

# -----------------------------
# TAB 4 — Evidence (never blank; uses expanders)
# -----------------------------
with tabs[4]:
    st.markdown('<div class="section-h">감사·검증 자료</div>', unsafe_allow_html=True)

    st.markdown("### 핵심 메시지")
    insight_box("핵심 메시지", [
        "주요 판단(효과·가드레일·세그먼트 경보)은 표준 산출물로 재현 가능합니다.",
        "정기 샘플링 감사로 운영 리스크를 선제 관리할 수 있습니다.",
    ])

    st.markdown("### 근거")
    files=[
        ("임원 원페이지 PDF", "executive_onepager.pdf"),
        ("일별 효과 추세", "impact_daily_delta.csv"),
        ("가드레일 결정", "guardrails_decision.csv"),
        ("세그먼트 경보", "segment_alerts.csv"),
        ("실험 요약", "impact_panel.csv"),
    ]
    rows=[]
    for label,f in files:
        rows.append({"자료":label, "파일":f, "상태":"존재" if exists(path_out(f)) else "없음", "수정시각": mtime(path_out(f)) if exists(path_out(f)) else "—"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=240)

    st.markdown("### 실행 권고")
    st.markdown("""- 월간 리포트에 ‘가드레일 사유’와 ‘세그먼트 경보’를 고정 포함합니\n- 모델/정책 변경 시 본 탭 산출물로 재현 가능성(재계산)을 확인합니다.\n- 고위험 케이스는 정기 샘플링 감사로 선제 관리합니다.""")

    with st.expander("원천 산출물(전체)", expanded=False):
        ip = read_csv(path_out("impact_panel.csv"))
        if not ip.empty:
            st.markdown("#### impact_panel.csv")
            st.dataframe(apply_business_labels(ip), use_container_width=True, hide_index=True)
        sig = read_csv(path_out("impact_significance_scipy.csv"))
        if not sig.empty:
            st.markdown("#### impact_significance_scipy.csv")
            st.dataframe(apply_business_labels(sig), use_container_width=True, hide_index=True)
        seg = read_csv(path_out("segment_alerts.csv"))
        if not seg.empty:
            st.markdown("#### segment_alerts.csv")
            st.dataframe(apply_business_labels(seg), use_container_width=True, hide_index=True)
