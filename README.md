# English PDF -> Roman Urdu Translator (Layout-Preserving)

A standalone pipeline that translates an English PDF — including scanned,
non-copyable, or image-based PDFs — into **Roman Urdu** (Urdu written in
the Latin alphabet, e.g. *"Aap kaise hain?"*), while keeping the original
visual layout: same page size, same positions, same images/shapes/colors.

Because Roman Urdu uses the plain Latin alphabet, no Arabic/Nastaliq text
shaping is needed — this keeps the rendering stage simple and reliable.

## How it works

```
 PDF ──▶ [1] Rasterize pages ──▶ [2] OCR + layout ──▶ [3] Translate
                                                              │
 Final PDF ◀── [5] Redraw Roman Urdu ◀── [4] Erase original text ◀┘
```

| Stage | File | What it does |
|---|---|---|
| 1. Rasterize | `ocr_layout.py` (`render_pdf_pages`) | Renders every page to a high-DPI image with PyMuPDF — this is what lets the tool handle scanned/image-only PDFs, since nothing downstream touches a text layer. |
| 2. OCR + layout | `ocr_layout.py` (`extract_text_blocks`) | Runs Tesseract's `image_to_data`, groups words → lines → paragraph blocks, and records each block's bounding box, average glyph height, and estimated text color. |
| 3. Translate | `translator.py` | Pluggable backend (Anthropic / OpenAI / offline echo) translates each block's text into Roman Urdu. Batches multiple blocks per API call. |
| 4. Erase | `inpaint.py` | Paints over each original text block using either sampled background color (`fill`, fast/default) or OpenCV texture inpainting (`inpaint`, for busy backgrounds). |
| 5. Redraw | `render.py` | Draws the translated text at the original coordinates, word-wrapping and auto-shrinking the font until it fits the original box, matching the sampled text color and bold/regular weight. |
| Assemble | `main.py` | Compiles the final page images back into a single multi-page PDF. |

`models.py` holds the shared `TextBlock` data structure so the erase/render
stages don't need to depend on the OCR/PDF libraries.

## 1. System dependencies

Install these **before** the Python packages:

**Tesseract OCR engine** (required by `pytesseract`):
```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y tesseract-ocr

# macOS (Homebrew)
brew install tesseract

# Windows
# Download and run the installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
# Then add the install folder (e.g. C:\Program Files\Tesseract-OCR) to PATH.
```

**Fonts** (for Latin-script Roman Urdu rendering): Linux systems typically
already have DejaVu Sans installed at
`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, which `render.py` looks
for automatically. If you don't have it:
```bash
sudo apt-get install -y fonts-dejavu-core
```
On macOS/Windows the script falls back to Arial automatically. To pin a
specific font, drop `DejaVuSans.ttf` / `DejaVuSans-Bold.ttf` into a
`fonts/` folder next to the scripts — `render.py` checks there first.

## 2. Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

If you only intend to use one translation backend, you can skip installing
the other (e.g. skip `openai` if you're only using `--backend anthropic`).

## 3. API key (translation backend)

Pick one:

**Anthropic (recommended)**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."       # macOS/Linux
setx ANTHROPIC_API_KEY "sk-ant-..."         # Windows
```

**OpenAI**
```bash
export OPENAI_API_KEY="sk-..."
```

**No key / offline test mode**: use `--backend echo`. This skips real
translation (it just tags each block with `[UR]`) so you can verify the
layout-preservation pipeline (erase + redraw + rebuild) works on your
machine before spending API credits.

## 4. Usage

```bash
python main.py \
  --input path/to/english_document.pdf \
  --output path/to/roman_urdu_output.pdf \
  --backend anthropic \
  --dpi 300
```

### All options
```
--input / -i         Path to the source English PDF               (required)
--output / -o         Path to write the translated PDF              (required)
--dpi                 Rasterization DPI, default 300 (use 400-600 for dense/small text)
--backend             anthropic | openai | echo                    (default: echo)
--api-key             Override API key instead of using the env var
--model               Override the default model for the backend
--erase-mode          fill (default, fast) | inpaint (for textured/gradient backgrounds)
--min-confidence      Minimum OCR confidence 0-100 to keep a word    (default: 40)
--align               left (default) | center
```

### Examples

Offline dry-run (no API key needed) to sanity-check layout preservation:
```bash
python main.py -i sample.pdf -o sample_test.pdf --backend echo
```

Scanned document with a busy/textured background, higher DPI for small print:
```bash
python main.py -i scanned_form.pdf -o scanned_form_urdu.pdf \
  --backend anthropic --dpi 400 --erase-mode inpaint
```

Using OpenAI instead:
```bash
python main.py -i report.pdf -o report_urdu.pdf \
  --backend openai --model gpt-4o-mini
```

## 5. Notes, limits, and tuning tips

- **Accuracy of erasure** depends on OCR bounding-box precision. For dense
  or low-quality scans, raise `--dpi` (e.g. 400–600) and/or lower
  `--min-confidence` slightly to catch faint text (at the risk of also
  catching noise — tune per document).
- **`fill` vs `inpaint`**: `fill` is faster and works great for typical flat
  or near-flat backgrounds (letters, reports, forms). Use `inpaint` for
  scans with background images, gradients, or watermarks behind the text.
- **Font fitting**: Roman Urdu translations are often 20–40% longer than
  the English source. `render.py` automatically shrinks the font size
  (down to an 8px floor) and word-wraps within the original box; if a
  block is still too small after translation, consider re-running that
  page at a higher `--dpi` so bounding boxes have more room.
- **Tables/columns**: multi-column layouts are supported because blocks are
  grouped by Tesseract's own paragraph detection, but very tight, small
  tables may need `--dpi` bumped for reliable OCR block separation.
- **Cost/speed**: translation is batched (default 25 blocks/request) to
  minimize API calls on large documents; adjust `batch_size` in
  `translator.py` if you hit request-size limits with a particular model.
- **Extending to a new translation provider**: implement the `Translator`
  interface in `translator.py` (just one method, `translate_batch`) and
  register it in `get_translator()` — nothing else in the pipeline needs
  to change.

## 6. Project structure

```
pdf_translator/
├── main.py           # CLI entry point / orchestrator
├── ocr_layout.py      # PDF rasterization + OCR/layout extraction
├── inpaint.py          # Original-text erasure (fill / inpaint modes)
├── render.py           # Roman Urdu redraw with auto-fit font scaling
├── translator.py        # Pluggable translation backends
├── models.py            # Shared TextBlock data structure
├── requirements.txt
└── README.md
```
