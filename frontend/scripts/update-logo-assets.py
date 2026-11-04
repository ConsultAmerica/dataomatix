"""Crop the new DataOMatix artwork into mark / wordmark / full / icon assets."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(
    r"C:\Users\nazia\.cursor\projects\e-projects-AI-Projects-dataomatix\assets"
    r"\image-172be3c1-c8b6-4d09-a01b-fa226c43a6b0.jpg"
)
OUT = ROOT / "public" / "brand"
FAVICON = ROOT / "src" / "app" / "favicon.ico"


def to_rgba(im: Image.Image, threshold: int = 248) -> Image.Image:
    """Turn near-white background into transparency."""
    rgba = im.convert("RGBA")
    arr = np.asarray(rgba).copy()
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    white = (r >= threshold) & (g >= threshold) & (b >= threshold)
    # Soft edge: fade nearly-white pixels
    near = (r >= threshold - 12) & (g >= threshold - 12) & (b >= threshold - 12) & ~white
    a = a.astype(np.float32)
    a[white] = 0
    # Blend near-white toward transparent
    strength = ((r.astype(np.float32) + g + b) / 3 - (threshold - 12)) / 12
    strength = np.clip(strength, 0, 1)
    a[near] = a[near] * (1 - strength[near])
    arr[:, :, 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def content_bbox(im: Image.Image, alpha_min: int = 8) -> tuple[int, int, int, int]:
    arr = np.asarray(im)
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > alpha_min)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def find_divider_x(rgb: Image.Image, bbox: tuple[int, int, int, int]) -> int:
    arr = np.asarray(rgb.convert("RGB"))
    x0, y0, x1, y1 = bbox
    band = arr[y0:y1, x0:x1, :]
    h, w, _ = band.shape
    scores: list[tuple[int, int]] = []
    for x in range(int(w * 0.22), int(w * 0.55)):
        col = band[:, x, :].astype(np.int16)
        # thin gray vertical stroke on white
        gray = (
            (np.abs(col[:, 0] - col[:, 1]) < 14)
            & (np.abs(col[:, 1] - col[:, 2]) < 14)
            & (col[:, 0] > 110)
            & (col[:, 0] < 210)
        )
        # mostly empty column except the short divider
        nonwhite = ~((col[:, 0] > 245) & (col[:, 1] > 245) & (col[:, 2] > 245))
        gsum = int(gray.sum())
        nsum = int(nonwhite.sum())
        if 12 < gsum < h * 0.55 and nsum < h * 0.65:
            scores.append((gsum * 2 - nsum, x0 + x))
    scores.sort(reverse=True)
    if not scores:
        # fallback: ~32% into content (icon is left third)
        return x0 + int((x1 - x0) * 0.30)
    return scores[0][1]


def trim(im: Image.Image, pad: int = 4) -> Image.Image:
    box = content_bbox(im)
    x0, y0, x1, y1 = box
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(im.width, x1 + pad)
    y1 = min(im.height, y1 + pad)
    return im.crop((x0, y0, x1, y1))


def on_dark_variant(im: Image.Image) -> Image.Image:
    """Slightly brighten for dark chrome; keep orange/blue intact."""
    arr = np.asarray(im.convert("RGBA")).astype(np.float32)
    rgb, a = arr[:, :, :3], arr[:, :, 3:4]
    # Lift dark navy letters a bit so they read on dark backgrounds without washing orange
    mask = (a[:, :, 0] > 20) & (rgb.mean(axis=2) < 90)
    rgb[mask] = np.clip(rgb[mask] * 1.35 + 28, 0, 255)
    out = np.concatenate([rgb, a], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def make_icon(mark: Image.Image, size: int = 512) -> Image.Image:
    """Square app icon: mark centered on transparent canvas."""
    m = trim(mark, pad=2)
    # fit into square with padding
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = min((size * 0.86) / m.width, (size * 0.86) / m.height)
    nw, nh = max(1, int(m.width * scale)), max(1, int(m.height * scale))
    resized = m.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
    return canvas


def save_png(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG", optimize=True)
    print(f"wrote {path.relative_to(ROOT)} {im.size}")


def main() -> None:
    raw = Image.open(SRC).convert("RGB")
    rgba = to_rgba(raw)
    full = trim(rgba, pad=6)
    save_png(full, OUT / "dataomatix-logo-full.png")
    # also keep jpg preview
    full.convert("RGB").save(OUT / "dataomatix-logo-full.jpg", "JPEG", quality=92, optimize=True)

    # divider between mark and word
    # Use original RGB for divider detection before transparency softens it
    bbox = content_bbox(rgba)
    div = find_divider_x(raw, bbox)
    print(f"divider x={div} bbox={bbox}")

    # Mark: left of divider; Word: right of divider
    mark = trim(rgba.crop((0, 0, div - 4, rgba.height)), pad=4)
    word = trim(rgba.crop((div + 4, 0, rgba.width, rgba.height)), pad=4)
    save_png(mark, OUT / "dataomatix-mark.png")
    save_png(word, OUT / "dataomatix-wordmark.png")
    save_png(on_dark_variant(mark), OUT / "dataomatix-mark-on-dark.png")
    save_png(on_dark_variant(word), OUT / "dataomatix-wordmark-on-dark.png")

    icon = make_icon(mark, 512)
    save_png(icon, OUT / "dataomatix-icon.png")

    # favicon multi-size ico
    sizes = [16, 32, 48]
    icons = [icon.resize((s, s), Image.Resampling.LANCZOS) for s in sizes]
    icons[0].save(FAVICON, format="ICO", sizes=[(s, s) for s in sizes], append_images=icons[1:])
    print(f"wrote {FAVICON.relative_to(ROOT)}")

    # Update component aspect ratios helper print
    print(f"MARK ratio {mark.width}/{mark.height} = {mark.width / mark.height:.4f}")
    print(f"WORD ratio {word.width}/{word.height} = {word.width / word.height:.4f}")


if __name__ == "__main__":
    main()
