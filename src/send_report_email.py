import os
import csv
from datetime import datetime
from src.render_email import build_email_html
from src.emailer import send_email

OUT = "out"

def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

def log_send(status: str, message: str):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "email_send_log.csv")
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["ts", "status", "message"])
        w.writerow([datetime.utcnow().isoformat() + "Z", status, message])

def main():
    load_dotenv(".env")
    subject_prefix = os.getenv("MAIL_SUBJECT_PREFIX", "[Fraud Detection]").strip()
    subject = f"{subject_prefix} Executive Summary"
    md_path = os.path.join(OUT, "executive_summary.md")
    html_body = build_email_html(md_path)
    attachments = [
        os.path.join(OUT, "executive_onepager.pdf"),
        os.path.join(OUT, "chart_impact_delta.png"),
        os.path.join(OUT, "impact_daily_delta.csv"),
        os.path.join(OUT, "impact_panel.csv"),
        os.path.join(OUT, "guardrails_decision.csv"),
        os.path.join(OUT, "segment_alerts.csv"),
        os.path.join(OUT, "impact_significance_scipy.csv"),
    ]
    try:
        send_email(subject=subject, html_body=html_body, attachments=attachments)
        log_send("OK", "sent")
    except Exception as e:
        log_send("FAIL", repr(e))
        raise

if __name__ == "__main__":
    main()
