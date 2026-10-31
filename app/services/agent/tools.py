"""코치 Agent가 호출하는 도구 (FR-09). 모든 숫자는 여기서 코드로 계산된다.

도구 입력은 모델이 만든 값이므로 항상 검증한 뒤 실행한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import User
from app.services import planner
from app.services.agent import memory as memory_service
from app.services.finance.budget import extra_spending_impact
from app.services.finance.money import fmt_won
from app.services.finance.savings import (
    DEFAULT_ANNUAL_RATE,
    months_to_reach,
    simulate_installment,
    simulate_youth_future_savings,
    youth_future_savings_tier,
)
from app.services.policies import eligibility, repository
from app.services.policies.search import search_policies


class ToolError(Exception):
    """모델에게 is_error로 돌려줄 입력 오류."""


@dataclass
class ToolContext:
    db: Session
    user: User
    sources: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    memories_saved: list[str] = field(default_factory=list)

    def add_source(self, policy: dict) -> None:
        for src in policy.get("sources", []):
            if not any(s["url"] == src["url"] for s in self.sources):
                self.sources.append({**src, "policy": policy["name"], "as_of": repository.as_of()})


def _int(args: dict, key: str, lo: int, hi: int, required: bool = True) -> int | None:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError(f"{key} 값이 필요합니다.")
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ToolError(f"{key}는 숫자여야 합니다.")
    value = int(value)
    if not lo <= value <= hi:
        raise ToolError(f"{key}는 {lo:,}~{hi:,} 범위여야 합니다.")
    return value


def _str(args: dict, key: str, max_len: int, choices: set[str] | None = None, required: bool = True) -> str | None:
    value = args.get(key)
    if value is None or value == "":
        if required:
            raise ToolError(f"{key} 값이 필요합니다.")
        return None
    if not isinstance(value, str) or len(value) > max_len:
        raise ToolError(f"{key}는 {max_len}자 이하 문자열이어야 합니다.")
    if choices and value not in choices:
        raise ToolError(f"{key}는 {sorted(choices)} 중 하나여야 합니다.")
    return value.strip()


def _require_profile(ctx: ToolContext):
    if ctx.user.profile is None or not ctx.user.profile.onboarding_done:
        raise ToolError("재무 프로필이 아직 없습니다. 먼저 재무 진단을 안내하세요.")
    return ctx.user.profile


# ---------------------------------------------------------------- 도구 구현

def get_my_finances(args: dict, ctx: ToolContext) -> dict:
    profile = _require_profile(ctx)
    result = planner.compute_budget(profile)
    return {
        "profile": {
            "age": profile.age, "employment_type": profile.employment_type, "company_size": profile.company_size,
            "monthly_income": profile.monthly_income, "annual_income": profile.annual_income,
            "housing_type": profile.housing_type, "rent": profile.rent, "fixed_costs": profile.fixed_costs,
            "debt_total": profile.debt_total, "debt_monthly": profile.debt_monthly, "savings": profile.savings,
            "saving_monthly": profile.saving_monthly, "region": profile.region, "goal": profile.goal_text,
        },
        "segment": {k: v for k, v in planner.compute_segment(profile, result).to_dict().items() if k != "links"},
        "monthly_plan": {a.label: a.amount for a in result.allocations},
        "monthly_plan_readable": {a.label: fmt_won(a.amount) for a in result.allocations},
        "emergency_fund": {"target": result.emergency_target, "gap": result.emergency_gap},
        "goal_feasibility": result.goal,
        "warnings": result.warnings,
        "goals": [
            {"name": g.name, "target_amount": g.target_amount, "target_months": g.target_months,
             "monthly_needed": g.monthly_needed}
            for g in ctx.user.goals[-3:]
        ],
    }


def simulate_savings(args: dict, ctx: ToolContext) -> dict:
    monthly = _int(args, "monthly_amount", 1_000, 10_000_000)
    product = _str(args, "product", 40, {"general", "youth_future_savings"}, required=False) or "general"
    rate_value = args.get("annual_rate", DEFAULT_ANNUAL_RATE)
    if isinstance(rate_value, bool) or not isinstance(rate_value, int | float) or not 0 <= rate_value <= 0.2:
        raise ToolError("annual_rate는 0~0.2 사이 소수여야 합니다 (예: 0.035).")

    if product == "youth_future_savings":
        profile = ctx.user.profile
        tier = youth_future_savings_tier(
            profile.annual_income if profile else None, profile.company_size if profile else None
        )
        result = simulate_youth_future_savings(monthly, tier, rate_value)
        policy = repository.get_policy("youth-future-savings")
        if policy:
            ctx.add_source(policy)
    else:
        months = _int(args, "months", 1, 240)
        result = simulate_installment(monthly, months, rate_value)

    data = result.to_dict()
    data["readable"] = {
        "원금": fmt_won(result.principal), "세전 이자": fmt_won(result.interest), "세금": fmt_won(result.tax),
        "정부기여금": fmt_won(result.contribution), "만기 수령액": fmt_won(result.total),
    }
    target = _int(args, "target_amount", 10_000, 10_000_000_000, required=False)
    if target:
        data["months_to_target"] = months_to_reach(target, monthly)
    return data


def check_extra_spending(args: dict, ctx: ToolContext) -> dict:
    amount = _int(args, "amount", 1_000, 100_000_000)
    profile = _require_profile(ctx)
    result = planner.compute_budget(profile)
    impact = extra_spending_impact(result, amount)
    impact["readable"] = {k: fmt_won(v) for k, v in impact.items() if isinstance(v, int) and not isinstance(v, bool)}
    impact["goal"] = result.goal
    return impact


def search_youth_policies(args: dict, ctx: ToolContext) -> dict:
    query = _str(args, "query", 200)
    profile = ctx.user.profile
    monthly = planner.goal_saving(ctx.user)
    results = []
    for policy, hits in search_policies(query, k=3):
        ctx.add_source(policy)
        item = {
            "policy_id": policy["id"], "name": policy["name"], "summary": policy["summary"],
            "evidence": [h.chunk.text[:300] for h in hits[:2]],
            "sources": [s["url"] for s in policy["sources"]], "as_of": repository.as_of(),
        }
        if profile:
            e = eligibility.evaluate(policy, profile, monthly)
            item.update({
                "status": e.status_label,
                "failed_conditions": [c.detail for c in e.failed],
                "needs_check": e.unknown,
                "estimate": e.estimate.label if e.estimate else None,
            })
        results.append(item)
    if not results:
        return {"results": [], "message": "관련 정책을 찾지 못했습니다. 공식 포털(온통청년·복지로) 확인을 안내하세요."}
    return {"results": results}


def get_policy_detail(args: dict, ctx: ToolContext) -> dict:
    ids = {p["id"] for p in repository.all_policies()}
    policy_id = _str(args, "policy_id", 60, ids)
    policy = repository.get_policy(policy_id)
    ctx.add_source(policy)
    data = {k: policy[k] for k in ("name", "agency", "summary", "benefit", "eligibility_text",
                                    "how_to_apply", "apply_period", "caution")}
    data["as_of"] = repository.as_of()
    if ctx.user.profile:
        data["my_eligibility"] = eligibility.evaluate(policy, ctx.user.profile, planner.goal_saving(ctx.user)).to_dict()
    return data


def save_memory(args: dict, ctx: ToolContext) -> dict:
    kind = _str(args, "kind", 20, set(memory_service.KINDS))
    content = _str(args, "content", 200)
    saved = memory_service.save_memory(ctx.db, ctx.user, kind, content)
    if saved:
        ctx.memories_saved.append(content)
    return {"saved": bool(saved), "content": content}


def set_goal(args: dict, ctx: ToolContext) -> dict:
    _require_profile(ctx)
    name = _str(args, "name", 50)
    target = _int(args, "target_amount", 10_000, 10_000_000_000)
    months = _int(args, "target_months", 1, 240)
    goal = planner.upsert_goal(ctx.db, ctx.user, name, target, months)
    plan = planner.create_plan(ctx.db, ctx.user)
    return {
        "goal": {"name": goal.name, "target_amount": target, "target_months": months,
                 "monthly_needed": goal.monthly_needed},
        "feasibility": plan.summary.get("goal"),
        "message": "목표를 저장하고 월급 배분 플랜을 다시 계산했습니다.",
    }


_REGISTRY: dict[str, Callable[[dict, ToolContext], dict]] = {
    "get_my_finances": get_my_finances,
    "simulate_savings": simulate_savings,
    "check_extra_spending": check_extra_spending,
    "search_youth_policies": search_youth_policies,
    "get_policy_detail": get_policy_detail,
    "save_memory": save_memory,
    "set_goal": set_goal,
}

TOOL_LABELS = {
    "get_my_finances": "내 재무 정보를 확인하고 있어요",
    "simulate_savings": "저축 결과를 계산하고 있어요",
    "check_extra_spending": "지출 영향을 계산하고 있어요",
    "search_youth_policies": "청년 정책을 찾고 있어요",
    "get_policy_detail": "정책 상세를 확인하고 있어요",
    "save_memory": "기억해두고 있어요",
    "set_goal": "목표를 저장하고 있어요",
}


def run_tool(name: str, args: object, ctx: ToolContext) -> tuple[dict, bool]:
    """도구를 실행한다. (결과, 오류 여부)를 돌려준다."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"알 수 없는 도구입니다: {name}"}, True
    if not isinstance(args, dict):
        return {"error": "INVALID_INPUT: 도구 입력은 JSON 객체여야 합니다."}, True
    try:
        result = fn(args, ctx)
    except ToolError as exc:
        return {"error": str(exc)}, True
    ctx.tools_used.append(name)
    ctx.outputs.append(result)
    return result, False


_POLICY_IDS = [p["id"] for p in repository.all_policies()]

# Claude API 도구 정의. 입력을 스트리밍하므로 run_tool에서 반드시 검증한다.
TOOL_SPECS: list[dict] = [
    {
        "name": "get_my_finances",
        "description": "사용자의 재무 프로필(소득·고정비·대출·저축·목표)과 현재 월급 배분 플랜, 비상금 목표, 목표 달성 가능성을 조회합니다. 개인 맞춤 답변 전에 먼저 호출하세요.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "simulate_savings",
        "description": "매달 같은 금액을 저축할 때 만기 수령액(원금·세전 이자·세금·정부기여금)을 계산합니다. product가 youth_future_savings이면 청년미래적금 규칙(3년, 월 50만 원 한도, 기여금, 비과세)을 적용합니다. target_amount를 주면 목표 도달까지 걸리는 개월 수도 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_amount": {"type": "integer", "description": "월 납입액(원)"},
                "months": {"type": "integer", "description": "납입 개월 수 (일반 적금일 때 필수)"},
                "product": {"type": "string", "enum": ["general", "youth_future_savings"]},
                "annual_rate": {"type": "number", "description": "연 이율 소수 (기본 0.035)"},
                "target_amount": {"type": "integer", "description": "목표 금액(원), 선택"},
            },
            "required": ["monthly_amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_extra_spending",
        "description": "이번 달 추가 지출을 할 때 목표 저축액과 목표 달성 시점에 주는 영향을 계산합니다. '이거 사도 될까?', '이번 달 더 써도 돼?' 같은 질문에 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {"amount": {"type": "integer", "description": "추가 지출 금액(원)"}},
            "required": ["amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_youth_policies",
        "description": "청년 금융·주거·세금 정책 문서를 검색하고, 사용자 프로필 기준 자격 판정과 예상 혜택을 함께 돌려줍니다. 정책·혜택·적금·청약·월세·세금 질문에는 반드시 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "검색어 또는 질문 (한국어)"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_policy_detail",
        "description": "특정 정책의 상세 정보(혜택·자격·신청 방법·기간·주의사항)와 사용자 자격 판정을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"policy_id": {"type": "string", "enum": _POLICY_IDS}},
            "required": ["policy_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_memory",
        "description": "다음 대화에서도 기억할 사용자의 약속·선호·중요한 변화를 저장합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(memory_service.KINDS)},
                "content": {"type": "string", "description": "30자 안팎의 한 문장"},
            },
            "required": ["kind", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_goal",
        "description": "사용자가 새 저축 목표를 정했을 때 저장하고 월급 배분 플랜을 다시 계산합니다. 사용자가 명확히 원할 때만 호출하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "목표 이름 (예: 전세보증금)"},
                "target_amount": {"type": "integer", "description": "목표 금액(원)"},
                "target_months": {"type": "integer", "description": "목표 기간(개월)"},
            },
            "required": ["name", "target_amount", "target_months"],
            "additionalProperties": False,
        },
    },
]

for _spec in TOOL_SPECS:
    _spec["eager_input_streaming"] = True
