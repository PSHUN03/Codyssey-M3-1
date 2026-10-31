"""진단 결과 유형 분류 (FR-05)."""

import pytest

from app.services.finance.budget import BudgetInput, calc_budget
from app.services.finance.segment import classify


def segment_of(saving_monthly: int = 0, **kwargs):
    r = calc_budget(BudgetInput(**kwargs))
    return classify(r.monthly_income, r.essential, r.total_saving, r.emergency_gap, saving_monthly)


@pytest.mark.parametrize("kwargs, saving_monthly, code", [
    # 꼭 나가는 돈 210만 > 실수령 200만
    ({"monthly_income": 2_000_000, "rent": 900_000, "fixed_costs": 700_000, "debt_monthly": 500_000}, 0, "A"),
    # 같아도 A (쓸 수 있는 돈 0)
    ({"monthly_income": 2_000_000, "rent": 1_000_000, "fixed_costs": 1_000_000}, 0, "A"),
    # 소득이 없으면 A
    ({"monthly_income": 0}, 0, "A"),
    # 적자이면 납입 중이어도 A가 먼저
    ({"monthly_income": 2_000_000, "rent": 1_500_000, "fixed_costs": 600_000}, 300_000, "A"),
    # 쓸 수 있는 돈 40만 → 저축 18만(9%) < 10%
    ({"monthly_income": 2_000_000, "rent": 1_000_000, "fixed_costs": 600_000}, 0, "B"),
    # 데모 페르소나: 저축 65만(27%)
    ({"monthly_income": 2_450_000, "rent": 500_000, "fixed_costs": 350_000, "debt_monthly": 150_000,
      "savings": 3_000_000, "housing_type": "월세"}, 200_000, "C"),
    # 계획상 저축 65만보다 많이 넣고 있으면 D
    ({"monthly_income": 2_450_000, "rent": 500_000, "fixed_costs": 350_000, "debt_monthly": 150_000,
      "housing_type": "월세"}, 700_000, "D"),
    # 여력이 적은데 납입 중이면 B보다 D가 먼저
    ({"monthly_income": 2_000_000, "rent": 1_000_000, "fixed_costs": 600_000}, 300_000, "D"),
])
def test_classify(kwargs, saving_monthly, code):
    assert segment_of(saving_monthly, **kwargs).code == code


def test_boundary_ten_percent():
    assert classify(1_000_000, 0, 100_000).code == "C"
    assert classify(1_000_000, 0, 99_999).code == "B"


def test_segment_texts_use_engine_numbers():
    d = segment_of(700_000, monthly_income=2_450_000, rent=500_000, fixed_costs=350_000, debt_monthly=150_000,
                   housing_type="월세")
    assert "70만 원" in d.reason and "65만 원" in d.reason and "5만 원" in d.reason
    assert d.actions and d.links
    assert all(" " not in link["href"] for link in d.links)  # 한글 질문은 URL 인코딩


def test_c_first_action_depends_on_emergency_fund():
    assert "비상금을 먼저" in classify(2_000_000, 500_000, 600_000, emergency_gap=1_000_000).actions[0]
    assert "충분" in classify(2_000_000, 500_000, 600_000, emergency_gap=0).actions[0]


def test_old_database_gets_new_column(tmp_path):
    """유형 판정용 열이 없던 기존 DB도 시작할 때 열이 추가된다."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import init_engine

    url = f"sqlite:///{tmp_path / 'old.db'}"
    old = create_engine(url)
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE profiles (user_id INTEGER PRIMARY KEY, savings INTEGER)"))
    old.dispose()

    engine = init_engine(url)
    assert "saving_monthly" in {c["name"] for c in inspect(engine).get_columns("profiles")}
    engine.dispose()
