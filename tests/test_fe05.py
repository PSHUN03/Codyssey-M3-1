"""FE-05 stays authenticated, sample-only, and preserves the original plan."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def config_from(html):
    match = re.search(r'<script id="receipt-preview-config" type="application/json">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def test_receipts_requires_an_onboarded_session(client):
    response = client.get('/plan/receipts', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'].startswith('/login')


def test_plan_links_to_receipts_and_preserves_its_original_controls(client):
    client.post('/demo')
    html = client.get('/plan').text
    assert 'href="/plan/receipts"' in html
    assert 'id="simulate-form"' in html
    assert 'data-action="regenerate"' in html
    assert 'name="monthly_amount"' in html
    assert '/static/js/receipts.js' not in html


def test_receipts_sample_page_has_camera_form_and_a_direct_return_to_plan(client):
    client.post('/demo')
    response = client.get('/plan/receipts')
    assert response.status_code == 200
    html = response.text
    assert 'capture="environment"' in html
    assert 'accept="image/*"' in html
    assert '최대 5MB' in html
    assert 'AI 인식 · 샘플' in html
    assert 'data-receipt-form' in html
    assert 'data-success-check' in html
    assert 'class="btn btn-secondary receipt-back" href="/plan"' in html
    assert '뒤로가기</a>' in html
    assert '플랜으로</a>' not in html
    assert 'history.back' not in html
    assert html.count('href="/plan" class="is-active"') == 2
    assert '/static/css/receipts.css' in html and '/static/js/receipts.js' in html
    config = config_from(html)
    assert config['mode'] == 'sample' and config['example'] == 'complete'
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', config['sample_date'])


def test_unread_sample_is_explicit_and_unknown_cases_are_rejected(client):
    client.post('/demo')
    assert config_from(client.get('/plan/receipts?example=missing').text)['example'] == 'missing'
    assert client.get('/plan/receipts?example=unknown').status_code == 422


def test_receipt_assets_are_not_loaded_on_unrelated_pages(client):
    client.post('/demo')
    for route in ('/home','/benefits','/coach','/settings'):
        html = client.get(route).text
        assert '/static/css/receipts.css' not in html
        assert '/static/js/receipts.js' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is needed for frontend regressions')
def test_receipt_frontend_validation():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([shutil.which('node'),'--test','tests/frontend/receipts.test.cjs','tests/frontend/receipt-contract.test.cjs'],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
