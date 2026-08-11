"""Deterministic, generalisable mapping from things we can actually detect in
the PDF (callout labels on the exploded-view page, room names on the floor
plan, footer dimensions) to BOQ line items.

Design rule: only phrasing that is safe for *any* future stand of this kind
lives here (e.g. "Lockable bar counter -- as per design"). Anything that is
specific to *this* stand's layout (which wall, which room a graphic backs
onto, how many distinct logos there really are) is deliberately left out --
that's exactly the gap boq.ai_narrative fills by actually looking at the
images for the current project.
"""
from __future__ import annotations

from boq.extract import ExtractionResult

# callout label (as it appears, upper-case, whitespace already collapsed to
# single spaces) -> list of (section, phrase). A callout can feed more than
# one section (e.g. the hanging structure is both a Stand build item and a
# Signing item).
CALLOUT_RULES: dict[str, list[tuple[str, str]]] = {
    "WOODEN HANGING WITH 3D LIT LOGO": [
        ("Signing", "Company logo on hanging fascia will be 3D lit -- as per dimensions"),
    ],
    "48 MM PLATFORM WITH DUAL LAMINATE & LIT": [
        ("Floor", "48mm raised platform with dual laminate with LED strip -- as per design"),
    ],
    "LEDHOLO SCREEN WALL": [
        ("AV/VIDEO", "LEDholo screen wall -- as per design"),
    ],
    "WOODEN IPAD STAND": [
        ("Stand", "Wooden iPad stand -- as per design"),
    ],
    "LOCKABLE INFO COUNTER WITH LIT 3D LOGO": [
        ("Stand", "Lockable reception/info counter with space for plants -- as per design"),
        ("Signing", "Logo on reception/info counter will be 3D lit -- as per dimensions"),
    ],
    "LOCKABLE BAR COUNTER": [
        ("Stand", "Lockable bar counter -- as per design"),
    ],
    "FROSTED ACRYLIC": [
        ("Stand", "Frosted acrylic wall -- as per design"),
    ],
    "BACKLIT GRAPHICS": [
        ("Signing", "Backlit graphics -- as per dimensions"),
    ],
    "BACKLIT": [
        ("Signing", "Graphic will be backlit -- as per dimensions"),
    ],
    "DIGITAL GRAPHIC WITH 3D LIT LETTERS": [
        ("Signing", "Graphic will be digital vinyl print with 3D lit letters -- as per dimensions"),
    ],
    "DIGITAL GRAPHIC": [
        ("Signing", "Graphic will be digital vinyl print -- as per dimensions"),
    ],
    "3D LIT LOGO": [
        ("Signing", "Company logo will be 3D lit -- as per dimensions"),
    ],

    # --- Vocabulary mined from other clients' spec decks (Ambadi Home and
    # ~20 past Fountainhead project BOQs) -- generic reusable elements only,
    # per the module design rule above. Mostly exists to lock in correct
    # casing for acronyms/units (LED, MS, 3D) and to fix common OCR typos,
    # since the generic fallback already gets plain labels right on its own.
    "MS FRAME": [("Stand", "MS frame -- as per design")],
    "LED LIGHT": [("Stand", "LED light -- as per design")],
    "LED LIGHT WITH ALL SHLEF": [("Stand", "LED light with shelf -- as per design")],
    "3D LETTER": [("Signing", "3D letter -- as per dimensions")],
    "3D LIT INDIA MAP": [("Stand", "3D lit India map -- as per design")],
    "VINYL CUT LOGO": [("Signing", "Vinyl cut logo -- as per dimensions")],
    "VINYL CUT LETTER": [("Signing", "Vinyl cut letter -- as per dimensions")],
    "LOGO VINYL CUT": [("Signing", "Logo vinyl cut -- as per dimensions")],
    "CLINT PRODUCT RUG": [("Stand", "Client product rug -- as per design")],
    "CLIENT PRODUCT RUG": [("Stand", "Client product rug -- as per design")],
    "ALL CERIFICAT WALL": [("Stand", "Certificate wall -- as per design")],
    "ALL CERTIFICATE WALL": [("Stand", "Certificate wall -- as per design")],
    "WOODEN FLOORING": [("Stand", "Wooden flooring -- as per design")],
    "WALLPAPER": [("Stand", "Wallpaper -- as per design")],
    "PLANT POT": [("Stand", "Plant pot -- as per design")],
    "WOODEN LOUVER": [("Stand", "Wooden louver -- as per design")],
    "SKIRTING LIGHT": [("Stand", "Skirting light -- as per design")],
    "RAMP": [("Stand", "Ramp -- as per design")],
    "TRUSS": [("Stand", "Truss -- as per design")],
    "FASCIA STRUCTURE": [("Stand", "Fascia structure -- as per design")],
    "HANGING FASCIA": [("Stand", "Hanging fascia -- as per design")],
    "SHELVES": [("Stand", "Shelves -- as per design")],
    "WOODEN SHELVES DISPLAY STRUCTURE": [
        ("Stand", "Wooden shelves display structure -- as per design"),
    ],
    "DISPLAY STRUCTURE": [("Stand", "Display structure -- as per design")],
    "WOODEN PODIUM": [("Stand", "Wooden podium -- as per design")],
    "INFO BOARD": [("Stand", "Info board -- as per design")],
    "OPEN SITTING AREA": [("Stand", "Open sitting area -- as per design")],
    "OPEN DISCUSSION AREA": [("Stand", "Open discussion area -- as per design")],
    "SOFA SITTING AREA": [("Stand", "Sofa sitting area -- as per design")],
    "BAR SEATING AREA": [("Stand", "Bar seating area -- as per design")],
    "SEMI CLOSED MEETING AREA": [("Stand", "Semi closed meeting area -- as per design")],
    "LOCKABLE RECEPTION DESK": [("Stand", "Lockable reception desk -- as per design")],
    "LOCKABLE RECEPTION COUNTER": [("Stand", "Lockable reception counter -- as per design")],
    "RUNNER PLANTER BOX": [("Stand", "Runner planter box -- as per design")],
    "L-SHAPED PLANTER BOX": [("Stand", "L-shaped planter box -- as per design")],
    "PLANTER BOX": [("Stand", "Planter box -- as per design")],
    "PLANTER WALL": [("Stand", "Planter wall -- as per design")],
}

# canonical room name (from extract.ROOM_KEYWORDS) -> (section, phrase, qty)
# qty is fixed per room instance detected (1 per True flag), except where a
# pair of rooms collapses into one combined line (meeting rooms, lounges).
ROOM_LINE_RULES: dict[str, tuple[str, str]] = {
    "Store room": ("Stand", "Lockable store room with shelves -- as per design"),
    "Kitchen": ("Stand", "Lockable Pantry room -- as per design"),
    "Bar area": ("Stand", "Bar area with concealed lights and hanging light at ceiling -- as per design"),
    "Lounge area": ("Stand", "Open sitting area -- as per design"),
}


# Words that reliably signal a graphic/branding treatment (Signing section)
# rather than a structural/build element (Stand section). Deliberately a
# short, high-precision list -- when in doubt, Stand is the safer default.
_SIGNING_KEYWORDS = ("vinyl", "logo", "letter", "graphic", "backlit", "print")

# Screen/video hardware belongs in AV/VIDEO only -- it must never also show
# up as a Stand build item or a Signing line, since that duplicates the same
# physical screen under two section headings and confuses client/vendor.
# Deliberately excludes bare "led" (e.g. "LED LIGHT" is a lighting fixture,
# not a screen) -- only fires when the label actually names a video device.
_AV_KEYWORDS = ("screen", "tv", "video", "monitor", "projector")


def _normalize_label(label: str) -> str:
    label = label.strip()
    return label[0].upper() + label[1:] if label else label


def _generic_fallback_line(label: str) -> tuple[str, str]:
    """For a callout label with no entry in CALLOUT_RULES -- i.e. any client
    whose design vocabulary doesn't match Milan's -- still produce a
    reasonable line instead of silently dropping it.
    """
    lowered = label.lower()
    if any(kw in lowered for kw in _AV_KEYWORDS):
        return "AV/VIDEO", f"{_normalize_label(label)} -- as per design"
    is_signing = any(kw in lowered for kw in _SIGNING_KEYWORDS)
    section = "Signing" if is_signing else "Stand"
    suffix = "as per dimensions" if is_signing else "as per design"
    return section, f"{_normalize_label(label)} -- {suffix}"


def _meeting_room_qty(rooms: dict) -> int:
    n = 0
    if rooms.get("Meeting room 1"):
        n += 1
    if rooms.get("Meeting room 2"):
        n += 1
    if n == 0 and rooms.get("Meeting room"):
        n = 1
    return n


def build_deterministic_lines(extraction: ExtractionResult) -> dict[str, list[dict]]:
    """Returns {section: [{"qty": str, "description": str, "source": str}]}"""
    sections: dict[str, list[dict]] = {
        "Floor": [], "Stand": [], "Signing": [], "AV/VIDEO": [],
    }

    def add(section: str, qty: str, description: str, source: str):
        sections.setdefault(section, []).append(
            {"qty": qty, "description": description, "source": source}
        )

    dims = extraction.dims
    area = extraction.cover.area or dims.stand_area

    # --- Floor -------------------------------------------------------------
    if area:
        floor_phrase = "raised platform -- as per design"
        for label, rules in CALLOUT_RULES.items():
            if label in extraction.callouts and any(sec == "Floor" for sec, _ in rules):
                floor_phrase = next(p for sec, p in rules if sec == "Floor")
                break
        add("Floor", f"{area}m2", floor_phrase, "dims+callout")

    # --- Stand: heights ------------------------------------------------------
    if dims.total_height:
        hanging = "WOODEN HANGING WITH 3D LIT LOGO" in extraction.callouts
        suffix = " including hanging fascia with truss and hanging creepers -- as per design" if hanging else " -- as per design"
        add("Stand", "1,0",
            f"Total height of {dims.total_height} m (height depends on height approval){suffix}",
            "dims")
    if dims.wall_height:
        add("Stand", "1,0",
            f"Wall height of {dims.wall_height} m (height depends on height approval) -- as per design",
            "dims")

    # --- Stand & Signing: callout-derived ------------------------------------
    rules_by_upper = {k.upper(): v for k, v in CALLOUT_RULES.items()}
    seen_signing_logo_count = sum(1 for l in extraction.callouts if l.upper() == "3D LIT LOGO")
    handled_3d_logo = False
    for label in extraction.callouts:
        rules = rules_by_upper.get(label.upper())
        if rules:
            for section, phrase in rules:
                if label.upper() == "3D LIT LOGO":
                    if handled_3d_logo:
                        continue
                    handled_3d_logo = True
                    add(section, f"{seen_signing_logo_count},0", phrase, "callout")
                    continue
                if section == "Floor":
                    continue  # handled above
                add(section, "1,0", phrase, "callout")
        else:
            section, phrase = _generic_fallback_line(label)
            add(section, "1,0", phrase, "callout-generic")

    # --- Stand: room-derived ---------------------------------------------
    meeting_qty = _meeting_room_qty(extraction.rooms)
    if meeting_qty:
        add("Stand", f"{meeting_qty},0",
            "Lockable meeting room with frosted glass door and concealed lights "
            "at ceiling and lockable cabinet -- as per design", "floorplan")

    for room, (section, phrase) in ROOM_LINE_RULES.items():
        if extraction.rooms.get(room):
            add(section, "1,0", phrase, "floorplan")

    for section in sections:
        sections[section] = _merge_duplicates(sections[section])
    return sections


def _merge_duplicates(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        key = item["description"]
        if key not in merged:
            merged[key] = dict(item)
            order.append(key)
            continue
        try:
            existing_qty = float(merged[key]["qty"].replace(",", "."))
            new_qty = float(item["qty"].replace(",", "."))
            merged[key]["qty"] = f"{int(existing_qty + new_qty)},0"
        except ValueError:
            pass
    return [merged[k] for k in order]
