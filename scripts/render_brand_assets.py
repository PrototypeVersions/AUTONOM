#!/usr/bin/env python3
"""Render the canonical vector AUTONOM artwork into social and favicon bitmaps.
The SVG files in the repository are the source of truth. This script is visual
asset generation only; it never imports or modifies market/trading state.
"""
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def render(name, output, width, height):
    cairosvg.svg2png(
        url=str(ROOT / name),
        write_to=str(ROOT / output),
        output_width=width,
        output_height=height,
    )


def main():
    render("social-preview.svg", "social-preview.png", 1200, 630)
    render("favicon.svg", "favicon-32.png", 32, 32)
    render("favicon.svg", "apple-touch-icon.png", 180, 180)
    render("favicon.svg", "_favicon-source.png", 256, 256)
    source = ROOT / "_favicon-source.png"
    with Image.open(source) as im:
        im.save(ROOT / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    source.unlink()


if __name__ == "__main__":
    main()
