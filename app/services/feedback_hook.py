"""'아쉬워요' 피드백을 n8n 웹훅으로 보내 GitHub Issue를 만든다 (FR-17, n8n/README.md W3).

사용자 응답을 막지 않도록 백그라운드에서 보내고, 실패하면 로그만 남긴다.
이메일·닉네임은 보내지 않고, 질문·답변·의견에 섞인 민감정보는 가린 뒤 보낸다.
이슈가 공개 저장소에 올라가므로 질문·답변 속 금액(소득·지출을 짐작할 수 있는 값)도 [금액]으로 바꾼다.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatMessage, Feedback
from app.security import mask_sensitive

log = logging.getLogger("sadari")

TIMEOUT_SECONDS = 5
MAX_TEXT = 2000
# "30만 원", "2,450,000원", "1억", "250만"처럼 단위가 붙은 금액
_AMOUNT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:억|천만|백만|십만|만|천)\s*원?|\d[\d,]*\s*원")


def _clean(text: str | None) -> str:
    masked, _ = mask_sensitive(text or "")
    return _AMOUNT_RE.sub("[금액]", masked)[:MAX_TEXT]


def build_payload(db: Session, feedback: Feedback, answer: ChatMessage) -> dict:
    """질문(바로 앞 사용자 메시지)·답변·의견만 담는다. 사람을 알아볼 수 있는 값은 넣지 않는다."""
    question = db.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == answer.session_id, ChatMessage.role == "user", ChatMessage.id < answer.id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    return {
        "feedback_id": feedback.id,
        "rating": feedback.rating,
        "comment": _clean(feedback.comment),
        "question": _clean(question.content if question else ""),
        "answer": _clean(answer.content),
        "tools_used": answer.tools_used or [],
        "flagged": answer.flagged,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }


def send(url: str, payload: dict, internal_key: str | None = None) -> None:
    headers = {"Content-Type": "application/json"}
    if internal_key:
        headers["X-Internal-Key"] = internal_key  # n8n에서 사다리가 보낸 요청인지 확인할 때 쓴다
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as res:
            log.info("피드백 웹훅 전송 %s (feedback_id=%s)", res.status, payload.get("feedback_id"))
    except Exception as exc:  # noqa: BLE001 - 웹훅 실패가 서비스 동작을 막으면 안 된다
        log.warning("피드백 웹훅 전송 실패 (feedback_id=%s): %s", payload.get("feedback_id"), exc)
