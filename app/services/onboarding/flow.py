"""재무 진단 질문 카드 (FR-03).

한 화면에 질문 하나씩 보여준다. 선택형·금액형 답은 버튼과 숫자 입력으로 받고,
목표처럼 자유롭게 적는 답만 규칙 해석 → 실패 시 LLM 추출(llm_extract)로 정리한 뒤
사용자가 확인·수정하게 한다. 질문 정의는 이 파일 한 곳에서 관리하고 화면은 API로 받아 그린다.
"""

from __future__ import annotations

import re

from app.services.finance.money import (
    find_duration_months,
    is_negative_answer,
    is_unknown_answer,
    parse_amount,
)

REGIONS = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
           "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
EMPLOYMENT_TYPES = ["정규직", "계약직", "프리랜서", "아르바이트", "자영업", "취업준비"]
COMPANY_SIZES = ["중소기업", "중견기업", "대기업", "공공기관"]
HOUSING_TYPES = ["부모님", "월세", "전세", "자가", "기타"]

# type: number | choice | amount(만 원 단위로 입력, min/max도 만 원) | text(AI가 해석)
# label: 마지막 확인 화면에 보여줄 짧은 이름
# when: {"다른 질문 key": [허용 값...]} 을 만족할 때만 묻는다
QUESTIONS: list[dict] = [
    {"key": "age", "label": "나이", "type": "number", "title": "만 나이를 알려 주세요",
     "help": "청년 정책은 대부분 만 19~34세가 대상이에요.", "unit": "세", "min": 15, "max": 60, "placeholder": "27"},
    {"key": "employment_type", "label": "일하는 형태", "type": "choice", "title": "지금 어떻게 일하고 있나요?",
     "options": [["정규직", "정규직"], ["계약직", "계약직·인턴"], ["프리랜서", "프리랜서"],
                 ["아르바이트", "아르바이트"], ["자영업", "자영업"], ["취업준비", "취업 준비 중"]]},
    {"key": "company_size", "label": "회사 규모", "type": "choice", "title": "회사 규모는요?",
     "help": "중소기업에 다니면 소득세를 줄여 주는 제도가 있어요.",
     "options": [["중소기업", "중소기업"], ["중견기업", "중견기업"], ["대기업", "대기업"],
                 ["공공기관", "공공기관"], ["", "잘 모르겠어요"]],
     "when": {"employment_type": ["정규직", "계약직"]}},
    {"key": "monthly_income", "label": "월 실수령액", "type": "amount", "title": "한 달에 실제로 받는 돈은요?",
     "help": "세금과 4대 보험을 뗀 실수령액이에요.", "placeholder": "245", "allow_zero": True, "max": 5000},
    {"key": "annual_income", "label": "세전 연봉", "type": "amount", "title": "세전 연봉은 얼마쯤인가요?",
     "help": "정책 자격을 확인할 때만 써요.", "placeholder": "3400", "optional": True, "skip_label": "잘 모르겠어요",
     "min": 100, "max": 100000},
    {"key": "housing_type", "label": "사는 곳", "type": "choice", "title": "지금 어디에 살고 있나요?",
     "options": [["부모님", "부모님 집"], ["월세", "월세"], ["전세", "전세"], ["자가", "내 집"], ["기타", "기숙사·기타"]]},
    {"key": "rent", "label": "월세", "type": "amount", "title": "월세는 얼마인가요?", "help": "관리비는 빼고 알려 주세요.",
     "placeholder": "50", "max": 500, "when": {"housing_type": ["월세"]}},
    {"key": "fixed_costs", "label": "고정비", "type": "amount", "title": "매달 꼭 나가는 돈은요?",
     "help": "통신비, 보험료, 교통비, 구독료를 합친 금액이에요. 월세는 빼고요.", "placeholder": "35", "allow_zero": True, "max": 1000},
    {"key": "has_debt", "label": "대출", "type": "choice", "title": "갚고 있는 대출이 있나요?", "help": "학자금, 신용대출, 카드론을 모두 포함해요.",
     "options": [["yes", "있어요"], ["no", "없어요"]]},
    {"key": "debt_total", "label": "남은 대출", "type": "amount", "title": "남은 대출은 얼마인가요?", "placeholder": "700",
     "max": 1000000, "when": {"has_debt": ["yes"]}},
    {"key": "debt_monthly", "label": "월 상환액", "type": "amount", "title": "매달 얼마씩 갚고 있나요?", "placeholder": "15",
     "max": 1000, "when": {"has_debt": ["yes"]}},
    {"key": "savings", "label": "모아둔 돈", "type": "amount", "title": "지금까지 모아둔 돈은요?",
     "help": "예금, 적금, 비상금을 합친 금액이에요.", "placeholder": "300", "allow_zero": True, "max": 1000000},
    {"key": "saving_monthly", "label": "매달 저축", "type": "amount", "title": "지금 매달 적금이나 저축에 넣는 돈은요?",
     "help": "자동이체로 빠지는 적금·청약을 합친 금액이에요. 없으면 0을 적어 주세요.", "placeholder": "30",
     "allow_zero": True, "max": 1000},
    {"key": "region", "label": "지역", "type": "choice", "title": "어느 지역에 살고 있나요?", "columns": 3,
     "options": [[r, r] for r in REGIONS]},
    {"key": "goal", "label": "목표", "type": "text", "title": "가장 먼저 이루고 싶은 목표는요?",
     "help": "금액과 기간을 함께 적어 주세요. 문장을 읽고 금액과 기간을 정리해 드려요.",
     "placeholder": "2년 안에 전세보증금 3천만 원", "optional": True, "skip_label": "아직 없어요"},
]


def parse_goal(text: str) -> dict | None:
    """목표 문장에서 금액·기간을 뽑는다. 금액을 못 찾으면 None."""
    if is_negative_answer(text) or is_unknown_answer(text):
        return None
    amount = parse_amount(text, assume_manwon=True)
    if amount is None or amount < 100_000:
        return None
    months = find_duration_months(text)
    if months is None and re.search(r"내년", text):
        months = 12
    return {"goal_text": text.strip()[:100], "goal_amount": amount, "goal_months": months}


def prefill(profile) -> dict:
    """진단을 다시 할 때 기존 답을 채워 넣는다. 금액은 화면과 같은 만 원 단위로 돌려준다."""
    if profile is None:
        return {}
    def manwon(v):
        return None if v is None else round(v / 10_000)
    has_debt = None if profile.debt_total is None else ("yes" if profile.debt_total > 0 else "no")
    return {
        "age": profile.age, "employment_type": profile.employment_type, "company_size": profile.company_size,
        "monthly_income": manwon(profile.monthly_income), "annual_income": manwon(profile.annual_income),
        "housing_type": profile.housing_type, "rent": manwon(profile.rent), "fixed_costs": manwon(profile.fixed_costs),
        "has_debt": has_debt, "debt_total": manwon(profile.debt_total), "debt_monthly": manwon(profile.debt_monthly),
        "savings": manwon(profile.savings), "saving_monthly": manwon(profile.saving_monthly), "region": profile.region,
        "goal": {"goal_text": profile.goal_text, "goal_amount": profile.goal_amount, "goal_months": profile.goal_months}
        if profile.goal_amount else None,
    }
