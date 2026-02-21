# FDS Ultimate

## 엔터프라이즈 보험 사기 탐지 시스템

> Data → Intelligence → Decision\
> GCP Free VM 환경에서 운영 가능한 실전형 Fraud Detection 플랫폼

------------------------------------------------------------------------

# 1. Executive Summary

FDS Ultimate는 보험금 사기 탐지를 위한 엔터프라이즈급 머신러닝 기반
시스템입니다.

주요 목적:

-   고위험 보험 청구건 탐지 (Risk Scoring)
-   세그먼트별 이질적 효과 분석 (HTE)
-   임원 보고용 KPI 대시보드 제공
-   원클릭 PDF 보고서 생성
-   자동화된 리포팅 워크플로우 지원

------------------------------------------------------------------------

# 2. Streamlit Cloud 배포 링크

아래 링크에서 데모 확인:

👉 https://YOUR-STREAMLIT-CLOUD-URL.streamlit.app

------------------------------------------------------------------------

# 3. 시스템 아키텍처

Raw Data\
↓\
Feature Engineering\
↓\
ML Model Training\
↓\
Risk Scoring\
↓\
Segment Analysis (HTE)\
↓\
Streamlit Dashboard\
↓\
PDF Export & Email

------------------------------------------------------------------------

# 4. 주요 기능

## 4.1 리스크 스코어링

-   보험 청구건 사기 확률 산출
-   고위험군 자동 분류

## 4.2 세그먼트 분석

-   채널별 효과 분석
-   상품별 위험도 비교
-   지역별 패턴 분석

## 4.3 임원 보고 대시보드

-   KPI 요약
-   리스크 분포 시각화
-   PDF Export 기능

------------------------------------------------------------------------

# 5. 기술 스택

-   Python 3.10+
-   scikit-learn
-   pandas
-   Streamlit
-   Plotly
-   GCP Free VM

------------------------------------------------------------------------

# 6. GCP Free VM 설치 방법

## 6.1 저장소 클론

``` bash
git clone https://github.com/Obok-obok/fds-ultimate.git
cd fds-ultimate
```

## 6.2 가상환경 생성

``` bash
python3 -m venv venv
source venv/bin/activate
```

## 6.3 패키지 설치

``` bash
pip install --upgrade pip
pip install -r requirements.txt
```

------------------------------------------------------------------------

# 7. 모델 학습 실행

``` bash
bash scripts/train.sh
```

또는

``` bash
python src/train_model.py
```

학습 결과: - models/ 폴더에 모델 저장 - 성능 지표 출력

------------------------------------------------------------------------

# 8. 리스크 스코어 실행

``` bash
bash scripts/score.sh
```

또는

``` bash
python src/score.py
```

------------------------------------------------------------------------

# 9. 대시보드 실행

``` bash
streamlit run app.py --server.port 8501
```

접속 주소:

http://YOUR_VM_EXTERNAL_IP:8501

------------------------------------------------------------------------

# 10. requirements.txt 예시

    pandas
    numpy
    scikit-learn
    plotly
    streamlit
    matplotlib
    joblib

requirements 재생성:

``` bash
pip freeze > requirements.txt
```

------------------------------------------------------------------------

# 11. 프로젝트 구조

fds-ultimate/ │ ├── app.py ├── requirements.txt ├── README.md ├── data/
├── models/ ├── src/ ├── scripts/

------------------------------------------------------------------------

# 12. Enterprise AI 원칙 반영

본 시스템은 『The Theory and Practice of Enterprise AI』의 원칙을
반영하여 설계되었습니다:

-   문제 정의 중심 설계
-   데이터 → 모델 → 의사결정 흐름 구조화
-   KPI 기반 성과 모니터링
-   해석 가능한 리스크 분석

------------------------------------------------------------------------

작성자: Obok-obok
