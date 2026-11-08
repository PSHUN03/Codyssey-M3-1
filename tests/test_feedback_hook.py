"""'아쉬워요' 피드백 → n8n 웹훅 (FR-17, PM-02)."""

import pytest

from app.config import get_settings
from app.services import feedback_hook
from tests.conftest import agree, onboard, signup
from tests.test_app_flow import chat

WEBHOOK = "https://n8n.example.test/webhook/sadari-feedback"


@pytest.fixture()
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(feedback_hook, "send", lambda url, payload, key=None: calls.append((url, payload, key)))
    return calls


@pytest.fixture()
def with_webhook(monkeypatch):
    monkeypatch.setenv("FEEDBACK_WEBHOOK_URL", WEBHOOK)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _answer_id(client, email, question):
    signup(client, email, "피드백테스터")
    agree(client)
    onboard(client)
    return chat(client, question)[-1]["message_id"]


def test_dislike_is_sent_without_personal_info(client, sent, with_webhook):
    message_id = _answer_id(client, "fb-dislike@example.com", "이번 달 30만 원 더 써도 될까?")
    res = client.post("/api/feedback", json={"message_id": message_id, "rating": -1,
                                             "comment": "제 번호 010-1234-5678로 연락 주세요"})
    assert res.json() == {"ok": True}
    assert len(sent) == 1
    url, payload, key = sent[0]
    assert url == WEBHOOK and key == "test-internal-key"
    assert payload["question"] == "이번 달 [금액] 더 써도 될까?"  # 공개 이슈라 금액은 가린다
    assert "16만 원" not in payload["answer"]
    assert payload["answer"] and payload["rating"] == -1
    assert "010-1234-5678" not in payload["comment"]  # 의견 속 전화번호는 가린다
    text = str(payload)
    assert "fb-dislike@example.com" not in text and "피드백테스터" not in text


def test_names_and_emails_are_hidden(client, sent, with_webhook):
    # 가짜 이름·이메일을 직접 적어도 공개 이슈로 가는 값에는 남지 않는다
    message_id = _answer_id(client, "fb-name@example.com", "제 이름은 김가짜예요. 피드백테스터 계정인데 월세 지원 받을 수 있어?")
    client.post("/api/feedback", json={"message_id": message_id, "rating": -1,
                                       "comment": "저는 박가명입니다. 답장은 fake.person@example.org 로 주세요"})
    payload = sent[0][1]
    text = str(payload)
    for leaked in ("김가짜", "박가명", "fake.person@example.org", "피드백테스터", "fb-name"):
        assert leaked not in text
    assert "[이메일 가림]" in payload["comment"] and "[이름 가림]" in payload["question"]


def test_like_is_not_sent(client, sent, with_webhook):
    message_id = _answer_id(client, "fb-like@example.com", "월세 지원 받을 수 있어?")
    client.post("/api/feedback", json={"message_id": message_id, "rating": 1})
    assert sent == []


def test_no_webhook_url_means_no_call(client, sent, monkeypatch):
    monkeypatch.delenv("FEEDBACK_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()
    message_id = _answer_id(client, "fb-nourl@example.com", "월세 지원 받을 수 있어?")
    assert client.post("/api/feedback", json={"message_id": message_id, "rating": -1}).json() == {"ok": True}
    assert sent == []


def test_send_failure_is_swallowed(caplog):
    # 닿지 않는 주소로 보내도 예외가 밖으로 나오지 않고 경고 로그만 남는다
    feedback_hook.send("http://127.0.0.1:9/webhook", {"feedback_id": 1})
    assert "전송 실패" in caplog.text


@pytest.mark.parametrize("text, expected", [
    ("월급 250만 원인데 30만 원 더 써도 돼?", "월급 [금액]인데 [금액] 더 써도 돼?"),
    ("2,450,000원 들어와요", "[금액] 들어와요"),
    ("배달 주 2회, 금리 3.5%", "배달 주 2회, 금리 3.5%"),
    ("이름: 홍길동, 메일 a.b+c@mail.example.com", "이름: [이름 가림], 메일 [이메일 가림]"),
    ("저는 이가짜라고 해요", "저는 [이름 가림]라고 해요"),
    ("이름을 바꾸고 싶어요", "이름을 바꾸고 싶어요"),
])
def test_amounts_are_hidden(text, expected):
    assert feedback_hook._clean(text) == expected
