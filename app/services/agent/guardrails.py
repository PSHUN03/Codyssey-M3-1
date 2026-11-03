"""가드레일 (FR-11): 투자 권유 차단, 수치 검증, AI 생성 표시."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.finance.money import find_amounts

AI_NOTICE = "AI가 만든 답변이라 틀릴 수 있어요. 가입이나 신청 전에는 공식 기관에서 한 번 더 확인해 주세요."

_INVEST_ASSETS = re.compile(
    r"주식|종목|코인|비트코인|이더리움|리플|ETF|etf|펀드|채권|리츠|레버리지|선물|옵션|"
    r"삼성전자|하이닉스|테슬라|엔비디아|애플|나스닥|S&P|s&p"
)
_INVEST_ACTIONS = re.compile(
    r"사도|살까|사야|살래|사면|팔까|팔아|매수|매도|추천|오를까|떨어질까|들어가|올인|타이밍|몰빵|넣어도|넣을까|갈아탈까"
)
_INVEST_DIRECT = re.compile(r"종목\s*(을|좀)?\s*추천|뭐\s*사(야|면)|어디에\s*투자")

_ADVICE_OUTPUT = re.compile(
    r"(매수|매도)(하세요|하시길|하시는\s*걸|를\s*추천|를\s*권)|(사세요|파세요)|추천\s*종목|목표\s*주가|지금\s*(사|매수)하"
)

INVESTMENT_GUARD_REPLY = (
    "특정 종목을 사거나 팔라고 말씀드리기는 어려워요. 개인에게 맞춘 투자 권유는 등록된 투자자문업자만 할 수 있어요.\n\n"
    "투자를 고민 중이라면 이 세 가지를 먼저 확인해 보세요.\n"
    "1. 생활비 3개월치 비상금이 있나요?\n"
    "2. 1~2년 안에 쓸 돈(전세금 같은)은 빼고 남는 돈인가요?\n"
    "3. 한 종목에 몰지 않고 나눠서, 오래 둘 수 있나요?\n\n"
    "비상금과 목표 저축을 빼고 남는 돈이 얼마인지는 계산해 드릴 수 있어요."
)


def is_investment_advice_request(text: str) -> bool:
    return bool(_INVEST_DIRECT.search(text) or (_INVEST_ASSETS.search(text) and _INVEST_ACTIONS.search(text)))


def contains_investment_advice(text: str) -> bool:
    return bool(_ADVICE_OUTPUT.search(text))


def collect_amounts(obj: object) -> set[int]:
    """도구 결과(JSON)에 들어 있는 모든 금액을 모은다. AI 응답의 숫자가 여기에 있으면 '근거 있는 숫자'다."""
    found: set[int] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, int | float):
        found.add(int(obj))
    elif isinstance(obj, str):
        found.update(find_amounts(obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            found |= collect_amounts(value)
    elif isinstance(obj, list | tuple | set):
        for value in obj:
            found |= collect_amounts(value)
    return found


def unverified_amounts(text: str, allowed: Iterable[int], min_amount: int = 10_000) -> list[int]:
    """응답에 나온 금액 중 도구 결과로 뒷받침되지 않는 것 (0.5% 이내 반올림 차이는 허용)."""
    allowed = set(allowed)
    missing = []
    for amount in find_amounts(text):
        if amount < min_amount:
            continue
        if any(abs(amount - a) <= max(1, a * 0.005) for a in allowed):
            continue
        missing.append(amount)
    return missing
