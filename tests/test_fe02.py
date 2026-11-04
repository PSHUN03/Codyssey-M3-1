"""FE-02 preview and explicit sample pages remain protected; the plan stays intact."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def config_from(html):
    match = re.search(r'<script id="spending-preview-config" type="application/json">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match[1])


def test_spending_requires_an_onboarded_session(client):
    response = client.get('/spending', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'].startswith('/login')


def test_plan_entry_keeps_its_calculator_and_controls(client):
    client.post('/demo')
    html = client.get('/plan').text
    assert 'href="/spending"' in html and '소비 분석 보기' in html
    assert 'id="simulate-form"' in html and 'name="monthly_amount"' in html
    assert 'data-action="regenerate"' in html
    assert '/static/js/spending.js' not in html


def test_spending_has_explicit_sample_data_and_local_category_controls(client):
    client.post('/demo')
    response = client.get('/spending?example=result')
    assert response.status_code == 200
    html = response.text
    config = config_from(html)
    assert config['mode'] == 'sample' and config['example'] == 'result'
    assert sum(row['amount'] for row in config['rows']) == 891_800
    assert sum(row['amount'] for row in config['rows'] if row['fixed']) == 627_800
    assert len(config['rows']) == 10 and len(config['categories']) == 8
    assert html.count('data-transaction="') == 10
    assert 'accept=".xlsx,.csv"' in html and '최대 2MB' in html
    assert '선택한 파일은 읽거나 전송하지 않아요.' in html
    assert 'class="btn btn-secondary spending-back" href="/plan"' in html
    assert html.count('href="/plan" class="is-active"') == 2
    assert '/static/js/spending.js' in html and '/static/css/spending.css' in html


def test_default_spending_uses_real_preview_without_sample_transactions(client):
    client.post('/demo')
    html = client.get('/spending').text
    config = config_from(html)
    assert config == {'mode': 'preview', 'example': 'idle', 'rows': []}
    assert '/static/js/spending-preview.js' in html
    assert '/static/js/spending.js?' not in html
    assert 'data-mapping-form' in html and 'data-confirm-partial' in html
    assert 'data-transaction="' not in html
    assert '파일을 전송해 내용을 확인해요.' in html
    assert '아직 저장되지 않아요.' in html
    assert 'href="/spending?example=result"' in html


def test_empty_error_examples_and_unknown_case(client):
    client.post('/demo')
    for example in ('empty', 'error'):
        assert config_from(client.get('/spending?example='+example).text)['example'] == example
    assert client.get('/spending?example=unknown').status_code == 422


def test_sample_page_does_not_supply_a_fake_transaction_api(client):
    client.post('/demo')
    assert client.post('/spending').status_code == 405
    for route in ('/home', '/benefits', '/coach', '/settings'):
        html = client.get(route).text
        assert '/static/js/spending.js' not in html and '/static/css/spending.css' not in html
        assert '/static/js/spending-preview.js' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is needed for frontend regressions')
def test_spending_frontend_validation_and_summary():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([shutil.which('node'), '--test', 'tests/frontend/spending.test.cjs', 'tests/frontend/spending-contract.test.cjs', 'tests/frontend/spending-preview.test.cjs'],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
