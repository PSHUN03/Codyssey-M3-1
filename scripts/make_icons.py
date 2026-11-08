"""보라색 화살표 탭·PWA·Apple 아이콘 생성. Pillow 필요.

실행: python scripts/make_icons.py
40×40 좌표는 app/templates/_macros.html의 logo_mark와 같다.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "app" / "static" / "icons"
PURPLE = "#6d4be4"
WHITE = "#ffffff"


def mark(size: int, *, rounded: bool, scale: float = 1.0) -> Image.Image:
    """마스커블 아이콘은 불투명 배경과 중앙 안전 영역 안의 화살표를 쓴다."""
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0) if rounded else PURPLE)
    draw = ImageDraw.Draw(image)
    unit = big / 40
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=12 * unit, fill=PURPLE)
    offset = big * (1 - scale) / 2
    stroke = 2.8 * unit * scale

    def point(x, y):
        return offset + x * unit * scale, offset + y * unit * scale

    for path in (((12, 28), (28, 12)), ((18, 12), (28, 12), (28, 22))):
        points = [point(x, y) for x, y in path]
        draw.line(points, fill=WHITE, width=round(stroke), joint="curve")
        for x, y in points:
            radius = stroke / 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)
    return image.resize((size, size), Image.Resampling.LANCZOS)


FAVICON_SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">
<rect width="40" height="40" rx="12" fill="{PURPLE}"/>
<path d="M12 28 28 12M18 12h10v10" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        mark(size, rounded=True).save(OUT / f"icon-{size}.png")
    mark(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon-purple-v1.png")
    mark(512, rounded=False, scale=0.8).save(OUT / "icon-maskable-512.png")
    (OUT / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    print("아이콘 생성 완료:", OUT)
