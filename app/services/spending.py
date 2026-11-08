"""거래내역 저장과 소비 분석 (BE-01, FR-13·14).

- 저장: DATA-06의 변환 결과(가린 가맹점명, 금액, 분류)만 저장하고 원본 파일은 저장하지 않는다.
  같은 날짜·금액·가맹점 거래는 한 번만 저장한다.
- 요약: 월별 카테고리 합계, 고정비 추정, 구독 후보, 저축 여력. 금액은 모두 이 모듈이 계산한다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction, User

FIXED_CATEGORIES = {"주거", "통신"}
_SUBSCRIPTION_RE = re.compile(
    r"넷플릭스|netflix|유튜브|youtube|멜론|스포티파이|spotify|디즈니|티빙|웨이브|왓챠|쿠팡\s*와우|구독|정기결제|애플\s*뮤직|icloud",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _month(d: date) -> str:
    return d.strftime("%Y-%m")


def save_transactions(db: Session, user: User, items: list[dict], source: str = "upload") -> dict:
    """변환된 거래를 저장한다. 이미 있는 거래(같은 날짜·금액·가맹점)는 건너뛴다."""
    existing = {(t.date, t.amount, t.merchant) for t in user.transactions}
    saved = skipped = 0
    for item in items:
        key = (date.fromisoformat(item["date"]), int(item["amount"]), str(item["merchant"])[:200])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        category = item.get("category") or "기타"
        is_fixed = key[1] < 0 and (category in FIXED_CATEGORIES or bool(_SUBSCRIPTION_RE.search(key[2])))
        db.add(Transaction(user_id=user.id, date=key[0], amount=key[1], merchant=key[2], category=category,
                           is_fixed=is_fixed, source=source))
        saved += 1
    db.commit()
    db.refresh(user)
    return {"saved": saved, "skipped": skipped}


def latest_month(db: Session, user: User) -> str | None:
    latest = db.scalar(select(Transaction.date).where(Transaction.user_id == user.id).order_by(Transaction.date.desc()))
    return _month(latest) if latest else None


def _subscription_candidates(transactions: list[Transaction], month: str) -> list[dict]:
    """같은 가맹점에서 같은 금액이 서로 다른 두 달 이상 나간 지출, 또는 구독 서비스 이름이 든 지출."""
    months_by_key: dict[tuple[str, int], set[str]] = defaultdict(set)
    for t in transactions:
        if t.amount < 0:
            months_by_key[(t.merchant, t.amount)].add(_month(t.date))
    found = []
    for (merchant, amount), months in months_by_key.items():
        if month not in months:
            continue
        if len(months) >= 2 or _SUBSCRIPTION_RE.search(merchant):
            found.append({"merchant": merchant, "monthly_amount": -amount, "months_seen": len(months)})
    return sorted(found, key=lambda s: -s["monthly_amount"])


def summary(db: Session, user: User, month: str | None = None) -> dict:
    month = month or latest_month(db, user)
    if month is None:
        return {"month": None, "has_data": False, "message": "아직 저장한 거래내역이 없어요."}
    if not _MONTH_RE.match(month):
        raise ValueError("month는 YYYY-MM 형식이어야 합니다.")
    all_rows = list(user.transactions)
    rows = [t for t in all_rows if _month(t.date) == month]
    expenses = [t for t in rows if t.amount < 0]
    income = sum(t.amount for t in rows if t.amount > 0)
    by_category: dict[str, int] = defaultdict(int)
    for t in expenses:
        by_category[t.category] += -t.amount
    total_spent = sum(by_category.values())
    subscriptions = _subscription_candidates(all_rows, month)
    subscription_keys = {(s["merchant"], -s["monthly_amount"]) for s in subscriptions}
    fixed = sum(-t.amount for t in expenses if t.is_fixed or (t.merchant, t.amount) in subscription_keys)
    profile_income = user.profile.monthly_income if user.profile and user.profile.monthly_income else None
    basis_income = income or profile_income or 0
    return {
        "month": month,
        "has_data": bool(rows),
        "transaction_count": len(rows),
        "income": income,
        "total_spent": total_spent,
        "by_category": [
            {"category": c, "amount": a, "share": round(a / total_spent, 3) if total_spent else 0}
            for c, a in sorted(by_category.items(), key=lambda kv: -kv[1])
        ],
        "fixed_estimate": fixed,
        "variable_spent": total_spent - fixed,
        "subscriptions": subscriptions,
        "top_expenses": [
            {"date": t.date.isoformat(), "merchant": t.merchant, "amount": -t.amount, "category": t.category}
            for t in sorted(expenses, key=lambda t: t.amount)[:5]
        ],
        "saving_capacity": basis_income - total_spent if basis_income else None,
        "income_basis": "거래내역 입금" if income else ("재무 프로필 실수령액" if profile_income else None),
    }
