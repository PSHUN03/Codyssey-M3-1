"""테스트는 항상 모의 AI 모드와 임시 SQLite DB로 실행한다 (API 키·비용 불필요)."""

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="sadari-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["INTERNAL_API_KEY"] = "test-internal-key"
os.environ["DAILY_CHAT_LIMIT"] = "50"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402


@pytest.fixture()
def client():
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


# 진단 화면이 /api/onboarding/complete로 보내는 값 (금액은 원 단위)
ONBOARDING_ANSWERS = {
    "age": 27, "employment_type": "정규직", "company_size": "중소기업",
    "monthly_income": 2_450_000, "annual_income": 34_000_000,
    "housing_type": "월세", "rent": 500_000, "fixed_costs": 350_000,
    "debt_total": 7_000_000, "debt_monthly": 150_000, "savings": 3_000_000, "region": "서울",
    "goal_text": "2년 안에 전세보증금 3천만 원", "goal_amount": 30_000_000, "goal_months": 24,
}


def signup(client: TestClient, email: str, nickname: str = "테스터") -> None:
    res = client.post("/signup", data={"email": email, "password": "password123", "nickname": nickname},
                      follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/consent"


def agree(client: TestClient) -> None:
    res = client.post("/consent", data={"terms": "on", "privacy": "on", "overseas": "on"}, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/onboarding"


def onboard(client: TestClient, answers: dict = ONBOARDING_ANSWERS) -> dict:
    res = client.post("/api/onboarding/complete", json=answers)
    assert res.status_code == 200, res.text
    return res.json()