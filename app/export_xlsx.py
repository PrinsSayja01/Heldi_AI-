from __future__ import annotations
import io
from typing import Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def generate_leads_workbook(leads: list[dict], runs: list[dict] | None = None) -> io.BytesIO:
    """
    Generates a professional 5-tab Excel workbook (.xlsx):
    1. Leads: one row per company with services, portfolio, contact, scores, status
    2. Evidence: field-level claims with source URL, excerpt, source type, retrieval date
    3. Scoring: score dimensions, points, weights, rationale
    4. Research Runs: job history with market, keywords, counts, status
    5. Read Me: scoring guide, source policy, limitations, definitions
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    
    # Styles
    navy_fill = PatternFill(start_color="101827", end_color="101827", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10, color="1F2937")
    title_font = Font(name="Calibri", size=14, bold=True, color="101827")
    sub_font = Font(name="Calibri", size=10, italic=True, color="4B5563")
    bold_font = Font(name="Calibri", size=10, bold=True, color="111827")
    thin_border_side = Side(border_style="thin", color="E5E7EB")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    alt_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")

    def style_header_row(ws, row_idx: int, num_cols: int):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
            cell.border = thin_border
        ws.row_dimensions[row_idx].height = 24

    def auto_fit_columns(ws, min_width: int = 12, max_width: int = 50):
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val = cell.value
                if val is not None:
                    s_len = len(str(val))
                    if s_len > max_len:
                        max_len = s_len
            ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 3, max_width))

    # --- 1. LEADS TAB ---
    ws_leads = wb.create_sheet(title="Leads")
    leads_headers = [
        "Lead ID", "City", "Country", "Company Name", "Website", "Domain", "Address",
        "WEG Mgmt", "Rental Mgmt", "Special Mgmt", "Portfolio Units", "Portfolio Bldgs",
        "Contact Person", "Contact Role", "Contact Email", "Email Type", "Phone",
        "Metering Signal", "Score", "Tier", "Confidence", "Completeness %",
        "Sales Status", "Review Notes", "Evidence Gaps", "Source Count"
    ]
    ws_leads.append(leads_headers)
    style_header_row(ws_leads, 1, len(leads_headers))
    ws_leads.freeze_panes = "A2"
    ws_leads.auto_filter.ref = f"A1:{get_column_letter(len(leads_headers))}{max(2, len(leads) + 1)}"

    for r_idx, l in enumerate(leads, start=2):
        gaps = " | ".join(l.get("gaps") or [])
        sources_cnt = len(l.get("sources") or [])
        row = [
            l.get("id"),
            l.get("city"),
            l.get("country"),
            l.get("name"),
            l.get("website") or "",
            l.get("domain") or "",
            l.get("address") or "",
            l.get("weg_management", "Unknown"),
            l.get("rental_management", "Unknown"),
            l.get("special_management", "Unknown"),
            l.get("portfolio_units") if l.get("portfolio_units") is not None else "",
            l.get("portfolio_buildings") if l.get("portfolio_buildings") is not None else "",
            l.get("contact_person") or "",
            l.get("contact_role") or "",
            l.get("contact_email") or "",
            l.get("email_type") or "",
            l.get("phone") or "",
            l.get("metering_signal", "Unknown"),
            l.get("score", 0),
            l.get("tier", "Tier 3"),
            l.get("confidence", "Low"),
            l.get("completeness", 0),
            l.get("status", "New"),
            l.get("notes") or "",
            gaps,
            sources_cnt
        ]
        ws_leads.append(row)
        for c_idx in range(1, len(row) + 1):
            cell = ws_leads.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = thin_border
            if r_idx % 2 == 1:
                cell.fill = alt_fill
            if c_idx in (11, 12, 19, 22, 26):  # numbers
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        ws_leads.row_dimensions[r_idx].height = 20

    auto_fit_columns(ws_leads)

    # --- 2. EVIDENCE TAB ---
    ws_evidence = wb.create_sheet(title="Evidence")
    evidence_headers = [
        "Lead ID", "Company Name", "Field", "Observed Value", "Verbatim Quote / Excerpt",
        "Source URL", "Source Type", "Retrieved Date", "Validation Status"
    ]
    ws_evidence.append(evidence_headers)
    style_header_row(ws_evidence, 1, len(evidence_headers))
    ws_evidence.freeze_panes = "A2"

    ev_row_count = 1
    for l in leads:
        lead_id = l.get("id")
        lead_name = l.get("name")
        ev_items = l.get("evidence") or []
        for e in ev_items:
            ev_row_count += 1
            row = [
                lead_id,
                lead_name,
                e.get("field", ""),
                str(e.get("value", "")),
                e.get("quote", ""),
                e.get("source_url", ""),
                "Official Website" if "http" in (e.get("source_url") or "") else "Public Source",
                l.get("updated_at") or l.get("created_at") or "",
                "Verified against source text"
            ]
            ws_evidence.append(row)
            for c_idx in range(1, len(row) + 1):
                cell = ws_evidence.cell(row=ev_row_count, column=c_idx)
                cell.font = data_font
                cell.border = thin_border
                if ev_row_count % 2 == 1:
                    cell.fill = alt_fill
            ws_evidence.row_dimensions[ev_row_count].height = 20

    if ev_row_count > 1:
        ws_evidence.auto_filter.ref = f"A1:{get_column_letter(len(evidence_headers))}{ev_row_count}"
    auto_fit_columns(ws_evidence)

    # --- 3. SCORING TAB ---
    ws_scoring = wb.create_sheet(title="Scoring")
    scoring_headers = ["Lead ID", "Company Name", "Total Score", "Tier", "Service Fit (35)", "Portfolio Scale (25)", "Contact Quality (20)", "Metering Signal (10)", "Evidence Quality (10)", "Scoring Rationale"]
    ws_scoring.append(scoring_headers)
    style_header_row(ws_scoring, 1, len(scoring_headers))
    ws_scoring.freeze_panes = "A2"

    for r_idx, l in enumerate(leads, start=2):
        raw = l.get("raw") or {}
        breakdown = raw.get("score_breakdown") or {}
        row = [
            l.get("id"),
            l.get("name"),
            l.get("score", 0),
            l.get("tier", ""),
            breakdown.get("service_fit", 0),
            breakdown.get("portfolio_scale", 0),
            breakdown.get("contact_quality", 0),
            breakdown.get("metering_signal", 0),
            breakdown.get("evidence_quality", 0),
            l.get("rationale") or l.get("summary") or ""
        ]
        ws_scoring.append(row)
        for c_idx in range(1, len(row) + 1):
            cell = ws_scoring.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = thin_border
            if r_idx % 2 == 1:
                cell.fill = alt_fill
            if 3 <= c_idx <= 9:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws_scoring.row_dimensions[r_idx].height = 20

    ws_scoring.auto_filter.ref = f"A1:{get_column_letter(len(scoring_headers))}{max(2, len(leads) + 1)}"
    auto_fit_columns(ws_scoring)

    # --- 4. RESEARCH RUNS TAB ---
    ws_runs = wb.create_sheet(title="Research Runs")
    runs_headers = ["Job ID", "City", "Country", "Status", "Progress %", "Processed", "Saved / Found", "Total Goal", "Started At", "Finished At", "Error / Note"]
    ws_runs.append(runs_headers)
    style_header_row(ws_runs, 1, len(runs_headers))
    ws_runs.freeze_panes = "A2"

    run_list = runs or []
    for r_idx, j in enumerate(run_list, start=2):
        row = [
            j.get("id"),
            j.get("city"),
            j.get("country"),
            j.get("status"),
            j.get("progress", 0),
            j.get("processed", 0),
            j.get("found", 0),
            j.get("total", 0),
            j.get("started_at"),
            j.get("finished_at") or "",
            j.get("error") or ""
        ]
        ws_runs.append(row)
        for c_idx in range(1, len(row) + 1):
            cell = ws_runs.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = thin_border
            if r_idx % 2 == 1:
                cell.fill = alt_fill
        ws_runs.row_dimensions[r_idx].height = 20

    if run_list:
        ws_runs.auto_filter.ref = f"A1:{get_column_letter(len(runs_headers))}{len(run_list) + 1}"
    auto_fit_columns(ws_runs)

    # --- 5. READ ME TAB ---
    ws_readme = wb.create_sheet(title="Read Me")
    readme_content = [
        ("Heidi Lead Intelligence Agent — Lead Research Export", title_font),
        ("Confidential & Evidence-Backed B2B Prospect Intelligence", sub_font),
        ("", None),
        ("1. METHODOLOGY & SCORING RUBRIC (100 TOTAL POINTS)", bold_font),
        ("• Service Fit (35 pts max): WEG Management = 15; Rental Management = 15; Special Property Mgmt (SEV) = 5. Awarded only when backed by public text.", data_font),
        ("• Portfolio Scale (25 pts max): Managed units disclosed on public pages: <100 = 5; 100-499 = 10; 500-1499 = 15; 1500-4999 = 20; 5000+ = 25. Units are never estimated.", data_font),
        ("• Contact Quality (20 pts max): Named decision-relevant person + public business email = 20; named person without direct email = 13; generic business inbox = 8; contact route only = 4.", data_font),
        ("• Metering Signal (10 pts max): Explicit public text showing remote-reading, heat allocators, submetering, HKVO, or transition needs.", data_font),
        ("• Evidence Quality (10 pts max): Verified official pages retrieved, multiple pages checked, verbatim source quotes present.", data_font),
        ("", None),
        ("2. KEY DEFINITIONS & LABELS", bold_font),
        ("• Unknown: Absence of evidence is NOT evidence of absence. A company without website mentions of WEG may still manage WEGs; the field remains Unknown.", data_font),
        ("• Seeded: Records imported from initial case-study workbook. Retain original notes and source links, scored conservatively until re-verified.", data_font),
        ("• Tier 1: Score 80-100 (Immediate high-priority outreach candidate).", data_font),
        ("• Tier 2: Score 60-79 (Solid qualified candidate with minor gaps).", data_font),
        ("• Tier 3: Score <60 (Early research stage, requires manual follow-up).", data_font),
        ("", None),
        ("3. COMPLIANCE & PRIVACY SAFEGUARDS", bold_font),
        ("• Local-First: Inference was executed exclusively on local Ollama hardware. No company text was sent to hosted third-party LLMs.", data_font),
        ("• No LinkedIn Scraping: All contact information is derived strictly from public official website pages, team directories, or imprints.", data_font),
        ("• No Guessed Emails: Personal emails are kept only when verbatim matching observed strings in fetched public pages.", data_font),
        ("• Outreach Notice: Public business email presence does not constitute legal marketing consent. Follow GDPR / national ePrivacy laws.", data_font),
    ]

    for r_idx, (text, font) in enumerate(readme_content, start=1):
        cell = ws_readme.cell(row=r_idx, column=1, value=text)
        if font:
            cell.font = font
        ws_readme.row_dimensions[r_idx].height = 22 if font == title_font else 18

    ws_readme.column_dimensions["A"].width = 110

    # Remove temporary initial sheet
    if default_sheet in wb.worksheets:
        wb.remove(default_sheet)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
