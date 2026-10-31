"""정책 자격 판정과 검색 (FR-07, NFR-03)."""

from dataclasses import dataclass
from datetime import date

import pytest

from app.services.policies import eligibility, repository
from app.services.policies.search import search_policies, tokenize

TODAY = date(2026, 9, 30)


@dataclass
class P:
    age: int | None = 27
    employment_type: str | None = "정규직"
    company_size: str | None = "중소기업"
    annual_income: int | None = 34_000_000
    housing_type: str | None = "월세"
    rent: int | None = 500_000


def status(policy_id: str, profile: P, today: date = TODAY) -> str:
    return eligibility.evaluate(repository.get_policy(policy_id), profile, 460_000, today).status


def test_all_policies_have_sources_and_rules():
    for p in repository.all_policies():
        assert p["sources"], p["id"]
        assert "rules" in p and p["summary"] and p["eligibility_text"]


def test_demo_persona_statuses():
    p = P()
    assert status("youth-future-savings", p) == "check"  # 가구소득은 알 수 없어 확인 필요
    assert status("youth-leap-account", p) == "closed"  # 신규 가입 종료
    assert status("pension-tax-credit", p) == "eligible"
    assert status("sme-youth-tax-cut", p) == "check"
    # 혼자 사는 연봉 3,400만 원이면 저소득 요건(1인 가구 중위소득 50~60%)을 넘는다
    assert status("youth-tomorrow-savings", p) == "ineligible"
    assert status("youth-rent-support", p, date(2026, 4, 15)) == "ineligible"


def test_rent_support_window():
    low_income = P(annual_income=15_000_000)
    assert status("youth-rent-support", low_income) == "closed"  # 2026 모집 기간(3/30~5/29) 종료
    assert status("youth-rent-support", low_income, date(2026, 4, 15)) == "check"


def test_ineligible_conditions():
    assert status("youth-future-savings", P(age=36)) == "ineligible"
    assert status("youth-future-savings", P(annual_income=80_000_000)) == "ineligible"
    assert status("youth-rent-support", P(housing_type="부모님", rent=0), date(2026, 4, 15)) == "ineligible"
    assert status("housing-dream-account", P(housing_type="자가")) == "ineligible"
    assert status("sme-youth-tax-cut", P(company_size="대기업")) == "ineligible"
    assert status("pension-tax-credit", P(employment_type="취업준비")) == "ineligible"


def test_unknown_profile_values_need_check():
    assert status("housing-dream-account", P(annual_income=None)) == "check"


def test_estimates():
    e = eligibility.evaluate(repository.get_policy("youth-future-savings"), P(), 460_000, TODAY)
    assert e.estimate.amount == 460_000 * 12 // 100 * 36  # 우대형 12%, 월 5만 5,200원 × 36
    rent = eligibility.evaluate(repository.get_policy("youth-rent-support"), P(annual_income=15_000_000), None,
                                date(2026, 4, 15))
    assert rent.estimate.amount == 200_000 * 24


def test_match_all_sorted_by_status():
    results = eligibility.match_all(P())
    order = [eligibility.STATUS_ORDER[r.status] for r in results]
    assert order == sorted(order)


def test_tokenize_korean_bigrams():
    assert tokenize("월세지원") == ["월세", "세지", "지원"]
    assert "irp" in tokenize("IRP 세액공제")


@pytest.mark.parametrize("query, expected", [
    ("월세 지원 받을 수 있어?", "youth-rent-support"),
    ("청년도약계좌 지금 가입할 수 있어?", "youth-leap-account"),
    ("연말정산 세액공제 받는 법", "pension-tax-credit"),
    ("중소기업 다니면 소득세 깎아준다던데", "sme-youth-tax-cut"),
    ("내 집 마련 청약통장", "housing-dream-account"),
    ("정부가 돈 보태주는 적금", "youth-future-savings"),
    ("저소득 청년 매칭 저축 30만 원", "youth-tomorrow-savings"),
])
def test_search_top_hit(query, expected):
    results = search_policies(query, k=3)
    assert results and results[0][0]["id"] == expected
