"""Claude API 호출 공통부.

API 키는 코드에서 다루지 않는다. SDK가 환경변수 ANTHROPIC_API_KEY를 직접 읽는다.
모의 모드(LLM_PROVIDER=mock)에서는 이 모듈의 함수가 None을 돌려주고, 호출부는 규칙 기반 로직으로 대체한다.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import anthropic

from app.config import get_settings

log = logging.getLogger("sadari.llm")

# 안전 분류기가 응답을 거절하면 서버가 다른 모델로 자동 재시도하도록 하는 베타 기능
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}


@lru_cache
def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(timeout=90.0, max_retries=2)


def supports_effort(model: str) -> bool:
    # Haiku 4.5는 effort 파라미터를 지원하지 않는다
    return not model.startswith("claude-haiku")


def use_fallback(model: str) -> bool:
    return get_settings().refusal_fallback and model in FALLBACK_MODELS


def structured_call(system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict | None:
    """경량 모델로 JSON 스키마에 맞는 결과를 받는다. 실패하면 None을 돌려준다."""
    settings = get_settings()
    if settings.is_mock:
        return None
    try:
        response = client().messages.create(
            model=settings.fast_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIError as exc:
        log.warning("structured_call 실패: %s", exc)
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def text_call(system: str, user: str, max_tokens: int = 2000) -> str | None:
    """경량 모델로 짧은 글(플랜 설명 등)을 생성한다. 실패하면 None."""
    settings = get_settings()
    if settings.is_mock:
        return None
    try:
        response = client().messages.create(
            model=settings.fast_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as exc:
        log.warning("text_call 실패: %s", exc)
        return None
    if response.stop_reason == "refusal":
        return None
    return "".join(b.text for b in response.content if b.type == "text").strip() or None


def nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}
