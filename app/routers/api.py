"""프로필·플랜·저축 시뮬레이션·메모리·피드백·계정 API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member, require_onboarded
from app.models import ChatMessage, Feedback, Memory, User
from app.services import account, planner
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
def feedback(payload: FeedbackIn, user: User = Depends(require_member), db: Session = Depends(get_db)):
    message = db.get(ChatMessage, payload.message_id)
    if message is None or message.user_id != user.id or message.role != "assistant":
        raise HTTPException(status_code=404)
    db.add(Feedback(user_id=user.id, message_id=message.id, rating=payload.rating, comment=payload.comment))
    db.commit()
    # TODO(FR-17): n8n 웹훅으로 전달해 GitHub Issue를 자동 생성한다 — docs/tasks/01_PM.md 참고
    return {"ok": True}


@router.delete("/account")
def delete_account(request: Request, user: User = Depends(require_member), db: Session = Depends(get_db)):
    account.delete_account(db, user)
    request.session.clear()
    return {"ok": True, "redirect": "/"}
