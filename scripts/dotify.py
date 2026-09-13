#!/usr/bin/env python3
"""
Converts a photo into a colored dot-matrix (halftone-style) SVG portrait,
in the style used by GitHub profile READMEs that render a headshot as dots.

Usage:
    python scripts/dotify.py assets/portrait-source.png -o assets/portrait \
        --cols 90 --bg-threshold 235 --detail 1.0

Outputs assets/portrait.svg (single file — GitHub profile READMEs render
fine on both light/dark themes since the background is baked in as dark,
matching the toolbox/radar sections of this README).
"""

import argparse
from xml.sax.saxutils import escape as xml_escape

from PIL import Image, ImageChops


def autocrop_background(img, bg_threshold=235, padding=20):
    """Crop away background margins around the subject, with a bit of padding.
    Uses the alpha channel when present (exact), otherwise a near-white
    color threshold (approximate)."""
    if img.mode == "RGBA":
        mask = img.split()[-1].point(lambda a: 255 if a > 10 else 0)
    else:
        gray = img.convert("L")
        mask = gray.point(lambda p: 255 if p < bg_threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)
    return img.crop((left, top, right, bottom))


def build_dots(image_path, cols, bg_threshold, detail, autocrop=True):
    src = Image.open(image_path)
    has_alpha = src.mode == "RGBA"
    if autocrop:
        src = autocrop_background(src, bg_threshold=bg_threshold)
    img = src.convert("RGB")
    w, h = img.size
    cell = w / cols
    rows = max(1, round(h / cell))
    small = img.resize((cols, rows), Image.LANCZOS)
    pixels = small.load()

    alpha_small = None
    if has_alpha:
        alpha_small = src.split()[-1].resize((cols, rows), Image.LANCZOS).load()

    dots = []
    for y in range(rows):
        for x in range(cols):
            r, g, b = pixels[x, y]
            if alpha_small is not None:
                if alpha_small[x, y] < 40:  # transparent -> background
                    continue
            elif r >= bg_threshold and g >= bg_threshold and b >= bg_threshold:
                # No alpha channel: fall back to guessing background by color.
                continue
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            # Brighter foreground content (skin highlights, light shirt
            # folds) reads as a bigger dot; dark content (hair, glasses,
            # shadow) as a smaller one — this is what gives the style its
            # "glowing" look rather than a flat silhouette.
            radius = (0.25 + 0.75 * luminance) * detail
            dots.append((x, y, r, g, b, radius))
    return dots, cols, rows


def render_svg(dots, cols, rows, bg_color="#0d1117", cell_px=8, max_radius_px=3.6, stroke=None, stroke_width=0.4):
    width = cols * cell_px
    height = rows * cell_px

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100%" height="100%" fill="{bg_color}"/>',
    ]
    stroke_attr = f' stroke="{stroke}" stroke-width="{stroke_width}"' if stroke else ""
    for x, y, r, g, b, radius in dots:
        cx = (x + 0.5) * cell_px
        cy = (y + 0.5) * cell_px
        rad = min(radius, 1.0) * max_radius_px
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.2f}" fill="rgb({r},{g},{b})"{stroke_attr}/>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", help="Path to the source photo")
    ap.add_argument("-o", "--output", default="assets/portrait", help="Output path (without .svg)")
    ap.add_argument("--cols", type=int, default=90, help="Number of dot columns")
    ap.add_argument("--bg-threshold", type=int, default=235, help="RGB value above which a pixel counts as background")
    ap.add_argument("--detail", type=float, default=1.0, help="Overall dot-size multiplier")
    ap.add_argument("--cell-px", type=int, default=8, help="Pixel spacing between dot centers in the output SVG")
    ap.add_argument("--bg-color", default="#0d1117", help="Canvas background color for the SVG")
    ap.add_argument("--stroke", default=None, help="Optional dot outline color (e.g. 'rgba(0,0,0,0.35)') — recommended for light backgrounds so pale dots stay visible")
    ap.add_argument("--stroke-width", type=float, default=0.4, help="Dot outline width, only used when --stroke is set")
    ap.add_argument("--no-autocrop", action="store_true", help="Skip auto-cropping surrounding white space")
    args = ap.parse_args()

    dots, cols, rows = build_dots(args.image, args.cols, args.bg_threshold, args.detail, autocrop=not args.no_autocrop)
    svg = render_svg(
        dots, cols, rows,
        bg_color=args.bg_color,
        cell_px=args.cell_px,
        stroke=args.stroke,
        stroke_width=args.stroke_width,
    )

    out_path = f"{args.output}.svg"
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Wrote {out_path} ({len(dots)} dots, {cols}x{rows} grid)")


if __name__ == "__main__":
    main()
