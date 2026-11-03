"""질문 카드형 재무 진단 (FR-03)과 랜딩 계산기."""

from app.services.onboarding.flow import QUESTIONS, parse_goal
from app.services.text import josa
from tests.conftest import ONBOARDING_ANSWERS, agree, onboard, signup


def test_questions_are_well_formed():
    keys = [q["key"] for q in QUESTIONS]
    assert len(keys) == len(set(keys))
    for q in QUESTIONS:
        assert q["type"] in {"number", "choice", "amount", "text"} and q["title"]
        if q["type"] == "choice":
            assert q["options"] and all(len(o) == 2 for o in q["options"])
        for dep in q.get("when", {}):
            assert keys.index(dep) < keys.index(q["key"]), "조건 질문은 기준 질문보다 뒤에 와야 한다"


def test_parse_goal():
    assert parse_goal("2년 안에 전세보증금 3천만 원") == {
        "goal_text": "2년 안에 전세보증금 3천만 원", "goal_amount": 30_000_000, "goal_months": 24}
    assert parse_goal("내년까지 천만 원")["goal_months"] == 12
    assert parse_goal("1000만 원 모으기")["goal_months"] is None
    assert parse_goal("아직 없어요") is None
    assert parse_goal("여행 가기") is None


def test_josa():
    assert josa("정규직", "으로/로") == "정규직으로"
    assert josa("프리랜서", "으로/로") == "프리랜서로"
    assert josa("서울", "으로/로") == "서울로"
    assert josa("245만 원", "을/를") == "245만 원을"
    assert josa("사과", "이/가") == "사과가"
    assert josa("17", "은/는") == "17은"


def test_questions_api_prefills_after_onboarding(client):
    signup(client, "cards@example.com")
    agree(client)
    data = client.get("/api/onboarding/questions").json()
    assert data["answers"] == {} and data["questions"][0]["key"] == "age"

    onboard(client)
    answers = client.get("/api/onboarding/questions").json()["answers"]
    assert answers["monthly_income"] == 245 and answers["rent"] == 50  # 화면과 같은 만 원 단위
    assert answers["has_debt"] == "yes"
    assert answers["goal"]["goal_amount"] == 30_000_000


def test_complete_normalizes_conditional_answers(client):
    signup(client, "normalize@example.com")
    agree(client)
    answers = {**ONBOARDING_ANSWERS, "employment_type": "프리랜서", "housing_type": "부모님",
               "goal_amount": 10_000_000, "goal_months": None, "region": "화성"}
    assert onboard(client, answers) == {"ok": True, "redirect": "/plan"}
    saved = client.get("/api/onboarding/questions").json()["answers"]
    assert saved["company_size"] is None and saved["rent"] == 0 and saved["region"] is None
    assert saved["goal"] is None  # 기간이 없는 목표는 저장하지 않는다


def test_complete_rejects_invalid_values(client):
    signup(client, "invalid@example.com")
    agree(client)
    bad = {**ONBOARDING_ANSWERS, "age": 9}
    assert client.post("/api/onboarding/complete", json=bad).status_code == 422
    bad = {**ONBOARDING_ANSWERS, "employment_type": "학생"}
    assert client.post("/api/onboarding/complete", json=bad).status_code == 422


def test_parse_goal_api(client):
    signup(client, "goal@example.com")
    agree(client)
    ok = client.post("/api/onboarding/parse-goal", json={"text": "1년 6개월 동안 500만 원"}).json()
    assert ok["ok"] and ok["goal"]["goal_amount"] == 5_000_000 and ok["goal"]["goal_months"] == 18
    fail = client.post("/api/onboarding/parse-goal", json={"text": "차 사기"}).json()
    assert not fail["ok"] and fail["goal"]["goal_text"] == "차 사기"


def test_quick_plan_without_login(client):
    res = client.post("/api/public/quick-plan", json={"monthly_income": 2_450_000, "rent": 500_000,
                                                      "fixed_costs": 350_000})
    data = res.json()
    assert res.status_code == 200
    assert sum(g["amount"] for g in data["groups"]) == 2_450_000
    assert data["total_saving"] > 0 and data["contribution_label"]
    low = client.post("/api/public/quick-plan", json={"monthly_income": 800_000, "rent": 600_000,
                                                      "fixed_costs": 300_000}).json()
    assert low["total_saving"] == 0 and low["warning"]
