"""Read the cover page's logo/banner images directly, via OCR, instead of
guessing the trade show / venue / company name from the PDF's file name.

The cover page of these decks has no text layer for this at all -- "IFF" and
"CPHI Milan | 8-10 October 2024 | Milan, Italy" are baked into two logo
graphics (top-left: exhibitor logo, top-right: trade-show banner). That's
readable by OCR even though it isn't extractable as text.

Optional: needs the Tesseract-OCR *program* installed on the machine (not
just the `pytesseract` Python package) -- see README. Falls back cleanly
(returns an empty result) if either isn't available, so callers should treat
this as a best-effort enhancement layered on top of filename parsing, not a
required step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    _OCR_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover -- exercised when deps missing
    pytesseract = None
    Image = None
    _OCR_IMPORT_ERROR = exc

from boq.extract import CITY_COUNTRY, DIM_PATTERNS

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
_MONTH_RE = "|".join(MONTHS)


@dataclass
class OcrCoverResult:
    company: str = ""
    trade_show: str = ""
    show_dates: str = ""
    venue: str = ""
    error: str | None = None


def ocr_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 -- pytesseract raises various errors when the binary is missing
        return False


def extract_cover_via_ocr(pdf_path: str, page_no: int = 1, dpi: int = 250) -> OcrCoverResult:
    if pytesseract is None:
        return OcrCoverResult(error=f"pytesseract not installed ({_OCR_IMPORT_ERROR})")
    if not ocr_available():
        return OcrCoverResult(error="Tesseract-OCR program not found on this machine")

    try:
        doc = fitz.open(pdf_path)
        pix = doc[page_no - 1].get_pixmap(dpi=dpi)
        doc.close()
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception as exc:  # noqa: BLE001
        return OcrCoverResult(error=f"could not render cover page: {exc}")

    w, h = img.size
    top_strip = img.crop((0, 0, w, int(h * 0.35)))
    left = top_strip.crop((0, 0, w // 2, top_strip.height))
    right = top_strip.crop((w // 2, 0, w, top_strip.height))

    result = OcrCoverResult()

    try:
        left_text = pytesseract.image_to_string(left.convert("L"), config="--psm 11")
    except Exception:  # noqa: BLE001
        left_text = ""
    company = _first_word_like_logo(left_text)
    if company:
        result.company = company

    try:
        right_text = pytesseract.image_to_string(right)
    except Exception:  # noqa: BLE001
        right_text = ""
    trade_show, city, dates = _parse_banner_text(right_text)
    if trade_show:
        year_m = re.search(r"(19|20)\d{2}", right_text)
        result.trade_show = f"{trade_show} {year_m.group(0)}".strip() if year_m else trade_show
    if dates:
        result.show_dates = dates
    if city:
        country = CITY_COUNTRY.get(city.upper())
        result.venue = f"{city}, {country}" if country else city

    return result


def _first_word_like_logo(text: str) -> str:
    for raw_line in text.splitlines():
        letters_only = re.sub(r"[^A-Za-z]", "", raw_line)
        if 2 <= len(letters_only) <= 12 and letters_only.isalpha():
            # skip generic tagline words that sometimes leak into this crop
            if letters_only.lower() in ("where", "science", "creativity", "meet", "the"):
                continue
            return letters_only.upper()
    return ""


def _parse_banner_text(text: str) -> tuple[str, str, str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    trade_show = ""
    for line in lines:
        letters_only = re.sub(r"[^A-Za-z]", "", line)
        # trade-show branding is written ALL CAPS (CPHI) just as often as
        # lowercase (heimtextil) -- don't require a specific casing style,
        # just something short and clearly a single word/name.
        if 3 <= len(letters_only) <= 15 and letters_only.isalpha():
            trade_show = letters_only.upper() if letters_only.isupper() else letters_only.capitalize()
            break

    date_m = re.search(rf"(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+({_MONTH_RE})\s+((?:19|20)\d{{2}})", text)
    dates = f"{date_m.group(1)}-{date_m.group(2)} {date_m.group(3)} {date_m.group(4)}" if date_m else ""

    city = ""
    city_m = re.search(r"([A-Z][a-zA-Z]+),\s*[A-Za-z]+\s*$", text.strip())
    if city_m:
        city = city_m.group(1)
    else:
        for line in lines:
            letters_only = re.sub(r"[^A-Za-z]", "", line)
            if letters_only and letters_only[0].isupper() and letters_only[1:].islower() and letters_only != trade_show:
                city = letters_only
                break

    return trade_show, city, dates


def ocr_dimensions_fallback(pdf_path: str, page_no: int = 2, dpi: int = 200) -> dict:
    """Some decks bake the STAND SIZE/AREA/WALL HEIGHT/TOTAL HEIGHT footer
    into a flattened image rather than real text (no page in the PDF has it
    as extractable text at all). Crop the footer's info box -- bottom-right
    corner, consistent across these decks -- from any content page and OCR
    it directly. Returns {} if OCR isn't available or nothing is found.
    """
    if not ocr_available():
        return {}
    try:
        doc = fitz.open(pdf_path)
        page_no = max(1, min(page_no, len(doc)))
        pix = doc[page_no - 1].get_pixmap(dpi=dpi)
        doc.close()
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:  # noqa: BLE001
        return {}

    w, h = img.size
    crop = img.crop((int(w * 0.72), int(h * 0.83), w, int(h * 0.99)))
    try:
        text = pytesseract.image_to_string(crop)
    except Exception:  # noqa: BLE001
        return {}

    result = {}
    for field_name, pattern in DIM_PATTERNS.items():
        m = pattern.search(text)
        if m:
            result[field_name] = m.group(1).strip()
    return result
