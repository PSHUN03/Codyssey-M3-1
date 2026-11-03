"""FE-01 sample pages preserve existing authenticated flows and plan features."""

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from app.services.checkin_preview import sample_config


def config_from(html):
    match = re.search(r'<script type="application/json" id="fe01-sample-config">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def test_sample_months_and_iso_week_cross_year_boundaries():
    config = sample_config(7, date(2027, 1, 1))
    assert [record["month"] for record in config["records"]] == [
        "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01",
    ]
    assert config["week"] == "2026-W53"
    assert sum(record["amount"] for record in config["records"]) == 3_200_000
    assert config["mode"] == "sample"


def test_progress_requires_an_onboarded_session(client):
    response = client.get("/progress", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_home_and_progress_share_sample_scope_and_show_explicit_labels(client):
    client.post("/demo")
    home = client.get("/home")
    progress = client.get("/progress")
    assert home.status_code == progress.status_code == 200
    assert config_from(home.text) == config_from(progress.text)
    assert "이번 주 냈나요?" in home.text
    assert "이번 달 얼마 모았나요?" in home.text
    assert "실제 저축 내역으로 저장되지 않아요" in home.text
    assert 'data-fe01-coach hidden' in home.text
    assert 'href="/progress"' in home.text
    assert "샘플 데이터" in progress.text
    assert "실제 내 저축 내역과 연결되지 않아요" in progress.text
    assert 'data-fe01-chart' in progress.text
    assert "홈으로" not in progress.text
    assert progress.text.count('href="/plan" class="is-active"') == 2


def test_new_demo_session_uses_a_different_sample_storage_scope(client):
    client.post("/demo")
    first = config_from(client.get("/home").text)
    client.post("/demo")
    second = config_from(client.get("/home").text)
    assert first["scope"] != second["scope"]
    assert first["records"] == second["records"]


def test_plan_keeps_calculator_and_regeneration_next_to_progress_entry(client):
    client.post("/demo")
    html = client.get("/plan").text
    assert 'id="simulate-form"' in html
    assert 'data-action="regenerate"' in html
    assert 'name="monthly_amount"' in html
    assert 'href="/progress"' in html
    assert 'data-fe01-chart' not in html


def test_new_assets_do_not_change_other_pages(client):
    client.post("/demo")
    for route in ("/benefits", "/coach", "/settings"):
        html = client.get(route).text
        assert "/static/css/fe01.css" not in html
        assert "/static/js/fe01.js" not in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for frontend regressions")
def test_sample_adapter_frontend_regressions():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which("node"), "--test", "tests/frontend/fe01-sample.test.cjs", "tests/frontend/checkin-contract.test.cjs"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
