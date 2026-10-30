"""가상 영수증 10장과 정답(answers.jsonl)을 만든다 (PM-07 → AI-02). Pillow 필요.

실행: python eval/receipts/make_receipts.py [--font 글꼴경로]

가게 이름, 사업자번호, 전화번호, 카드번호는 모두 지어낸 값이다. 같은 입력이면 항상 같은 이미지가 나온다.
실제 영수증보다 깔끔하므로 이 셋의 정확도는 "가상 영수증 기준"이라고 밝힌다.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent
WIDTH = 576  # 80mm 감열지를 약 7px/mm로
MARGIN = 28
FONT_CANDIDATES = [("C:/Windows/Fonts/gulim.ttc", 1), ("C:/Windows/Fonts/malgun.ttf", 0),
                   ("/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf", 0)]


def won(n: int) -> str:
    return f"{n:,}"


# 영수증 내용. items: (품목, 단가, 수량). 금액 = 단가 × 수량
RECEIPTS = [
    {"file": "r01.jpg", "merchant": "초록편의점 둔산점", "date": "2026-10-28", "time": "14:32",
     "items": [("삼각김밥 참치", 1500, 2), ("바나나우유", 1700, 1), ("컵라면 매운맛", 1450, 1)],
     "style": "clean", "note": "깨끗함"},
    {"file": "r02.jpg", "merchant": "하루커피 대흥점", "date": "2026-10-27", "time": "09:05",
     "items": [("아메리카노(R)", 4500, 2), ("크로플", 3800, 1)],
     "style": "tilted", "note": "7도 기울어짐"},
    {"file": "r03.jpg", "merchant": "마당국밥", "date": "2026-10-26", "time": "12:48",
     "items": [("순대국밥", 9000, 2), ("공기밥 추가", 1000, 1)],
     "style": "blurred", "note": "초점 흐림"},
    {"file": "r04.jpg", "merchant": "알뜰마트 유성점", "date": "2026-10-25", "time": "19:21",
     "items": [("두부 300g", 1980, 1), ("계란 15구", 6480, 1), ("양파 1.5kg", 3990, 1), ("우유 900ml", 2850, 2),
               ("식빵", 3200, 1), ("라면 5입", 4580, 1), ("세제 리필", 7900, 1), ("휴지 30롤", 15900, 1)],
     "style": "long", "note": "품목 8개, 긴 영수증"},
    {"file": "r05.jpg", "merchant": "달빛베이커리", "date": "2026-10-24", "time": "21:10",
     "items": [("소금빵", 3200, 3), ("우유식빵", 4800, 1)],
     "style": "dark", "note": "어두운 조명"},
    {"file": "r06.jpg", "merchant": "온새미분식", "date": "2026-10-23", "time": "18:40",
     "items": [("떡볶이", 5000, 1), ("모둠튀김", 4000, 1), ("김밥", 3500, 2)],
     "style": "crumpled", "note": "구겨지고 원근 왜곡"},
    {"file": "r07.jpg", "merchant": "새벽세탁", "date": "2026-10-22", "time": "08:15",
     "items": [("셔츠 세탁", 3000, 3), ("코트 드라이", 12000, 1)],
     "style": "smudged", "note": "합계와 품목 금액 하나가 얼룩으로 가려짐. 총액은 알 수 없음(null)",
     "hide_total": True},
    {"file": "r08.jpg", "merchant": "바로마켓", "date": "2026-10-21", "time": "22:03",
     "items": [("생수 2L x6", 5900, 1), ("즉석밥 12개입", 13800, 1)], "shipping": 3000,
     "style": "online", "note": "온라인 주문 화면 캡처, 배송비 포함"},
    {"file": "r09.jpg", "merchant": "그린약국", "date": "2026-10-20", "time": "17:55",
     "items": [("종합감기약", 6500, 1), ("비타민C 60정", 12000, 1), ("밴드", 2500, 1)], "discount": 1000,
     "style": "clean", "note": "할인 1,000원 적용 후 총액"},
    {"file": "r10.jpg", "merchant": "한빛한식뷔페", "date": "2026-10-19", "time": "12:20",
     "items": [("점심뷔페", 8800, 2)],
     "style": "faded", "note": "감열지 색 바램, 공급가액·부가세 따로 표시"},
]


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    candidates = [(path, 0)] if path else FONT_CANDIDATES
    for font_path, index in candidates:
        try:
            return ImageFont.truetype(font_path, size, index=index)
        except OSError:
            continue
    raise SystemExit("한글 글꼴을 찾지 못했습니다. --font 로 글꼴 파일을 지정하세요.")


def totals(r: dict) -> tuple[int, int]:
    subtotal = sum(price * qty for _, price, qty in r["items"])
    return subtotal, subtotal + r.get("shipping", 0) - r.get("discount", 0)


def draw_paper(r: dict, font: ImageFont.FreeTypeFont, big: ImageFont.FreeTypeFont) -> tuple[Image.Image, dict]:
    """영수증 종이를 그리고, 얼룩으로 가릴 위치를 돌려준다."""
    lines: list[tuple[str, object]] = []  # (종류, 값)
    if r["style"] == "online":
        lines += [("big", "주문 상세"), ("left", f"{r['merchant']} · 주문일 {r['date'].replace('-', '.')} {r['time']}"),
                  ("left", "주문번호 20261021-000417"), ("rule", None)]
    else:
        lines += [("big", r["merchant"]), ("center", "사업자 000-00-00000  대표 김가상"),
                  ("center", "대전광역시 가상구 예시로 12  042-000-0000"), ("rule", None),
                  ("left", f"[판매] {r['date']} {r['time']}"), ("rule", None),
                  ("cols", ("품명", "단가", "수량", "금액")), ("rule", None)]
    for name, price, qty in r["items"]:
        lines.append(("item", (name, price, qty)))
    lines.append(("rule", None))
    subtotal, total = totals(r)
    if r.get("shipping"):
        lines += [("pair", ("상품금액", won(subtotal))), ("pair", ("배송비", won(r["shipping"])))]
    if r.get("discount"):
        lines += [("pair", ("소계", won(subtotal))), ("pair", ("할인", f"-{won(r['discount'])}"))]
    if r["style"] == "faded":
        supply = round(total / 1.1)
        lines += [("pair", ("공급가액", won(supply))), ("pair", ("부가세", won(total - supply)))]
    lines.append(("total", ("합계" if r["style"] != "online" else "결제금액", won(total))))
    if r["style"] != "online":
        lines += [("rule", None), ("left", "신용카드  9410-12**-****-3456"), ("left", "승인번호 00000000  일시불"),
                  ("center", "감사합니다")]
    else:
        lines += [("left", "결제수단 카드 9410-12**-****-3456")]

    line_h, big_h = 34, 50
    height = MARGIN * 2 + sum(big_h if kind == "big" else line_h for kind, _ in lines)
    paper = Image.new("L", (WIDTH, height), 250)
    d = ImageDraw.Draw(paper)
    ink = 25
    y = MARGIN
    marks: dict = {}
    right = WIDTH - MARGIN
    for kind, value in lines:
        if kind == "big":
            w = big.getlength(value)
            d.text(((WIDTH - w) / 2, y), value, font=big, fill=ink)
            y += big_h
            continue
        if kind == "center":
            d.text(((WIDTH - font.getlength(value)) / 2, y), value, font=font, fill=ink)
        elif kind == "left":
            d.text((MARGIN, y), value, font=font, fill=ink)
        elif kind == "rule":
            d.text((MARGIN, y), "-" * 46, font=font, fill=ink)
        elif kind == "cols":
            name, price, qty, amount = value
            d.text((MARGIN, y), name, font=font, fill=ink)
            for text, x in ((price, 380), (qty, 440), (amount, right)):
                d.text((x - font.getlength(text), y), text, font=font, fill=ink)
        elif kind == "item":
            name, price, qty = value
            amount = won(price * qty)
            d.text((MARGIN, y), name, font=font, fill=ink)
            for text, x in ((won(price), 380), (str(qty), 440), (amount, right)):
                d.text((x - font.getlength(text), y), text, font=font, fill=ink)
            # 얼룩 위치: 단가부터 금액까지 가려서 수량으로 금액을 거꾸로 계산할 수 없게 한다
            marks.setdefault("first_amount", (380 - font.getlength(won(price)) - 6, y - 2, right + 6, y + line_h - 4))
        elif kind in ("pair", "total"):
            label, text = value
            f = big if kind == "total" else font
            d.text((MARGIN, y), label, font=f, fill=ink)
            d.text((right - f.getlength(text), y), text, font=f, fill=ink)
            if kind == "total":
                marks["total"] = (right - f.getlength(text) - 8, y - 4, right + 6, y + line_h + 6)
        y += line_h
    return paper, marks


def smudge(paper: Image.Image, box: tuple[float, float, float, float], rng: random.Random) -> None:
    d = ImageDraw.Draw(paper)
    x0, y0, x1, y1 = box
    for _ in range(14):
        cx, cy = rng.uniform(x0, x1), rng.uniform(y0, y1)
        r = rng.uniform(12, 24)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rng.randint(70, 110))
    d.rectangle(box, fill=95)


def photograph(paper: Image.Image, style: str, rng: random.Random) -> Image.Image:
    """종이를 책상 위에 놓고 찍은 사진처럼 만든다."""
    if style == "faded":
        paper = paper.point(lambda v: 250 - (250 - v) * 0.35)  # 글씨가 옅어짐
    if style == "crumpled":
        d = ImageDraw.Draw(paper)
        for _ in range(9):  # 접힌 자국
            y = rng.uniform(0, paper.height)
            d.line((0, y, paper.width, y + rng.uniform(-40, 40)), fill=rng.randint(200, 225), width=2)
    rgb = Image.merge("RGB", [paper.point(lambda v: min(255, v + 3)), paper, paper.point(lambda v: max(0, v - 6))])
    pad = 70
    canvas = Image.new("RGB", (rgb.width + pad * 2, rgb.height + pad * 2), (118, 104, 88))  # 나무 책상 색
    shadow = Image.new("L", rgb.size, 0).point(lambda _: 120)
    canvas.paste((60, 52, 44), (pad + 10, pad + 12), shadow)
    canvas = canvas.filter(ImageFilter.GaussianBlur(6))
    canvas.paste(rgb, (pad, pad))

    if style == "tilted":
        canvas = canvas.rotate(7, expand=True, fillcolor=(118, 104, 88), resample=Image.BICUBIC)
    if style == "crumpled":
        w, h = canvas.size
        coeffs = _perspective([(0, 0), (w, 0), (w, h), (0, h)],
                              [(30, 10), (w - 5, 45), (w - 40, h - 5), (10, h - 30)])
        canvas = canvas.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(118, 104, 88))
    if style == "blurred":
        canvas = canvas.filter(ImageFilter.GaussianBlur(1.6))
    if style == "dark":
        canvas = canvas.point(lambda v: int(v * 0.42))
    noise = Image.effect_noise(canvas.size, 10).convert("RGB")
    return Image.blend(canvas, noise, 0.06)


def _perspective(src, dst):
    """dst 좌표를 src 좌표로 보내는 PERSPECTIVE 변환 계수 (Pillow는 역변환 계수를 받는다)."""
    rows = []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    n = 8
    for col in range(n):  # 가우스 소거 (numpy 없이)
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                f = rows[r][col] / rows[col][col]
                rows[r] = [a - f * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def answer(r: dict) -> dict:
    hidden = r.get("hide_total")
    items = [{"name": name, "amount": price * qty} for name, price, qty in r["items"]]
    if hidden:
        items[0]["amount"] = None  # 첫 품목 금액도 얼룩으로 가려 총액을 거꾸로 계산할 수 없다
    return {"file": r["file"], "date": r["date"], "merchant": r["merchant"],
            "total": None if hidden else totals(r)[1], "items": items, "note": r["note"], "synthetic": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", help="한글 고정폭 글꼴 파일 (기본: Windows 굴림체)")
    args = parser.parse_args()
    font, big = load_font(args.font, 22), load_font(args.font, 30)
    answers = []
    for i, r in enumerate(RECEIPTS):
        rng = random.Random(1000 + i)
        paper, marks = draw_paper(r, font, big)
        if r.get("hide_total"):
            smudge(paper, marks["total"], rng)
            smudge(paper, marks["first_amount"], rng)
        photograph(paper, r["style"], rng).save(OUT / r["file"], quality=85)
        answers.append(answer(r))
    (OUT / "answers.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in answers),
                                       encoding="utf-8", newline="\n")
    print(f"영수증 {len(answers)}장과 answers.jsonl을 {OUT}에 만들었습니다.")


if __name__ == "__main__":
    main()
