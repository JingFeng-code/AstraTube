"""建置時產生桌面版圖示：新月和星星，配色與介面的月光銀一致。

工作列可能是深色或淺色，所以固定用深灰藍底，不跟著主題變。
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"
ROOT.mkdir(parents=True, exist_ok=True)

_TILE = (79, 88, 112, 255)
_MOON = (255, 255, 255, 255)
_STAR = (255, 233, 168, 255)
_SCALE = 4


def _star(unit: float, x: float, y: float, r: float) -> list[tuple[float, float]]:
    points = []
    for i in range(10):
        radius = r * (0.45 if i % 2 else 1)
        angle = -math.pi / 2 + i * math.pi / 5
        points.append(((x + radius * math.cos(angle)) * unit, (y + radius * math.sin(angle)) * unit))
    return points


def image(size: int) -> Image.Image:
    # 先畫大再縮小，小尺寸圖示的邊緣才不會有鋸齒
    big = size * _SCALE
    unit = big / 100
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(24 * unit), fill=_TILE)
    draw.ellipse(((46 - 30) * unit, (52 - 30) * unit, (46 + 30) * unit, (52 + 30) * unit), fill=_MOON)
    draw.ellipse(((58 - 26) * unit, (44 - 26) * unit, (58 + 26) * unit, (44 + 26) * unit), fill=_TILE)
    draw.polygon(_star(unit, 66, 40, 14), fill=_STAR)
    return canvas.resize((size, size), Image.LANCZOS)


image(32).save(ROOT / "32x32.png")
image(128).save(ROOT / "128x128.png")
image(256).save(ROOT / "icon.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Generated desktop icons")
