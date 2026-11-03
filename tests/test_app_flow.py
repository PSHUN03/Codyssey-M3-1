"""가입 → 동의 → 진단 → 플랜·혜택 → AI 코치 → 피드백·메모리 → 탈퇴 전체 흐름 (모의 AI 모드)."""

import json

from tests.conftest import agree, onboard, signup


def sse_events(res) -> list[dict]:
    return [json.loads(line[6:]) for line in res.text.split("\n") if line.startswith("data: ")]


def chat(client, message: str) -> list[dict]:
    res = client.post("/api/coach/chat", json={"message": message})
    assert res.status_code == 200, res.text
    return sse_events(res)


def answer_text(events: list[dict]) -> str:
    replaced = [e["text"] for e in events if e["type"] == "replace"]
    return replaced[-1] if replaced else "".join(e["text"] for e in events if e["type"] == "delta")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "llm_provider": "mock"}


def test_guards_redirect_and_401(client):
    assert client.get("/home", follow_redirects=False).headers["location"] == "/login"
    assert client.post("/api/coach/chat", json={"message": "hi"}).status_code == 401
    signup(client, "guard@example.com")
    assert client.get("/home", follow_redirects=False).headers["location"] == "/consent"
    agree(client)
    assert client.get("/home", follow_redirects=False).headers["location"] == "/onboarding"
    assert client.post("/api/coach/chat", json={"message": "hi"}).status_code == 409


def test_consent_requires_all_required_items(client):
    signup(client, "consent@example.com")
    res = client.post("/consent", data={"terms": "on", "privacy": "on"})
    assert res.status_code == 400 and "필수" in res.text


def test_full_user_journey(client):
    signup(client, "journey@example.com", "지우")
    agree(client)
    done = onboard(client)
    assert done["redirect"] == "/plan"

    for path in ("/home", "/plan", "/benefits", "/benefits/youth-future-savings", "/coach", "/settings"):
        res = client.get(path)
        assert res.status_code == 200, path
    plan_page = client.get("/plan").text
    assert "46만 원" in plan_page and "계산 엔진" in plan_page
    assert "진단 결과" in plan_page and "저축 여력 있음" in plan_page  # 데모 답변은 C 유형

    # AI 코치: 지출 영향 계산 (도구 호출 → 계산 엔진 숫자)
    events = chat(client, "이번 달 30만 원 더 써도 될까?")
    done_event = events[-1]
    assert done_event["type"] == "done" and "check_extra_spending" in done_event["tools"]
    assert "16만 원" in answer_text(events)

    # 정책 질문: RAG 검색 + 출처
    events = chat(client, "월세 지원 받을 수 있어?")
    assert "청년월세 지원" in answer_text(events)
    assert events[-1]["sources"]

    # 투자 권유 요청은 가드레일이 막는다
    events = chat(client, "삼성전자 지금 사도 돼?")
    assert "투자자문업자" in answer_text(events)

    # 민감정보는 가린 뒤 처리한다
    events = chat(client, "제 계좌 110-123-456789로 월급 들어와요")
    assert events[0]["type"] == "notice"

    # 약속을 말하면 장기 메모리에 저장된다
    chat(client, "앞으로 배달은 주 2회만 할게")
    assert "배달은 주 2회만" in client.get("/settings").text

    # 피드백
    fb = client.post("/api/feedback", json={"message_id": done_event["message_id"], "rating": 1})
    assert fb.json() == {"ok": True}

    # 저축 시뮬레이션 API
    sim = client.post("/api/goals/simulate", json={"monthly_amount": 300_000, "product": "youth_future_savings"})
    assert sim.status_code == 200 and sim.json()["contribution"] == 36_000 * 36

    # 프로필 수정 → 플랜 재계산
    assert client.put("/api/profile", json={"rent": 400_000}).json() == {"ok": True}

    # 탈퇴하면 데이터가 삭제되고 다시 로그인할 수 없다
    assert client.delete("/api/account").json()["ok"] is True
    res = client.post("/login", data={"email": "journey@example.com", "password": "password123"})
    assert res.status_code == 400


def test_demo_mode(client):
    res = client.post("/demo", follow_redirects=False)
    assert res.headers["location"] == "/home"
    home = client.get("/home").text
    assert "지우(데모)" in home and "청년미래적금" in home
    events = chat(client, "청년미래적금에 월 30만 원 넣으면 얼마 받아?")
    assert "만기" in answer_text(events)


def test_memory_delete_only_own(client):
    client.post("/demo")
    settings = client.get("/settings").text
    assert "원금이 보장되는" in settings
    assert client.delete("/api/memories/999999").status_code == 404


def test_internal_api_requires_key(client):
    assert client.get("/internal/ping").status_code == 401
    assert client.get("/internal/ping", headers={"X-Internal-Key": "test-internal-key"}).json() == {"ok": True}


def test_pwa_files(client):
    assert client.get("/manifest.webmanifest").json()["short_name"] == "사다리"
    assert client.get("/sw.js").status_code == 200
