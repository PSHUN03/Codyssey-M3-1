"""Claude 호출 사용량 기록 (AI-05)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db import new_session
from app.models import LlmUsage
from app.services.agent import coach, usage

HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'usage.db'}")


def _usage(inp, out, cache_read=0, cache_write=0):
    return SimpleNamespace(input_tokens=inp, output_tokens=out,
                           cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)


def test_record_and_summary(client):
    usage.record("coach", "claude-sonnet-4", _usage(1200, 300, cache_read=900), 1500.4, tools=["get_my_finances"])
    usage.record("coach", "claude-sonnet-4", _usage(800, 100), 500, stop_reason="end_turn")
    usage.record("structured", "claude-haiku-4", None, 200)

    with new_session() as db:
        rows = db.scalars(select(LlmUsage).order_by(LlmUsage.id)).all()
        assert [r.kind for r in rows] == ["coach", "coach", "structured"]
        assert rows[0].tools == ["get_my_finances"] and rows[0].latency_ms == 1500
        assert rows[2].input_tokens == 0  # usage가 없어도 기록은 남는다

    data = client.get("/internal/usage/summary?days=7", headers=HEADERS).json()
    sonnet = next(i for i in data["items"] if i["model"] == "claude-sonnet-4")
    assert sonnet == {
        "model": "claude-sonnet-4", "kind": "coach", "calls": 2, "input_tokens": 2000, "output_tokens": 400,
        "cache_read_tokens": 900, "cache_write_tokens": 0, "avg_latency_ms": 1000,
    }
    assert data["totals"]["calls"] == 3


def test_summary_requires_internal_key(client):
    assert client.get("/internal/usage/summary").status_code == 401


def test_record_failure_does_not_raise(monkeypatch):
    def broken_session():
        raise RuntimeError("db down")

    monkeypatch.setattr(usage, "new_session", broken_session)
    usage.record("coach", "m", _usage(1, 1), 1)  # 예외 없이 끝나야 한다


class _FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter([SimpleNamespace(type="text", text="이번 달은 괜찮아요.")])

    def get_final_message(self):
        return self.message


def test_anthropic_coach_records_each_turn(client, monkeypatch):
    message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="이번 달은 괜찮아요.")],
        stop_reason="end_turn", usage=_usage(50, 10),
    )
    monkeypatch.setattr(coach.AnthropicCoach, "_open_stream", staticmethod(lambda model, params: _FakeStream(message)))
    monkeypatch.setattr(coach, "recent_memories", lambda user: [])
    user = SimpleNamespace(nickname="테스터", profile=None)
    ctx = SimpleNamespace(user=user)

    events = list(coach.AnthropicCoach().stream(ctx, [], "질문"))

    assert events == [{"type": "delta", "text": "이번 달은 괜찮아요."}]
    with new_session() as db:
        row = db.scalars(select(LlmUsage)).one()
        assert (row.kind, row.input_tokens, row.output_tokens, row.stop_reason) == ("coach", 50, 10, "end_turn")
