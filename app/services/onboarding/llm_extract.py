"""규칙으로 해석하지 못한 목표 문장을 경량 LLM으로 정리한다. 결과는 같은 범위 규칙으로 다시 검증한다."""

from __future__ import annotations

from app.services.agent import llm
from app.services.agent.prompts import ONBOARDING_EXTRACT_SYSTEM

_INT = llm.nullable({"type": "integer"})
_GOAL_SCHEMA = {
    "type": "object",
    "properties": {"goal_text": {"type": "string"}, "goal_amount_won": _INT, "goal_months": _INT},
    "required": ["goal_text", "goal_amount_won", "goal_months"],
    "additionalProperties": False,
}


def extract_goal(text: str) -> dict | None:
    data = llm.structured_call(
        ONBOARDING_EXTRACT_SYSTEM,
        f"질문: 가장 먼저 이루고 싶은 돈 목표는요?\n추출할 항목: 목표 설명, 목표 금액(원), 기간(개월)\n사용자 답변: {text}",
        _GOAL_SCHEMA, max_tokens=400,
    )
    if not data:
        return None
    amount = data.get("goal_amount_won")
    if not amount or amount < 100_000:
        return None
    months = data.get("goal_months")
    if months is not None and not 1 <= months <= 240:
        months = None
    return {"goal_text": (data.get("goal_text") or text).strip()[:100], "goal_amount": amount, "goal_months": months}
