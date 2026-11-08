"""FE-01 기간 설정과 명시적인 샘플 데이터. DB를 읽거나 변경하지 않는다."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def api_config(user_id: int, today: date | None = None) -> dict:
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso = today.isocalendar()
    return {
        "mode": "api", "scope": str(user_id),
        "month": f"{today.year:04d}-{today.month:02d}",
        "month_label": f"{today.year}년 {today.month}월",
        "week": f"{iso.year}-W{iso.week:02d}",
        "week_label": f"{monday.month}월 {monday.day}일 ~ {sunday.month}월 {sunday.day}일",
    }


def sample_config(user_id: int, today: date | None = None) -> dict:
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    first = today.year * 12 + today.month - 1
    months = []
    for offset, amount in zip(range(-5, 1), (40, 45, 50, 60, 60, 65), strict=True):
        year, month = divmod(first + offset, 12)
        months.append({"month": f"{year:04d}-{month + 1:02d}", "amount": amount * 10_000})
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso = today.isocalendar()
    return {
        "mode": "sample",
        "scope": str(user_id),
        "month": months[-1]["month"],
        "month_label": f"{today.year}년 {today.month}월",
        "week": f"{iso.year}-W{iso.week:02d}",
        "week_label": f"{monday.month}월 {monday.day}일 ~ {sunday.month}월 {sunday.day}일",
        "goal": {"name": "전세보증금 3천만 원 모으기", "amount": 30_000_000},
        "records": months,
    }
