"""
render.py
---------
Stage 5: draw the translated Roman Urdu text back onto the erased page
canvases at the original block coordinates, matching approximate style
(color, alignment) and auto-shrinking the font so the (usually longer)
Roman Urdu text still fits inside the original bounding box.

Roman Urdu is written with the plain Latin alphabet (e.g. "Aap kaise
hain?"), so no complex Arabic/Nastaliq text-shaping is required -- any
good Unicode Latin TTF font works, which keeps this module simple and
dependency-light.
"""

from __future__ import annotations

import os
from typing import List

from PIL import Image, ImageDraw, ImageFont

from models import TextBlock

# Reasonable set of fallback fonts across Linux/Mac/Windows. The pipeline
# will use the first one it finds; ship DejaVuSans.ttf alongside the script
# as a guaranteed-available fallback (see README for the download note).
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]

_FONT_CANDIDATES_BOLD = [
    os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def _first_existing(paths: List[str]) -> str | None:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


_REGULAR_FONT_PATH = _first_existing(_FONT_CANDIDATES)
_BOLD_FONT_PATH = _first_existing(_FONT_CANDIDATES_BOLD) or _REGULAR_FONT_PATH


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _BOLD_FONT_PATH if bold else _REGULAR_FONT_PATH
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_and_fit(draw: ImageDraw.ImageDraw, text: str, box_w: int, box_h: int,
                   start_size: int, bold: bool, min_size: int = 8) -> tuple:
    """Binary-search-ish shrink loop: find the largest font size (down to
    `min_size`) at which the text, word-wrapped to `box_w`, still fits
    within `box_h`. Returns (font, wrapped_lines)."""
    size = start_size
    while size >= min_size:
        font = _load_font(size, bold=bold)
        words = text.split()
        lines, current = [], ""
        for word in words:
            trial = f"{current} {word}".strip()
            trial_w = draw.textbbox((0, 0), trial, font=font)[2]
            if trial_w <= box_w or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 2
        total_h = line_height * len(lines)
        max_line_w = max((draw.textbbox((0, 0), l, font=font)[2] for l in lines), default=0)

        if total_h <= box_h and max_line_w <= box_w:
            return font, lines, line_height
        size -= 1

    # Fall back to the smallest size even if it slightly overflows height;
    # width wrapping still keeps it readable rather than clipped mid-word.
    font = _load_font(min_size, bold=bold)
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        trial_w = draw.textbbox((0, 0), trial, font=font)[2]
        if trial_w <= box_w or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 2
    return font, lines, line_height


def draw_translated_blocks(images: List[Image.Image], blocks: List[TextBlock],
                            translations: dict, align: str = "left") -> List[Image.Image]:
    """Draw each block's translated text onto its page at the original
    coordinates, auto-shrinking font size so it fits the bounding box.

    `translations` maps a synthetic block id (its index in `blocks`) to
    the translated string, matching the TranslationUnit ids used upstream.
    """
    pages = [img.copy() for img in images]
    draws = [ImageDraw.Draw(p) for p in pages]

    for idx, block in enumerate(blocks):
        text = translations.get(idx, block.text)
        if not text.strip():
            continue

        draw = draws[block.page_index]
        # Heuristic: treat visually bold text as blocks whose average glyph
        # height is large relative to the page (headings/titles).
        is_heading_like = block.avg_font_height >= 22

        start_size = max(8, int(block.avg_font_height * 0.9))
        font, lines, line_height = _wrap_and_fit(
            draw, text, box_w=block.w, box_h=block.h,
            start_size=start_size, bold=is_heading_like,
        )

        color = block.dominant_color_rgb
        y = block.y
        for line in lines:
            line_w = draw.textbbox((0, 0), line, font=font)[2]
            if align == "center":
                x = block.x + max(0, (block.w - line_w) // 2)
            else:
                x = block.x
            draw.text((x, y), line, font=font, fill=color)
            y += line_height

    return pages
