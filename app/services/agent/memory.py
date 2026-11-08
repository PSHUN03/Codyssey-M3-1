"""장기 메모리 (FR-10, AI-07). 선호·약속·변화를 저장해 다음 대화의 맥락으로 쓴다.

- 저장 항목: 코칭 선호, 스스로 한 약속, 앞으로의 생활 변화 (KINDS)
- 저장하지 않는 것: 금액·부채 같은 재무 수치, 계좌·카드·전화·주민번호 (재무 수치는 프로필에서 따로 관리한다)
- 보관 기간: 코치 대화에 마지막으로 쓰인 지 RETENTION_DAYS일이 지나면 지운다
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Memory, User
from app.security import mask_sensitive
from app.services.agent import llm
from app.services.agent.prompts import MEMORY_EXTRACT_SYSTEM
from app.services.finance.money import find_amounts

KINDS = {"preference": "선호", "commitment": "약속", "fact": "변화"}
MAX_MEMORIES = 50
RETENTION_DAYS = 180  # 마지막 사용 후 6개월
REJECT_REASON = "금액이나 부채 같은 재무 수치, 계좌·연락처는 기억하지 않아요. 숫자는 재무 프로필에서 관리해요."

_FIGURE_RE = re.compile(r"(대출|빚|부채|카드값|연봉|월급|소득|월세|보증금|잔액|이자)\s*[0-9]")


def contains_financial_figure(text: str) -> bool:
    """금액(1천 원 이상), 재무 항목 옆의 숫자, 계좌·카드 같은 민감정보가 있으면 True."""
    if any(amount >= 1_000 for amount in find_amounts(text)):
        return True
    if _FIGURE_RE.search(text):
        return True
    _, masked = mask_sensitive(text)
    return bool(masked)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def purge_expired(db: Session, user: User, now: datetime | None = None) -> int:
    """마지막 사용(없으면 저장 시각) 후 RETENTION_DAYS일이 지난 기억을 지운다."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)
    expired = [m for m in user.memories if _as_utc(m.last_used_at or m.created_at) < cutoff]
    for memory in expired:
        db.delete(memory)
    if expired:
        db.commit()
        db.refresh(user)
    return len(expired)


def mark_used(db: Session, memories: list[Memory]) -> None:
    if not memories:
        return
    now = datetime.now(UTC)
    for memory in memories:
        memory.last_used_at = now
    db.commit()

_COMMIT_RE = re.compile(r"할게|하겠|하기로|안\s*할|줄일게|줄이겠|모을게|아낄게|끊을게|참을게|지킬게")
_PREF_RE = re.compile(r"원금\s*보장|안전한|안정적|위험(은|이|한\s*건)?\s*(싫|부담|무서)|공격적|손해\s*보기\s*싫")
_FACT_RE = re.compile(r"이사|이직|퇴사|입사|결혼|전세\s*계약|만기|대출\s*받")
_FUTURE_RE = re.compile(r"예정|할\s*거|갈\s*거|계획|다음\s*달|내년|곧|[0-9]+월에")


def recent_memories(user: User, limit: int = 10) -> list[Memory]:
    return user.memories[-limit:]


def save_memory(db: Session, user: User, kind: str, content: str) -> Memory | None:
    content = content.strip()[:200]
    if kind not in KINDS or not content or contains_financial_figure(content):
        return None
    if any(m.content == content for m in user.memories):
        return None
    if len(user.memories) >= MAX_MEMORIES:
        db.delete(user.memories[0])  # 가장 오래된 기억부터 정리
    memory = Memory(user_id=user.id, kind=kind, content=content)
    db.add(memory)
    db.commit()
    db.refresh(user)
    return memory


def extract_by_rules(user_text: str) -> list[tuple[str, str]]:
    text = user_text.strip()
    short = text if len(text) <= 80 else text[:77] + "…"
    if _COMMIT_RE.search(text):
        return [("commitment", short)]
    if _PREF_RE.search(text):
        return [("preference", short)]
    if _FACT_RE.search(text) and _FUTURE_RE.search(text):
        return [("fact", short)]
    return []


_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "content": {"type": "string"},
                },
                "required": ["kind", "content"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["memories"],
    "additionalProperties": False,
}


def extract_memories(user_text: str, assistant_text: str) -> list[tuple[str, str]]:
    """경량 모델로 기억할 정보를 추출하고, 실패하거나 모의 모드면 규칙으로 대체한다."""
    data = llm.structured_call(
        MEMORY_EXTRACT_SYSTEM, f"사용자: {user_text}\n\n코치: {assistant_text}", _SCHEMA, max_tokens=800
    )
    if data is None:
        return extract_by_rules(user_text)
    return [(m["kind"], m["content"]) for m in data.get("memories", [])[:2]]
