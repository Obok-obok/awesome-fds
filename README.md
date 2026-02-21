# 보험금 사기 탐지 기반 정책 효과 검증 시스템 (Claim FDS)

## 실험 기반 재무 효과 측정 및 안전한 정책 확장 프레임워크

------------------------------------------------------------------------

# 1. 연구 및 시스템 개요

본 시스템은 보험금 사기 탐지(Fraud Detection)를 단순한 분류 문제로
접근하지 않는다.\
대신, **"모델이 실제 재무 성과를 창출하는가?"**라는 질문에 답하기 위한
실험 기반 정책 검증 시스템으로 설계되었다.

핵심 목적은 다음과 같다.

1.  모델 기반 의사결정이 통제군 대비 재무적 절감 효과를 창출하는지
    정량적으로 검증
2.  통계적으로 유의한 효과가 존재하는 경우에만 정책을 확대
3.  효과가 특정 세그먼트에 집중되는지(Heterogeneous Treatment Effect)
    분석
4.  가드레일(Guardrails)을 통해 재무적 역전 및 이상 현상을 사전에 차단
5.  위 결과를 임원 보고 수준의 One-Page 리포트로 자동 생성

이는 "예측 모델 운영"이 아닌, **의사결정 중심 AI(Decision-Centric AI)**
운영 체계를 구현한 것이다.

------------------------------------------------------------------------

# 2. 전체 아키텍처

``` mermaid
flowchart TD
A[청구 데이터] --> B[Feature Engineering]
B --> C[모델 학습]
C --> D[배치 스코어링]
D --> E[실험군 배정]
E --> F[효과 측정 (Impact)]
F --> G[통계적 유의성 검정]
G --> H[가드레일 판정]
H --> I[Executive One-Pager 생성]
I --> J[Streamlit 대시보드 및 이메일 발송]
```

------------------------------------------------------------------------

# 3. 데이터 구조

## 3.1 입력 데이터 (data/claims.csv)

주요 변수:

-   claim_id (청구 ID)
-   claim_date (청구일)
-   claim_amount (청구금액)
-   paid_amount (지급금액)
-   channel (채널)
-   product_line (상품군)
-   region (지역)
-   hospital_grade (의료기관 등급)
-   prior_claim_cnt_12m (최근 12개월 청구 건수)
-   elapsed_months (가입 경과 개월 수)
-   premium_monthly (월 보험료)
-   doc_uploaded_cnt (제출 서류 수)

------------------------------------------------------------------------

# 4. 모델링 방법론

## 4.1 Feature Engineering

파일: `src/features.py`

-   범주형 인코딩
-   수치형 정규화
-   위험도 기반 파생 변수 생성

## 4.2 모델 학습

파일: `src/train.py`, `src/validate.py`, `src/calibrate.py`

-   기본 모델: Logistic Regression
-   평가 지표:
    -   ROC-AUC
    -   Precision / Recall
    -   Calibration Curve

Champion / Challenger 구조를 통해 모델 교체 시 안정성을 확보한다.

------------------------------------------------------------------------

# 5. 실험 설계

파일: `src/experiment.py`

모델 적용 집단(Treatment)과 기존 정책 집단(Control)을 무작위 배정한다.

Treatment 비율은 정책 설정값에 따라 결정되며, 이는 운영 리스크를
통제하기 위한 핵심 변수다.

------------------------------------------------------------------------

# 6. 효과 측정 방법론

## 6.1 평균 효과 (ATE)

통제군과 처리군 평균 지급액 차이:

Δ = E\[Y\|T=0\] − E\[Y\|T=1\]

여기서:

-   Y = 지급금액
-   T = 처리 여부

파일: `src/impact_panel.py`

------------------------------------------------------------------------

## 6.2 이질적 효과 (HTE)

세그먼트 s에 대해:

HTE_s = E\[Y\|T=0, S=s\] − E\[Y\|T=1, S=s\]

이를 통해 특정 채널/상품/지역에서 정책 효과가 집중되는지 분석한다.

------------------------------------------------------------------------

# 7. 통계적 유의성 검정

파일: `src/stats_impact_scipy.py`

Welch's t-test를 사용한다.

t 통계량:

t = (X̄\_c − X̄\_t) / sqrt(s_c²/n_c + s_t²/n_t)

특징:

-   등분산 가정 불필요
-   Welch--Satterthwaite 자유도 근사
-   보험 데이터 특성상 분산 차이를 허용하는 것이 합리적

p-value \< α 인 경우 통계적으로 유의한 절감 효과로 판단한다.

------------------------------------------------------------------------

# 8. 가드레일(Guardrails) 설계

파일: `src/guardrails.py`

판정 기준:

1.  통계적 유의성 확보
2.  재무적 역전(negative lift) 없음
3.  세그먼트 급격한 이상 증가 없음

출력:

-   GO
-   HOLD
-   ROLLBACK

------------------------------------------------------------------------

# 9. KPI 정의

  KPI              정의                  계산 파일
  ---------------- --------------------- -----------------------
  MTD 절감액       월 누적 절감          impact_panel.py
  QTD 절감액       분기 누적 절감        impact_panel.py
  건당 지급 개선   통제-처리 평균 차이   impact_panel.py
  검토 전환율      리뷰 전환 비율        experiment.py
  Treatment 비중   처리군 비율           experiment.py
  p-value          통계 유의성           stats_impact_scipy.py
  가드레일 상태    정책 판정             guardrails.py

------------------------------------------------------------------------

# 10. Executive Reporting

파일:

-   `src/executive_report.py`
-   `src/pdf_onepager.py`
-   `src/executive_charts.py`

구조:

1.  핵심 메시지
2.  근거 (정량 지표)
3.  실행 권고

------------------------------------------------------------------------

# 11. 배포 방법 (GCP VM)

``` bash
git clone <repo>
cd repo

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.simulate_production_outputs --scenario GO --days 120

streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

------------------------------------------------------------------------

# 12. Enterprise AI 관점에서의 의의

본 시스템은 다음 원칙을 따른다.

1.  AI는 예측이 아니라 의사결정 시스템이다.
2.  모든 정책은 실험을 통해 검증되어야 한다.
3.  통계적 유의성이 확보되지 않으면 확장하지 않는다.
4.  가드레일은 재무 성과보다 우선한다.
5.  지속적 피드백 루프를 통해 안전하게 개선한다.

이는 기업 환경에서 요구되는 "안전한 AI 확장(Safe AI Rollout)"의 모범
사례에 해당한다.

------------------------------------------------------------------------

# License

Internal / Educational Use Only
