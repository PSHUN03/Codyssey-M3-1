"""거래내역 저장과 소비 분석 (BE-01). 거래는 모두 지어낸 값이다."""

import pytest
from sqlalchemy import func, select

from app.db import new_session
from app.models import Transaction, User
from app.services.agent.tools import ToolContext, run_tool
from tests.conftest import agree, onboard, signup

CSV = "\n".join([
    "거래일,적요,출금액,입금액",
    "2026-09-05,넷플릭스,13500,",
    "2026-09-10,가짜통신 요금,55000,",
    "2026-10-01,가짜회사 급여,,2450000",
    "2026-10-03,월세 이체,500000,",
    "2026-10-05,넷플릭스,13500,",
    "2026-10-07,스타벅스 둔산점,6500,",
    "2026-10-10,가짜통신 요금,55000,",
    "2026-10-12,쿠팡,89000,",
    "2026-10-20,카드 1234-5678-9012-3456 결제,30000,",
]).encode("utf-8")


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'spending.db'}")


def _member(client, email="spending@example.test"):
    signup(client, email)
    agree(client)
    onboard(client)
    with new_session() as db:
        return db.scalar(select(User).where(User.email == email)).id


def _upload(client, content=CSV):
    return client.post("/api/transactions/upload", files={"file": ("fake.csv", content, "text/csv")})


def test_upload_saves_masked_rows_once(client):
    assert _upload(client).status_code == 401
    user_id = _member(client)

    first = _upload(client).json()
    assert first["saved"] == 9 and first["skipped"] == 0 and first["errors"] == []
    again = _upload(client).json()
    assert again["saved"] == 0 and again["skipped"] == 9  # 같은 파일을 다시 올려도 중복 저장하지 않는다

    with new_session() as db:
        rows = db.scalars(select(Transaction).where(Transaction.user_id == user_id)).all()
        assert len(rows) == 9
        assert not any("1234-5678-9012-3456" in t.merchant for t in rows)
        assert next(t for t in rows if t.merchant == "월세 이체").is_fixed


def test_summary_by_month(client):
    _member(client)
    _upload(client)

    data = client.get("/api/transactions/summary?month=2026-10").json()
    assert data["has_data"] and data["transaction_count"] == 7
    assert data["income"] == 2_450_000
    assert data["total_spent"] == 500_000 + 13_500 + 6_500 + 55_000 + 89_000 + 30_000
    assert data["by_category"][0] == {"category": "주거", "amount": 500_000,
                                      "share": round(500_000 / data["total_spent"], 3)}
    subs = {s["merchant"] for s in data["subscriptions"]}
    assert subs == {"넷플릭스", "가짜통신 요금"}  # 두 달 이상 같은 금액이거나 구독 서비스
    assert data["fixed_estimate"] >= 500_000 + 13_500 + 55_000
    assert data["saving_capacity"] == 2_450_000 - data["total_spent"]
    assert data["top_expenses"][0]["amount"] == 500_000

    # 월을 비우면 가장 최근 달
    assert client.get("/api/transactions/summary").json()["month"] == "2026-10"
    assert client.get("/api/transactions/summary?month=2026-13").status_code == 422


def test_summary_without_data_and_profile_income_basis(client):
    _member(client)
    assert client.get("/api/transactions/summary").json() == {
        "month": None, "has_data": False, "message": "아직 저장한 거래내역이 없어요."}
    _upload(client, "거래일,적요,출금액,입금액\n2026-11-01,편의점,4000,".encode())
    data = client.get("/api/transactions/summary").json()
    assert data["income_basis"] == "재무 프로필 실수령액"
    assert data["saving_capacity"] == 2_450_000 - 4_000


def test_coach_tool_and_account_deletion(client):
    user_id = _member(client)
    _upload(client)
    with new_session() as db:
        user = db.get(User, user_id)
        result, is_error = run_tool("analyze_spending", {"month": "2026-09"}, ToolContext(db=db, user=user))
        assert not is_error and result["total_spent"] == 13_500 + 55_000
        _, bad = run_tool("analyze_spending", {"month": "9월"}, ToolContext(db=db, user=user))
        assert bad

    assert client.request("DELETE", "/api/account").status_code in (200, 204, 303)
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 0
