"""담당 기능 연결용 API. 업로드 파일·원문은 DB/디스크에 보관하지 않는다."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, WeeklyReport
from app.services import savings_products, transactions


def create_router(require_onboarded) -> APIRouter:
    """로그인·동의·진단을 검사하는 앱 의존성을 전달해 라우터를 생성한다."""
    router = APIRouter(prefix="/api")


    @router.post("/transactions/preview")
    async def preview(file: UploadFile = File(...), mapping: str | None = Form(None),
                      header_row: int | None = Form(None), user: User = Depends(require_onboarded)):
        content = await file.read(transactions.MAX_BYTES + 1)
        try:
            columns = json.loads(mapping) if mapping else None
            structured_call = None
            if not get_settings().is_mock:
                from app.services.agent.llm import structured_call
            return transactions.parse_transactions(content, file.filename or "", mapping=columns, header_row=header_row,
                                                   structured_call=structured_call)
        except ValueError:
            raise HTTPException(status_code=422, detail="파일 크기·형식 또는 컬럼 매핑을 확인해 주세요.") from None
        finally:
            await file.close()


    @router.get("/products/compare")
    def compare(term_months: int = 12, product_type: str = "savings", user: User = Depends(require_onboarded)):
        try:
            return savings_products.compare_savings_products(term_months, product_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except savings_products.ProductAPIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None


    @router.get("/reports/weekly")
    def weekly(user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
        report = db.scalar(select(WeeklyReport).where(WeeklyReport.user_id == user.id)
                           .order_by(WeeklyReport.week.desc()).limit(1))
        return {"report": {"body": report.body, "week": report.week} if report else None}

    return router
