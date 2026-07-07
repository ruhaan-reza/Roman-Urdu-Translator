"""
models.py
---------
Shared data structures used across pipeline stages. Kept dependency-free
(no fitz/pytesseract/cv2 imports) so that modules like render.py and
inpaint.py can be imported/tested without pulling in the OCR/PDF stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TextBlock:
    """A paragraph-level text block detected on a page, with everything
    the downstream stages need: position, original text, and style hints
    used to approximate the original typography when we redraw it."""
    page_index: int
    x: int
    y: int
    w: int
    h: int
    text: str
    avg_font_height: float          # pixels, used to pick an initial font size
    dominant_color_rgb: tuple       # estimated text color (R, G, B)
    line_count: int = 1
    words: List[dict] = field(default_factory=list)  # raw tesseract word rows
