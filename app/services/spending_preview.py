"""Fictional FE-02 preview data, deliberately separate from transaction APIs and DBs."""

from datetime import datetime, timedelta, timezone

CATEGORIES = ("주거", "식비", "카페", "교통", "쇼핑", "통신", "구독", "기타")


def sample_spending(example: str = "result") -> dict:
    today = datetime.now(timezone(timedelta(hours=9))).date()
    entries = (
        (1, "월세", 500_000, "주거", True),
        (1, "모아마켓", 82_000, "식비", False),
        (1, "함께식당", 18_500, "식비", False),
        (2, "사다리 커피", 15_500, "카페", False),
        (2, "대중교통 정기권", 68_000, "교통", True),
        (2, "모아스토어", 125_000, "쇼핑", False),
        (3, "라이트통신", 39_000, "통신", True),
        (3, "플레이온", 11_900, "구독", True),
        (3, "멜로디뮤직", 8_900, "구독", True),
        (3, "동네식당", 23_000, "식비", False),
    )
    return {
        "mode": "sample", "example": example,
        "month_label": f"{today.year}년 {today.month}월",
        "categories": CATEGORIES,
        "rows": [
            {"id": index, "date": today.replace(day=min(day, today.day)).isoformat(),
             "merchant": merchant, "amount": amount, "category": category, "fixed": fixed}
            for index, (day, merchant, amount, category, fixed) in enumerate(entries, 1)
        ],
    }
