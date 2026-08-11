"""Assemble the final BOQ .docx, styled after BOQ_expected.docx:
header field table, three hero images, a numbered specifications table,
then Fountainhead's fixed legal boilerplate and a signature block.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

from boq import legal_text

SECTION_ORDER = [
    "1 Floor", "2 Stand", "3 Furniture", "4 Electrical | Lightning",
    "5 Miscellaneous", "6 Signing", "7 Installation | Dismantling | Transport",
    "8 AV/VIDEO",
]

ACCENT_BLUE = "0070C0"  # matches BOQ_expected.docx's title/heading color exactly
LETTERHEAD_BG = Path(__file__).resolve().parent / "assets" / "letterhead_bg.png"


def _bold_run(paragraph, text, size=11, color=None):
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def _add_letterhead(doc, image_path: Path, header_lines: list[str]):
    """Fountainhead's two-part letterhead, repeated on every page: the
    company info block (name/address/registration/contact) as ordinary
    header text at the top, and the triangle graphic as a floating picture
    anchored to the bottom of the page, positioned behind the text so it
    never displaces content.
    """
    section = doc.sections[0]
    header = section.header
    header.is_linked_to_previous = False

    for idx, line in enumerate(header_lines):
        p = header.paragraphs[0] if idx == 0 else header.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        run.font.color.rgb = RGBColor.from_string("595959")
        if idx == 0:
            run.font.size = Pt(9)
            run.bold = True
        else:
            run.font.size = Pt(8)

    if not image_path.exists():
        return
    paragraph = header.add_paragraph() if header_lines else (
        header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    )
    run = paragraph.add_run()
    run.add_picture(str(image_path), width=section.page_width)

    drawing = run._element.find(qn("w:drawing"))
    inline = drawing.find(qn("wp:inline"))
    extent = inline.find(qn("wp:extent"))
    docPr = inline.find(qn("wp:docPr"))
    graphic = inline.find(qn("a:graphic"))
    cy = int(extent.get("cy"))

    anchor = OxmlElement("wp:anchor")
    for attr, val in {
        "distT": "0", "distB": "0", "distL": "0", "distR": "0",
        "simplePos": "0", "relativeHeight": "1", "behindDoc": "1",
        "locked": "0", "layoutInCell": "1", "allowOverlap": "1",
    }.items():
        anchor.set(attr, val)

    simple_pos = OxmlElement("wp:simplePos")
    simple_pos.set("x", "0")
    simple_pos.set("y", "0")

    position_h = OxmlElement("wp:positionH")
    position_h.set("relativeFrom", "page")
    offset_h = OxmlElement("wp:posOffset")
    offset_h.text = "0"
    position_h.append(offset_h)

    position_v = OxmlElement("wp:positionV")
    position_v.set("relativeFrom", "page")
    offset_v = OxmlElement("wp:posOffset")
    offset_v.text = str(int(section.page_height) - cy)
    position_v.append(offset_v)

    wrap_none = OxmlElement("wp:wrapNone")

    anchor.append(simple_pos)
    anchor.append(position_h)
    anchor.append(position_v)
    anchor.append(extent)
    anchor.append(wrap_none)
    anchor.append(docPr)
    anchor.append(graphic)

    drawing.replace(inline, anchor)


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


TAB_STOP = Cm(2.2)


def _add_specifications(doc, sections: dict[str, list[dict]]):
    """Plain paragraphs, not a table -- matches BOQ_expected.docx exactly:
    a bold section-name line, then one paragraph per item with the quantity
    and description separated by a tab, using a hanging indent so wrapped
    lines fall under the description rather than back at the margin.
    """
    for section_name in SECTION_ORDER:
        heading = doc.add_paragraph()
        _bold_run(heading, section_name, size=11)

        items = sections.get(section_name, [])
        for item in items:
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = TAB_STOP
            pf.first_line_indent = -TAB_STOP
            pf.tab_stops.add_tab_stop(TAB_STOP)
            run = p.add_run(f"{item.get('qty', '')}\t{item.get('description', '')}")
            run.font.size = Pt(10)

        doc.add_paragraph()


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

    _add_letterhead(doc, LETTERHEAD_BG, legal_text.COMPANY_HEADER_LINES)

    _add_header_field_table(doc, header_fields)
    doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    area = header_fields.get("area", "")
    trade_show = header_fields.get("trade_show", "")
    venue = header_fields.get("venue", "")
    _bold_run(title, f"Total stand price EUR | {area} sqm | {trade_show} | {venue}", size=12, color=ACCENT_BLUE)

    doc.add_paragraph()
    if image_paths:
        _add_images_row(doc, image_paths[:3])
    doc.add_paragraph()

    spec_heading = doc.add_paragraph()
    run = _bold_run(spec_heading, "Specifications", size=13, color=ACCENT_BLUE)
    run.underline = True

    _add_specifications(doc, sections)

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
