"""
main.py
-------
CLI entry point that wires together the full pipeline:

  PDF -> page images -> OCR/layout -> translate -> erase -> redraw -> PDF

Usage:
    python main.py --input document.pdf --output document_urdu.pdf \
                    --backend anthropic --api-key sk-ant-...

    # or, offline dry-run (no translation, just to sanity-check the pipeline)
    python main.py --input document.pdf --output test.pdf --backend echo

Run `python main.py --help` for all options.
"""

from __future__ import annotations

import argparse
import sys
import time

from PIL import Image

from ocr_layout import render_pdf_pages, extract_text_blocks
from inpaint import erase_text_blocks
from render import draw_translated_blocks
from translator import get_translator, TranslationUnit


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Translate an English PDF into Roman Urdu while preserving layout."
    )
    p.add_argument("--input", "-i", required=True, help="Path to the source English PDF")
    p.add_argument("--output", "-o", required=True, help="Path to write the translated PDF")
    p.add_argument("--dpi", type=int, default=300,
                   help="Rasterization DPI (higher = sharper but slower). Default: 300")
    p.add_argument("--backend", choices=["anthropic", "openai", "echo"], default="echo",
                   help="Translation backend. 'echo' requires no API key (offline test mode).")
    p.add_argument("--api-key", default=None,
                   help="API key for the chosen backend. Falls back to env var if omitted.")
    p.add_argument("--model", default=None,
                   help="Override the default model for the chosen backend.")
    p.add_argument("--erase-mode", choices=["fill", "inpaint"], default="fill",
                   help="Text erasure strategy. 'fill' = solid background color (fast, robust). "
                        "'inpaint' = OpenCV texture reconstruction (better for busy backgrounds).")
    p.add_argument("--min-confidence", type=int, default=40,
                   help="Minimum OCR confidence (0-100) to keep a detected word. Default: 40")
    p.add_argument("--align", choices=["left", "center"], default="left",
                   help="Text alignment for redrawn Roman Urdu text.")
    return p


def run_pipeline(input_pdf: str, output_pdf: str, dpi: int, backend: str,
                  api_key: str | None, model: str | None, erase_mode: str,
                  min_confidence: int, align: str) -> None:
    t0 = time.time()

    print(f"[1/5] Rendering '{input_pdf}' to images @ {dpi} DPI ...")
    pages = render_pdf_pages(input_pdf, dpi=dpi)
    print(f"      -> {len(pages)} page(s) rendered.")

    print("[2/5] Running OCR + layout analysis ...")
    blocks = extract_text_blocks(pages, min_confidence=min_confidence)
    print(f"      -> {len(blocks)} text block(s) detected across all pages.")
    if not blocks:
        print("      No text detected. Writing pages through unchanged.")

    print(f"[3/5] Translating text blocks via '{backend}' backend ...")
    translator = get_translator(backend, api_key=api_key, model=model)
    units = [TranslationUnit(id=i, text=b.text) for i, b in enumerate(blocks)]
    translations = translator.translate_batch(units) if units else {}
    print(f"      -> {len(translations)} block(s) translated.")

    print(f"[4/5] Erasing original English text (mode='{erase_mode}') ...")
    erased_pages = erase_text_blocks(pages, blocks, mode=erase_mode)

    print(f"[5/5] Rendering Roman Urdu text back onto pages (align='{align}') ...")
    final_pages = draw_translated_blocks(erased_pages, blocks, translations, align=align)

    print(f"      Compiling {len(final_pages)} page(s) into '{output_pdf}' ...")
    save_pages_as_pdf(final_pages, output_pdf)

    print(f"Done in {time.time() - t0:.1f}s -> {output_pdf}")


def save_pages_as_pdf(pages: list[Image.Image], output_path: str) -> None:
    """Compile a list of RGB PIL images into a single multi-page PDF."""
    if not pages:
        raise ValueError("No pages to save.")
    rgb_pages = [p.convert("RGB") for p in pages]
    first, rest = rgb_pages[0], rgb_pages[1:]
    first.save(output_path, save_all=True, append_images=rest)


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        run_pipeline(
            input_pdf=args.input, output_pdf=args.output, dpi=args.dpi,
            backend=args.backend, api_key=args.api_key, model=args.model,
            erase_mode=args.erase_mode, min_confidence=args.min_confidence,
            align=args.align,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
