"""로그인 없이 쓰는 공개 API — 랜딩의 월급 계산기."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.finance.budget import BudgetInput, calc_budget
from app.services.finance.money import fmt_won
from app.services.finance.savings import simulate_youth_future_savings

router = APIRouter(prefix="/api/public")


class QuickPlanIn(BaseModel):
    monthly_income: int = Field(ge=0, le=50_000_000)
    rent: int = Field(0, ge=0, le=5_000_000)
    fixed_costs: int = Field(0, ge=0, le=10_000_000)
    with_parents: bool = False


@router.post("/quick-plan")
def quick_plan(payload: QuickPlanIn):
    """계산 엔진만 쓰는 즉석 계산 (AI 호출 없음, 저장하지 않음)."""
    result = calc_budget(BudgetInput(
        monthly_income=payload.monthly_income, rent=payload.rent, fixed_costs=payload.fixed_costs,
        housing_type="부모님" if payload.with_parents else None,
    ))
    contribution = None
    if result.total_saving >= 10_000:
        monthly = min(result.total_saving // 1_000 * 1_000, 500_000)
        contribution = simulate_youth_future_savings(monthly, "general").contribution
    return {
        "total_saving": result.total_saving,
        "total_saving_label": fmt_won(result.total_saving),
        "savings_rate": result.savings_rate,
        "groups": [
            {"key": "fixed", "label": "꼭 나가는 돈", "amount": result.essential},
            {"key": "living", "label": "생활비", "amount": result.amount_of("living")},
            {"key": "saving", "label": "저축", "amount": result.total_saving},
        ],
        "emergency_target_label": fmt_won(result.emergency_target),
        "contribution_label": fmt_won(contribution) if contribution else None,
        "warning": result.warnings[0] if result.warnings else None,
    }
