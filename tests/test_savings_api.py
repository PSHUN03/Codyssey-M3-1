from tests.conftest import agree, onboard, signup


def setup_user(client, email):
    signup(client, email)
    agree(client)
    onboard(client)


def test_weekly_savings_check_create_and_update(client):
    setup_user(client, "weekly@test.com")

    response = client.put(
        "/api/savings/weekly-check",
        json={"week": "2026-W45", "paid": True},
    )

    assert response.status_code == 200
    assert response.json()["paid"] is True

    response = client.put(
        "/api/savings/weekly-check",
        json={"week": "2026-W45", "paid": False},
    )

    assert response.status_code == 200
    assert response.json()["paid"] is False


def test_weekly_savings_check_invalid_week(client):
    setup_user(client, "weekly-invalid@test.com")

    response = client.put(
        "/api/savings/weekly-check",
        json={"week": "2026-99", "paid": True},
    )

    assert response.status_code == 422


def test_weekly_savings_check_nonexistent_week(client):
    setup_user(client, "weekly-nonexistent@test.com")

    response = client.put(
        "/api/savings/weekly-check",
        json={"week": "2025-W53", "paid": True},
    )

    assert response.status_code == 422


def test_monthly_savings_create_and_update(client):
    setup_user(client, "monthly@test.com")

    response = client.post(
        "/api/savings/monthly",
        json={"month": "2026-11", "amount": 300000},
    )

    assert response.status_code == 200
    assert response.json()["amount"] == 300000
    assert response.json()["progress"]["saved_amount"] == 3300000

    response = client.post(
        "/api/savings/monthly",
        json={"month": "2026-11", "amount": 500000},
    )

    assert response.status_code == 200
    assert response.json()["amount"] == 500000
    assert response.json()["progress"]["saved_amount"] == 3500000


def test_monthly_savings_invalid_input(client):
    setup_user(client, "monthly-invalid@test.com")

    response = client.post(
        "/api/savings/monthly",
        json={"month": "2026-13", "amount": 300000},
    )

    assert response.status_code == 422

    response = client.post(
        "/api/savings/monthly",
        json={"month": "2026-11", "amount": -1000},
    )

    assert response.status_code == 422