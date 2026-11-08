"""거래내역 미리보기(DATA-06)와 저장·요약(BE-01). 원본 파일은 저장하지 않는다."""
import json
from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_onboarded
from app.models import User
from app.services import spending, transactions

router = APIRouter(prefix="/api")


async def _parse(file: UploadFile, mapping: str | None, header_row: int | None) -> dict:
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


@router.post("/transactions/preview")
async def preview(file: UploadFile = File(...), mapping: str | None = Form(None),
                  header_row: int | None = Form(None), user: User = Depends(require_onboarded)):
    return await _parse(file, mapping, header_row)


@router.post("/transactions/upload")
async def upload(file: UploadFile = File(...), mapping: str | None = Form(None), header_row: int | None = Form(None),
                 user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    """미리보기와 같은 변환을 거쳐 거래를 저장한다. 컬럼을 고르지 못한 파일은 저장하지 않고 미리보기를 돌려준다."""
    parsed = await _parse(file, mapping, header_row)
    if parsed["needs_mapping"]:
        return {**parsed, "saved": 0, "skipped": 0}
    result = spending.save_transactions(db, user, parsed["transactions"])
    return {"needs_mapping": False, **result, "errors": parsed["errors"]}


class PreviewedTransaction(BaseModel):
    date: Date
    merchant: str = Field(max_length=2000)
    amount: int = Field(ge=-100_000_000, le=100_000_000)
    category: Literal["식비", "교통", "쇼핑", "주거", "의료", "교육", "통신", "문화", "기타", "수입"]


class SaveRequest(BaseModel):
    transactions: list[PreviewedTransaction] = Field(min_length=1, max_length=transactions.MAX_ROWS)


@router.post("/transactions/save")
def save_previewed(body: SaveRequest, user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    """미리보기에서 확인한 거래(분류 수정 포함)를 저장한다. 가맹점명은 한 번 더 가리고, 0원 거래는 건너뛴다."""
    rows = [
        {"date": t.date.isoformat(), "merchant": transactions.redact(t.merchant)[:200], "amount": t.amount,
         "category": "수입" if t.amount > 0 else ("기타" if t.category == "수입" else t.category)}
        for t in body.transactions if t.amount != 0
    ]
    result = spending.save_transactions(db, user, rows)
    months = sorted({row["date"][:7] for row in rows})
    return {**result, "months": months}


@router.get("/transactions/summary")
def summary(month: str | None = Query(None, description="YYYY-MM, 비우면 가장 최근 달"),
            user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    try:
        return spending.summary(db, user, month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
