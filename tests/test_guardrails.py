"""가드레일과 보안 유틸 (FR-11, NFR-04~06)."""

import pytest

from app.security import hash_password, mask_sensitive, verify_password
from app.services.agent.guardrails import (
    collect_amounts,
    contains_investment_advice,
    is_investment_advice_request,
    unverified_amounts,
)


@pytest.mark.parametrize("text", [
    "삼성전자 지금 사도 돼?", "비트코인 언제 팔까?", "종목 추천해줘", "ETF 뭐 사야 해?", "테슬라 오를까요",
])
def test_investment_requests_detected(text):
    assert is_investment_advice_request(text)


@pytest.mark.parametrize("text", [
    "ETF가 뭐야?", "적금이랑 예금 차이 알려줘", "청년미래적금 얼마 받아?", "이번 달 30만 원 더 써도 될까?",
])
def test_normal_questions_not_flagged(text):
    assert not is_investment_advice_request(text)


def test_investment_advice_in_output():
    assert contains_investment_advice("지금 엔비디아를 매수하세요.")
    assert not contains_investment_advice("투자 전에 비상금부터 모으는 게 좋아요.")


def test_mask_sensitive():
    text, found = mask_sensitive("주민번호 990101-1234567, 계좌 110-123-456789, 전화 010-1234-5678")
    assert "990101" not in text and "456789" not in text and "5678" not in text
    assert set(found) == {"주민등록번호", "계좌번호", "전화번호"}
    assert mask_sensitive("2026-10-01에 월급 245만 원")[1] == []  # 날짜는 계좌로 오인하지 않는다
    # 숫자 바로 뒤에 조사가 붙어도 가린다
    assert mask_sensitive("계좌 110-123-456789로 들어와요")[1] == ["계좌번호"]
    assert mask_sensitive("번호는 01012345678이에요")[1] == ["전화번호"]


def test_unverified_amounts():
    allowed = collect_amounts({"goal": 460_000, "note": "생활비 80만 원", "nested": [{"x": 5_400_000}]})
    assert unverified_amounts("목표 저축 46만 원, 생활비 80만 원, 비상금 540만 원", allowed) == []
    assert unverified_amounts("매달 123만 원을 모으세요", allowed) == [1_230_000]


def test_password_hash_roundtrip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", None)
