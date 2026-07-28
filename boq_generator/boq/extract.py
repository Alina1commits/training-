"""Deterministic extraction of structured data from a Fountainhead-style
exhibition-stand specification PDF.

Everything in here is pulled from real text/pixels in the PDF -- nothing is
invented. Narrative gaps (things a human designer wrote freeform, with no
literal source in the PDF) are intentionally left to boq.ai_narrative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

# These decks embed a custom "ti" ligature glyph that PyMuPDF decodes to the
# lookalike codepoint U+019F (poppler's pdftotext just drops it silently).
# Undoing that -- plus the standard fi/fl ligatures -- recovers real words
# ("RecepƟon" -> "Reception").
_LIGATURE_FIXES = {"Ɵ": "ti", "ﬁ": "fi", "ﬂ": "fl"}

# ---------------------------------------------------------------------------
# Known vocabulary. These lists are what let the extractor recognise a page's
# *role* (specs list / callout page / floor plan) regardless of its page
# number, and what let it recognise room types on a floor plan regardless of
# how the PDF's text layer chops up rotated/stacked labels.
# ---------------------------------------------------------------------------

SPEC_SECTION_ALIASES = {
    "miscellaneous": "Miscellaneous",
    "furniture": "Furniture",
    "electrical": "Electrical | Lightning",
    "electrical | lightning": "Electrical | Lightning",
    "av/video": "AV/VIDEO",
    "av/vide0": "AV/VIDEO",
}

ROOM_KEYWORDS = [
    ("MEETING ROOM 1", "Meeting room 1"),
    ("MEETING ROOM 2", "Meeting room 2"),
    ("MEETING ROOM", "Meeting room"),
    ("STORE ROOM", "Store room"),
    ("STORAGE ROOM", "Store room"),
    ("PANTRY", "Pantry"),
    ("KITCHEN", "Kitchen"),
    ("BAR AREA", "Bar area"),
    ("INFO COUNTER", "Info counter"),
    ("RECEPTION", "Reception counter"),
    ("LOUNGE 1", "Lounge 1"),
    ("LOUNGE 2", "Lounge 2"),
    ("LOUNGE AREA", "Lounge area"),
    ("DISCUSSION TABLE", "Discussion table"),
    ("VIP LOUNGE", "VIP lounge"),
]

# Unit suffix varies by deck: "MTR" (IFF/Milan), plain "M"/"m" (Ambadi/
# Heimtextil), occasionally "MT" or "Meter(s)" -- accept them all.
_UNIT = r"(?:MTRS?|MT|METERS?|M)\b"

DIM_PATTERNS = {
    "stand_size": re.compile(rf"STAND\s*SIZE\s*:?\s*([0-9.]+\s*X\s*[0-9.]+)\s*{_UNIT}", re.I),
    "stand_area": re.compile(r"STAND\s*AREA\s*:?\s*([0-9.]+)\s*S?QM", re.I),
    "wall_height": re.compile(rf"WALL\s*HEIGHT\s*:?\s*([0-9.]+)\s*{_UNIT}", re.I),
    "total_height": re.compile(rf"TOTAL\s*HEIGHT\s*:?\s*([0-9.]+)\s*{_UNIT}", re.I),
}

QTY_LINE_RE = re.compile(r"^\s*(\d+[.,]\d+)\s+(.+?)\s*$")
SECTION_HEADER_RE = re.compile(r"^\s*(\d+)?\s*([A-Za-z][A-Za-z0-9 /|]*)\s*$")

FOOTER_NOISE = (
    "PROPOSED EXHIBITION",
    "STAND DESIGN FOR",
    "ALL FURNITURE PICTURES",
    "ALL DESIGNS ARE THE PROPERTY",
)


@dataclass
class Dimensions:
    stand_size: str = ""
    stand_area: str = ""
    wall_height: str = ""
    total_height: str = ""


@dataclass
class SpecItem:
    qty: str
    description: str


@dataclass
class CoverMeta:
    project: str = ""
    company: str = ""
    trade_show: str = ""
    show_dates: str = ""
    venue: str = ""
    area: str = ""


@dataclass
class ExtractionResult:
    dims: Dimensions = field(default_factory=Dimensions)
    specs: dict = field(default_factory=dict)  # section name -> [SpecItem]
    callouts: list = field(default_factory=list)  # raw callout label strings
    rooms: dict = field(default_factory=dict)  # canonical room name -> bool
    cover: CoverMeta = field(default_factory=CoverMeta)
    page_count: int = 0
    specs_page: int | None = None
    callouts_page: int | None = None
    floorplan_page: int | None = None


def _fix_ligatures(text: str) -> str:
    for bad, good in _LIGATURE_FIXES.items():
        text = text.replace(bad, good)
    return text


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


_REPEAT_RE = re.compile(r"^(.+?)\1+$")


def _dedupe_repeated_tokens(text: str) -> str:
    """Floor-plan labels are exported with a bold/stroke effect that repeats
    each word 2-3x with no separating space ("LOUNGELOUNGELOUNGE", "111").
    Collapse each whitespace-separated token to its minimal repeating unit.
    """
    out = []
    for tok in text.split():
        m = _REPEAT_RE.match(tok)
        out.append(m.group(1) if m else tok)
    return " ".join(out)


class SpecExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)

    def close(self):
        self.doc.close()

    # -- page role detection -------------------------------------------------
    def _page_plain_text(self, page_no: int) -> str:
        return self.doc[page_no - 1].get_text()

    def _page_text_sorted(self, page_no: int) -> str:
        """Reading-order text for a page, with ligature glyphs repaired."""
        return _fix_ligatures(self.doc[page_no - 1].get_text("text", sort=True))

    def find_specs_page(self) -> int | None:
        for i in range(len(self.doc)):
            t = self._page_plain_text(i + 1)
            low = t.lower().replace("ﬁ", "fi").replace("ꞌ", "'")
            if "furniture" in low and ("miscellaneous" in low or "electrical" in low):
                return i + 1
        return None

    def find_callouts_page(self) -> int | None:
        for i in range(len(self.doc)):
            t = self._page_plain_text(i + 1)
            if "3D LIT LOGO".lower() in t.lower() or (
                "BACKLIT" in t.upper() and "TOP ELEVATION" not in t.upper()
                and "FRONT ELEVATION" not in t.upper() and "STAND SIZE" in t.upper()
            ):
                return i + 1
        return None

    def find_floorplan_page(self) -> int | None:
        for i in range(len(self.doc)):
            t = self._page_plain_text(i + 1).upper()
            if "TOP ELEVATION" in t:
                return i + 1
        return None

    def find_dims_page(self) -> int | None:
        for i in range(len(self.doc)):
            t = self._page_plain_text(i + 1).upper()
            if "STAND SIZE" in t and "TOTAL HEIGHT" in t:
                return i + 1
        return None

    # -- structured parsing ---------------------------------------------------
    def parse_dimensions(self) -> Dimensions:
        dims = Dimensions()
        page = self.find_dims_page()
        if page:
            text = self._page_text_sorted(page)
            for field_name, pattern in DIM_PATTERNS.items():
                m = pattern.search(text)
                if m:
                    setattr(dims, field_name, m.group(1).strip())

        # Some decks flatten this footer into a picture -- no page has it as
        # real text at all. Fall back to OCR-reading the info box directly.
        if not any([dims.stand_size, dims.stand_area, dims.wall_height, dims.total_height]):
            from boq.ocr_cover import ocr_dimensions_fallback  # local import: optional dependency
            ocr_dims = ocr_dimensions_fallback(self.pdf_path, page_no=min(2, len(self.doc)))
            for field_name, value in ocr_dims.items():
                setattr(dims, field_name, value)
        return dims

    def parse_specs_list(self) -> tuple[dict, int | None]:
        page = self.find_specs_page()
        if not page:
            return {}, None
        text = self._page_text_sorted(page)
        sections: dict[str, list[SpecItem]] = {}
        current = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            qty_m = QTY_LINE_RE.match(line)
            if qty_m:
                if current is None:
                    current = "Uncategorised"
                    sections.setdefault(current, [])
                qty, desc = qty_m.group(1), qty_m.group(2).strip()
                sections.setdefault(current, []).append(SpecItem(qty=qty, description=desc))
                continue
            header_m = SECTION_HEADER_RE.match(line)
            if header_m:
                label = header_m.group(2).strip().lower()
                canonical = SPEC_SECTION_ALIASES.get(label)
                if canonical:
                    current = canonical
                    sections.setdefault(current, [])
        return sections, page

    @staticmethod
    def _labels_from_text(text: str) -> list[str]:
        labels = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            # the page's own "Specifications" heading sometimes lands on the
            # same sorted line as a nearby label -- strip it, keep the rest
            line = re.sub(r"\bSpecificat(?:i)?ons?\b", "", line, flags=re.I).strip()
            if not line:
                continue
            if any(noise in line.upper() for noise in FOOTER_NOISE):
                continue
            if any(pattern.search(line) for pattern in DIM_PATTERNS.values()):
                continue
            letters = re.sub(r"[^A-Za-z]", "", line)
            if len(letters) < 2:
                continue
            if re.fullmatch(r"[0-9.\sxXmM:–-]+", line):
                continue
            # callout labels are short phrases, not the boilerplate sentences
            # that also live on these pages -- length is a reliable enough
            # filter regardless of whether the deck writes labels in ALL
            # CAPS (Milan/IFF) or Title Case (other clients).
            if len(line) > 45:
                continue
            labels.append(line)
        return labels

    def parse_callouts(self) -> tuple[list, int | None]:
        page = self.find_callouts_page()
        if page:
            return self._labels_from_text(self._page_text_sorted(page)), page

        # Some decks (e.g. a 3D render exported with label callouts drawn
        # directly onto the image) have no text layer at all for this page
        # -- find_callouts_page() can't see it via text search. OCR each
        # remaining page and keep whichever one both carries the
        # "Specifications" heading and yields a plausible batch of labels.
        from boq.ocr_cover import ocr_page_text  # local import: optional dependency
        reserved = {p for p in (self.find_specs_page(), self.find_floorplan_page()) if p}
        for i in range(len(self.doc)):
            page_no = i + 1
            if page_no in reserved or page_no == 1:
                continue
            text = ocr_page_text(self.pdf_path, page_no)
            if "specification" not in text.lower():
                continue
            labels = self._labels_from_text(text)
            if len(labels) >= 5:
                return labels, page_no
        return [], None

    def parse_rooms(self) -> tuple[dict, int | None]:
        page = self.find_floorplan_page()
        rooms = {canonical: False for _, canonical in ROOM_KEYWORDS}
        counts = {canonical: 0 for _, canonical in ROOM_KEYWORDS}
        if not page:
            return rooms, None
        deduped = _dedupe_repeated_tokens(self._page_text_sorted(page)).upper()
        for keyword, canonical in ROOM_KEYWORDS:
            n = deduped.count(keyword)
            if n:
                rooms[canonical] = True
                counts[canonical] = max(counts[canonical], n)
        rooms["_counts"] = counts
        return rooms, page

    def parse_cover_meta(self, original_filename: str) -> CoverMeta:
        meta = CoverMeta()
        page1 = self._page_text_sorted(1)
        m = re.search(r"AREA\s*:\s*([0-9.]+)\s*sqm", page1, re.I)
        if m:
            meta.area = m.group(1)

        name = Path(original_filename).stem
        name = re.sub(r"^SPECIFICATION[_\s]*", "", name, flags=re.I)
        parts = [p.strip() for p in re.split(r"[_]+", name) if p.strip()]

        project_part, show_part, date_part = "", "", ""
        for part in parts:
            if re.search(r"\d+\.?\d*\s*sqm", part, re.I):
                if not meta.area:
                    am = re.search(r"([0-9.]+)\s*sqm", part, re.I)
                    if am:
                        meta.area = am.group(1)
                continue
            if re.search(r"\b(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)\b", part, re.I) or re.search(r"\d{1,2}\s*[-–]\s*\d{1,2}", part):
                date_part = part
                continue
            if not project_part:
                project_part = part
            elif not show_part:
                show_part = part

        if project_part:
            meta.company = project_part
            meta.project = project_part.split()[0]
        if show_part:
            year_m = re.search(r"(19|20)\d{2}", show_part)
            city_m = re.sub(r"(19|20)\d{2}", "", show_part).strip()
            words = city_m.split()
            show_name = words[0] if words else show_part
            city = " ".join(words[1:]) if len(words) > 1 else ""
            year = year_m.group(0) if year_m else ""
            meta.trade_show = f"{show_name} {year}".strip()
            if city:
                country = CITY_COUNTRY.get(city.upper())
                meta.venue = f"{city}, {country}" if country else city
        if date_part:
            date_part = re.sub(r"^Oct\.?", "October", date_part, flags=re.I)
            month_m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)", date_part, re.I)
            days_m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", date_part)
            if month_m and days_m:
                meta.show_dates = f"{days_m.group(1)}-{days_m.group(2)} {month_m.group(1).title()} {year_m.group(0) if show_part and year_m else ''}".strip()

        # OCR on the cover page's logo/banner images is more reliable than
        # guessing from the file name (it works no matter how the PDF was
        # renamed) -- use it to fill in or correct whatever it can read.
        from boq.ocr_cover import extract_cover_via_ocr  # local import: optional dependency
        ocr = extract_cover_via_ocr(self.pdf_path)
        if ocr.company:
            meta.company = ocr.company
            meta.project = ocr.company
        if ocr.trade_show:
            meta.trade_show = ocr.trade_show
        if ocr.show_dates:
            meta.show_dates = ocr.show_dates
        if ocr.venue:
            meta.venue = ocr.venue

        return meta

    def render_page_png(self, page_no: int, out_path: str, dpi: int = 150) -> str:
        page = self.doc[page_no - 1]
        pix = page.get_pixmap(dpi=dpi)
        pix.save(out_path)
        return out_path

    def run(self, original_filename: str) -> ExtractionResult:
        result = ExtractionResult()
        result.page_count = len(self.doc)
        result.dims = self.parse_dimensions()
        result.specs, result.specs_page = self.parse_specs_list()
        result.callouts, result.callouts_page = self.parse_callouts()
        result.rooms, result.floorplan_page = self.parse_rooms()
        result.cover = self.parse_cover_meta(original_filename)
        if not result.cover.area:
            result.cover.area = result.dims.stand_area
        return result


CITY_COUNTRY = {
    "MILAN": "Italy", "BOLOGNA": "Italy", "ROME": "Italy",
    "PARIS": "France", "LYON": "France",
    "FRANKFURT": "Germany", "DUESSELDORF": "Germany", "DUSSELDORF": "Germany",
    "COLOGNE": "Germany", "MUNICH": "Germany", "HANNOVER": "Germany", "BERLIN": "Germany",
    "BARCELONA": "Spain", "MADRID": "Spain",
    "BASEL": "Switzerland", "ZURICH": "Switzerland", "GENEVA": "Switzerland",
    "AMSTERDAM": "Netherlands", "UTRECHT": "Netherlands",
    "LONDON": "UK", "BIRMINGHAM": "UK",
    "DUBAI": "UAE", "ABU DHABI": "UAE",
    "LAS VEGAS": "USA", "CHICAGO": "USA", "ORLANDO": "USA", "NEW YORK": "USA",
    "MUMBAI": "India", "NEW DELHI": "India", "BENGALURU": "India",
    "SINGAPORE": "Singapore", "SHANGHAI": "China", "GUANGZHOU": "China",
}
