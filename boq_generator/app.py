"""BOQ Generator -- small local web app.

Upload a Fountainhead-style exhibition-stand specification PDF, review/edit
the extracted data, optionally pull in AI-drafted lines for the sections
that need visual judgement, then download the finished BOQ .docx.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import Flask, render_template, request, send_file, redirect, url_for, flash

from boq.extract import SpecExtractor
from boq.assemble import build_sections, default_header_fields, show_start_date
from boq.ai_narrative import suggest_additional_lines
from boq.docx_builder import build_boq_docx

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

SECTION_KEYS = [
    "1 Floor", "2 Stand", "3 Furniture", "4 Electrical | Lightning",
    "5 Miscellaneous", "6 Signing", "7 Installation | Dismantling | Transport",
    "8 AV/VIDEO",
]
AI_SECTIONS = ["1 Floor", "2 Stand", "6 Signing"]  # the sections AI is allowed to add to
SHORT_NAME = {"1 Floor": "Floor", "2 Stand": "Stand", "6 Signing": "Signing"}

DEFAULT_HERO_PAGES = [4, 5, 6]

app = Flask(__name__)
app.secret_key = os.environ.get("BOQ_APP_SECRET", "dev-secret-change-me")

# In-memory job store. Fine for a small single-user local tool; restart
# clears it (the uploaded PDF and any generated docx stay on disk under
# uploads//output, a fresh upload just needs to happen again).
JOBS: dict[str, dict] = {}


def _job_dir(job_id: str) -> Path:
    d = UPLOAD_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sections_to_text(sections: dict[str, list[dict]]) -> dict[str, str]:
    out = {}
    for key in SECTION_KEYS:
        lines = [f"{it['qty']} | {it['description']}" for it in sections.get(key, [])]
        out[key] = "\n".join(lines)
    return out


def _text_to_items(text: str) -> list[dict]:
    items = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            qty, desc = line.split("|", 1)
        else:
            qty, desc = "1,0", line
        qty = qty.strip()
        desc = desc.strip()
        if desc:
            items.append({"qty": qty, "description": desc})
    return items


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("spec_pdf")
    if not f or not f.filename:
        flash("Please choose a spec PDF to upload.")
        return redirect(url_for("index"))

    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_dir(job_id)
    pdf_path = job_dir / "spec.pdf"
    f.save(pdf_path)

    ex = SpecExtractor(str(pdf_path))
    extraction = ex.run(f.filename)

    reserved = {p for p in (extraction.specs_page, extraction.callouts_page, extraction.floorplan_page) if p}
    candidate_pages = [p for p in range(3, extraction.page_count) if p not in reserved]
    if not candidate_pages:
        candidate_pages = [p for p in range(1, extraction.page_count + 1) if p not in reserved]

    thumbs_dir = job_dir / "thumbs"
    thumbs_dir.mkdir(exist_ok=True)
    thumbs = {}
    for p in candidate_pages:
        out_path = thumbs_dir / f"page_{p}.png"
        ex.render_page_png(p, str(out_path), dpi=70)
        thumbs[p] = f"/uploads/{job_id}/thumbs/page_{p}.png"
    ex.close()

    sections = build_sections(extraction)
    header = default_header_fields(extraction)

    default_selection = [p for p in DEFAULT_HERO_PAGES if p in candidate_pages]
    while len(default_selection) < 3 and candidate_pages:
        for p in candidate_pages:
            if p not in default_selection:
                default_selection.append(p)
            if len(default_selection) == 3:
                break

    JOBS[job_id] = {
        "pdf_path": str(pdf_path),
        "original_filename": f.filename,
        "extraction": extraction,
        "candidate_pages": candidate_pages,
        "thumbs": thumbs,
        "sections_text": _sections_to_text(sections),
        "header": header,
        "selected_pages": default_selection,
        "ai_note": None,
    }

    return redirect(url_for("review", job_id=job_id))


@app.route("/uploads/<job_id>/thumbs/<fname>")
def serve_thumb(job_id, fname):
    path = UPLOAD_DIR / job_id / "thumbs" / fname
    if not path.exists():
        return "not found", 404
    return send_file(path)


@app.route("/review/<job_id>", methods=["GET"])
def review(job_id):
    job = JOBS.get(job_id)
    if not job:
        flash("That session has expired -- please upload the spec PDF again.")
        return redirect(url_for("index"))
    return render_template(
        "review.html",
        job_id=job_id,
        header=job["header"],
        sections_text=job["sections_text"],
        section_keys=SECTION_KEYS,
        candidate_pages=job["candidate_pages"],
        thumbs=job["thumbs"],
        selected_pages=job["selected_pages"],
        ai_note=job["ai_note"],
        original_filename=job["original_filename"],
    )


@app.route("/review/<job_id>/ai_suggest", methods=["POST"])
def ai_suggest(job_id):
    job = JOBS.get(job_id)
    if not job:
        flash("That session has expired -- please upload the spec PDF again.")
        return redirect(url_for("index"))

    _update_job_from_form(job, request.form)

    selected_pages = job["selected_pages"]
    ex = SpecExtractor(job["pdf_path"])
    image_paths = []
    tmp_dir = _job_dir(job_id) / "ai_images"
    tmp_dir.mkdir(exist_ok=True)
    pages_for_ai = list(dict.fromkeys(
        selected_pages
        + ([job["extraction"].callouts_page] if job["extraction"].callouts_page else [])
        + ([job["extraction"].floorplan_page] if job["extraction"].floorplan_page else [])
    ))
    for p in pages_for_ai:
        out_path = tmp_dir / f"ai_{p}.png"
        ex.render_page_png(p, str(out_path), dpi=110)
        image_paths.append(str(out_path))
    ex.close()

    current_sections = {
        SHORT_NAME[k]: _text_to_items(job["sections_text"][k]) for k in AI_SECTIONS
    }
    suggestions, err = suggest_additional_lines(job["extraction"], current_sections, image_paths)
    job["ai_note"] = err if err else "AI suggestions added below (marked [AI]) -- review before generating."

    for short, key in SHORT_NAME.items():
        for item in suggestions.get(short, []):
            marker = f"{item['qty']} | [AI] {item['description']}"
            job["sections_text"][key] = (job["sections_text"][key] + "\n" + marker).strip()

    return redirect(url_for("review", job_id=job_id))


@app.route("/review/<job_id>/generate", methods=["POST"])
def generate(job_id):
    job = JOBS.get(job_id)
    if not job:
        flash("That session has expired -- please upload the spec PDF again.")
        return redirect(url_for("index"))

    _update_job_from_form(job, request.form)

    sections = {}
    for key in SECTION_KEYS:
        text = job["sections_text"][key]
        text = text.replace("[AI] ", "")
        sections[key] = _text_to_items(text)
    if job["extraction"].specs_page is None:
        pass  # sections 3/4/5/8 already whatever the user typed

    from boq.legal_text import INSTALLATION_SECTION
    sections["7 Installation | Dismantling | Transport"] = [
        {"qty": qty, "description": desc} for qty, desc in INSTALLATION_SECTION
    ]

    selected_pages = job["selected_pages"][:3]
    ex = SpecExtractor(job["pdf_path"])
    hero_dir = _job_dir(job_id) / "hero"
    hero_dir.mkdir(exist_ok=True)
    hero_paths = []
    for p in selected_pages:
        out_path = hero_dir / f"hero_{p}.png"
        ex.render_page_png(p, str(out_path), dpi=150)
        hero_paths.append(str(out_path))
    ex.close()

    start = show_start_date(job["extraction"])
    out_name = f"BOQ_{job['header'].get('project') or 'stand'}.docx".replace(" ", "_")
    out_path = OUTPUT_DIR / f"{job_id}_{out_name}"
    build_boq_docx(str(out_path), job["header"], hero_paths, sections, start)

    return send_file(out_path, as_attachment=True, download_name=out_name)


def _update_job_from_form(job: dict, form) -> None:
    for field in ("client", "contact_person", "trade_show", "email", "show_dates",
                  "doc_date", "venue", "project", "area"):
        if field in form:
            job["header"][field] = form.get(field, "")

    for key in SECTION_KEYS:
        form_key = f"section__{key}"
        if form_key in form:
            job["sections_text"][key] = form.get(form_key, "")

    selected = form.getlist("hero_pages")
    if selected:
        job["selected_pages"] = [int(p) for p in selected][:3]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
