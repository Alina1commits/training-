# BOQ Generator

Turns a Fountainhead-style exhibition-stand specification PDF (render images +
a simple specs list + a labelled exploded-view page + a floor plan) into a
formatted Bill of Quantities `.docx`, styled after `BOQ_expected.docx`.

## How it works

The PDF is not one big blob of prose -- most of what ends up in the BOQ is
real, extractable text, it's just scattered across the deck as separate
PowerPoint text boxes. The pipeline:

1. **`boq/extract.py`** -- finds, by content (not fixed page numbers), the
   specs-list page, the labelled exploded-view ("callout") page, the floor
   plan, and every page that carries the `STAND SIZE / STAND AREA / WALL
   HEIGHT / TOTAL HEIGHT` footer. Also fixes a font quirk in these decks
   where the "ti" ligature glyph is dropped or mis-decoded ("Recep on desk"
   -> "Reception desk").
2. **`boq/callout_map.py`** -- a small, deliberately generic dictionary that
   turns known callout labels ("LOCKABLE BAR COUNTER", "48 MM PLATFORM WITH
   DUAL LAMINATE & LIT", ...) and floor-plan room names into BOQ line items,
   in Fountainhead's house phrasing.
3. **`boq/ai_narrative.py`** *(optional)* -- calls the Claude API with the
   actual render images plus everything already extracted, and asks it to
   propose *additional* Floor/Stand/Signing lines for things a human
   designer would describe freehand ("Walls will have roll paint finish")
   that have no literal text source in the PDF. Skipped cleanly if
   `ANTHROPIC_API_KEY` isn't set.
4. **`boq/legal_text.py`** -- Fountainhead's fixed quotation boilerplate
   (terms, payment conditions, notes, cancellation/dispute clauses), plus
   the one part of the schedule that *is* computed: technical-drawing/
   graphics/production-start/handover deadlines, each a fixed number of days
   before the show's opening date.
5. **`boq/docx_builder.py`** -- assembles the final document: header field
   table, three hero images, the numbered specifications table, and the
   boilerplate/signature block.
6. **`app.py`** -- a small Flask app tying it together with a review/edit
   step in between extraction and the final document, since some fields
   (Client, Contact Person, Email) simply aren't in the spec PDF and some
   AI-suggested lines deserve a human glance before they go out to a client.

### The three hero images

Per your instruction, the three images at the top of the BOQ default to
**pages 4, 5 and 6** of the uploaded PDF. Because not every deck's pages 4-6
are equally good renders (in the sample IFF file, page 6 happens to
duplicate page 3), the review page shows thumbnails of every render page and
lets you swap the selection before generating -- the default selection is
always 4/5/6.

## Setup

```bash
cd boq_generator
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

You'll also need `poppler` fonts/rendering support is not required (PDF
rendering is done in-process via PyMuPDF), but LibreOffice is handy if you
want to sanity-check a generated `.docx` by converting it to PDF yourself
(`soffice --headless --convert-to pdf out.docx`) -- not required to run the
app itself.

For the optional AI-assisted narrative step, set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# optional: override the model (defaults to claude-sonnet-5)
export BOQ_AI_MODEL=claude-sonnet-5
```

## Run

```bash
python3 app.py            # http://127.0.0.1:5000
# or: PORT=8080 python3 app.py
```

1. Upload the spec PDF.
2. Review the extracted header fields, pick the 3 hero images (defaults to
   pages 4/5/6), and edit any of the 8 specification sections -- each is a
   plain-text box, one line per item as `qty | description`.
3. Optionally click **"Add AI-suggested lines"** to have Claude look at the
   selected images and propose extra Floor/Stand/Signing lines (marked
   `[AI]` so you can spot and edit/remove them before generating).
4. Click **"Generate BOQ .docx"** to download the finished document.

## Notes / limitations

- Client, Contact Person and Email are never in the spec PDF -- they're left
  blank for you to fill in, same as the reference document.
- Trade show name / dates / venue / project are parsed from the **filename**
  (e.g. `SPECIFICATION_ IFF Pharma Solutions_ 142.5 sqm_ CPHI Milan 2024_
  Oct. 8-10.pdf`), since the cover page carries them as logos/images rather
  than text. Double-check these on the review page.
- Deterministic room/quantity counts derived from the floor plan (e.g. how
  many discussion tables) are approximate -- the text layer repeats each
  label 2-3x for a bold/stroke effect and wraps some labels across lines, so
  counts are a lower-bound hint rather than ground truth. Verify visually.
- The AI-assisted step is intentionally scoped to *adding* lines the
  deterministic parser can't source, not rewriting anything -- if
  `ANTHROPIC_API_KEY` isn't set, the app still produces a complete BOQ, just
  without those extra narrative lines.
