"""n8n 등 내부 자동화 전용 API. X-Internal-Key 헤더로 인증한다.

여기에 추가할 엔드포인트 (docs/tasks/05_RAG_자동화.md):
- POST /internal/policies/ingest   정책 데이터 수집·갱신 (FR-18)
- POST /internal/reports/weekly    주간 체크인 리포트 생성 (FR-15)
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import weekly_reports
from app.services.policies import ingest, youthcenter

router = APIRouter(prefix="/internal")


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = get_settings().internal_api_key
    if not expected or not hmac.compare_digest(x_internal_key or "", expected):
        raise HTTPException(status_code=401, detail="내부 API 키가 올바르지 않습니다.")


@router.get("/ping", dependencies=[Depends(require_internal_key)])
def ping():
    """n8n에서 연결을 확인할 때 쓴다."""
    return {"ok": True}


@router.post("/policies/ingest", dependencies=[Depends(require_internal_key)])
def ingest_policies():
    try:
        return ingest.ingest(youthcenter.fetch_policies())
    except youthcenter.PolicyAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/reports/weekly", dependencies=[Depends(require_internal_key)])
def prepare_weekly(db: Session = Depends(get_db)):
    return {"reports": weekly_reports.prepare_reports(db)}


@router.post("/reports/{report_id}/claim", dependencies=[Depends(require_internal_key)])
def claim_weekly(report_id: str, db: Session = Depends(get_db)):
    return {"report": weekly_reports.claim_report(db, report_id)}


class DeliveryIn(BaseModel):
    claim_token: str = Field(min_length=20, max_length=64)


@router.post("/reports/{report_id}/complete", dependencies=[Depends(require_internal_key)])
def complete_weekly(report_id: str, payload: DeliveryIn, db: Session = Depends(get_db)):
    if not weekly_reports.complete_report(db, report_id, payload.claim_token):
        raise HTTPException(status_code=409, detail="유효한 발송 건이 아닙니다.")
    return {"ok": True}
