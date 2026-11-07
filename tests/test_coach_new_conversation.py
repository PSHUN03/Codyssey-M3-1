"""새 대화는 기존 기록을 지우지 않고 새 세션으로 분리한다."""

from app.db import new_session
from app.models import ChatMessage
from tests.test_app_flow import chat


def test_new_conversation_preserves_previous_messages_and_starts_fresh(client):
    client.post("/demo")
    first = chat(client, "이전 대화 보존 확인")[-1]["message_id"]
    with new_session() as db:
        previous_session = db.get(ChatMessage, first).session_id

    response = client.post("/api/coach/new-session", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/coach"
    page = client.get("/coach").text
    assert "coach-is-empty" in page
    assert "이전 대화 보존 확인" not in page

    second = chat(client, "새 대화 연결 확인")[-1]["message_id"]
    with new_session() as db:
        assert db.get(ChatMessage, first).session_id == previous_session
        assert db.get(ChatMessage, second).session_id != previous_session
    refreshed = client.get("/coach").text
    assert "새 대화 연결 확인" in refreshed
    assert "이전 대화 보존 확인" not in refreshed


def test_new_conversation_requires_login(client):
    response = client.post("/api/coach/new-session", follow_redirects=False)
    assert response.status_code == 401
