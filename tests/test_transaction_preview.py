from pathlib import Path

import pytest

from app.services.transactions import parse_transactions
from tests.conftest import agree, onboard, signup


@pytest.mark.parametrize("name", ["kb_fake.csv", "shinhan_fake.xlsx", "kakao_fake.csv"])
def test_bank_fixture(name):
    file = Path(__file__).parent / "fixtures" / "transactions" / name
    result = parse_transactions(file.read_bytes(), name)
    assert len(result["transactions"]) == 2 and not result["errors"]

def test_preview_auth_masking_and_mapping(client):
    content = "거래일,적요,출금액\n".encode()
    assert client.post("/api/transactions/preview", files={"file": ("x.csv", content)}).status_code == 401
    signup(client, "preview@example.test")
    agree(client)
    onboard(client)
    content = "거래일,적요,출금액\n2026-10-01,커피 12345678901234,5000".encode()
    response = client.post("/api/transactions/preview", files={"file": ("fake.csv", content)})
    assert response.status_code == 200
    assert response.json()["transactions"][0]["amount"] == -5000
    assert "12345678901234" not in response.text
    assert client.post("/api/transactions/preview", files={"file": ("fake.csv", content)}, data={"mapping":"invalid"}).status_code == 422
