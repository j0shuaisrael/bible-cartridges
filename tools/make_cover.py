#!/usr/bin/env python3
"""Deterministic procedural stand-in covers, one distinct design per psalm.

    python3 tools/make_cover.py --psalm 2 --size 3072 --out psalms/002/cover.png
    python3 tools/make_cover.py --psalm 119 --size 4096 --out psalms/119/cover.png

STAND-IN — Pol's real cover art is still owed. Every cover is marked twice:
a visible "STAND-IN COVER · PSALM N" label on the image itself, and a
"Stand-in" PNG text chunk in the file metadata. A later worker swaps in
the real art by replacing psalms/NNN/cover.png; nothing else changes.

Design: a vertical gradient whose hue steps by the golden angle per psalm,
concentric arcs + radial rays from a seeded focal point, a soft vignette.
Deterministic (seeded by psalm number) so re-running reproduces the file.
Built at low resolution and upscaled for the smooth parts so a 4096x4096
render stays fast and the PNG stays compressible.
"""
import argparse
import colorsys
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def make_cover(n: int, size: int) -> Image.Image:
    rng = random.Random(10_000 + n)
    hue = (n * 137.508) % 360 / 360.0
    hue2 = (hue + 0.08 + rng.random() * 0.06) % 1.0
    c_top = tuple(round(255 * v) for v in colorsys.hsv_to_rgb(hue, 0.55, 0.32))
    c_bot = tuple(round(255 * v) for v in colorsys.hsv_to_rgb(hue2, 0.65, 0.78))
    c_glow = tuple(round(255 * v) for v in colorsys.hsv_to_rgb((hue + 0.5) % 1.0, 0.35, 0.95))

    # Smooth vertical gradient, built small and upscaled.
    small = 256
    grad = Image.new("RGB", (1, small))
    grad.putdata([
        tuple(round(c_top[i] + (c_bot[i] - c_top[i]) * y / (small - 1)) for i in range(3))
        for y in range(small)
    ])
    img = grad.resize((size, size), Image.BICUBIC).convert("RGB")

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    fx, fy = size * (0.30 + 0.4 * rng.random()), size * (0.28 + 0.25 * rng.random())
    # Radial rays from the focal point.
    for k in range(24):
        ang = 2 * math.pi * k / 24 + rng.random() * 0.1
        x2, y2 = fx + math.cos(ang) * size, fy + math.sin(ang) * size
        d.line([(fx, fy), (x2, y2)], fill=c_glow + (10,), width=max(2, size // 256))
    # Concentric arcs.
    for k in range(1, 7):
        r = size * (0.08 + 0.09 * k) * (0.8 + 0.4 * rng.random())
        d.ellipse([fx - r, fy - r, fx + r, fy + r],
                  outline=c_glow + (26,), width=max(2, size // 512))
    # A few soft translucent discs.
    for _ in range(9):
        cx, cy = rng.random() * size, rng.random() * size
        r = size * rng.uniform(0.03, 0.12)
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=c_glow + (rng.randint(6, 16),))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Vignette, built small and upscaled.
    vg = Image.new("L", (128, 128), 0)
    vd = ImageDraw.Draw(vg)
    vd.ellipse([-32, -32, 160, 160], fill=255)
    vg = vg.resize((size, size), Image.BICUBIC)
    black = Image.new("RGB", (size, size), (0, 0, 0))
    img = Image.composite(img, black, vg.point(lambda p: 255 - int((255 - p) * 0.45)))

    # Stand-in label, bottom centre.
    d = ImageDraw.Draw(img)
    label = f"PSALM {n}  ·  STAND-IN COVER"
    sub = "Bible Cartridges — real cover art still owed"
    f1 = _font(FONT_BOLD, max(28, size // 48))
    f2 = _font(FONT, max(20, size // 72))
    for text, font, y_frac in ((label, f1, 0.90), (sub, f2, 0.935)):
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (size - tw) // 2, int(size * y_frac)
        d.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0))
        d.text((x, y), text, font=font, fill=(255, 255, 255))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--psalm", type=int, required=True)
    ap.add_argument("--size", type=int, choices=[3072, 4096], default=3072)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if not 1 <= args.psalm <= 150:
        raise SystemExit(f"psalm out of range: {args.psalm}")
    img = make_cover(args.psalm, args.size)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Stand-in",
                  f"Procedural placeholder cover for Psalm {args.psalm}; "
                  "Pol's real cover art is still owed.")
    meta.add_text("Psalm", str(args.psalm))
    img.save(out, pnginfo=meta)
    print(f"wrote {out} ({img.size[0]}x{img.size[1]}, {out.stat().st_size} bytes, STAND-IN)")


if __name__ == "__main__":
    main()
