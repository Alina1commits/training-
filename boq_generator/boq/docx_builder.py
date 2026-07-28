"""Assemble the final BOQ .docx, styled after BOQ_expected.docx:
header field table, three hero images, a numbered specifications table,
then Fountainhead's fixed legal boilerplate and a signature block.
"""
from __future__ import annotations

from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from boq import legal_text

SECTION_ORDER = [
    "1 Floor", "2 Stand", "3 Furniture", "4 Electrical | Lightning",
    "5 Miscellaneous", "6 Signing", "7 Installation | Dismantling | Transport",
    "8 AV/VIDEO",
]

HEADER_SHADE = "D9E2F3"


def _shade_cell(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_cell_borders(cell, sz="4", color="999999"):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:color"), color)
        borders.append(el)
    tcPr.append(borders)


def _bold_run(paragraph, text, size=11, color=None):
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def _add_header_field_table(doc, header_fields: dict):
    table = doc.add_table(rows=4, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    rows = [
        ("Client:", header_fields.get("client", ""), "Contact Person:", header_fields.get("contact_person", "")),
        ("Trade Show:", header_fields.get("trade_show", ""), "Email:", header_fields.get("email", "")),
        ("Date:", header_fields.get("show_dates", ""), "Date:", header_fields.get("doc_date", "")),
        ("Venue:", header_fields.get("venue", ""), "Project:", header_fields.get("project", "")),
    ]
    widths = [Cm(3.2), Cm(5.8), Cm(3.2), Cm(5.8)]
    for row_idx, row_vals in enumerate(rows):
        for col_idx, val in enumerate(row_vals):
            cell = table.cell(row_idx, col_idx)
            cell.width = widths[col_idx]
            p = cell.paragraphs[0]
            if col_idx in (0, 2):
                _bold_run(p, val, size=10)
            else:
                run = p.add_run(val)
                run.font.size = Pt(10)
    return table


def _add_images_row(doc, image_paths: list[str]):
    table = doc.add_table(rows=1, cols=len(image_paths) or 1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, path in enumerate(image_paths):
        cell = table.cell(0, idx)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(path, width=Cm(5.4))


def _add_bullets(doc, bullets: list[str], size=10):
    for b in bullets:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(b)
        run.font.size = Pt(size)


def _add_specs_table(doc, sections: dict[str, list[dict]]):
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    qty_width, desc_width = Cm(2.2), Cm(14.0)

    for section_name in SECTION_ORDER:
        header_row = table.add_row()
        header_row.cells[0].merge(header_row.cells[1])
        p = header_row.cells[0].paragraphs[0]
        _bold_run(p, section_name, size=11)
        for c in header_row.cells:
            _shade_cell(c, HEADER_SHADE)
            _set_cell_borders(c)

        items = sections.get(section_name, [])
        if not items:
            row = table.add_row()
            row.cells[0].width = qty_width
            row.cells[1].width = desc_width
            for c in row.cells:
                _set_cell_borders(c)
            continue

        for item in items:
            row = table.add_row()
            qty_cell, desc_cell = row.cells[0], row.cells[1]
            qty_cell.width = qty_width
            desc_cell.width = desc_width
            qty_cell.paragraphs[0].add_run(str(item.get("qty", ""))).font.size = Pt(10)
            desc_cell.paragraphs[0].add_run(str(item.get("description", ""))).font.size = Pt(10)
            for c in row.cells:
                _set_cell_borders(c)
    return table


def build_boq_docx(
    output_path: str,
    header_fields: dict,
    image_paths: list[str],
    sections: dict[str, list[dict]],
    show_start: date | None,
):
    doc = Document()

    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    _add_header_field_table(doc, header_fields)
    doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    area = header_fields.get("area", "")
    trade_show = header_fields.get("trade_show", "")
    venue = header_fields.get("venue", "")
    _bold_run(title, f"Total stand price EUR | {area} sqm | {trade_show} | {venue}", size=12)

    doc.add_paragraph()
    if image_paths:
        _add_images_row(doc, image_paths[:3])
    doc.add_paragraph()

    spec_heading = doc.add_paragraph()
    run = _bold_run(spec_heading, "Specifications", size=13)
    run.underline = True

    _add_specs_table(doc, sections)

    doc.add_paragraph()
    _add_bullets(doc, legal_text.schedule_bullets(show_start))

    doc.add_paragraph()
    _bold_run(doc.add_paragraph(), "Not included in the quotation:", size=11)
    doc.add_paragraph(legal_text.NOT_INCLUDED_INTRO)
    _add_bullets(doc, legal_text.NOT_INCLUDED_BULLETS)

    doc.add_paragraph()
    _bold_run(doc.add_paragraph(), "Payment Conditions:", size=11)
    _add_bullets(doc, legal_text.PAYMENT_CONDITIONS)

    doc.add_paragraph()
    _bold_run(doc.add_paragraph(), "Note:", size=11)
    _add_bullets(doc, legal_text.NOTES)

    doc.add_paragraph()
    _bold_run(doc.add_paragraph(), "Cancellation of orders", size=11)
    doc.add_paragraph(legal_text.CANCELLATION_TEXT)

    doc.add_paragraph()
    _bold_run(doc.add_paragraph(), "Resolve the dispute", size=11)
    doc.add_paragraph(legal_text.DISPUTE_TEXT)

    doc.add_paragraph()
    doc.add_paragraph("Client Confirmation with")
    doc.add_paragraph()
    doc.add_paragraph("Name of the authorized person: ______________________")
    doc.add_paragraph()
    doc.add_paragraph("Sign with company stamp: ______________________")
    doc.add_paragraph()
    doc.add_paragraph("Date: ______________________")

    doc.save(output_path)
    return output_path
