import os
import html
import pandas as pd
from datetime import datetime

OUT = "out"

def md_to_html_basic(md: str) -> str:
    lines = md.splitlines()
    out = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        s = line.rstrip()
        if s.startswith("# "):
            out.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("- "):
            out.append(f"<li>{html.escape(s[2:])}</li>")
        elif s.strip() == "":
            out.append("<br/>")
        else:
            out.append(f"<p>{html.escape(s)}</p>")
    joined = "\n".join(out)
    if "<li>" in joined:
        joined = joined.replace("<li>", "<ul><li>", 1) + "</ul>"
    return joined

def build_email_html(md_path: str) -> str:
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Missing report: {md_path}")
    md = open(md_path, "r", encoding="utf-8").read()
    body = md_to_html_basic(md)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    banner = f"""<div style="padding:12px;border-radius:10px;background:#f6f7f9;border:1px solid #e5e7eb;">
    <b>Fraud Executive Summary</b> <span style="color:#6b7280;">({ts})</span>
    </div>"""
    return f"""<html><body style="font-family:Arial, Helvetica, sans-serif; color:#111827; line-height:1.4;">
    {banner}<div style="margin-top:14px;">{body}</div></body></html>"""
