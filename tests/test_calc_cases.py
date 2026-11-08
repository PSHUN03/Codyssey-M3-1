"""평가 테스트셋: 계산 케이스 20개 (PM-07, NFR-02).

기대값은 코드 결과를 복사한 것이 아니라 규칙(ADR-0005)으로 손으로 계산한 값이다.
계산식은 각 케이스의 주석에 적었다. 규칙이 바뀌면 주석의 계산부터 다시 한다.
"""

import pytest

from app.services.finance.budget import BudgetInput, calc_budget
from app.services.finance.savings import (
    simulate_installment,
    simulate_youth_future_savings,
    youth_future_savings_tier,
)
from app.services.finance.segment import classify

# ── 월급 배분 (5개) ─────────────────────────────────────────


def test_c01_alone_without_savings():
    # 쓸 수 있는 돈 300만 - 100만 = 200만, 저축 45% = 90만, 생활비 110만
    # 비상금 목표 3 × (100만 + 110만) = 630만, 모아 둔 돈 0 → 저축의 30% = 27만을 비상금으로
    r = calc_budget(BudgetInput(monthly_income=3_000_000, rent=600_000, fixed_costs=400_000))
    assert (r.disposable, r.total_saving, r.amount_of("living")) == (2_000_000, 900_000, 1_100_000)
    assert (r.emergency_target, r.amount_of("emergency"), r.amount_of("goal")) == (6_300_000, 270_000, 630_000)


def test_c02_with_parents_and_enough_emergency_fund():
    # 쓸 수 있는 돈 170만, 부모님과 거주라 60% = 102만, 생활비 68만
    # 비상금 목표 3 × (30만 + 68만) = 294만 ≤ 모아 둔 돈 500만 → 비상금 배정 0, 목표 저축 102만
    r = calc_budget(BudgetInput(monthly_income=2_000_000, fixed_costs=300_000, savings=5_000_000,
                                housing_type="부모님"))
    assert (r.total_saving, r.amount_of("living"), r.emergency_target) == (1_020_000, 680_000, 2_940_000)
    assert (r.emergency_gap, r.amount_of("emergency"), r.amount_of("goal")) == (0, 0, 1_020_000)


def test_c03_saving_is_floored_to_ten_thousand_won():
    # 2,345,678 × 0.45 = 1,055,555.1 → 만 원 단위 내림 105만, 나머지는 생활비. 합계는 실수령액과 같다
    r = calc_budget(BudgetInput(monthly_income=2_345_678))
    assert r.total_saving == 1_050_000
    assert r.amount_of("living") == 1_295_678
    assert sum(a.amount for a in r.allocations) == 2_345_678


def test_c04_goal_not_feasible():
    # c01의 목표 저축 63만으로 1년 1,200만: 매달 100만 필요, 1,200만 / 63만 = 19.05 → 20개월
    r = calc_budget(BudgetInput(monthly_income=3_000_000, rent=600_000, fixed_costs=400_000,
                                goal_amount=12_000_000, goal_months=12))
    assert r.goal == {"target_amount": 12_000_000, "target_months": 12, "monthly_needed": 1_000_000,
                      "monthly_planned": 630_000, "feasible": False, "months_needed": 20}


def test_c05_zero_disposable_saves_nothing():
    # 꼭 나가는 돈 = 실수령액이면 쓸 수 있는 돈 0 → 저축 0, 경고
    r = calc_budget(BudgetInput(monthly_income=2_000_000, rent=800_000, fixed_costs=700_000, debt_monthly=500_000))
    assert (r.disposable, r.total_saving) == (0, 0)
    assert r.warnings


# ── 적금 만기액 (8개) ───────────────────────────────────────


@pytest.mark.parametrize("monthly, months, rate, tax_free, interest, tax, total", [
    # c06: 10만 × 12개월, 3.5%: 이자 = 100,000 × 0.035 × 78 / 12 = 22,750, 세금 22,750 × 0.154 = 3,503.5 → 3,503
    (100_000, 12, 0.035, False, 22_750, 3_503, 1_219_247),
    # c07: 30만 × 24개월, 4%: 이자 = 300,000 × 0.04 × 300 / 12 = 300,000, 세금 46,200
    (300_000, 24, 0.04, False, 300_000, 46_200, 7_453_800),
    # c08: 50만 × 36개월, 3.5%, 비과세: 이자 = 500,000 × 0.035 × 666 / 12 = 971,250
    (500_000, 36, 0.035, True, 971_250, 0, 18_971_250),
])
def test_c06_to_c08_installment(monthly, months, rate, tax_free, interest, tax, total):
    r = simulate_installment(monthly, months, rate, tax_free=tax_free)
    assert (r.interest, r.tax, r.total) == (interest, tax, total)


def test_c09_installment_rejects_zero():
    with pytest.raises(ValueError):
        simulate_installment(0, 12)


def test_c10_youth_future_preferential_full():
    # 우대형 50만: 기여금 = min(50만 × 12%, 6만) = 6만 × 36개월 = 216만, 비과세
    r = simulate_youth_future_savings(500_000, "preferential")
    assert (r.contribution, r.tax, r.principal) == (2_160_000, 0, 18_000_000)


def test_c11_youth_future_preferential_partial():
    # 우대형 40만: 기여금 = 40만 × 12% = 4.8만 × 36개월 = 172.8만
    assert simulate_youth_future_savings(400_000, "preferential").contribution == 1_728_000


def test_c12_youth_future_general_capped():
    # 일반형 20만: 20만 × 6% = 1.2만 (한도 3만 미만) × 36 = 43.2만
    assert simulate_youth_future_savings(200_000, "general").contribution == 432_000


def test_c13_youth_future_unknown_income_assumes_general():
    r = simulate_youth_future_savings(500_000, None)
    assert r.contribution == 30_000 * 36
    assert any("일반형으로 가정" in note for note in r.notes)


# ── 청년미래적금 유형 경계 (1개, 6가지 입력) ─────────────────


@pytest.mark.parametrize("income, size, tier", [
    (36_000_000, "중소기업", "preferential"),  # 3,600만 이하 + 중소기업
    (36_000_001, "중소기업", "general"),        # 1원 넘으면 일반형
    (60_000_000, "대기업", "general"),          # 6,000만 이하
    (60_000_001, "대기업", "tax_free"),         # 6,000만 초과 ~ 7,500만
    (75_000_000, "대기업", "tax_free"),
    (75_000_001, "대기업", None),               # 가입 대상 아님
])
def test_c14_youth_future_tier_boundaries(income, size, tier):
    assert youth_future_savings_tier(income, size) == tier


# ── 유형 분류 경계 (6개) ────────────────────────────────────


def _segment(income, essential, housing=None, saving_monthly=0):
    r = calc_budget(BudgetInput(monthly_income=income, fixed_costs=essential, housing_type=housing))
    return classify(r.monthly_income, r.essential, r.total_saving, r.emergency_gap, saving_monthly)


def test_c15_alone_b_c_boundary():
    # 실수령 250만, 혼자: 194만이면 56만 × 45% = 25.2만 → 25만 (10.0%) C, 195만이면 24만 (9.6%) B
    assert _segment(2_500_000, 1_940_000).code == "C"
    assert _segment(2_500_000, 1_950_000).code == "B"


def test_c16_with_parents_b_c_boundary():
    # 부모님과 거주: 208만이면 42만 × 60% = 25.2만 → 25만 (10.0%) C, 209만이면 24만 (9.6%) B
    assert _segment(2_500_000, 2_080_000, "부모님").code == "C"
    assert _segment(2_500_000, 2_090_000, "부모님").code == "B"


def test_c17_saving_equal_to_plan_is_not_d():
    # 계획상 저축 25만과 같게 넣고 있으면 D가 아니다
    assert _segment(2_500_000, 1_940_000, saving_monthly=250_000).code == "C"


def test_c18_saving_above_plan_is_d():
    # 규칙 v1: 계획보다 1원이라도 많이 넣으면 D (ADR-0009에서 여유 범위를 정하면 이 케이스를 고친다)
    assert _segment(2_500_000, 1_940_000, saving_monthly=250_001).code == "D"


def test_c19_b_reason_shows_rate():
    # B 판정 이유에 저축 가능액(24만 원)과 비율(10% 미만)이 계산 값 그대로 나온다
    reason = _segment(2_500_000, 1_950_000).reason
    assert "24만 원" in reason and "10%" in reason


def test_c20_deficit_wins_over_saving():
    # 꼭 나가는 돈 260만 > 실수령 250만이면 납입 중이어도 A
    assert _segment(2_500_000, 2_600_000, saving_monthly=300_000).code == "A"
