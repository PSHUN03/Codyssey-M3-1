"""영수증 인식 (AI-02). 모의 모드와 가짜 Vision 응답으로 검증한다."""

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import new_session
from app.models import ChatMessage
from app.services import receipts
from tests.conftest import agree, onboard, signup

ROOT = Path(__file__).resolve().parents[1]
JPEG = (ROOT / "eval" / "receipts" / "r01.jpg").read_bytes()
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'receipts.db'}")


def _member(client):
    signup(client, "receipt@example.test")
    agree(client)
    onboard(client)


def test_scan_requires_login_and_returns_sample_in_mock_mode(client):
    assert client.post("/api/receipts/scan", files={"file": ("r.jpg", JPEG, "image/jpeg")}).status_code == 401
    _member(client)
    res = client.post("/api/receipts/scan", files={"file": ("r.jpg", JPEG, "image/jpeg")})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "sample" and body["currency"] == "KRW"
    assert body["total_amount"] == 6150 and body["date"] == "2026-10-28"


def test_scan_rejects_other_formats_and_large_files(client):
    _member(client)
    gif = client.post("/api/receipts/scan", files={"file": ("a.gif", b"GIF89a....", "image/gif")})
    assert gif.status_code == 422 and "JPG나 PNG" in gif.json()["detail"]
    big = b"\xff\xd8\xff" + b"0" * receipts.MAX_BYTES
    assert client.post("/api/receipts/scan", files={"file": ("big.jpg", big, "image/jpeg")}).status_code == 413
    assert client.post("/api/receipts/scan", files={"file": ("e.jpg", b"", "image/jpeg")}).status_code == 422


def test_scan_does_not_store_anything(client):
    _member(client)
    with new_session() as db:
        before = db.scalar(select(func.count()).select_from(ChatMessage))
    client.post("/api/receipts/scan", files={"file": ("r.png", PNG, "image/png")})
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage)) == before


def test_vision_result_is_normalized_and_masked():
    seen = {}

    def fake_vision(system, image_b64, media_type, schema):
        seen["media_type"] = media_type
        return {
            "date": "2026-10-27",
            "merchant_name": "하루커피 대흥점 카드 9410-12**-****-3456",
            "total_amount": None,  # 가려진 합계는 null 그대로
            "items": [{"name": "아메리카노 010-1234-5678", "amount": 4500}, {"name": "크로플", "amount": True}],
        }

    result = receipts.scan(PNG, vision_call=fake_vision)
    assert seen["media_type"] == "image/png"
    assert result["source"] == "ai" and result["total_amount"] is None
    assert "3456" not in json.dumps(result, ensure_ascii=False)
    assert "010-1234-5678" not in json.dumps(result, ensure_ascii=False)
    assert result["items"][1]["amount"] is None  # 숫자가 아니면 버린다
    assert set(result["masked"]) == {"카드번호", "전화번호"}


@pytest.mark.parametrize(("raw", "expected"), [("2026-13-01", None), ("어제", None), (" 2026-10-01 ", "2026-10-01")])
def test_invalid_dates_become_null(raw, expected):
    assert receipts.normalize({"date": raw, "items": []}, source="ai")["date"] == expected


def test_vision_failure_is_reported():
    with pytest.raises(receipts.ReceiptError):
        receipts.scan(JPEG, vision_call=lambda *args: None)


def test_eval_scoring_with_fake_vision():
    spec = importlib.util.spec_from_file_location("run_receipt_eval", ROOT / "eval" / "run_receipt_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    answers = [json.loads(line) for line in (ROOT / "eval" / "receipts" / "answers.jsonl").read_text(encoding="utf-8").splitlines()][:2]
    by_file = {a["file"]: a for a in answers}

    queue = list(answers)

    def perfect(system, image_b64, media_type, schema):
        a = queue.pop(0)
        return {"date": a["date"], "merchant_name": a["merchant"], "total_amount": a["total"], "items": []}

    result = module.score(answers, perfect)
    assert result["n"] == 2 and result["accuracy"] == {"date": 1.0, "merchant": 1.0, "total": 1.0, "card_masked": 1.0}
    assert {r["file"] for r in result["rows"]} == set(by_file)
