"""AI-02 영수증 인식 API. 사진과 인식 결과를 저장하지 않는다 (저장은 사용자가 확인한 뒤 별도 단계)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.deps import require_onboarded
from app.models import User
from app.services import receipts

router = APIRouter(prefix="/api")


@router.post("/receipts/scan")
async def scan_receipt(file: UploadFile = File(...), user: User = Depends(require_onboarded)):
    content = await file.read(receipts.MAX_BYTES + 1)
    await file.close()
    vision_call = None
    if not get_settings().is_mock:
        from app.services.agent.llm import vision_structured_call as vision_call
    try:
        return receipts.scan(content, vision_call=vision_call)
    except receipts.ReceiptError as exc:
        status = 413 if len(content) > receipts.MAX_BYTES else 422
        raise HTTPException(status_code=status, detail=str(exc)) from None
