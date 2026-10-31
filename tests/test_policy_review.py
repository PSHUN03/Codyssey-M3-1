"""공식 자료 대조 후 날짜·지역 및 보수적인 판정을 검증한다."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.policies import eligibility, repository


def result(policy_id, day, **changes):
    fields = dict(age=27, employment_type="정규직", company_size="중소기업",
                  annual_income=34_000_000, housing_type="월세", rent=500_000, region="서울")
    fields.update(changes)
    return eligibility.evaluate(repository.get_policy(policy_id), SimpleNamespace(**fields), today=day)


def test_review_scope_is_explicit_and_never_confirms_individual_eligibility():
    reviewed = [p for p in repository.all_policies() if p.get("review_status") in {"official_summary_checked", "official_partial"}]
    assert len(reviewed) == 13
    assert sum(p["review_status"] == "official_summary_checked" for p in reviewed) == 10
    assert sum(p["review_status"] == "official_partial" for p in reviewed) == 3
    for p in reviewed:
        assert p["review"]["individual_eligibility_verified"] is False
        assert p["unknown_checks"] and p["sources"]
        assert result(p["id"], date(2026, 10, 31)).status != "eligible"


def test_seoul_region_and_historical_age_need_separate_checks():
    day = date(2026, 6, 10)
    assert result("seoul-double-savings", day, region="부산").status == "ineligible"
    missing = result("seoul-double-savings", day, region=None)
    assert missing.status == "check"
    assert any(c.label == "거주 지역" and c.ok is None for c in missing.checks)
    assert result("seoul-double-savings", day, age=36).status == "check"
    assert result("seoul-double-savings", day, region="서울특별시").status == "check"
    assert result("seoul-double-savings", date(2026, 10, 31)).status == "closed"


@pytest.mark.parametrize("policy_id", ["icl-student-loan", "general-student-loan"])
def test_student_application_window(policy_id):
    assert result(policy_id, date(2026, 7, 1)).status == "check"
    assert result(policy_id, date(2026, 11, 17)).status == "check"
    assert result(policy_id, date(2026, 11, 18)).status == "closed"


@pytest.mark.parametrize("day, expected", [
    (date(2026, 10, 31), "check"), (date(2026, 12, 1), "check"),
    (date(2026, 12, 2), "closed"), (date(2027, 3, 1), "check"),
    (date(2027, 3, 16), "closed"),
])
def test_multiple_tax_application_windows(day, expected):
    assert result("earned-income-credit", day).status == expected


def test_household_income_is_not_inferred_from_personal_salary():
    assert result("youth-jeonse-loan", date(2026, 10, 31), annual_income=60_000_000).status == "check"


def test_explicit_age_exclusions():
    assert result("training-card", date(2026, 10, 31), age=75).status == "ineligible"
    assert result("student-repayment-deferral", date(2026, 10, 31), age=36).status == "ineligible"
