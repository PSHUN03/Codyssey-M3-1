"""PWA 아이콘과 파비콘 생성 (Pillow 필요). 실행: python scripts/make_icons.py

로고: 위로 갈수록 길어지는 가로대 세 칸. 늘어나는 자산을 뜻하고, 맨 위 칸이 다음 목표다.
40×40 격자 기준 좌표를 쓰며 app/templates/_macros.html의 logo_mark와 같은 모양이다.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "app" / "static" / "icons"
INK = (14, 15, 12)
SAGE = (232, 235, 230)
LIME = (159, 232, 112)
INK_DEEP = (22, 51, 0)

# (x, y, 너비) — 높이 5, 모서리 2.5
BARS = [(10, 26, 10), (10, 17.5, 15), (10, 9, 20)]


def mark(size: int, background, bars, *, rounded: bool, scale: float = 1.0) -> Image.Image:
    """scale < 1이면 가로대를 가운데로 모아 마스커블 아이콘의 안전 영역 안에 넣는다."""
    ss = 4  # 슈퍼샘플링으로 가장자리를 부드럽게
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    unit = big / 40
    if rounded:
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(11 * unit), fill=background)
    else:
        draw.rectangle([0, 0, big, big], fill=background)
    offset = big * (1 - scale) / 2
    for (x, y, w), color in zip(BARS, bars, strict=True):
        x0, y0 = offset + x * unit * scale, offset + y * unit * scale
        x1, y1 = x0 + w * unit * scale, y0 + 5 * unit * scale
        draw.rounded_rectangle([x0, y0, x1, y1], radius=2.5 * unit * scale, fill=color)
    return img.resize((size, size), Image.LANCZOS)


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">
<rect width="40" height="40" rx="11" fill="#0e0f0c"/>
<rect x="10" y="26" width="10" height="5" rx="2.5" fill="#e8ebe6"/>
<rect x="10" y="17.5" width="15" height="5" rx="2.5" fill="#e8ebe6"/>
<rect x="10" y="9" width="20" height="5" rx="2.5" fill="#9fe870"/>
</svg>
"""

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    app_bars = [INK_DEEP, INK_DEEP, INK_DEEP]
    mark(192, LIME, app_bars, rounded=True).save(OUT / "icon-192.png")
    mark(512, LIME, app_bars, rounded=True).save(OUT / "icon-512.png")
    mark(512, LIME, app_bars, rounded=False, scale=0.8).save(OUT / "icon-maskable-512.png")
    (OUT / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    print("아이콘 생성 완료:", OUT)
