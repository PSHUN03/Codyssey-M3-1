"""환경변수 기반 설정. 비밀값(API 키 등)은 코드와 저장소에 넣지 않는다."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

load_dotenv(PROJECT_DIR / ".env")

log = logging.getLogger("sadari")

PROVIDERS = {"mock", "anthropic"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    database_url: str
    llm_provider: str
    coach_model: str
    fast_model: str
    coach_effort: str
    refusal_fallback: bool
    daily_chat_limit: int
    internal_api_key: str | None

    @property
    def is_mock(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        # API 키가 없으면 모의 AI 모드로 동작해 키 없이도 전체 흐름을 확인할 수 있다
        provider = "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "mock"
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER는 {sorted(PROVIDERS)} 중 하나여야 합니다: {provider}")

    secret = os.getenv("SECRET_KEY")
    if not secret:
        secret = secrets.token_urlsafe(32)
        log.warning("SECRET_KEY가 없어 임시 키를 사용합니다. 서버가 재시작되면 로그인이 풀립니다.")

    return Settings(
        env=os.getenv("APP_ENV", "development"),
        secret_key=secret,
        database_url=os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_DIR / 'sadari.db'}",
        llm_provider=provider,
        coach_model=os.getenv("COACH_MODEL") or "claude-opus-5-5",
        fast_model=os.getenv("FAST_MODEL") or "claude-haiku-4-5",
        coach_effort=os.getenv("COACH_EFFORT") or "medium",
        refusal_fallback=(os.getenv("REFUSAL_FALLBACK") or "true").lower() != "false",
        daily_chat_limit=_int("DAILY_CHAT_LIMIT", 50),
        internal_api_key=os.getenv("INTERNAL_API_KEY") or None,
    )
