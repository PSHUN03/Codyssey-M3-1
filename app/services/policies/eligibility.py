"""정책 자격 판정 (FR-07). 자격 여부는 LLM이 아니라 이 규칙 코드가 판단한다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from app.services.finance.money import fmt_won
from app.services.finance.savings import (
    YOUTH_FUTURE_SAVINGS,
    simulate_youth_future_savings,
    youth_future_savings_tier,
)
from app.services.policies import repository

KST = timezone(timedelta(hours=9))

STATUS_LABELS = {
    "eligible": "받을 수 있어요",
    "check": "조건 확인 필요",
    "closed": "지금은 신청 불가",
    "ineligible": "해당 없음",
}
STATUS_ORDER = {"eligible": 0, "check": 1, "closed": 2, "ineligible": 3}
EMPLOYED_TYPES = {"정규직", "계약직", "프리랜서", "아르바이트", "자영업"}


class ProfileLike(Protocol):
    age: int | None
    employment_type: str | None
    company_size: str | None
    annual_income: int | None
    housing_type: str | None
    rent: int | None


@dataclass
class Check:
    label: str
    ok: bool | None  # None = 정보 부족으로 판단 보류
    detail: str


@dataclass
class Estimate:
    amount: int | None
    label: str


@dataclass
class Eligibility:
    policy_id: str
    name: str
    status: str
    status_label: str
    checks: list[Check] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    estimate: Estimate | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.ok is False]


def today_kst() -> date:
    return datetime.now(KST).date()


def _employed(profile: ProfileLike) -> bool | None:
    if profile.employment_type is None:
        return None
    return profile.employment_type in EMPLOYED_TYPES


def _checks(rules: dict, profile: ProfileLike) -> list[Check]:
    checks: list[Check] = []
    if "age_min" in rules or "age_max" in rules:
        lo, hi = rules.get("age_min", 0), rules.get("age_max", 200)
        if profile.age is None:
            checks.append(Check("나이", None, f"만 {lo}~{hi}세 대상이에요. 나이를 알려주시면 확인할게요."))
        else:
            checks.append(Check("나이", lo <= profile.age <= hi, f"만 {lo}~{hi}세 대상 (현재 만 {profile.age}세)"))
    if "annual_income_max" in rules:
        cap = rules["annual_income_max"]
        if profile.annual_income is None:
            checks.append(Check("소득", None, f"총급여 {fmt_won(cap)} 이하 대상이에요. 연봉 정보가 필요해요."))
        else:
            checks.append(Check("소득", profile.annual_income <= cap,
                                f"총급여 {fmt_won(cap)} 이하 대상 (입력 연봉 {fmt_won(profile.annual_income)})"))
    if rules.get("homeless"):
        if profile.housing_type is None:
            checks.append(Check("무주택", None, "무주택 청년 대상이에요."))
        else:
            checks.append(Check("무주택", profile.housing_type != "자가", "무주택 청년 대상"))
    if rules.get("separate_from_parents"):
        if profile.housing_type is None:
            checks.append(Check("독립 거주", None, "부모와 따로 사는 청년 대상이에요."))
        else:
            checks.append(Check("독립 거주", profile.housing_type != "부모님", "부모와 따로 사는 청년 대상"))
    if rules.get("rent_required"):
        paying = profile.housing_type == "월세" and (profile.rent or 0) > 0
        known = profile.housing_type is not None
        checks.append(Check("월세 납부", paying if known else None, "월세를 내고 있어야 해요"))
    if "company_size" in rules:
        allowed = rules["company_size"]
        if profile.company_size is None:
            checks.append(Check("재직 기업", None, f"{'·'.join(allowed)} 재직자 대상이에요. 회사 규모를 알려주세요."))
        else:
            checks.append(Check("재직 기업", profile.company_size in allowed,
                                f"{'·'.join(allowed)} 재직자 대상 (현재 {profile.company_size})"))
    if rules.get("employed"):
        employed = _employed(profile)
        checks.append(Check("소득 활동", employed, "근로·사업소득이 있어야 해요"))
    if cap := rules.get("single_household_income_cap"):
        detail = f"혼자 사는 1인 가구라면 연소득 약 {fmt_won(cap['annual'])} 이하 ({cap['label']}, 추정)"
        if profile.housing_type in (None, "부모님") or profile.annual_income is None:
            checks.append(Check("가구 소득", None, detail + ". 가구 소득은 따로 확인해야 해요"))
        else:
            checks.append(Check("가구 소득", profile.annual_income <= cap["annual"], detail))
    return checks


def _estimate(kind: str | None, profile: ProfileLike, monthly_saving: int | None) -> Estimate | None:
    if kind == "youth_future_savings":
        tier = youth_future_savings_tier(profile.annual_income, profile.company_size)
        if profile.annual_income is not None and tier is None:
            return None
        if tier == "tax_free":
            return Estimate(None, "정부기여금은 없고 이자소득세가 면제돼요")
        monthly = min(monthly_saving or YOUTH_FUTURE_SAVINGS["monthly_max"], YOUTH_FUTURE_SAVINGS["monthly_max"])
        monthly = max(monthly // 1_000 * 1_000, 1_000)
        result = simulate_youth_future_savings(monthly, tier)
        tier_label = YOUTH_FUTURE_SAVINGS["tiers"][tier or "general"]["label"]
        return Estimate(result.contribution,
                        f"월 {fmt_won(monthly)} 납입 시 3년간 정부기여금 약 {fmt_won(result.contribution)} ({tier_label} 가정)")
    if kind == "rent_support":
        per_month = min(profile.rent or 0, 200_000)
        if per_month <= 0:
            return Estimate(None, "월 최대 20만 원, 최대 24개월")
        return Estimate(per_month * 24, f"월 {fmt_won(per_month)} × 24개월 = 최대 {fmt_won(per_month * 24)}")
    if kind == "sme_tax":
        return Estimate(None, "소득세 90% 감면 (연 최대 200만 원, 5년)")
    if kind == "tomorrow_savings":
        return Estimate(10_800_000, "3년간 정부지원 최대 1,080만 원 (본인 월 10만 원 저축 시)")
    if kind == "pension_tax":
        rate = 0.165 if (profile.annual_income or 0) <= 55_000_000 else 0.132
        refund = int(9_000_000 * rate)
        return Estimate(refund, f"연 900만 원 납입 시 최대 {fmt_won(refund)} 환급 (공제율 {rate * 100:.1f}%)")
    if kind == "housing_dream":
        return Estimate(None, "최대 연 4.5% 금리 + 당첨 시 저금리 대출 연계")
    return None


def evaluate(policy: dict, profile: ProfileLike, monthly_saving: int | None = None,
             today: date | None = None) -> Eligibility:
    rules = policy.get("rules", {})
    checks = _checks(rules, profile)
    today = today or today_kst()

    if any(c.ok is False for c in checks):
        status = "ineligible"
    elif rules.get("new_enrollment_open") is False:
        status = "closed"
    elif (window := rules.get("apply_window")) and not (
        date.fromisoformat(window["start"]) <= today <= date.fromisoformat(window["end"])
    ):
        status = "closed"
    elif any(c.ok is None for c in checks) or policy.get("unknown_checks"):
        status = "check"
    else:
        status = "eligible"

    return Eligibility(
        policy_id=policy["id"], name=policy["name"], status=status, status_label=STATUS_LABELS[status],
        checks=checks, unknown=list(policy.get("unknown_checks", [])),
        estimate=_estimate(policy.get("estimate"), profile, monthly_saving) if status != "ineligible" else None,
    )


def match_all(profile: ProfileLike, monthly_saving: int | None = None) -> list[Eligibility]:
    """모든 정책을 판정해 받을 가능성이 높고 예상 수혜액이 큰 순서로 정렬한다."""
    results = [evaluate(p, profile, monthly_saving) for p in repository.all_policies()]
    return sorted(results, key=lambda e: (STATUS_ORDER[e.status], -((e.estimate and e.estimate.amount) or 0)))
