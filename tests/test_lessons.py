"""금융 기초 학습 카드 (FR-21, PM-05)."""

from app.services import lessons
from tests.conftest import agree, onboard, signup


def test_cards_and_quiz_are_complete():
    data = lessons.load()
    assert len(data["cards"]) == 8
    for card in data["cards"]:
        assert len(card["lines"]) == 3 and card["example"] and card["source"]["url"]
    assert len(data["quiz"]) == 3
    for q in data["quiz"]:
        assert 0 <= q["answer"] < len(q["options"]) and q["explain"]


def test_quiz_numbers_match_engine():
    # 1번 문제의 정답(32만 5천 원)이 계산 엔진 결과와 같아야 한다
    from app.services.finance.savings import simulate_installment

    assert simulate_installment(1_000_000, 12, 0.05).interest == 325_000


def test_learn_page_and_home_entry(client):
    signup(client, "learn@example.com")
    agree(client)
    onboard(client)
    page = client.get("/learn")
    assert page.status_code == 200
    assert "예금자보호는 1억 원까지" in page.text and "답은 저장하지 않아요" in page.text
    assert 'href="/learn"' in client.get("/home").text
