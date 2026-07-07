"""
inpaint.py
----------
Stage 3: erase the original English text from each page image while
leaving surrounding layout, images, shapes, and colors untouched.

Two strategies are supported:

  - "fill"     : fast, robust. Estimates the local background color just
                 outside each text block's bounding box and paints the
                 block with a solid rectangle of that color. Works very
                 well for the common case of text on a flat/near-flat
                 background (the vast majority of reports, letters,
                 forms, articles).

  - "inpaint"  : uses OpenCV's Navier-Stokes/Telea inpainting to
                 reconstruct texture under the text mask. Better for
                 textured or gradient backgrounds, slightly slower.

The mode is configurable per-run; "fill" is the default because it is
faster and more predictable for typical documents.
"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np
from PIL import Image

from models import TextBlock


def _sample_background_color(img_np: np.ndarray, x: int, y: int, w: int, h: int,
                              border: int = 6) -> tuple:
    """Sample a thin ring of pixels just outside the text block to estimate
    the true background color, ignoring the text strokes themselves."""
    H, W = img_np.shape[:2]
    x0, y0 = max(0, x - border), max(0, y - border)
    x1, y1 = min(W, x + w + border), min(H, y + h + border)

    outer = img_np[y0:y1, x0:x1].reshape(-1, 3)
    inner_mask = np.ones((y1 - y0, x1 - x0), dtype=bool)
    iy0, ix0 = max(0, y - y0), max(0, x - x0)
    iy1, ix1 = min(y1 - y0, iy0 + h), min(x1 - x0, ix0 + w)
    inner_mask[iy0:iy1, ix0:ix1] = False

    ring_pixels = img_np[y0:y1, x0:x1][inner_mask]
    if ring_pixels.size == 0:
        ring_pixels = outer
    # Median is robust against stray dark text pixels leaking into the ring
    return tuple(int(v) for v in np.median(ring_pixels, axis=0))


def erase_text_blocks(images: List[Image.Image], blocks: List[TextBlock],
                       mode: str = "fill", padding: int = 3) -> List[Image.Image]:
    """Return new page images with every detected text block erased.

    `padding` slightly over-erases each box (in pixels) to fully remove
    anti-aliased glyph edges.
    """
    pages_np = [np.array(img).copy() for img in images]

    # group blocks by page for slightly better locality/perf
    by_page: dict = {}
    for b in blocks:
        by_page.setdefault(b.page_index, []).append(b)

    for page_index, page_blocks in by_page.items():
        canvas = pages_np[page_index]
        if mode == "inpaint":
            mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
            for b in page_blocks:
                x0 = max(0, b.x - padding)
                y0 = max(0, b.y - padding)
                x1 = min(canvas.shape[1], b.x + b.w + padding)
                y1 = min(canvas.shape[0], b.y + b.h + padding)
                mask[y0:y1, x0:x1] = 255
            canvas = cv2.inpaint(canvas, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
        else:  # "fill"
            for b in page_blocks:
                x0 = max(0, b.x - padding)
                y0 = max(0, b.y - padding)
                x1 = min(canvas.shape[1], b.x + b.w + padding)
                y1 = min(canvas.shape[0], b.y + b.h + padding)
                bg = _sample_background_color(canvas, b.x, b.y, b.w, b.h)
                canvas[y0:y1, x0:x1] = bg
        pages_np[page_index] = canvas

    return [Image.fromarray(p) for p in pages_np]
