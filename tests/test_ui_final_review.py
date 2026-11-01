"""Regressions for FE-03 preview selection, empty chat and feedback markup."""

import re

from app.services.policies import repository


def test_every_benefit_can_be_selected_without_opening_detail(client):
    client.post("/demo")
    for policy in repository.all_policies():
        response = client.get("/benefits", params={"selected": policy["id"]})
        assert response.status_code == 200
        preview = re.search(r'<aside[^>]+id="benefit-preview"[^>]*>(.*?)</aside>', response.text, re.S)
        assert preview, policy["id"]
        assert f'<h2>{policy["name"]}</h2>' in preview.group(1)
        assert f'href="/benefits/{policy["id"]}"' in preview.group(1)
        assert f'data-benefit-select="{policy["id"]}"' in response.text
        assert "내용보기" in response.text


def test_unknown_benefit_preview_falls_back_to_a_real_policy(client):
    client.post("/demo")
    response = client.get("/benefits", params={"selected": "missing-policy"})
    assert response.status_code == 200
    assert 'id="benefit-preview"' in response.text
    assert 'class="benefit-preview-content"' in response.text
    assert 'href="/benefits/missing-policy"' not in response.text


def test_empty_chat_has_guidance_in_composer_and_accessible_description(client):
    client.post("/demo")
    response = client.get("/coach")
    assert response.status_code == 200
    assert "coach-is-empty" in response.text
    assert 'class="msg bot"' not in response.text
    assert "아직 대화가 없어요" not in response.text
    assert 'placeholder="지우(데모)님 플랜을 보고 답해 드려요.' in response.text
    assert 'aria-describedby="coach-input-help"' in response.text
    assert 'id="coach-feedback"' in response.text
    assert 'role="log" aria-live="polite"' in response.text


def test_profile_fields_keep_native_fallback_and_required_input(client):
    client.post("/demo")
    response = client.get("/settings")
    assert response.status_code == 200
    assert response.text.count("data-profile-select") == 4
    assert 'for="profile-company"' in response.text
    assert 'name="company_size" id="profile-company"' in response.text
    assert 'name="age" inputmode="numeric" autocomplete="off" required' in response.text
    assert 'id="profile-status"' in response.text
    assert 'id="memory-status"' in response.text
    assert 'class="card settings-account"' in response.text
    assert '>삭제</button>' in response.text
    assert '>수정</a>' in response.text


def test_plan_uses_only_the_two_column_layout_and_full_width_simulator(client):
    client.post("/demo")
    response = client.get("/plan")
    assert response.status_code == 200
    assert 'class="card span-12 plan-simulator"' in response.text
    assert 'class="card span-7' not in response.text
    assert 'class="card span-5' not in response.text
    assert "매달 넣을 돈과 기간을 입력하고 계산하기를 눌러 주세요." in response.text


def test_common_page_feedback_is_available_for_public_and_member_pages(client):
    for route in ("/", "/login", "/signup", "/privacy", "/terms"):
        response = client.get(route)
        assert response.status_code == 200
        assert 'id="page-feedback"' in response.text
    client.post("/demo")
    for route in ("/home", "/plan", "/benefits", "/coach", "/settings"):
        response = client.get(route)
        assert response.status_code == 200
        assert 'id="page-feedback"' in response.text
