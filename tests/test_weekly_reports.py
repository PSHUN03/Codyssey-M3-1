from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import new_session
from app.models import Consent, User, WeeklyReport
from app.services import weekly_reports
from tests.conftest import agree, onboard, signup

HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'weekly.db'}")


def create_member(client):
    signup(client, "fictional@example.test")
    agree(client)
    onboard(client)
    with new_session() as db:
        user = db.scalar(select(User).where(User.email == "fictional@example.test"))
        db.add(Consent(user_id=user.id, kind="weekly_email", agreed=True, version="test"))
        db.commit()
        return user.id


def test_auth_and_api_key_fail_closed(client):
    assert client.post("/internal/reports/weekly").status_code == 401
    assert client.get("/api/reports/weekly").status_code == 401


def test_weekly_idempotency_claim_ack_and_deletion(client):
    create_member(client)
    first = client.post("/internal/reports/weekly", headers=HEADERS).json()
    again = client.post("/internal/reports/weekly", headers=HEADERS).json()
    assert first == again and len(first["reports"]) == 1
    report_id = first["reports"][0]["report_id"]
    claimed = client.post(f"/internal/reports/{report_id}/claim", headers=HEADERS).json()["report"]
    assert claimed["email"] == "fictional@example.test"
    assert "확인할 수 없어요" in claimed["body"]
    assert client.post(f"/internal/reports/{report_id}/claim", headers=HEADERS).json()["report"] is None
    assert client.post(f"/internal/reports/{report_id}/complete", headers=HEADERS,
                       json={"claim_token": "wrong-token-that-is-long-enough"}).status_code == 409
    assert client.post(f"/internal/reports/{report_id}/complete", headers=HEADERS,
                       json={"claim_token": claimed["claim_token"]}).status_code == 200
    assert client.get("/api/reports/weekly").json()["report"]
    home = client.get("/home").text
    assert "이번 주 리포트" in home and "실제 납입 기록은 아직 연결되지 않아" in home
    client.delete("/api/account")
    with new_session() as db:
        assert db.get(WeeklyReport, report_id) is None


def test_withdrawn_consent_cancels_claim(client):
    uid = create_member(client)
    report_id = client.post("/internal/reports/weekly", headers=HEADERS).json()["reports"][0]["report_id"]
    with new_session() as db:
        db.add(Consent(user_id=uid, kind="weekly_email", agreed=False, version="test"))
        db.commit()
    assert client.post(f"/internal/reports/{report_id}/claim", headers=HEADERS).json()["report"] is None


def test_opt_out_gets_home_card_and_stale_users_skipped(client):
    uid = create_member(client)
    with new_session() as db:
        user = db.get(User, uid)
        db.add(Consent(user_id=uid, kind="weekly_email", agreed=False, version="test"))
        db.commit()
        assert weekly_reports.prepare_reports(db) == []
        assert db.scalar(select(WeeklyReport).where(WeeklyReport.user_id == uid)).status == "home"
        user.profile.updated_at = datetime.now(UTC) - timedelta(days=40)
        db.commit()
        assert weekly_reports.generate_reports(db) == []


def test_demo_users_not_sent_reports(client):
    client.post("/demo")
    assert client.post("/internal/reports/weekly", headers=HEADERS).json() == {"reports": []}


