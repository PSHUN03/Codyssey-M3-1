"""n8n 등 내부 자동화 전용 API. X-Internal-Key 헤더로 인증한다.

여기에 추가할 엔드포인트 (docs/tasks/05_RAG_자동화.md):
- POST /internal/policies/ingest   정책 데이터 수집·갱신 (FR-18)
- POST /internal/reports/weekly    주간 체크인 리포트 생성 (FR-15)
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings

router = APIRouter(prefix="/internal")


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = get_settings().internal_api_key
    if not expected or not hmac.compare_digest(x_internal_key or "", expected):
        raise HTTPException(status_code=401, detail="내부 API 키가 올바르지 않습니다.")


@router.get("/ping", dependencies=[Depends(require_internal_key)])
def ping():
    """n8n에서 연결을 확인할 때 쓴다."""
    return {"ok": True}
