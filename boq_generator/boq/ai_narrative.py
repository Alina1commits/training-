"""AI-assisted drafting of the BOQ lines that have no literal source text in
the spec PDF -- things a designer wrote freehand ("Walls will have roll
paint finish", "Semi-open lounge area with wooden partition..."). We show
the model the actual render images plus everything the deterministic
extractor already found, and ask it only to ADD lines that are visually
grounded and not already covered.

Requires OPENAI_API_KEY in the environment. If it's missing, or the call
fails for any reason, callers get an empty suggestion list plus an error
string -- the rest of the BOQ (which is fully deterministic) still works.
"""
from __future__ import annotations

import base64
import json
import os
import re

DEFAULT_MODEL = os.environ.get("BOQ_AI_MODEL", "gpt-5-nano")

SYSTEM_PROMPT = """You are assisting a exhibition-stand contractor (Fountainhead) in \
drafting a Bill of Quantities (BOQ) for a trade-show stand, from a client-facing \
specification/render deck.

You will be shown:
1. Photorealistic render images of the stand (several angles).
2. A floor-plan image with room labels.
3. Facts already extracted by deterministic parsing (dimensions, room names, \
callout labels, and the BOQ lines already generated from them).

Your job is ONLY to propose ADDITIONAL line items for three sections -- \
"Floor", "Stand" and "Signing" -- that are clearly visible in the images and \
are NOT already covered by the lines you're shown. Do not repeat or rephrase \
lines that already exist. Do not invent elements you cannot actually see.

Style rules (match this exactly, these are Fountainhead's house style):
- Each line is a short imperative phrase, no subject pronoun, e.g. \
"Walls will have roll paint finish -- as per design" or "Wooden meeting \
table -- as per design".
- "Stand" lines end with "-- as per design" (structural/build items).
- "Signing" lines describe a graphic/branding treatment and end with \
"-- as per dimensions" (e.g. "Graphic on X will be Y -- as per dimensions").
- Quantities are written as "N,0" (comma decimal), e.g. "2,0".
- Keep descriptions concise (one sentence, no trailing period inside the \
"as per..." qualifier).

Respond with STRICT JSON only, no prose, no markdown fences, in this shape:
{"Floor": [{"qty": "1,0", "description": "..."}],
 "Stand": [{"qty": "1,0", "description": "..."}],
 "Signing": [{"qty": "1,0", "description": "..."}]}
Omit a section entirely (or leave its list empty) if you have nothing to add.
If you are not confident an element is really there, leave it out -- fewer, \
correct lines are better than more, speculative ones.
"""


def _b64_image_data_url(path: str) -> str:
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _hints_text(extraction, deterministic_lines: dict) -> str:
    lines = []
    lines.append(f"Dimensions: stand size {extraction.dims.stand_size} mtr, "
                  f"area {extraction.dims.stand_area} sqm, wall height "
                  f"{extraction.dims.wall_height} m, total height {extraction.dims.total_height} m.")
    rooms_present = [r for r, v in extraction.rooms.items() if v and not r.startswith("_")]
    lines.append("Rooms/areas detected on floor plan: " + (", ".join(rooms_present) or "none detected"))
    lines.append("Callout labels detected on the exploded-view page: " + (", ".join(extraction.callouts) or "none detected"))
    lines.append("")
    lines.append("BOQ lines already generated (do not repeat these):")
    for section in ("Floor", "Stand", "Signing"):
        for item in deterministic_lines.get(section, []):
            lines.append(f"  [{section}] {item['qty']} {item['description']}")
    return "\n".join(lines)


def suggest_additional_lines(extraction, deterministic_lines: dict, image_paths: list[str]) -> tuple[dict, str | None]:
    """Returns (suggestions_dict, error). suggestions_dict is {} on failure."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {}, "OPENAI_API_KEY is not set -- skipping AI-assisted suggestions."

    try:
        import openai
    except ImportError:
        return {}, "the 'openai' package is not installed -- skipping AI-assisted suggestions."

    content = [{"type": "text", "text": _hints_text(extraction, deterministic_lines)}]
    for p in image_paths:
        try:
            content.append({"type": "image_url", "image_url": {"url": _b64_image_data_url(p)}})
        except OSError:
            continue

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            max_completion_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
        text = resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001 -- surface any failure as a soft error
        return {}, f"AI suggestion call failed: {exc}"

    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}, "AI response was not valid JSON -- skipping AI-assisted suggestions."

    out = {}
    for section in ("Floor", "Stand", "Signing"):
        items = data.get(section) or []
        cleaned = []
        for it in items:
            qty = str(it.get("qty", "1,0")).strip()
            desc = str(it.get("description", "")).strip()
            if desc:
                cleaned.append({"qty": qty, "description": desc, "source": "ai"})
        if cleaned:
            out[section] = cleaned
    return out, None
