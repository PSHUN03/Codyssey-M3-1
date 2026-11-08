"""DATA-06 거래내역 미리보기. 원본 및 변환 결과를 저장하지 않는다."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.deps import require_onboarded
from app.models import User
from app.services import transactions

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


