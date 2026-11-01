"""Empty-state regressions found during the FE-03 accessibility audit."""

from app.routers import pages


def test_empty_benefits_has_message_outside_desktop_detail(client, monkeypatch):
    client.post("/demo")
    monkeypatch.setattr(pages, "_matches", lambda user: [])

    response = client.get("/benefits")

    assert response.status_code == 200
    # The desktop detail panel is hidden on mobile. The list itself must explain
    # an empty result and provide a recovery link at every screen width.
    listing = response.text.split('<ul class="benefit-list">', 1)[1].split("</ul>", 1)[0]
    assert 'role="status"' in listing
    assert "지금 조건으로 찾은 혜택이 없어요" in listing
    assert 'href="/settings"' in listing


def test_missing_plan_preserves_generation_action(client, monkeypatch):
    client.post("/demo")
    monkeypatch.setattr(pages.planner, "latest_plan", lambda user: None)

    for path in ("/home", "/plan"):
        response = client.get(path)
        assert response.status_code == 200
        assert "아직 플랜이 없어요" in response.text
        assert 'data-action="regenerate"' in response.text
