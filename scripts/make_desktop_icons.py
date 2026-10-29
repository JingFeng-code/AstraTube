"""Generate a deterministic TEMPORARY alpha icon at build time.

A proper visual identity must replace this placeholder before public release.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"
ROOT.mkdir(parents=True, exist_ok=True)


def image(size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (14, 27, 49, 255))
    draw = ImageDraw.Draw(canvas)
    pad = size // 6
    draw.rounded_rectangle((pad, pad, size - pad, size - pad),
                           radius=size // 7, fill=(35, 124, 181, 255))
    draw.polygon([(size*.43, size*.32), (size*.43, size*.68),
                  (size*.71, size*.50)], fill=(255, 255, 255, 255))
    return canvas


image(32).save(ROOT / "32x32.png")
image(128).save(ROOT / "128x128.png")
image(256).save(ROOT / "icon.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Generated desktop alpha placeholder icons")
