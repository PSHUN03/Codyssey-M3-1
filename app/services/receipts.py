"""영수증 인식 (AI-02, FR-19). 사진은 저장하지 않고, 인식 결과만 돌려준다.

- 이미지: JPEG·PNG, 5MB 이하. 파일 앞부분의 시그니처로 형식을 확인한다.
- 추출: 경량 모델 Vision + JSON 스키마(날짜·가맹점·합계·품목). 읽지 못한 값은 null로 두고 추측하지 않는다.
- 추측 방지: 모델이 프롬프트를 어기고 가려진 합계를 채우는 경우가 있어(r07) 서버에서 한 번 더 거른다.
  합계 줄을 또렷이 읽지 못했다고 답했거나, 금액을 못 읽은 품목이 있는데 합계가 읽은 품목 금액의 합과 같으면 null.
- 개인정보: 결과의 카드번호·전화번호 등은 돌려주기 전에 가린다 (일부가 *로 찍힌 카드번호 포함).
- 모의 모드: 사진과 무관한 고정 예시 결과를 돌려주고 source="sample"로 표시한다.
"""

from __future__ import annotations

import base64
import re
from datetime import date

from app.security import mask_sensitive

MAX_BYTES = 5 * 1024 * 1024
MEDIA_TYPES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
MAX_ITEMS = 30

# 영수증에는 "9410-12**-****-3456"처럼 일부가 *로 찍힌 카드번호가 많다
_PARTIAL_CARD_RE = re.compile(r"\d{4}[- ]?[\d*]{2,4}[- ]?[\d*]{4}[- ]?[\d*]{3,4}")

VISION_SYSTEM = """당신은 한국 영수증 사진에서 정보를 읽는 도우미입니다.
- date: 결제 날짜를 YYYY-MM-DD로. 연도가 없거나 읽을 수 없으면 null
- merchant_name: 가게 이름. 지점명이 있으면 함께. 읽을 수 없으면 null
- total_amount: 실제로 결제한 최종 합계(할인·배송비 반영 후). 공급가액·부가세·소계가 아니라 결제 금액을 고르세요. 가려졌거나 읽을 수 없으면 null이며, 품목 금액을 더해 추측하지 마세요
- total_visible: 합계 금액 줄의 숫자를 사진에서 직접, 또렷하게 모두 읽었으면 true. 얼룩·가림·잘림·흐림으로 일부라도 안 보이면 false
- items: 품목 이름과 금액(수량이 있으면 수량을 반영한 금액). 읽을 수 없는 금액은 null
금액은 원 단위 정수입니다. 카드번호, 전화번호, 사업자번호는 결과에 넣지 마세요."""

_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "amount": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "required": ["name", "amount"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "merchant_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "total_amount": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "total_visible": {"type": "boolean"},
        "items": {"type": "array", "items": _ITEM},
    },
    "required": ["date", "merchant_name", "total_amount", "total_visible", "items"],
    "additionalProperties": False,
}

SAMPLE_RESULT = {
    "date": "2026-10-28",
    "merchant_name": "예시 편의점",
    "total_amount": 6150,
    "items": [{"name": "삼각김밥", "amount": 3000}, {"name": "바나나우유", "amount": 1700},
              {"name": "컵라면", "amount": 1450}],
}


class ReceiptError(ValueError):
    pass


def detect_media_type(content: bytes) -> str:
    if not content:
        raise ReceiptError("사진을 선택해 주세요.")
    if len(content) > MAX_BYTES:
        raise ReceiptError("사진은 5MB 이하만 올릴 수 있어요.")
    for signature, media_type in MEDIA_TYPES.items():
        if content.startswith(signature):
            return media_type
    raise ReceiptError("JPG나 PNG 사진만 올릴 수 있어요.")


def _mask(text: str | None) -> tuple[str | None, list[str]]:
    if text is None:
        return None, []
    masked, kinds = mask_sensitive(text)
    if _PARTIAL_CARD_RE.search(masked):
        masked = _PARTIAL_CARD_RE.sub("[카드번호 가림]", masked)
        kinds = [*kinds, "카드번호"] if "카드번호" not in kinds else kinds
    return masked.strip()[:100] or None, kinds


def _valid_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _valid_amount(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= 100_000_000 else None


def _checked_total(raw: dict, items: list[dict]) -> int | None:
    """보이지 않는 합계를 지어낸 흔적이 있으면 null로 둔다."""
    total = _valid_amount(raw.get("total_amount"))
    if total is None or raw.get("total_visible") is False:
        return None
    known = [item["amount"] for item in items if item["amount"] is not None]
    if known and len(known) < len(items) and total == sum(known):
        return None  # 금액을 못 읽은 품목이 있는데 합계가 읽은 품목만의 합과 같다 = 더해서 추측한 값
    return total


def normalize(raw: dict, source: str) -> dict:
    """모델 결과를 화면 계약(date, merchant_name, total_amount, currency)에 맞추고 개인정보를 가린다."""
    masked_kinds: list[str] = []
    merchant, kinds = _mask(raw.get("merchant_name") if isinstance(raw.get("merchant_name"), str) else None)
    masked_kinds += kinds
    items = []
    for item in (raw.get("items") or [])[:MAX_ITEMS]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name, kinds = _mask(item["name"])
        masked_kinds += kinds
        if name:
            items.append({"name": name, "amount": _valid_amount(item.get("amount"))})
    return {
        "date": _valid_date(raw.get("date")),
        "merchant_name": merchant,
        "total_amount": _checked_total(raw, items),
        "currency": "KRW",
        "items": items,
        "source": source,
        "masked": sorted(set(masked_kinds)),
    }


def scan(content: bytes, vision_call=None) -> dict:
    """영수증 사진을 읽는다. vision_call이 없으면(모의 모드) 고정 예시를 돌려준다."""
    media_type = detect_media_type(content)
    if vision_call is None:
        return normalize(SAMPLE_RESULT, source="sample")
    data = vision_call(VISION_SYSTEM, base64.b64encode(content).decode(), media_type, SCHEMA)
    if data is None:
        raise ReceiptError("영수증을 읽지 못했어요. 밝은 곳에서 다시 찍거나 직접 입력해 주세요.")
    return normalize(data, source="ai")
