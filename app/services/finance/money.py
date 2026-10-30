"""한국어 금액·기간 표현 파싱과 표시 형식."""

from __future__ import annotations

import re

_UNITS = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000, "십만": 100_000, "만": 10_000, "천": 1_000}
_RANK = {"억": 4, "천만": 3, "백만": 3, "십만": 3, "만": 3, "천": 2, None: 1}

# 숫자 + (단위) + (원). 단위는 긴 것부터 매칭되도록 나열한다.
_AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|십만|만|천)?(\s*원)?")
# 숫자 없이 쓰는 표현 ("천만 원", "백만원")
_WORD_AMOUNT_RE = re.compile(r"(?<![\d가-힣])(천만|백만|십만)\s*원?")
# 금액이 아닌 숫자 뒤에 오는 말
_NOT_MONEY_SUFFIX = ("년", "개월", "달", "살", "세", "%", "퍼", "명", "회", "번", "시", "일", "주", "월", "배", "위", "등", "차")


def find_amounts(text: str, assume_manwon: bool = False) -> list[int]:
    """문장에서 금액(원)을 순서대로 찾는다.

    - "245만 원", "2,450,000원", "3천만", "1억 2천만", "138만 7,500원"을 모두 인식한다.
    - assume_manwon=True이면 단위 없는 작은 숫자("250")를 만 원 단위로 본다(설문 응답용).
    """
    amounts: list[int] = []
    current: float | None = None
    current_rank = 0
    last_end = -1
    current_closed = False  # "원"으로 끝나면 금액이 완결된 것으로 본다

    for m in _AMOUNT_RE.finditer(text):
        raw, unit, won = m.group(1), m.group(2), m.group(3)
        tail = text[m.end():].lstrip()
        if unit is None and not won and tail.startswith(_NOT_MONEY_SUFFIX):
            continue  # "2년", "27살", "5%" 등은 금액이 아니다
        value = float(raw.replace(",", ""))
        gap = text[last_end:m.start()] if last_end >= 0 else None

        chained = (
            current is not None
            and not current_closed
            and gap is not None
            and gap.strip() == ""
            and current_rank > _RANK[unit]
        )
        if chained and current_rank == 4 and unit in (None, "천"):
            # "1억 2천" / "1억 5000"은 관용적으로 만 원 단위를 뜻한다
            value *= 1_000 if unit == "천" else 1
            unit = "만"

        if unit:
            amount = value * _UNITS[unit]
        elif won or not assume_manwon or value >= 100_000:
            amount = value
        else:
            amount = value * 10_000

        if chained:
            current = (current or 0) + amount
        else:
            if current is not None:
                amounts.append(round(current))
            current = amount
        current_rank = _RANK[unit]
        current_closed = bool(won)
        last_end = m.end()

    if current is not None:
        amounts.append(round(current))

    if not amounts:
        amounts = [_UNITS[m.group(1)] for m in _WORD_AMOUNT_RE.finditer(text)]
    return amounts


def parse_amount(text: str, assume_manwon: bool = True) -> int | None:
    found = find_amounts(text, assume_manwon=assume_manwon)
    return found[0] if found else None


def find_duration_months(text: str) -> int | None:
    """ "2년" → 24, "18개월" → 18, "1년 6개월" → 18, "1년 반" → 18, "6달" → 6."""
    years = re.search(r"(\d+(?:\.\d+)?)\s*년(\s*반)?", text)
    months = re.search(r"(\d+)\s*(?:개월|달)", text)
    if not years and not months:
        return None
    total = 0.0
    if years:
        total += float(years.group(1)) * 12 + (6 if years.group(2) else 0)
    if months:
        total += int(months.group(1))
    return round(total) or None


def is_negative_answer(text: str) -> bool:
    return bool(re.search(r"없(어|음|습|다|는)|없$|0원|^0$|아니(요|오)|해당\s*없", text.strip()))


def is_unknown_answer(text: str) -> bool:
    return bool(re.search(r"모르|모름|몰라|잘\s*모|기억\s*안|패스|건너", text))


def fmt_won(n: int | float | None) -> str:
    """읽기 쉬운 금액 표기: 2450000 → '245만 원', 1387500 → '138만 7,500원'."""
    if n is None:
        return "-"
    n = int(round(n))
    sign = "-" if n < 0 else ""
    n = abs(n)
    eok, rest = divmod(n, 100_000_000)
    man, won = divmod(rest, 10_000)
    parts = []
    if eok:
        parts.append(f"{eok:,}억")
    if man:
        parts.append(f"{man:,}만")
    if won:
        parts.append(f"{won:,}")
    if not parts:
        return "0원"
    return sign + " ".join(parts) + ("원" if won else " 원")


def floor_to(n: float, unit: int = 10_000) -> int:
    return int(n // unit * unit)
