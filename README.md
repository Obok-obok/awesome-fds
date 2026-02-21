# 보험금 사기 탐지 기반 정책 효과 검증 시스템 (Claim FDS)

## 재무 성과 중심 실험·확장 의사결정 플랫폼

------------------------------------------------------------------------

# 1. 프로젝트 개요

본 시스템은 보험금 사기 탐지 모델을 단순 예측 도구로 사용하지 않는다.\
목적은 명확하다.

> 모델이 실제 재무 절감 효과를 창출하는지 검증하고,\
> 안전하게 정책을 확대할 수 있는지를 판단하는 것.

즉, 본 시스템은 **모델 성능 관리가 아닌, 정책 성과 관리 시스템**이다.

핵심 질문은 다음 세 가지다.

1.  처리군은 통제군 대비 지급액을 얼마나 절감했는가?
2.  그 차이는 통계적으로 유의한가?
3.  리스크는 통제 가능한 수준인가?

------------------------------------------------------------------------

# 2. 전체 아키텍처

``` mermaid
flowchart TD
A[Claims Data] --> B[Feature Engineering]
B --> C[Model Training]
C --> D[Batch Scoring]
D --> E[Experiment Assignment]
E --> F[Impact Measurement]
F --> G[Statistical Test]
G --> H[Guardrail Decision]
H --> I[Executive Report]
I --> J[Dashboard and Email]
```

------------------------------------------------------------------------

# 3. 데이터 구조

## 입력 데이터 (data/claims.csv)

주요 변수:

-   claim_id
-   claim_date
-   claim_amount
-   paid_amount
-   channel
-   product_line
-   region
-   hospital_grade
-   prior_claim_cnt_12m
-   elapsed_months
-   premium_monthly
-   doc_uploaded_cnt

------------------------------------------------------------------------

# 4. 모델링 구조

## Feature Engineering

파일: src/features.py

-   범주형 인코딩
-   수치형 정규화
-   위험 지표 생성

## 모델 학습

파일: src/train.py, src/validate.py, src/calibrate.py

-   기본 모델: Logistic Regression
-   평가 지표: ROC-AUC, Precision, Recall, Calibration

모델 저장 위치: models/champion.joblib\
models/challenger.joblib

------------------------------------------------------------------------

# 5. 실험 설계

파일: src/experiment.py

-   통제군(Control)과 처리군(Treatment) 무작위 배정
-   Treatment 비율 정책 설정 가능
-   정책 모드 관리 (Experiment / Shadow)

------------------------------------------------------------------------

# 6. 효과 측정 방법론

## 6.1 평균 효과 (Average Treatment Effect)

Δ = 평균 지급액(통제군) − 평균 지급액(처리군)

파일: src/impact_panel.py

------------------------------------------------------------------------

## 6.2 세그먼트별 효과 (HTE)

특정 세그먼트 s에 대해:

HTE_s = 평균(통제군, s) − 평균(처리군, s)

→ 어느 채널·상품·지역에서 정책 효과가 극대화되는지 파악

------------------------------------------------------------------------

# 7. 통계적 검증

파일: src/stats_impact_scipy.py

Welch t-test 사용

t = (평균_c − 평균_t) / sqrt(분산_c/n_c + 분산_t/n_t)

특징:

-   등분산 가정 불필요
-   실제 보험 데이터에 적합
-   p-value 기반 유의성 판단

------------------------------------------------------------------------

# 8. Guardrail 설계

파일: src/guardrails.py

판정 기준:

1.  통계적 유의성 확보
2.  재무 역전 없음
3.  세그먼트 이상 급증 없음

출력:

-   GO
-   HOLD
-   ROLLBACK

------------------------------------------------------------------------

# 9. KPI 정의

  KPI              정의                  산출 파일
  ---------------- --------------------- -----------------------
  MTD 절감         월 누적 절감액        impact_panel.py
  QTD 절감         분기 누적 절감액      impact_panel.py
  건당 지급 개선   통제 대비 평균 차이   impact_panel.py
  검토 전환율      리뷰 전환 비율        experiment.py
  Treatment 비중   처리군 비율           experiment.py
  p-value          통계적 유의성         stats_impact_scipy.py
  Guardrail 상태   정책 판정             guardrails.py

------------------------------------------------------------------------

# 10. Executive Reporting

파일:

-   src/executive_report.py
-   src/pdf_onepager.py
-   src/executive_charts.py

산출물:

-   out/executive_summary.md
-   out/executive_onepager.pdf

구성:

1.  핵심 메시지
2.  정량 근거
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

접속:

http://`<YOUR_VM_EXTERNAL_IP>`{=html}:8501

------------------------------------------------------------------------

# License

Internal Use Only
