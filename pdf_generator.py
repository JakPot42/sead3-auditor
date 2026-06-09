"""
pdf_generator.py
================
Builds the "SEAD 3 Compliance Brief" memo as a PDF using ReportLab.

The layout mimics an official privacy-act memorandum:
    * top + bottom classification banners
    * memo meta block (TO / FROM / DATE / SUBJECT)
    * Executive Summary
    * Event Details table
    * Compliance Assessment (color-coded to the status)
    * signature/footer block

Returns raw PDF bytes so the FastAPI layer can stream it without touching disk.
"""

from __future__ import annotations

import datetime as _dt
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import (
    CLASSIFICATION_BANNER,
    DEMO_BANNER,
    DEMO_MODE,
    FSO_NAME,
    ORG_NAME,
    ComplianceStatus,
)
from helpers import mask_ssn

# Status -> banner color for the Compliance Assessment box.
_STATUS_COLORS = {
    ComplianceStatus.ON_TIME.value: colors.HexColor("#15803d"),    # green
    ComplianceStatus.WARNING.value: colors.HexColor("#b45309"),    # amber
    ComplianceStatus.LATE.value: colors.HexColor("#b91c1c"),       # red
    ComplianceStatus.PENDING_REVIEW.value: colors.HexColor("#475569"),  # slate
}


def _banner_paragraph(text: str, style_sheet) -> Paragraph:
    banner_style = ParagraphStyle(
        "Banner",
        parent=style_sheet["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
        alignment=TA_CENTER,
        backColor=colors.HexColor("#1e293b"),
        borderPadding=(4, 4, 4, 4),
        leading=12,
    )
    return Paragraph(text, banner_style)


def build_compliance_brief(
    *,
    employee_name: str,
    ssn: str,
    event_type: str,
    event_date: _dt.date,
    submission_date: _dt.date,
    reporting_deadline: _dt.date,
    compliance_status: str,
    days_delta: int,
    destination_country: str | None,
    details: str | None,
    explanation: str,
    fso_name: str | None = None,
    record_id: int | None = None,
) -> bytes:
    """Render the memo and return the PDF as bytes."""
    fso_name = fso_name or FSO_NAME
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.55 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        title="SEAD 3 Compliance Brief",
        author=ORG_NAME,
    )

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "MemoTitle", parent=styles["Title"], fontName="Times-Bold",
        fontSize=16, spaceAfter=2, alignment=TA_CENTER,
    )
    h_sub = ParagraphStyle(
        "MemoSub", parent=styles["Normal"], fontName="Times-Italic",
        fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#475569"),
    )
    h_section = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, textColor=colors.HexColor("#1e293b"),
        spaceBefore=9, spaceAfter=3,
    )
    body = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Times-Roman",
        fontSize=10.5, leading=14, alignment=TA_LEFT,
    )

    story: list = []

    # --- top classification banner --------------------------------------- #
    story.append(_banner_paragraph(CLASSIFICATION_BANNER, styles))
    story.append(Spacer(1, 10))

    # --- letterhead ------------------------------------------------------- #
    story.append(Paragraph(ORG_NAME.upper(), h_title))
    story.append(Paragraph("Office of the Facility Security Officer", h_sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.2,
                            color=colors.HexColor("#1e293b")))
    story.append(Spacer(1, 4))
    story.append(Paragraph("MEMORANDUM FOR THE RECORD", ParagraphStyle(
        "MFR", parent=body, fontName="Times-Bold", fontSize=12,
        alignment=TA_CENTER, spaceAfter=8)))

    # --- meta block (TO / FROM / DATE / SUBJECT) -------------------------- #
    ref = f"SEAD3-{record_id:05d}" if record_id else "SEAD3-DRAFT"
    meta_rows = [
        ["TO:", "Personnel Security File / Adjudication Record"],
        ["FROM:", f"{fso_name}, Facility Security Officer"],
        ["DATE:", submission_date.strftime("%d %B %Y")],
        ["REF:", ref],
        ["SUBJECT:", f"SEAD 3 Reportable Activity \u2014 {event_type}"],
    ]
    meta_tbl = Table(meta_rows, colWidths=[0.9 * inch, 5.6 * inch])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#94a3b8")))

    # --- executive summary ------------------------------------------------ #
    story.append(Paragraph("1. Executive Summary", h_section))
    summary = (
        f"This memorandum documents a reportable activity self-disclosed by "
        f"<b>{employee_name}</b> (SSN {mask_ssn(ssn)}) under Security Executive "
        f"Agent Directive 3 (SEAD 3). The activity is categorized as "
        f"<b>{event_type}</b>. Based on the dates of record, the FSO compliance "
        f"engine assessed this report as <b>{compliance_status.upper()}</b>."
    )
    story.append(Paragraph(summary, body))

    # --- event details ---------------------------------------------------- #
    story.append(Paragraph("2. Event Details", h_section))
    detail_rows = [
        ["Field", "Value"],
        ["Employee", employee_name],
        ["Activity Type", event_type],
        ["Date of Event / Departure", event_date.strftime("%d %B %Y")],
    ]
    if destination_country:
        detail_rows.append(["Destination Country", destination_country])
    detail_rows.append(["Date Reported to FSO", submission_date.strftime("%d %B %Y")])
    if details:
        # keep the verbatim disclosure for the record
        detail_rows.append(["Disclosure (verbatim)", details])
    detail_tbl = Table(detail_rows, colWidths=[2.0 * inch, 4.5 * inch])
    detail_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 1), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f1f5f9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(detail_tbl)

    # --- compliance assessment ------------------------------------------- #
    story.append(Paragraph("3. Compliance Assessment", h_section))
    status_color = _STATUS_COLORS.get(compliance_status,
                                      colors.HexColor("#475569"))

    if days_delta >= 0:
        timing_line = (
            f"Reporting threshold met with {days_delta} day(s) of margin "
            f"(deadline {reporting_deadline:%d %B %Y})."
        )
    else:
        timing_line = (
            f"Reporting threshold MISSED by {abs(days_delta)} day(s) "
            f"(deadline {reporting_deadline:%d %B %Y})."
        )

    assess_data = [[Paragraph(
        f"<b>DETERMINATION: {compliance_status.upper()}</b><br/>{timing_line}",
        ParagraphStyle("Assess", parent=body, textColor=colors.white,
                       fontName="Helvetica-Bold", fontSize=11, leading=15))]]
    assess_tbl = Table(assess_data, colWidths=[6.5 * inch])
    assess_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), status_color),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(assess_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<i>{explanation}</i>", body))

    # --- attestation / signature ----------------------------------------- #
    story.append(Paragraph("4. FSO Action", h_section))
    story.append(Paragraph(
        "The above report has been logged in the facility compliance register. "
        "Where flagged LATE, the FSO should document mitigating circumstances and "
        "determine whether an incident report into DISS/JPAS-successor systems is "
        "warranted per agency guidance.", body))
    story.append(Spacer(1, 10))
    sig_tbl = Table(
        [["_______________________________", ""],
         [f"{fso_name}", ""],
         ["Facility Security Officer", ""]],
        colWidths=[3.2 * inch, 3.3 * inch])
    sig_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(sig_tbl)

    def _footer(canvas, doc_):
        canvas.saveState()
        # faint diagonal watermark so sample memos can't be mistaken for real ones
        if DEMO_MODE:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 44)
            canvas.setFillColor(colors.HexColor("#e2e8f0"))
            canvas.translate(letter[0] / 2, letter[1] / 2)
            canvas.rotate(40)
            canvas.drawCentredString(0, 0, "DEMONSTRATION")
            canvas.restoreState()
        # bottom classification banner
        canvas.setFillColor(colors.HexColor("#1e293b"))
        canvas.rect(0, 0.45 * inch, letter[0], 0.22 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(letter[0] / 2, 0.5 * inch, CLASSIFICATION_BANNER)
        # privacy act footnote
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica-Oblique", 6.5)
        canvas.drawCentredString(
            letter[0] / 2, 0.30 * inch,
            "Protected under the Privacy Act of 1974 (5 U.S.C. 552a). "
            "Contains PII \u2014 handle, store, and destroy accordingly.")
        canvas.drawRightString(letter[0] - 0.9 * inch, 0.30 * inch,
                               f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
