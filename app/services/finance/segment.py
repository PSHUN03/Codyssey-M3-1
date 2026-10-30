"""진단 결과로 사용자 유형(A~D)을 나누는 규칙 (FR-05). 계산 엔진 결과만 보고 정하며 AI는 쓰지 않는다.

A 적자      꼭 나가는 돈이 실수령액과 같거나 더 많음
D 유지 어려움 지금 매달 넣는 돈이 계획상 저축 가능액보다 많음
B 여력 부족  저축 가능액이 실수령액의 10% 미만
C 여력 있음  그 밖의 경우

A를 가장 먼저, D를 B·C보다 먼저 본다. 적자이면 납입 여부와 관계없이 적자 대응이 먼저이고,
납입 중인 사람은 여력이 적더라도 '유지'가 당장의 문제이기 때문이다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from urllib.parse import quote

from app.services.finance.money import fmt_won
from app.services.text import josa

SEGMENT_RULE_VERSION = "v1"
LOW_SAVING_RATE = 0.10  # 저축 가능액이 실수령액의 10% 미만이면 B

SEGMENTS = {
    "A": {"name": "적자", "rule": "꼭 나가는 돈이 실수령액과 같거나 더 많아요"},
    "B": {"name": "저축 여력 부족", "rule": f"저축할 수 있는 돈이 실수령액의 {int(LOW_SAVING_RATE * 100)}% 미만이에요"},
    "C": {"name": "저축 여력 있음", "rule": f"저축할 수 있는 돈이 실수령액의 {int(LOW_SAVING_RATE * 100)}% 이상이에요"},
    "D": {"name": "저축 유지 어려움", "rule": "지금 매달 넣는 돈이 저축할 수 있는 돈보다 많아요"},
}


@dataclass
class Segment:
    code: str
    name: str
    reason: str
    actions: list[str]
    links: list[dict] = field(default_factory=list)  # {"label", "href"}
    rule_version: str = SEGMENT_RULE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def classify(monthly_income: int, essential: int, total_saving: int, emergency_gap: int = 0,
             saving_monthly: int = 0) -> Segment:
    """계산 엔진이 낸 값(실수령액, 꼭 나가는 돈, 계획상 저축)과 지금 매달 넣는 돈으로 유형을 정한다."""
    income = max(int(monthly_income or 0), 0)
    essential = max(int(essential or 0), 0)
    total_saving = max(int(total_saving or 0), 0)
    saving_monthly = max(int(saving_monthly or 0), 0)
    rate = total_saving / income if income else 0.0

    if income - essential <= 0:
        return _segment(
            "A",
            f"꼭 나가는 돈 {josa(fmt_won(essential), '이/가')} 실수령액 {fmt_won(income)}보다 많거나 같아요.",
            ["저축보다 고정 지출을 먼저 줄여요. 통신비·보험료·구독료처럼 매달 빠지는 돈부터 살펴보세요.",
             "소득이 적어도 받을 수 있는 지원 정책이 있는지 확인해요."],
            [("코치와 지출 줄이기", "/coach?q=매달 나가는 고정 지출을 줄이고 싶어요"), ("받을 수 있는 혜택", "/benefits")],
        )
    if saving_monthly > total_saving:
        return _segment(
            "D",
            f"지금 매달 {josa(fmt_won(saving_monthly), '을/를')} 넣고 있는데, 계획상 저축할 수 있는 돈은 "
            f"{fmt_won(total_saving)}이에요. 모자라는 {josa(fmt_won(saving_monthly - total_saving), '이/가')} "
            "생활비에서 빠지고 있을 수 있어요.",
            ["지금 납입액을 끝까지 낼 수 있는지 먼저 점검해요.",
             "해지하기 전에 납입액을 줄이거나 목표 기간을 늘리는 방법을 검토해요."],
            [("코치와 납입액 조정", "/coach?q=적금 납입액을 계속 낼 수 있을지 점검하고 싶어요"), ("받을 수 있는 혜택", "/benefits")],
        )
    if rate < LOW_SAVING_RATE:
        return _segment(
            "B",
            f"계획상 저축할 수 있는 돈이 월 {fmt_won(total_saving)}으로 실수령액의 {round(rate * 100)}%예요. "
            f"기준({int(LOW_SAVING_RATE * 100)}%)보다 적어요.",
            ["새는 돈을 먼저 찾아요. 배달·구독·카드 할부처럼 줄일 수 있는 지출을 점검해요.",
             "저축 여력이 적어도 받을 수 있는 지원 정책을 확인해요."],
            [("받을 수 있는 혜택", "/benefits"), ("코치와 새는 돈 찾기", "/coach?q=새는 돈을 찾고 싶어요")],
        )
    first = ("비상금을 먼저 채우고, 나머지는 목표에 모아요." if emergency_gap > 0
             else "비상금은 충분하니 저축은 모두 목표에 써요.")
    return _segment(
        "C",
        f"계획상 저축할 수 있는 돈이 월 {fmt_won(total_saving)}으로 실수령액의 {round(rate * 100)}%예요.",
        [first, "청년 혜택으로 같은 돈을 더 크게 모을 수 있는지 확인해요."],
        [("받을 수 있는 혜택", "/benefits"), ("적금으로 계산해 보기", "#simulate-form")],
    )


def _segment(code: str, reason: str, actions: list[str], links: list[tuple[str, str]]) -> Segment:
    def encode(href: str) -> str:
        path, sep, q = href.partition("?q=")
        return f"{path}?q={quote(q)}" if sep else href

    return Segment(code=code, name=SEGMENTS[code]["name"], reason=reason, actions=actions,
                   links=[{"label": label, "href": encode(href)} for label, href in links])
