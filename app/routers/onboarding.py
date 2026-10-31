"""재무 진단 API (FR-03) — 질문 카드 목록, 목표 문장 해석, 진단 완료."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_member
from app.models import User
from app.security import mask_sensitive
from app.services import account
from app.services.onboarding import flow, llm_extract

router = APIRouter(prefix="/api/onboarding")


@router.get("/questions")
def questions(user: User = Depends(require_member)):
    return {"questions": flow.QUESTIONS, "answers": flow.prefill(user.profile)}


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)


@router.post("/parse-goal")
def parse_goal(payload: ParseIn, user: User = Depends(require_member)):
    """목표 문장을 금액·기간으로 정리한다. 규칙으로 안 되면 경량 LLM이 해석하고, 결과는 사용자가 확인한다."""
    text, _ = mask_sensitive(payload.text.strip())
    goal = flow.parse_goal(text)
    by_ai = False
    if goal is None and not get_settings().is_mock:
        goal = llm_extract.extract_goal(text)
        by_ai = goal is not None
    if goal is None:
        return {"ok": False, "message": "금액을 찾지 못했어요. 아래에 직접 적어주세요.", "goal": {"goal_text": text[:100]}}
    return {"ok": True, "by_ai": by_ai, "goal": goal}


class AnswersIn(BaseModel):
    age: int = Field(ge=15, le=60)
    employment_type: Literal["정규직", "계약직", "프리랜서", "아르바이트", "자영업", "취업준비"]
    company_size: Literal["중소기업", "중견기업", "대기업", "공공기관"] | None = None
    monthly_income: int = Field(ge=0, le=50_000_000)
    annual_income: int | None = Field(None, ge=1_000_000, le=1_000_000_000)
    housing_type: Literal["부모님", "월세", "전세", "자가", "기타"]
    rent: int = Field(0, ge=0, le=5_000_000)
    fixed_costs: int = Field(0, ge=0, le=10_000_000)
    debt_total: int = Field(0, ge=0, le=10_000_000_000)
    debt_monthly: int = Field(0, ge=0, le=10_000_000)
    savings: int = Field(0, ge=0, le=10_000_000_000)
    saving_monthly: int = Field(0, ge=0, le=10_000_000)
    region: str | None = None
    goal_text: str | None = Field(None, max_length=100)
    goal_amount: int | None = Field(None, ge=100_000, le=10_000_000_000)
    goal_months: int | None = Field(None, ge=1, le=240)

    @field_validator("region")
    @classmethod
    def known_region(cls, v: str | None) -> str | None:
        return v if v in flow.REGIONS else None


@router.post("/complete")
def complete(payload: AnswersIn, user: User = Depends(require_member), db: Session = Depends(get_db)):
    answers = payload.model_dump()
    if answers["employment_type"] not in ("정규직", "계약직"):
        answers["company_size"] = None
    if answers["housing_type"] != "월세":
        answers["rent"] = 0
    if answers["goal_text"]:
        answers["goal_text"], _ = mask_sensitive(answers["goal_text"])
    if not (answers["goal_amount"] and answers["goal_months"]):
        answers["goal_amount"] = answers["goal_months"] = None
        answers["goal_text"] = answers["goal_text"] or None
    account.apply_profile(db, user, answers)
    return {"ok": True, "redirect": "/plan"}
