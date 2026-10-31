"""적금·정책금융상품 만기액 시뮬레이션 (FR-06)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

INTEREST_TAX_RATE = 0.154  # 이자소득세 14% + 지방소득세 1.4%
DEFAULT_ANNUAL_RATE = 0.035  # 가정 금리. 은행·상품마다 다르므로 화면에 '가정'이라고 표시한다

# 청년미래적금 규칙 (출처·기준일: app/data/policies.json의 youth-future-savings)
YOUTH_FUTURE_SAVINGS = {
    "months": 36,
    "monthly_max": 500_000,
    "tiers": {
        "preferential": {"label": "우대형", "rate": 0.12, "monthly_cap": 60_000},
        "general": {"label": "일반형", "rate": 0.06, "monthly_cap": 30_000},
        "tax_free": {"label": "비과세형", "rate": 0.0, "monthly_cap": 0},
    },
}


@dataclass
class SavingsResult:
    monthly: int
    months: int
    annual_rate: float
    principal: int
    interest: int
    tax: int
    contribution: int
    total: int
    tax_free: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_installment(
    monthly: int,
    months: int,
    annual_rate: float = DEFAULT_ANNUAL_RATE,
    *,
    tax_free: bool = False,
    contribution_rate: float = 0.0,
    contribution_monthly_cap: int | None = None,
) -> SavingsResult:
    """정기적금(매월 같은 금액 납입, 단리) 만기액을 계산한다.

    이자 = 월납입액 × 연이율 × (n(n+1)/2) / 12. 정부기여금의 이자는 보수적으로 제외한다.
    """
    if monthly <= 0 or months <= 0:
        raise ValueError("월 납입액과 기간은 0보다 커야 합니다.")
    principal = monthly * months
    interest = math.floor(monthly * annual_rate * (months * (months + 1) / 2) / 12)
    tax = 0 if tax_free else math.floor(interest * INTEREST_TAX_RATE)
    per_month = monthly * contribution_rate
    if contribution_monthly_cap is not None:
        per_month = min(per_month, contribution_monthly_cap)
    contribution = math.floor(per_month) * months
    notes = [f"연 {annual_rate * 100:.1f}% 단리를 가정한 계산이에요. 실제 금리는 은행·우대조건마다 달라요."]
    if tax_free:
        notes.append("이자소득세가 면제되는 상품으로 계산했어요.")
    if contribution:
        notes.append("정부기여금에 붙는 이자는 계산에서 뺐어요(보수적 계산).")
    return SavingsResult(
        monthly=monthly, months=months, annual_rate=annual_rate, principal=principal, interest=interest,
        tax=tax, contribution=contribution, total=principal + interest - tax + contribution,
        tax_free=tax_free, notes=notes,
    )


def youth_future_savings_tier(annual_income: int | None, company_size: str | None) -> str | None:
    """총급여와 재직 기업 규모로 청년미래적금 유형을 추정한다. 가구소득 요건은 별도 확인이 필요하다."""
    if annual_income is None:
        return None
    if annual_income <= 36_000_000 and company_size == "중소기업":
        return "preferential"
    if annual_income <= 60_000_000:
        return "general"
    if annual_income <= 75_000_000:
        return "tax_free"
    return None  # 가입 대상 아님


def simulate_youth_future_savings(
    monthly: int, tier: str | None, annual_rate: float = DEFAULT_ANNUAL_RATE
) -> SavingsResult:
    rules = YOUTH_FUTURE_SAVINGS
    tier_key = tier or "general"
    tier_rule = rules["tiers"][tier_key]
    capped = min(monthly, rules["monthly_max"])
    result = simulate_installment(
        capped, rules["months"], annual_rate, tax_free=True,
        contribution_rate=tier_rule["rate"], contribution_monthly_cap=tier_rule["monthly_cap"],
    )
    result.notes.insert(0, f"청년미래적금 {tier_rule['label']} 기준(3년, 월 최대 50만 원)으로 계산했어요.")
    if tier is None:
        result.notes.insert(1, "소득 정보가 부족해 일반형으로 가정했어요.")
    if monthly > rules["monthly_max"]:
        result.notes.append("월 납입 한도(50만 원)를 넘는 금액은 제외했어요.")
    return result


def months_to_reach(target: int, monthly: int, current: int = 0) -> int | None:
    if monthly <= 0:
        return None
    return max(math.ceil((target - current) / monthly), 0)
