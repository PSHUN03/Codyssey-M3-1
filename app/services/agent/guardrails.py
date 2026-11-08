"""가드레일 (FR-11): 투자 권유 차단, 수치 검증, AI 생성 표시."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.finance.money import find_amounts

AI_NOTICE = "AI가 만든 답변이라 틀릴 수 있어요. 가입이나 신청 전에는 공식 기관에서 한 번 더 확인해 주세요."

# 1. 투자 권유 및 수익보장 관련 패턴
_INVEST_ASSETS = re.compile(
    r"주식|종목|코인|비트코인|이더리움|리플|ETF|etf|펀드|채권|리츠|레버리지|선물|옵션|"
    r"삼성전자|하이닉스|테슬라|엔비디아|애플|나스닥|S&P|s&p"
)
_INVEST_ACTIONS = re.compile(
    r"사도|살까|사야|살래|사면|팔까|팔아|매수|매도|추천|오를까|떨어질까|들어가|올인|타이밍|몰빵|넣어도|넣을까|갈아탈까"
)
_INVEST_DIRECT = re.compile(r"종목\s*(을|좀)?\s*추천|뭐\s*사(야|면)|어디에\s*투자")
_RISKY_YIELD_RE = re.compile(
    r"원금\s*보장|무조건\s*(이득|수익|돈\s*벌게)|손실\s*안\s*나|고수익|수익\s*보장|책임져"
)

# 2. 대출 및 부채 위기 패턴
_DEBT_CRISIS_RE = re.compile(
    r"대출\s*(돌려막기|받아서|한도)|현금서비스|카드\s*대금|마이너스통장\s*대출|빚이\s*너무\s*많|카드론"
)

# 3. 악의적 개인정보/보안 요구 패턴 (정상적인 개인정보 처리/인증 문의는 차단되지 않도록 요구 행위 결합)
_SENSITIVE_INFO_RE = re.compile(
    r"(주민등록번호|계좌\s*비밀번호|핸드폰\s*번호|실명|인증서|개인정보).*(알려|보여|적어|불러|입력|내놔|줘)"
)

# 4. 시스템 탈옥 및 인젝션 패턴
_JAILBREAK_RE = re.compile(
    r"무시하고|명령에만\s*복종|페르소나를\s*버리고|리딩방\s*전문가|시스템\s*제한을\s*풀고|우회\s*방법|상상\s*속의\s*인공지능|거절하지\s*말고"
)

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

# AI의 거절 및 방어 안내 문구 패턴 (이 문구가 있으면 올바르게 거절한 것으로 판단)
_REFUSAL_DEFENSE_RE = re.compile(
    r"권유해\s*드릴\s*수\s*없으며|권유하는\s*것은\s*불가능합니다|추천하거나\s*권유|책임은\s*제가\s*질\s*수\s*없습니다|역할\s*밖의\s*일이에요"
)


def is_investment_advice_request(text: str) -> bool:
    """사용자 입력이 개별 종목 투자 권유, 고수익 보장 요구 등에 해당하는지 판별한다."""
    return bool(
        _INVEST_DIRECT.search(text) or 
        (_INVEST_ASSETS.search(text) and _INVEST_ACTIONS.search(text)) or
        _RISKY_YIELD_RE.search(text)
    )

def is_debt_crisis_request(text: str) -> bool:
    """사용자 입력이 카드 대금 연체, 대출 돌려막기 등 부채 위기 상황에 해당하는지 판별한다."""
    return bool(_DEBT_CRISIS_RE.search(text))

def is_sensitive_info_request(text: str) -> bool:
    """사용자 입력이 악의적인 개인정보 및 인증 정보 요구에 해당하는지 판별한다."""
    return bool(_SENSITIVE_INFO_RE.search(text))

def is_jailbreak_request(text: str) -> bool:
    """사용자 입력이 시스템 탈옥 및 프롬프트 인젝션 시도에 해당하는지 판별한다."""
    return bool(_JAILBREAK_RE.search(text))

def contains_investment_advice(text: str) -> bool:
    """답변에 명시적인 매수·매도 권유가 있는지 판별한다.

    거절 문구가 함께 있어도 권유 문장이 있으면 위반이다. 상품 이름만 나오는 설명(IRP 안의 펀드 등)은 막지 않는다."""
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

def enforce_verified_amounts(text: str, allowed: Iterable[int]) -> str:
    """근거 없는 금액(환각 수치)이 포함된 경우, 
    위험한 문자열 기반 숫자 치환 대신 안전한 주의 문구를 덧붙여 보정한다."""
    allowed_list = list(allowed)
    missing = unverified_amounts(text, allowed_list)
    if not missing:
        return text
    
    # 숫자를 억지로 고치는 대신, 검증되지 않은 금액이 감지되었음을 알리는 주의 문구를 추가합니다.
    warning_msg = "\n\n(※ 안내된 금액 중 일부는 검증되지 않은 수치가 포함되어 있으니 가입 전 공식 기관에서 다시 확인해 주세요.)"
    if warning_msg not in text:
        return text + warning_msg
    return text