"""AI 코치 채팅 API — Server-Sent Events 스트리밍 (FR-09, FR-10, FR-11)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, new_session
from app.deps import require_onboarded
from app.models import ChatMessage, ChatSession, User
from app.security import mask_sensitive
from app.services.agent.coach import get_coach
from app.services.agent.guardrails import (
    INVESTMENT_GUARD_REPLY,
    collect_amounts,
    contains_investment_advice,
    unverified_amounts,
)
from app.services.agent.memory import extract_memories, save_memory
from app.services.agent.tools import ToolContext
from app.services.policies.eligibility import KST, today_kst

log = logging.getLogger("sadari.coach")
router = APIRouter(prefix="/api/coach")

HISTORY_TURNS = 12


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _today_count(db: Session, user_id: int) -> int:
    start_kst = datetime.combine(today_kst(), time.min, tzinfo=KST)
    return db.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= start_kst.astimezone(UTC),
        )
    ) or 0


def _coach_session(db: Session, user: User) -> ChatSession:
    sessions = [s for s in user.chat_sessions if s.kind == "coach"]
    if sessions:
        return sessions[-1]
    session = ChatSession(user_id=user.id, kind="coach", state={})
    db.add(session)
    db.commit()
    return session


@router.post("/chat")
def chat(payload: ChatIn, user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    settings = get_settings()
    if _today_count(db, user.id) >= settings.daily_chat_limit:
        return JSONResponse(
            {"detail": f"오늘 코치 대화 한도({settings.daily_chat_limit}회)를 모두 썼어요. 내일 다시 이용해 주세요."},
            status_code=429,
        )

    text, masked_kinds = mask_sensitive(payload.message.strip())
    session = _coach_session(db, user)
    history = [{"role": m.role, "content": m.content} for m in session.messages[-HISTORY_TURNS:]]
    db.add(ChatMessage(session_id=session.id, user_id=user.id, role="user", content=text))
    db.commit()

    return StreamingResponse(
        _stream_reply(user.id, session.id, history, text, masked_kinds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_reply(user_id: int, session_id: int, history: list[dict], text: str, masked: list[str]) -> Iterator[str]:
    # 스트리밍 중에는 요청 의존성의 DB 세션이 이미 닫혔을 수 있으므로 별도 세션을 쓴다
    db = new_session()
    try:
        user = db.get(User, user_id)
        ctx = ToolContext(db=db, user=user)
        if masked:
            yield _sse({"type": "notice", "text": f"{', '.join(masked)}로 보이는 정보는 가린 뒤 전달했어요."})

        parts: list[str] = []
        for event in get_coach().stream(ctx, history, text):
            if event["type"] == "delta":
                parts.append(event["text"])
            yield _sse(event)

        answer = "".join(parts).strip()
        flagged = False
        if contains_investment_advice(answer):
            # 출력 가드레일: 개별 투자상품 권유가 섞이면 안전한 안내문으로 교체한다
            answer, flagged = INVESTMENT_GUARD_REPLY, True
            yield _sse({"type": "replace", "text": answer})
        if not answer:
            answer = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
            yield _sse({"type": "replace", "text": answer})

        # 수치 검증: 도구 결과로 뒷받침되지 않는 금액이 있으면 표시해 검토 대상으로 남긴다
        unverified = unverified_amounts(answer, collect_amounts(ctx.outputs))
        if unverified:
            flagged = True
            log.warning("근거 없는 금액 감지 user=%s amounts=%s", user_id, unverified)

        message = ChatMessage(session_id=session_id, user_id=user_id, role="assistant", content=answer,
                              sources=ctx.sources, tools_used=ctx.tools_used, flagged=flagged)
        db.add(message)
        db.commit()
        yield _sse({"type": "done", "message_id": message.id, "sources": ctx.sources, "tools": ctx.tools_used})

        if not ctx.memories_saved:
            for kind, content in extract_memories(text, answer):
                save_memory(db, user, kind, content)
    except Exception:
        log.exception("코치 응답 처리 실패")
        yield _sse({"type": "error", "text": "답변 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요."})
    finally:
        db.close()
