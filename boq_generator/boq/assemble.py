"""Glue: turn an ExtractionResult (+ optional AI suggestions) into the
{section_name: [{"qty","description"}]} shape docx_builder expects, keyed
exactly like docx_builder.SECTION_ORDER.
"""
from __future__ import annotations

from datetime import date, datetime

from boq import legal_text
from boq.callout_map import build_deterministic_lines
from boq.extract import ExtractionResult

SPEC_SECTION_KEYS = {
    "Furniture": "3 Furniture",
    "Electrical | Lightning": "4 Electrical | Lightning",
    "Miscellaneous": "5 Miscellaneous",
    "AV/VIDEO": "8 AV/VIDEO",
}


def _parse_show_start(show_dates: str) -> date | None:
    if not show_dates:
        return None
    # "8-10 October 2024" -> use the first day
    import re
    m = re.match(r"(\d{1,2})-\d{1,2}\s+([A-Za-z]+)\s+(\d{4})", show_dates)
    if not m:
        return None
    day, month_name, year = m.groups()
    try:
        return datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def build_sections(extraction: ExtractionResult, ai_suggestions: dict | None = None) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {k: [] for k in [
        "1 Floor", "2 Stand", "3 Furniture", "4 Electrical | Lightning",
        "5 Miscellaneous", "6 Signing", "7 Installation | Dismantling | Transport",
        "8 AV/VIDEO",
    ]}

    deterministic = build_deterministic_lines(extraction)
    ai_suggestions = ai_suggestions or {}

    key_by_short = {
        "Floor": "1 Floor", "Stand": "2 Stand", "Signing": "6 Signing",
        "AV/VIDEO": "8 AV/VIDEO",
    }
    for short, key in key_by_short.items():
        for item in deterministic.get(short, []):
            sections[key].append({"qty": item["qty"], "description": item["description"]})
        for item in ai_suggestions.get(short, []):
            sections[key].append({"qty": item["qty"], "description": item["description"]})

    for canonical, items in extraction.specs.items():
        key = SPEC_SECTION_KEYS.get(canonical)
        if not key:
            continue
        for it in items:
            sections[key].append({"qty": it.qty, "description": it.description})

    sections["7 Installation | Dismantling | Transport"] = [
        {"qty": qty, "description": desc} for qty, desc in legal_text.INSTALLATION_SECTION
    ]

    return sections


def default_header_fields(extraction: ExtractionResult) -> dict:
    return {
        "client": extraction.cover.company or extraction.cover.project,
        "contact_person": "",
        "trade_show": extraction.cover.trade_show,
        "email": "",
        "show_dates": extraction.cover.show_dates,
        "doc_date": date.today().strftime("%d.%m.%Y"),
        "venue": extraction.cover.venue,
        "project": extraction.cover.project,
        "area": extraction.cover.area or extraction.dims.stand_area,
    }


def show_start_date(extraction: ExtractionResult) -> date | None:
    return _parse_show_start(extraction.cover.show_dates)
