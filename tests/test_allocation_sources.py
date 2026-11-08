"""배분 기준과 출처 표시 (BE-06)."""

from tests.conftest import agree, onboard, signup


def test_plan_shows_allocation_rules_and_sources(client):
    signup(client, "sources@example.test")
    agree(client)
    onboard(client)
    page = client.get("/plan").text
    assert "배분 기준과 출처" in page
    assert "korea.kr/news/customizedNewsView.do?newsId=148920502" in page
    assert "kbthink.com/savings/basics/savings-ratio.html" in page
    assert "공식 기준은 없어요" in page  # 근거를 찾지 못한 값은 그렇다고 밝힌다
