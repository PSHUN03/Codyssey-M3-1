"""월급 배분 계산 (FR-05). 같은 입력이면 항상 같은 결과가 나오는 결정론적 규칙."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from app.services.finance.money import floor_to, fmt_won
from app.services.text import josa

RULE_VERSION = "v1"

# 사다리 배분 규칙 v1 — 팀 검토 후 조정한다 (docs/adr/0005 참고)
SAVINGS_RATIO_WITH_PARENTS = 0.60  # 부모님과 살면 주거비 부담이 적어 저축 비중을 높인다
SAVINGS_RATIO_DEFAULT = 0.45
EMERGENCY_MONTHS = 3  # 비상금 목표 = 필수지출+생활비 3개월치
EMERGENCY_SHARE = 0.30  # 비상금이 부족하면 저축액의 30%를 비상금으로 먼저 채운다


@dataclass
class BudgetInput:
    monthly_income: int
    rent: int = 0
    fixed_costs: int = 0
    debt_monthly: int = 0
    savings: int = 0
    housing_type: str | None = None
    goal_amount: int | None = None
    goal_months: int | None = None


@dataclass
class Allocation:
    key: str
    label: str
    amount: int
    ratio: float
    kind: str  # fixed | living | saving


@dataclass
class BudgetResult:
    allocations: list[Allocation]
    monthly_income: int
    essential: int
    disposable: int
    total_saving: int
    savings_rate: float
    emergency_target: int
    emergency_gap: int
    goal: dict | None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    def amount_of(self, key: str) -> int:
        return next((a.amount for a in self.allocations if a.key == key), 0)


def calc_budget(inp: BudgetInput) -> BudgetResult:
    income = max(int(inp.monthly_income or 0), 0)
    rent, fixed, debt = (max(int(v or 0), 0) for v in (inp.rent, inp.fixed_costs, inp.debt_monthly))
    essential = rent + fixed + debt
    disposable = income - essential
    notes: list[str] = []
    warnings: list[str] = []

    if disposable <= 0:
        warnings.append(
            f"매달 꼭 나가는 돈({fmt_won(essential)})이 실수령액({fmt_won(income)})보다 많아요. "
            "저축보다 고정 지출을 줄이는 게 먼저예요."
        )
        allocations = _allocations(income, rent, fixed, debt, living=max(disposable, 0), emergency=0, goal=0)
        return BudgetResult(
            allocations=allocations, monthly_income=income, essential=essential, disposable=disposable,
            total_saving=0, savings_rate=0.0, emergency_target=0, emergency_gap=0, goal=None,
            notes=notes, warnings=warnings,
        )

    with_parents = inp.housing_type == "부모님"
    ratio = SAVINGS_RATIO_WITH_PARENTS if with_parents else SAVINGS_RATIO_DEFAULT
    total_saving = floor_to(disposable * ratio)
    living = disposable - total_saving
    notes.append(f"꼭 나가는 돈 {fmt_won(essential)}을 빼면 쓸 수 있는 돈은 {fmt_won(disposable)}이에요.")
    if with_parents:
        notes.append(f"부모님 집에 살아 주거비 부담이 적으니 그중 {int(ratio * 100)}%인 "
                     f"{josa(fmt_won(total_saving), '을/를')} 저축으로 잡았어요.")
    else:
        notes.append(f"혼자 사는 생활비를 고려해 그중 {int(ratio * 100)}%인 "
                     f"{josa(fmt_won(total_saving), '을/를')} 저축으로 잡았어요.")

    emergency_target = EMERGENCY_MONTHS * (essential + living)
    emergency_gap = max(emergency_target - max(int(inp.savings or 0), 0), 0)
    emergency = min(emergency_gap, floor_to(total_saving * EMERGENCY_SHARE)) if emergency_gap else 0
    goal_saving = total_saving - emergency
    if emergency:
        notes.append(f"비상금은 {EMERGENCY_MONTHS}개월 생활비인 {fmt_won(emergency_target)}이 목표예요. "
                     f"{fmt_won(emergency_gap)}이 모자라서 매달 {josa(fmt_won(emergency), '을/를')} 먼저 채워요.")
    else:
        notes.append(f"비상금 {fmt_won(emergency_target)}은 이미 충분해서 저축은 모두 목표에 써요.")

    goal = _goal_feasibility(inp.goal_amount, inp.goal_months, goal_saving)
    if goal and not goal["feasible"]:
        warnings.append(
            f"목표({fmt_won(goal['target_amount'])}, {goal['target_months']}개월)를 이루려면 매달 "
            f"{fmt_won(goal['monthly_needed'])}이 필요한데 지금 계획은 {fmt_won(goal_saving)}이에요. "
            f"이 속도면 {goal['months_needed']}개월이 걸려요."
        )

    return BudgetResult(
        allocations=_allocations(income, rent, fixed, debt, living, emergency, goal_saving),
        monthly_income=income, essential=essential, disposable=disposable, total_saving=total_saving,
        savings_rate=round(total_saving / income, 3) if income else 0.0,
        emergency_target=emergency_target, emergency_gap=emergency_gap, goal=goal,
        notes=notes, warnings=warnings,
    )


def _goal_feasibility(target: int | None, months: int | None, monthly: int) -> dict | None:
    if not target or not months:
        return None
    needed = math.ceil(target / months)
    return {
        "target_amount": target,
        "target_months": months,
        "monthly_needed": needed,
        "monthly_planned": monthly,
        "feasible": monthly >= needed,
        "months_needed": math.ceil(target / monthly) if monthly > 0 else None,
    }


def _allocations(income: int, rent: int, fixed: int, debt: int, living: int, emergency: int, goal: int) -> list[Allocation]:
    rows = [
        ("rent", "월세", rent, "fixed"),
        ("fixed_costs", "고정비", fixed, "fixed"),
        ("debt", "대출 상환", debt, "fixed"),
        ("living", "생활비", living, "living"),
        ("emergency", "비상금", emergency, "saving"),
        ("goal", "목표 저축", goal, "saving"),
    ]
    return [
        Allocation(key, label, amount, round(amount / income, 3) if income else 0.0, kind)
        for key, label, amount, kind in rows
        if amount > 0 or key in ("living", "goal")
    ]


def extra_spending_impact(result: BudgetResult, amount: int) -> dict:
    """이번 달 추가 지출을 목표 저축에서 뺀다고 가정했을 때의 영향 (코치의 '써도 될까?' 질문용)."""
    goal_saving = result.amount_of("goal")
    living = result.amount_of("living")
    after = goal_saving - amount
    impact: dict = {
        "extra_amount": amount,
        "living_budget": living,
        "goal_saving_before": goal_saving,
        "goal_saving_after": max(after, 0),
        "exceeds_goal_saving": after < 0,
    }
    goal = result.goal
    if goal and goal_saving > 0:
        impact["delay_months"] = round(amount / goal_saving, 1)
    return impact
