import os
import re
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepInFrame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _find_korean_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansKR-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def _register_font():
    font_path = _find_korean_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("KFont", font_path))
            return "KFont"
        except Exception:
            pass
    return "Helvetica"

def _pick_highlights(md_text: str, max_lines: int = 10):
    lines = [l.strip() for l in (md_text or "").splitlines()]
    bullets = [l[2:].strip() for l in lines if l.startswith("- ")]
    if bullets:
        return bullets[:max_lines]
    nonempty = [l for l in lines if l]
    return nonempty[:max_lines]

def export_onepager_pdf(
    output_pdf: str,
    ci: dict,
    kpis: dict,
    highlights: list[str],
    chart_left: str | None,
    chart_right: str | None,
    methods_summary: list[dict] | None = None,
):
    os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)

    font_name = _register_font()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("title", parent=styles["Title"], fontName=font_name, fontSize=18, leading=22, textColor=colors.HexColor("#111827"))
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontName=font_name, fontSize=11, leading=14, textColor=colors.HexColor("#111827"), spaceAfter=4)
    p_style = ParagraphStyle("p", parent=styles["BodyText"], fontName=font_name, fontSize=9.5, leading=12, textColor=colors.HexColor("#111827"))
    small_style = ParagraphStyle("small", parent=styles["BodyText"], fontName=font_name, fontSize=8.5, leading=10, textColor=colors.HexColor("#6b7280"))

    doc = SimpleDocTemplate(output_pdf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm,
                            title=ci.get("report_title","Executive Report"))
    story = []

    logo_path = ci.get("logo_path","")
    company = ci.get("company_name","COMPANY")
    report_title = ci.get("report_title","Fraud Program — Executive Report")
    accent = ci.get("accent_color","#0B3B8C")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    left = []
    if logo_path and os.path.exists(logo_path):
        try:
            left.append(Image(logo_path, width=32*mm, height=14*mm))
        except Exception:
            pass
    left.append(Paragraph(f"<b>{company}</b>", small_style))

    right = [
        Paragraph(f"<b>{report_title}</b>", title_style),
        Paragraph(f"Generated: {ts}", small_style),
        Paragraph(f"Policy: {kpis.get('policy_ver','NA')} · Mode: {kpis.get('policy_mode','NA')} · Control: {kpis.get('control_rate','NA')}", small_style),
    ]
    hdr = Table([[left, right]], colWidths=[55*mm, 120*mm])
    hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story.append(hdr)

    line = Table([[""]], colWidths=[175*mm], rowHeights=[2.2*mm])
    line.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor(accent)),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(line)
    story.append(Spacer(1,6))

    if bool(kpis.get("red_flag", False)):
        rf = Table([["RED FLAG: Negative segments detected or guardrails triggered rollback. Immediate review required."]], colWidths=[175*mm])
        rf.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FEF2F2")),("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#FECACA")),
                                ("TEXTCOLOR",(0,0),(-1,-1),colors.HexColor("#991B1B")),("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),10),
                                ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        story.append(rf)
        story.append(Spacer(1,6))

    kpi_rows = [
        [("Effect / Claim (KRW)", kpis.get("effect_per_claim","NA")), ("Saving Today (Est.)", kpis.get("saving_today","NA")), ("Saving MTD (Est.)", kpis.get("saving_mtd","NA"))],
        [("Saving QTD (Est.)", kpis.get("saving_qtd","NA")), ("Welch p-value", kpis.get("p_value","NA")), ("Guardrails", kpis.get("guardrails_badge","NA"))],
    ]
    kpi_table_data = []
    for row in kpi_rows:
        cells = []
        for title, value in row:
            cells.append(Paragraph(f'<font color="#6b7280" size="8">{title}</font><br/><font size="12"><b>{value}</b></font>',
                                   ParagraphStyle("kpi", fontName=font_name, leading=14)))
        kpi_table_data.append(cells)
    kpi_tbl = Table(kpi_table_data, colWidths=[58*mm,58*mm,58*mm])
    kpi_tbl.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.7,colors.HexColor("#e5e7eb")),
                                 ("BACKGROUND",(0,0),(-1,-1),colors.white),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                 ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    story.append(kpi_tbl)
    story.append(Spacer(1,8))

    story.append(Paragraph("Executive Highlights", h_style))
    hl_paras = [Paragraph(f"• {re.sub(r'<.*?>','',h)}", p_style) for h in (highlights or [])]
    story.append(KeepInFrame(175*mm, 35*mm, hl_paras, mode="shrink"))
    story.append(Spacer(1,8))

    # BCG style: prefer one decision-critical chart.
    story.append(Paragraph("Key Chart", h_style))
    if chart_left and os.path.exists(chart_left) and not chart_right:
        try:
            story.append(Image(chart_left, width=175*mm, height=60*mm))
        except Exception:
            story.append(Paragraph("Chart not available", small_style))
    else:
        chart_cells = []
        for cpath in [chart_left, chart_right]:
            if cpath and os.path.exists(cpath):
                try:
                    chart_cells.append(Image(cpath, width=84*mm, height=58*mm))
                except Exception:
                    chart_cells.append(Paragraph("Chart not available", small_style))
            else:
                chart_cells.append(Paragraph("Chart not available", small_style))
        charts_tbl = Table([chart_cells], colWidths=[87.5*mm,87.5*mm])
        charts_tbl.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
        story.append(charts_tbl)

    if methods_summary:
        story.append(Spacer(1,6))
        story.append(Paragraph("Methods Summary (Top 3)", h_style))
        rows = [["Estimator","Effect/Claim (KRW)","p-value"]]
        for r in methods_summary[:3]:
            rows.append([str(r.get("method","NA")), str(r.get("effect_per_claim","NA")), str(r.get("p_value","NA"))])
        ms = Table(rows, colWidths=[95*mm,45*mm,35*mm])
        ms.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F9FAFB")),("FONTNAME",(0,0),(-1,-1),font_name),
                                ("FONTSIZE",(0,0),(-1,0),9),("FONTSIZE",(0,1),(-1,-1),9),
                                ("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#E5E7EB")),("INNERGRID",(0,0),(-1,-1),0.7,colors.HexColor("#E5E7EB")),
                                ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(ms)

    story.append(Spacer(1,6))
    story.append(Paragraph("Note: One-page PDF is generated from out/ artifacts (executive_summary.md + KPI + charts).", small_style))

    doc.build(story)
    return output_pdf
