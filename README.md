# Claim Fraud Detection System (FDS)

## Executive Impact Measurement & Policy Optimization Platform

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-dashboard-red)
![Status](https://img.shields.io/badge/status-production_ready-success)
![License](https://img.shields.io/badge/license-internal-lightgrey)

------------------------------------------------------------------------

# 🌐 Live Dashboard

If deployed on a GCP VM:

👉 **Streamlit Dashboard URL**\
http://`<YOUR_VM_EXTERNAL_IP>`{=html}:8501

(Replace `<YOUR_VM_EXTERNAL_IP>` with your actual VM external IP)

------------------------------------------------------------------------

# 🎯 System Objective

This project is not just a fraud model.

It is a **policy optimization and financial impact measurement system**
designed to:

-   Quantify savings via Control vs Treatment experiments
-   Ensure statistical validity
-   Maintain operational guardrails
-   Automatically generate Executive one-page reports
-   Support Champion / Challenger rollout
-   Enable self-healing model governance

------------------------------------------------------------------------

# 🏗 End-to-End Architecture

``` mermaid
flowchart TD
A[Raw Claims] --> B[Feature Engineering]
B --> C[Model Training]
C --> D[Batch Scoring]
D --> E[Experiment Assignment]
E --> F[Impact Panel Estimation]
F --> G[Welch T-test Significance]
G --> H[Guardrails Decision Engine]
H --> I[Executive One-Pager PDF]
I --> J[Streamlit Dashboard & Email Delivery]
```

------------------------------------------------------------------------

# 📂 Repository Structure (v5.5)

    app_exec_dashboard.py
    requirements.txt
    Makefile
    .env.example

    assets/
    data/
    models/
    out/
    src/

------------------------------------------------------------------------

# 📥 Input Data

## data/claims.csv

Required fields:

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

# 🧠 Modeling Pipeline

## Feature Engineering

`src/features.py`

-   Encoding
-   Derived variables
-   Risk indicators

## Model Training

`src/train.py` `src/validate.py` `src/calibrate.py`

Evaluation Metrics: - AUC - Precision / Recall - Calibration curve

Models stored in:

    models/
     ├── champion.joblib
     ├── challenger.joblib
     ├── fraud_lr.joblib

------------------------------------------------------------------------

# 🧪 Experiment Design

`src/experiment.py`

-   Random assignment
-   Treatment ratio control
-   Policy mode control

------------------------------------------------------------------------

# 📊 Impact & Statistics

## Panel Impact

`src/impact_panel.py`

Δ Savings = Avg(Paid_Control) − Avg(Paid_Treatment)

## HTE (Segment Effect)

HTE_s = E\[Y\|T=0, S=s\] − E\[Y\|T=1, S=s\]

## Statistical Significance

`src/stats_impact_scipy.py`

Welch's t-test:

t = (X̄\_c − X̄\_t) / sqrt(s_c²/n_c + s_t²/n_t)

-   No equal variance assumption
-   Welch--Satterthwaite df approximation
-   p-value derived from t-distribution

------------------------------------------------------------------------

# 🛑 Guardrails Framework

`src/guardrails.py`

Decision Rules: - p-value threshold - Financial reversal detection -
Segment anomaly detection

Outputs: - GO - HOLD - ROLLBACK

File: out/guardrails_decision.csv

------------------------------------------------------------------------

# 📈 KPI Dictionary

  -------------------------------------------------------------------------
  KPI              Description                      Source
  ---------------- -------------------------------- -----------------------
  MTD Saving       Month-to-date estimated savings  impact_panel.py

  QTD Saving       Quarter-to-date estimated        impact_panel.py
                   savings                          

  Avg Saving per   Mean control vs treatment diff   impact_panel.py
  Claim                                             

  Review Rate      \% flagged for review            experiment.py

  Treatment Share  \% treatment allocation          experiment.py

  p-value          Statistical significance         stats_impact_scipy.py

  Guardrail Status Rollout safety check             guardrails.py
  -------------------------------------------------------------------------

------------------------------------------------------------------------

# 📄 Executive Reporting

Generated via:

-   `src/executive_report.py`
-   `src/executive_charts.py`
-   `src/pdf_onepager.py`

Outputs:

-   out/executive_summary.md
-   out/executive_onepager.pdf

------------------------------------------------------------------------

# 📧 Automated Email Reporting

-   src/send_report_email.py
-   src/emailer.py
-   src/render_email.py

Supports: - Markdown to HTML conversion - PDF attachment - SMTP delivery

------------------------------------------------------------------------

# 🔁 Champion / Challenger & Self-Healing

-   src/promote_if_better.py
-   src/rollout_controller.py
-   src/run_self_healing.sh

Supports: - Automatic model promotion - Automatic rollback on guardrail
breach

------------------------------------------------------------------------

# 🚀 Deployment (GCP VM)

``` bash
git clone <repo>
cd repo

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.simulate_production_outputs --scenario GO --days 120

streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

Open browser: http://`<YOUR_VM_EXTERNAL_IP>`{=html}:8501

------------------------------------------------------------------------

# 📚 Enterprise AI Principles

This system follows Enterprise AI best practices:

1.  AI as decision policy, not prediction tool
2.  Controlled experimentation required
3.  Statistical validation mandatory
4.  Guardrails override financial gain
5.  Continuous feedback loop & safe rollout

------------------------------------------------------------------------

# 📜 License

Internal / Educational Use Only
