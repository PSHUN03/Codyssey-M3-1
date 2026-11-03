"""재무 프로필 → 월급 배분 플랜 생성과 조회 (FR-05, FR-06)."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models import BudgetPlan, Goal, Profile, User
from app.services.agent import llm
from app.services.agent.guardrails import collect_amounts, unverified_amounts
from app.services.agent.prompts import PLAN_EXPLAIN_SYSTEM
from app.services.finance.budget import BudgetInput, BudgetResult, calc_budget
from app.services.finance.money import fmt_won
from app.services.finance.segment import Segment, classify

log = logging.getLogger("sadari.planner")


def budget_input(profile: Profile) -> BudgetInput:
    return BudgetInput(
        monthly_income=profile.monthly_income or 0,
        rent=profile.rent or 0,
        fixed_costs=profile.fixed_costs or 0,
        debt_monthly=profile.debt_monthly or 0,
        savings=profile.savings or 0,
        housing_type=profile.housing_type,
        goal_amount=profile.goal_amount,
        goal_months=profile.goal_months,
    )


def compute_budget(profile: Profile) -> BudgetResult:
    return calc_budget(budget_input(profile))


def compute_segment(profile: Profile, result: BudgetResult) -> Segment:
    return classify(result.monthly_income, result.essential, result.total_saving, result.emergency_gap,
                    profile.saving_monthly or 0)


def plan_segment(plan: BudgetPlan | None, profile: Profile | None) -> dict | None:
    """플랜에 저장된 유형. 유형을 저장하기 전에 만든 플랜이면 플랜의 요약값으로 다시 판정한다."""
    if plan is None:
        return None
    if plan.summary.get("segment"):
        return plan.summary["segment"]
    s = plan.summary
    return classify(s["monthly_income"], s["essential"], s["total_saving"], s.get("emergency_gap", 0),
                    (profile.saving_monthly if profile else 0) or 0).to_dict()


def latest_plan(user: User) -> BudgetPlan | None:
    return user.plans[-1] if user.plans else None


def goal_saving(user: User) -> int | None:
    plan = latest_plan(user)
    if not plan:
        return None
    return next((a["amount"] for a in plan.allocations if a["key"] == "goal"), None)


def template_explanation(result: BudgetResult) -> str:
    return "\n".join(result.notes + result.warnings)


def ai_explanation(result: BudgetResult) -> str | None:
    """경량 모델이 설명을 쓰고, 계산 결과에 없는 금액이 들어가면 버린다 (수치 환각 차단)."""
    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    text = llm.text_call(PLAN_EXPLAIN_SYSTEM, f"계산 결과:\n{payload}", max_tokens=1500)
    if not text:
        return None
    unverified = unverified_amounts(text, collect_amounts(result.to_dict()))
    if unverified:
        log.warning("플랜 설명에 근거 없는 금액이 있어 템플릿으로 대체: %s", unverified)
        return None
    return text


def create_plan(db: Session, user: User) -> BudgetPlan:
    if user.profile is None:
        raise ValueError("재무 프로필이 없습니다.")
    result = compute_budget(user.profile)
    segment = compute_segment(user.profile, result)
    explanation = ai_explanation(result)
    plan = BudgetPlan(
        user_id=user.id,
        allocations=[a.__dict__ for a in result.allocations],
        summary={
            "monthly_income": result.monthly_income,
            "essential": result.essential,
            "disposable": result.disposable,
            "total_saving": result.total_saving,
            "savings_rate": result.savings_rate,
            "emergency_target": result.emergency_target,
            "emergency_gap": result.emergency_gap,
            "goal": result.goal,
            "segment": segment.to_dict(),
        },
        notes=result.notes + result.warnings,
        explanation=explanation or template_explanation(result),
        explanation_by_ai=explanation is not None,
        rule_version=result.rule_version,
    )
    db.add(plan)
    db.commit()
    db.refresh(user)
    return plan


def upsert_goal(db: Session, user: User, name: str, target_amount: int, target_months: int) -> Goal:
    goal = Goal(
        user_id=user.id, name=name[:100], target_amount=target_amount, target_months=target_months,
        monthly_needed=-(-target_amount // target_months),
    )
    db.add(goal)
    if user.profile:
        user.profile.goal_text = name[:200]
        user.profile.goal_amount = target_amount
        user.profile.goal_months = target_months
    db.commit()
    return goal


def profile_facts(profile: Profile | None) -> list[tuple[str, str]]:
    """화면·도구에 보여줄 프로필 요약 (라벨, 값)."""
    if profile is None:
        return []
    housing = profile.housing_type or "-"
    if profile.housing_type == "월세" and profile.rent:
        housing += f" ({fmt_won(profile.rent)})"
    job = " ".join(filter(None, [profile.company_size, profile.employment_type])) or "-"
    return [
        ("나이", f"만 {profile.age}세" if profile.age else "-"),
        ("일하는 형태", job),
        ("월 실수령액", fmt_won(profile.monthly_income)),
        ("연봉(세전)", fmt_won(profile.annual_income) if profile.annual_income else "모름"),
        ("주거", housing),
        ("고정비", fmt_won(profile.fixed_costs)),
        ("대출", f"{fmt_won(profile.debt_total)} (월 {fmt_won(profile.debt_monthly)} 상환)" if profile.debt_total else "없음"),
        ("모아둔 돈", fmt_won(profile.savings)),
        ("매달 저축", fmt_won(profile.saving_monthly) if profile.saving_monthly else "없음"),
        ("지역", profile.region or "-"),
        ("목표", profile.goal_text or "-"),
    ]
