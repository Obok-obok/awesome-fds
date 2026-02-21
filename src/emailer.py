import os
import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import formatdate

def _getenv(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def _parse_recipients(s: str) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]

def send_email(subject: str, html_body: str, attachments: list[str]) -> None:
    enabled = _getenv("MAIL_ENABLED", "0")
    if enabled != "1":
        print("MAIL_ENABLED!=1, skip sending email")
        return

    host = _getenv("SMTP_HOST")
    port = int(_getenv("SMTP_PORT", "587"))
    user = _getenv("SMTP_USER")
    pwd = _getenv("SMTP_PASS")

    mail_from = _getenv("MAIL_FROM", user)
    to = _parse_recipients(_getenv("MAIL_TO"))
    cc = _parse_recipients(_getenv("MAIL_CC"))
    bcc = _parse_recipients(_getenv("MAIL_BCC"))

    if not host or not user or not pwd:
        raise RuntimeError("Missing SMTP_HOST/SMTP_USER/SMTP_PASS env vars")
    if not to:
        raise RuntimeError("MAIL_TO is empty")

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)

    msg.set_content("This email contains an HTML report. Please view in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    for path in attachments:
        if not path or not os.path.exists(path):
            continue
        ctype, _ = mimetypes.guess_type(path)
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(path))

    recipients = to + cc + bcc

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg, from_addr=mail_from, to_addrs=recipients)

    print("email sent to:", recipients)
