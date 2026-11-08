"""Claude 호출 사용량 기록 (AI-05, NFR-08).

호출마다 모델, 입력·출력·캐시 토큰, 지연 시간, 사용한 도구를 로그와 `llm_usage` 테이블에 남긴다.
사용자 식별 정보와 대화 내용은 기록하지 않는다. 기록이 실패해도 답변 흐름은 막지 않는다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import new_session
from app.models import LlmUsage

log = logging.getLogger("sadari.usage")


def _tokens(usage: object, name: str) -> int:
    return int(getattr(usage, name, 0) or 0)


def record(kind: str, model: str, usage: object, latency_ms: float,
           tools: list[str] | None = None, stop_reason: str | None = None) -> None:
    """SDK 응답의 `usage`를 받아 한 줄 로그와 DB 행으로 남긴다."""
    row = LlmUsage(
        kind=kind,
        model=model,
        input_tokens=_tokens(usage, "input_tokens"),
        output_tokens=_tokens(usage, "output_tokens"),
        cache_read_tokens=_tokens(usage, "cache_read_input_tokens"),
        cache_write_tokens=_tokens(usage, "cache_creation_input_tokens"),
        latency_ms=int(latency_ms),
        tools=list(tools or []),
        stop_reason=stop_reason,
    )
    log.info(
        "llm_usage kind=%s model=%s in=%d out=%d cache_read=%d cache_write=%d latency_ms=%d tools=%s stop=%s",
        row.kind, row.model, row.input_tokens, row.output_tokens, row.cache_read_tokens,
        row.cache_write_tokens, row.latency_ms, ",".join(row.tools) or "-", stop_reason or "-",
    )
    try:
        with new_session() as db:
            db.add(row)
            db.commit()
    except Exception:  # noqa: BLE001 - 사용량 기록 실패가 답변을 막으면 안 된다
        log.exception("사용량 기록 실패")


def summary(db: Session, days: int = 7) -> dict:
    """최근 days일 동안의 모델·용도별 호출 수, 토큰 합계, 평균 지연 시간."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(
            LlmUsage.model,
            LlmUsage.kind,
            func.count(),
            func.sum(LlmUsage.input_tokens),
            func.sum(LlmUsage.output_tokens),
            func.sum(LlmUsage.cache_read_tokens),
            func.sum(LlmUsage.cache_write_tokens),
            func.avg(LlmUsage.latency_ms),
        )
        .where(LlmUsage.created_at >= since)
        .group_by(LlmUsage.model, LlmUsage.kind)
        .order_by(LlmUsage.model, LlmUsage.kind)
    ).all()
    items = [
        {
            "model": model,
            "kind": kind,
            "calls": calls,
            "input_tokens": int(inp or 0),
            "output_tokens": int(out or 0),
            "cache_read_tokens": int(cr or 0),
            "cache_write_tokens": int(cw or 0),
            "avg_latency_ms": round(float(lat or 0)),
        }
        for model, kind, calls, inp, out, cr, cw, lat in rows
    ]
    totals = {
        key: sum(i[key] for i in items)
        for key in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    }
    return {"days": days, "since": since.isoformat(), "items": items, "totals": totals}
