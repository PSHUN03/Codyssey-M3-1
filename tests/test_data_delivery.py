"""팀 앱 이관 전에도 내부 API와 동의·발송·삭제 경계를 실제 DB로 확인한다."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.models import Consent, Profile, User, WeeklyReport
from app.routers import data, internal
from app.services import weekly_reports

HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture()
def delivery(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'delivery.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        user = User(email="synthetic@example.test", nickname="가짜 회원")
        user.profile = Profile(age=27, onboarding_done=True, saving_monthly=100_000)
        user.consents.append(Consent(kind="weekly_email", agreed=True))
        db.add(user)
        db.commit()
        uid = user.id
    app = FastAPI()
    def database():
        with factory() as db:
            yield db
    def denied():
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    def member():
        with factory() as db:
            return db.get(User, uid)
    app.include_router(internal.router)
    app.include_router(data.create_router(denied))
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, app, factory, uid, denied, member
    engine.dispose()


def test_apis_require_authentication_and_configuration(delivery, monkeypatch):
    client, app, factory, uid, denied, member = delivery
    assert client.post("/internal/reports/weekly").status_code == 401
    assert client.post("/internal/policies/ingest").status_code == 401
    assert client.get("/api/reports/weekly").status_code == 401
    assert client.post("/api/transactions/preview", files={"file": ("x.csv", b"test")}).status_code == 401
    app.dependency_overrides[denied] = member
    monkeypatch.delenv("FSS_API_KEY", raising=False)
    assert client.get("/api/products/compare").status_code == 503
    monkeypatch.delenv("YOUTHCENTER_API_KEY", raising=False)
    assert client.post("/internal/policies/ingest", headers=HEADERS).status_code == 503


def test_delivery_is_idempotent_and_ownership_is_enforced(delivery):
    client, app, factory, uid, denied, member = delivery
    app.dependency_overrides[denied] = member
    first = client.post("/internal/reports/weekly", headers=HEADERS).json()
    assert first == client.post("/internal/reports/weekly", headers=HEADERS).json()
    report_id = first["reports"][0]["report_id"]
    route = f"/internal/reports/{report_id}"
    claimed = client.post(route + "/claim", headers=HEADERS).json()["report"]
    assert claimed["email"] == "synthetic@example.test"
    assert "확인할 수 없어요" in claimed["body"]
    assert client.post(route + "/claim", headers=HEADERS).json()["report"] is None
    assert client.post(route + "/complete", headers=HEADERS,
                       json={"claim_token": "incorrect-token-long-enough"}).status_code == 409
    assert client.post(route + "/complete", headers=HEADERS,
                       json={"claim_token": claimed["claim_token"]}).status_code == 200
    assert client.get("/api/reports/weekly").json()["report"]
    with factory() as db:
        other = User(nickname="다른 회원")
        db.add(other)
        db.flush()
        db.add(WeeklyReport(id="other-user-report", user_id=other.id, week="9999-01-01",
                            body="다른 회원 비공개 본문", status="home"))
        db.commit()
    assert "다른 회원 비공개 본문" not in client.get("/api/reports/weekly").text
    with factory() as db:
        db.delete(db.get(User, uid))
        db.commit()
        assert db.get(WeeklyReport, report_id) is None


def test_opt_out_blocks_pending_delivery(delivery):
    client, app, factory, uid, denied, member = delivery
    report_id = client.post("/internal/reports/weekly", headers=HEADERS).json()["reports"][0]["report_id"]
    with factory() as db:
        db.add(Consent(user_id=uid, kind="weekly_email", agreed=False))
        db.commit()
    assert client.post(f"/internal/reports/{report_id}/claim", headers=HEADERS).json()["report"] is None
    with factory() as db:
        assert db.get(WeeklyReport, report_id).status == "cancelled"


def test_opt_out_stale_and_demo_members(delivery):
    client, app, factory, uid, denied, member = delivery
    with factory() as db:
        db.add(Consent(user_id=uid, kind="weekly_email", agreed=False))
        db.commit()
        assert weekly_reports.prepare_reports(db) == []
        assert db.scalar(select(WeeklyReport).where(WeeklyReport.user_id == uid)).status == "home"
        db.get(User, uid).profile.updated_at = datetime.now(UTC) - timedelta(days=40)
        db.commit()
        assert weekly_reports.generate_reports(db) == []
        db.get(User, uid).is_demo = True
        db.get(User, uid).profile.updated_at = datetime.now(UTC)
        db.commit()
        assert weekly_reports.generate_reports(db) == []


def test_preview_masks_sensitive_input_and_validates_mapping(delivery):
    client, app, factory, uid, denied, member = delivery
    app.dependency_overrides[denied] = member
    content = "거래일,적요,출금액\n2026-10-01,커피 12345678901234,5000".encode()
    result = client.post("/api/transactions/preview", files={"file": ("fake.csv", content)})
    assert result.status_code == 200
    assert result.json()["transactions"][0]["amount"] == -5000
    assert "12345678901234" not in result.text
    assert client.post("/api/transactions/preview", files={"file": ("fake.csv", content)},
                       data={"mapping": "not-json"}).status_code == 422
