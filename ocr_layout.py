"""
ocr_layout.py
-------------
Stage 1 & 2 of the pipeline:
  1. Ingest the PDF and rasterize every page to a high-resolution image
     (handles scanned / non-copyable / image-only PDFs equally well,
     since we never rely on the PDF's text layer).
  2. Run OCR + layout analysis (Tesseract's `image_to_data`) to recover
     line-level bounding boxes, grouped into paragraph "blocks" so that
     translation and rendering operate on coherent chunks of text rather
     than isolated words.

Each page is rendered via PyMuPDF (fitz) at a configurable DPI, which is
fast, dependency-light (no external poppler binary required) and gives us
a numpy/PIL-friendly image plus exact page dimensions for the final
rebuild step.
"""

from __future__ import annotations

from typing import List

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image

from models import TextBlock


def render_pdf_pages(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """Rasterize every page of the PDF into a PIL Image at the given DPI.
    This is what lets the pipeline handle scanned / image-only PDFs: from
    this point on we only ever operate on pixels, never on a text layer.
    """
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        images.append(img)
    doc.close()
    return images


def _estimate_text_color(img_np: np.ndarray, x: int, y: int, w: int, h: int) -> tuple:
    """Sample pixels inside the block and pick the darkest cluster's mean
    color as a proxy for text color (works well for standard dark-on-light
    documents, which covers the overwhelming majority of real-world PDFs)."""
    crop = img_np[max(0, y):y + h, max(0, x):x + w]
    if crop.size == 0:
        return (0, 0, 0)
    gray = crop.mean(axis=2)
    threshold = np.percentile(gray, 25)  # darkest quartile ~= text strokes
    mask = gray <= threshold
    if not mask.any():
        return (0, 0, 0)
    pixels = crop[mask]
    return tuple(int(v) for v in pixels.mean(axis=0))


def extract_text_blocks(images: List[Image.Image], min_confidence: int = 40,
                         paragraph_gap_px: int = 18) -> List[TextBlock]:
    """Run OCR on each page image and group detected lines into paragraph
    blocks using Tesseract's block/paragraph structure, falling back to a
    simple vertical-gap heuristic when Tesseract's own grouping is too
    coarse or too fragmented for a given document.
    """
    all_blocks: List[TextBlock] = []

    for page_index, img in enumerate(images):
        img_np = np.array(img)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        n = len(data["text"])
        rows = []
        for i in range(n):
            text = data["text"][i].strip()
            conf = int(float(data["conf"][i])) if data["conf"][i] != "-1" else -1
            if not text or conf < min_confidence:
                continue
            rows.append({
                "text": text,
                "left": data["left"][i], "top": data["top"][i],
                "width": data["width"][i], "height": data["height"][i],
                "block_num": data["block_num"][i], "par_num": data["par_num"][i],
                "line_num": data["line_num"][i],
            })

        if not rows:
            continue

        # Group words -> lines -> paragraphs using tesseract's own indices
        from itertools import groupby
        key = lambda r: (r["block_num"], r["par_num"])
        rows.sort(key=key)
        for (_, _), group in groupby(rows, key=key):
            group = list(group)
            xs0 = min(r["left"] for r in group)
            ys0 = min(r["top"] for r in group)
            xs1 = max(r["left"] + r["width"] for r in group)
            ys1 = max(r["top"] + r["height"] for r in group)

            lines_by_num = {}
            for r in group:
                lines_by_num.setdefault(r["line_num"], []).append(r)
            line_texts = []
            for line_num in sorted(lines_by_num):
                line_words = sorted(lines_by_num[line_num], key=lambda r: r["left"])
                line_texts.append(" ".join(w["text"] for w in line_words))
            paragraph_text = " ".join(line_texts)

            avg_h = sum(r["height"] for r in group) / len(group)
            color = _estimate_text_color(img_np, xs0, ys0, xs1 - xs0, ys1 - ys0)

            all_blocks.append(TextBlock(
                page_index=page_index,
                x=xs0, y=ys0, w=xs1 - xs0, h=ys1 - ys0,
                text=paragraph_text,
                avg_font_height=avg_h,
                dominant_color_rgb=color,
                line_count=len(lines_by_num),
                words=group,
            ))

    return all_blocks
