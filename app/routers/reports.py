"""DATA-04 본인 주간 리포트 조회 API."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_onboarded
from app.models import User, WeeklyReport

router = APIRouter(prefix="/api")

@router.get("/reports/weekly")
def weekly(user: User = Depends(require_onboarded), db: Session = Depends(get_db)):
    report = db.scalar(select(WeeklyReport).where(WeeklyReport.user_id == user.id).order_by(WeeklyReport.week.desc()).limit(1))
    return {"report": {"body": report.body, "week": report.week} if report else None}
