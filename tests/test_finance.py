"""재무 계산 엔진 (FR-05, FR-06, NFR-02)."""

import pytest

from app.services.finance.budget import BudgetInput, calc_budget, extra_spending_impact
from app.services.finance.money import find_amounts, find_duration_months, fmt_won, parse_amount
from app.services.finance.savings import (
    simulate_installment,
    simulate_youth_future_savings,
    youth_future_savings_tier,
)


@pytest.mark.parametrize("text, expected", [
    ("245만 원", [2_450_000]),
    ("2,450,000원", [2_450_000]),
    ("3천만", [30_000_000]),
    ("1억 2천만 원", [120_000_000]),
    ("1억2000만", [120_000_000]),
    ("138만 7,500원", [1_387_500]),
    ("2년 안에 전세보증금 3천만 원", [30_000_000]),
    ("월세 50에 관리비 7만", [500_000, 70_000]),
    ("27살", []),
    ("5만 3천원", [53_000]),
    ("천만원 모으기", [10_000_000]),
])
def test_find_amounts(text, expected):
    assert find_amounts(text, assume_manwon=True) == expected


def test_parse_amount_bare_number_is_manwon():
    assert parse_amount("250") == 2_500_000
    assert parse_amount("250", assume_manwon=False) == 250


@pytest.mark.parametrize("text, months", [("2년", 24), ("18개월", 18), ("1년 6개월", 18), ("1년 반 안에", 18),
                                           ("6달", 6), ("내년", None)])
def test_duration(text, months):
    assert find_duration_months(text) == months


@pytest.mark.parametrize("n, text", [(2_450_000, "245만 원"), (1_387_500, "138만 7,500원"),
                                     (120_000_000, "1억 2,000만 원"), (0, "0원")])
def test_fmt_won(n, text):
    assert fmt_won(n) == text


DEMO = BudgetInput(monthly_income=2_450_000, rent=500_000, fixed_costs=350_000, debt_monthly=150_000,
                   savings=3_000_000, housing_type="월세", goal_amount=30_000_000, goal_months=24)


def test_budget_demo_persona():
    r = calc_budget(DEMO)
    assert r.essential == 1_000_000
    assert r.disposable == 1_450_000
    assert r.total_saving == 650_000  # 가처분 45%를 만 원 단위 내림
    assert r.amount_of("living") == 800_000
    assert r.emergency_target == 5_400_000  # 3 × (필수지출 + 생활비)
    assert r.amount_of("emergency") == 190_000
    assert r.amount_of("goal") == 460_000
    assert r.goal["feasible"] is False and r.goal["months_needed"] == 66


def test_budget_allocations_sum_to_income():
    for inp in (DEMO, BudgetInput(monthly_income=2_050_000, housing_type="부모님", savings=0),
                BudgetInput(monthly_income=3_333_333, rent=420_000, fixed_costs=123_456)):
        r = calc_budget(inp)
        assert sum(a.amount for a in r.allocations) == inp.monthly_income


def test_budget_is_deterministic():
    assert calc_budget(DEMO).to_dict() == calc_budget(DEMO).to_dict()


def test_budget_with_parents_saves_more():
    base = BudgetInput(monthly_income=2_000_000, fixed_costs=300_000)
    with_parents = calc_budget(BudgetInput(**{**base.__dict__, "housing_type": "부모님"}))
    alone = calc_budget(BudgetInput(**{**base.__dict__, "housing_type": "전세"}))
    assert with_parents.total_saving > alone.total_saving


def test_budget_deficit_warns_and_saves_nothing():
    r = calc_budget(BudgetInput(monthly_income=1_500_000, rent=900_000, fixed_costs=700_000))
    assert r.total_saving == 0 and r.warnings


def test_extra_spending_impact():
    impact = extra_spending_impact(calc_budget(DEMO), 300_000)
    assert impact["goal_saving_after"] == 160_000
    assert impact["exceeds_goal_saving"] is False


def test_installment_interest_and_tax():
    r = simulate_installment(500_000, 36, 0.05)
    assert r.principal == 18_000_000
    assert r.interest == 1_387_500  # 500,000 × 0.05 × 666 / 12
    assert r.tax == 213_675
    assert r.total == 18_000_000 + 1_387_500 - 213_675


def test_youth_future_savings_contribution():
    general = simulate_youth_future_savings(500_000, "general")
    assert general.contribution == 30_000 * 36 and general.tax == 0
    preferential = simulate_youth_future_savings(300_000, "preferential")
    assert preferential.contribution == 36_000 * 36
    capped = simulate_youth_future_savings(800_000, "general")
    assert capped.monthly == 500_000


@pytest.mark.parametrize("income, size, tier", [
    (34_000_000, "중소기업", "preferential"), (34_000_000, "대기업", "general"),
    (70_000_000, "대기업", "tax_free"), (80_000_000, "대기업", None), (None, None, None),
])
def test_youth_future_savings_tier(income, size, tier):
    assert youth_future_savings_tier(income, size) == tier
