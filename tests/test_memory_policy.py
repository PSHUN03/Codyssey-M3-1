"""장기 메모리 저장 항목과 보관 기간 (AI-07)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import new_session
from app.models import Memory, User
from app.services.agent import memory
from tests.conftest import agree, onboard, signup


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'memory.db'}")


def _member(client, email="memory-policy@example.test"):
    signup(client, email)
    agree(client)
    onboard(client)
    with new_session() as db:
        return db.scalar(select(User).where(User.email == email)).id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("매달 30만 원 모으기로 함", True),
        ("대출 700만 원 먼저 갚기로 함", True),
        ("3천만 모을 때까지 배달 참기로 함", True),
        ("월세 50 부담돼서 이사 고민 중", True),
        ("계좌 110-123-456789로 받기로 함", True),
        ("배달은 주 2회만 하기로 함", False),
        ("커피는 하루 1잔만 마시기로 함", False),
        ("원금 보장되는 상품을 선호함", False),
        ("내년 3월에 이직 예정", False),
    ],
)
def test_contains_financial_figure(text, expected):
    assert memory.contains_financial_figure(text) is expected


def test_coach_does_not_remember_financial_figures(client):
    _member(client)
    client.post("/api/coach/chat", json={"message": "매달 30만 원 모으기로 약속할게"})
    client.post("/api/coach/chat", json={"message": "배달은 주 2회만 하기로 약속할게"})

    with new_session() as db:
        contents = [m.content for m in db.scalars(select(Memory)).all()]
    assert any("배달은 주 2회" in c for c in contents)
    assert not any("30만" in c for c in contents)


def test_expired_memories_are_purged_and_used_ones_kept(client):
    user_id = _member(client)
    now = datetime.now(UTC)
    with new_session() as db:
        db.add_all([
            Memory(user_id=user_id, kind="commitment", content="오래돼서 지워질 약속", created_at=now - timedelta(days=200)),
            Memory(user_id=user_id, kind="preference", content="최근에 쓰인 선호",
                   created_at=now - timedelta(days=300), last_used_at=now - timedelta(days=10)),
            Memory(user_id=user_id, kind="fact", content="새로 저장한 변화", created_at=now - timedelta(days=1)),
        ])
        db.commit()

    page = client.get("/settings")
    assert page.status_code == 200
    assert "6개월이 지나면 자동으로 지워요" in page.text
    assert "오래돼서 지워질 약속" not in page.text

    with new_session() as db:
        contents = {m.content for m in db.scalars(select(Memory).where(Memory.user_id == user_id)).all()}
    assert contents == {"최근에 쓰인 선호", "새로 저장한 변화"}


def test_chat_marks_memories_as_used(client):
    user_id = _member(client)
    with new_session() as db:
        db.add(Memory(user_id=user_id, kind="preference", content="안전한 저축을 선호함"))
        db.commit()

    client.post("/api/coach/chat", json={"message": "이번 달 계획 알려줘"})

    with new_session() as db:
        saved = db.scalar(select(Memory).where(Memory.user_id == user_id))
        assert saved.last_used_at is not None


def test_privacy_page_states_retention(client):
    assert "6개월이 지나면 자동으로 삭제합니다" in client.get("/privacy").text
