"""프로필·플랜·저축 시뮬레이션·메모리·피드백·계정 API."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_member, require_onboarded
from app.models import (
    ChatMessage,
    Feedback,
    Goal,
    Memory,
    MonthlySavingsRecord,
    Profile,
    User,
    WeeklySavingsCheck,
)
from app.services import account, feedback_hook, planner
from app.services.agent.tools import ToolContext, run_tool

router = APIRouter(prefix="/api")


class ProfileIn(BaseModel):
    age: int | None = Field(None, ge=15, le=60)
    region: str | None = Field(None, max_length=20)
    employment_type: Literal["정규직", "계약직", "프리랜서", "아르바이트", "자영업", "취업준비"] | None = None
    company_size: Literal["중소기업", "중견기업", "대기업", "공공기관"] | None = None
    monthly_income: int | None = Field(None, ge=0, le=50_000_000)
    annual_income: int | None = Field(None, ge=0, le=1_000_000_000)
    housing_type: Literal["부모님", "월세", "전세", "자가", "기타"] | None = None
    rent: int | None = Field(None, ge=0, le=5_000_000)
    fixed_costs: int | None = Field(None, ge=0, le=10_000_000)
    debt_total: int | None = Field(None, ge=0, le=10_000_000_000)
    debt_monthly: int | None = Field(None, ge=0, le=10_000_000)
    savings: int | None = Field(None, ge=0, le=10_000_000_000)
    saving_monthly: int | None = Field(None, ge=0, le=10_000_000)


@router.put("/profile")
def update_profile(payload: ProfileIn, user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user.profile, key, value)
    if user.profile.housing_type != "월세":
        user.profile.rent = 0
    db.commit()
    planner.create_plan(db, user)
    return {"ok": True}


@router.post("/plans/generate")
def generate_plan(user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    plan = planner.create_plan(db, user)
    return {"ok": True, "plan_id": plan.id}


class SimulateIn(BaseModel):
    monthly_amount: int = Field(ge=1_000, le=10_000_000)
    months: int | None = Field(None, ge=1, le=240)
    product: Literal["general", "youth_future_savings"] = "general"


@router.post("/goals/simulate")
def simulate(payload: SimulateIn, user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    result, is_error = run_tool("simulate_savings", payload.model_dump(exclude_none=True), ToolContext(db=db, user=user))
    if is_error:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class WeeklySavingsIn(BaseModel):
    week: str
    paid: bool


@router.put("/savings/weekly-check")
def save_weekly_check(
    payload: WeeklySavingsIn,
    user: User = Depends(require_onboarded),
    db: Session = Depends(get_db),
):
    if not re.fullmatch(r"\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])", payload.week):
        raise HTTPException(status_code=422, detail="Invalid week")

    year = int(payload.week[:4])
    week = int(payload.week[6:])

    try:
        from datetime import date

        date.fromisocalendar(year, week, 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid week") from None

    record = db.scalar(
        select(WeeklySavingsCheck).where(
            WeeklySavingsCheck.user_id == user.id,
            WeeklySavingsCheck.week == payload.week,
        )
    )

    if record is None:
        record = WeeklySavingsCheck(
            user_id=user.id,
            week=payload.week,
            deposited=payload.paid,
        )
        db.add(record)
    else:
        record.deposited = payload.paid

    db.commit()

    return {
        "ok": True,
        "week": record.week,
        "paid": record.deposited,
    }


class MonthlySavingsIn(BaseModel):
    month: str
    amount: int = Field(ge=0, le=10_000_000)

CHECKIN_WEEKS = 8  # 이슈 BE-04 완료 기준: 최근 8주
SAVINGS_MONTHS = 12  # 최근 12개월


def _savings_progress(db: Session, user: User) -> dict:
    """기존 보유 저축 + 월별 기록 합계를 최근 목표 금액과 비교한다."""
    profile = db.get(Profile, user.id)
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id.desc()))
    total = (profile.savings or 0) if profile else 0
    total += db.scalar(
        select(func.coalesce(func.sum(MonthlySavingsRecord.amount), 0)).where(MonthlySavingsRecord.user_id == user.id)
    )
    percentage = None
    if goal and goal.target_amount > 0:
        percentage = min(100, round(total / goal.target_amount * 100, 1))
    return {"saved_amount": total, "target_amount": goal.target_amount if goal else None, "percentage": percentage}


@router.get("/checkins")
def get_checkins(user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    records = db.scalars(
        select(WeeklySavingsCheck)
        .where(WeeklySavingsCheck.user_id == user.id)
        .order_by(WeeklySavingsCheck.week.desc())
        .limit(CHECKIN_WEEKS)
    ).all()
    return {"checkins": [{"week": r.week, "paid": r.deposited} for r in records]}


@router.get("/savings")
def get_savings(user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    records = db.scalars(
        select(MonthlySavingsRecord)
        .where(MonthlySavingsRecord.user_id == user.id)
        .order_by(MonthlySavingsRecord.month.desc())
        .limit(SAVINGS_MONTHS)
    ).all()
    return {
        "savings": [{"month": r.month, "amount": r.amount} for r in records],
        "progress": _savings_progress(db, user),
    }


@router.post("/savings/monthly")
def save_monthly_savings(
    payload: MonthlySavingsIn,
    user: User = Depends(require_onboarded),
    db: Session = Depends(get_db),
):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", payload.month):
        raise HTTPException(status_code=422, detail="Invalid month")

    record = db.scalar(
        select(MonthlySavingsRecord).where(
            MonthlySavingsRecord.user_id == user.id,
            MonthlySavingsRecord.month == payload.month,
        )
    )

    if record is None:
        record = MonthlySavingsRecord(
            user_id=user.id,
            month=payload.month,
            amount=payload.amount,
        )
        db.add(record)
    else:
        record.amount = payload.amount

    db.commit()

    return {
        "ok": True,
        "month": record.month,
        "amount": record.amount,
        "progress": _savings_progress(db, user),
    }


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(require_member), db: Session = Depends(get_db)):
    memory = db.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        raise HTTPException(status_code=404)
    db.delete(memory)
    db.commit()
    return {"ok": True}


class FeedbackIn(BaseModel):
    message_id: int
    rating: Literal[1, -1]
    comment: str | None = Field(None, max_length=500)


@router.post("/feedback")
def feedback(payload: FeedbackIn, background: BackgroundTasks, user: User = Depends(require_member),
             db: Session = Depends(get_db)):
    message = db.get(ChatMessage, payload.message_id)
    if message is None or message.user_id != user.id or message.role != "assistant":
        raise HTTPException(status_code=404)
    row = Feedback(user_id=user.id, message_id=message.id, rating=payload.rating, comment=payload.comment)
    db.add(row)
    db.commit()
    settings = get_settings()
    if payload.rating == -1 and settings.feedback_webhook_url:
        # 아쉬워요는 n8n을 거쳐 GitHub Issue가 된다 (FR-17). 응답을 기다리게 하지 않도록 뒤에서 보낸다
        background.add_task(feedback_hook.send, settings.feedback_webhook_url,
                            feedback_hook.build_payload(db, row, message), settings.internal_api_key)
    return {"ok": True}


@router.delete("/account")
def delete_account(request: Request, user: User = Depends(require_member), db: Session = Depends(get_db)):
    account.delete_account(db, user)
    request.session.clear()
    return {"ok": True, "redirect": "/"}
