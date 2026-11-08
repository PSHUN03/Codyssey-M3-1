"""보안 강화 (BE-03): 로그인 시도 제한, 예시 계정 정리, 운영 환경 감지, 보안 헤더."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import new_session
from app.models import ChatSession, Memory, User
from app.services import account
from tests.conftest import signup

HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'security.db'}")


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def test_five_failures_lock_login_for_ten_minutes(client):
    signup(client, "lock-test@example.test")
    client.post("/logout")

    for _ in range(4):
        assert _login(client, "lock-test@example.test", "wrong-password").status_code == 400
    fifth = _login(client, "lock-test@example.test", "wrong-password")
    assert fifth.status_code == 429 and "10분 동안 잠겼어요" in fifth.text

    # 잠긴 동안에는 맞는 비밀번호도 막는다
    assert _login(client, "lock-test@example.test", "password123").status_code == 429


def test_lock_expires_and_success_clears_failures(client):
    signup(client, "expire-test@example.test")
    client.post("/logout")
    past = datetime.now(UTC) - timedelta(minutes=11)
    with new_session() as db:
        for _ in range(5):
            account.record_login_failure(db, "expire-test@example.test", now=past)
        assert not account.login_locked(db, "expire-test@example.test")

    assert _login(client, "Expire-Test@example.test ", "password123").status_code == 303
    with new_session() as db:
        # 성공하면 실패 기록이 지워져 다시 5번까지 시도할 수 있다
        assert account.record_login_failure(db, "expire-test@example.test") is False


def test_unknown_email_is_locked_the_same_way(client):
    for _ in range(5):
        _login(client, "nobody@example.test", "whatever-123")
    assert _login(client, "nobody@example.test", "whatever-123").status_code == 429


def test_demo_cleanup_removes_only_old_demo_users(client):
    client.post("/demo", follow_redirects=False)  # 방금 만든 예시 계정은 남는다
    old = datetime.now(UTC) - timedelta(days=2)
    with new_session() as db:
        stale = User(nickname="지우(데모)", is_demo=True, created_at=old)
        member = User(nickname="회원", email="keep@example.test", created_at=old)
        db.add_all([stale, member])
        db.commit()
        db.add_all([Memory(user_id=stale.id, kind="preference", content="오래된 예시 기억"),
                    ChatSession(user_id=stale.id, kind="coach", state={})])
        db.commit()

    assert client.post("/internal/demo/cleanup").status_code == 401
    assert client.post("/internal/demo/cleanup", headers=HEADERS).json() == {"deleted": 1}

    with new_session() as db:
        users = db.scalars(select(User)).all()
        assert sorted((u.is_demo, u.nickname) for u in users) == [(False, "회원"), (True, "지우(데모)")]
        assert db.scalars(select(Memory).where(Memory.content == "오래된 예시 기억")).first() is None


def test_render_environment_counts_as_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("RENDER", "true")
    get_settings.cache_clear()
    try:
        assert get_settings().is_production
    finally:
        monkeypatch.delenv("RENDER")
        get_settings.cache_clear()
    assert not get_settings().is_production


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "microphone=()" in headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in headers  # 개발 환경에서는 붙이지 않는다


def test_demo_cleanup_workflow_contract():
    workflow = json.loads((Path(__file__).resolve().parents[1] / "n8n" / "demo_cleanup.json").read_text(encoding="utf-8"))
    assert not workflow["active"]
    assert workflow["settings"]["timezone"] == "Asia/Seoul"
    urls = [n["parameters"].get("url", "") for n in workflow["nodes"]]
    assert any("/internal/demo/cleanup" in u for u in urls)
