"""DATA-04: 주간 리포트. 수치는 코드로 계산하고 외부 발송은 별도 worker가 담당한다."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ChatMessage, Consent, User, WeeklyReport
from app.services.finance.money import fmt_won


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def generate_reports(db: Session, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    week = week_start((now + timedelta(hours=9)).date()).isoformat()
    reports = []
    for user in db.scalars(select(User).where(User.is_demo.is_(False))):
        profile = user.profile
        if not profile or not profile.onboarding_done:
            continue
        latest_chat = db.scalar(select(ChatMessage.created_at).where(ChatMessage.user_id == user.id)
                                .order_by(ChatMessage.created_at.desc()).limit(1))
        activity = [v for v in (latest_chat, profile.updated_at) if v]
        if not activity or max(_aware(v) for v in activity) < cutoff:
            continue
        consent = db.scalar(select(Consent).where(Consent.user_id == user.id, Consent.kind == "weekly_email")
                            .order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1))
        goal = user.goals[-1] if user.goals else None
        monthly = profile.saving_monthly
        lines = ["이번 주 저축 계획을 점검해 보세요."]
        if goal:
            lines.append(f"목표: {fmt_won(goal.target_amount)}. 월 필요 저축: {fmt_won(goal.monthly_needed)}.")
        if monthly is not None:
            lines.append(f"입력한 월 저축 계획: {fmt_won(monthly)}.")
        lines.append("실제 납입 기록은 아직 연결되지 않아 납입 여부·달성률은 확인할 수 없어요.")
        lines.append("이번 주 실천: 적금 납입 내역을 확인하고 주간 체크를 남겨 주세요.")
        key = hashlib.sha256(f"weekly:{user.id}:{week}".encode()).hexdigest()
        reports.append({"user_id": user.id, "week": week, "idempotency_key": key,
                        "subject": "사다리 이번 주 저축 체크인", "body": "\n".join(lines),
                        "email_allowed": bool(consent and consent.agreed and user.email),
                        "email": user.email if consent and consent.agreed else None,
                        "delivery": "email" if consent and consent.agreed and user.email else "home",
                        "payment_status": "unknown", "by_ai": False})
    return reports


def consent_still_valid(db: Session, user_id: int) -> str | None:
    user = db.get(User, user_id)
    if not user or user.is_demo:
        return None
    latest = db.scalar(select(Consent).where(Consent.user_id == user_id, Consent.kind == "weekly_email")
                       .order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1))
    return user.email if latest and latest.agreed else None


def prepare_reports(db: Session, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    week = week_start((now + timedelta(hours=9)).date()).isoformat()
    for data in generate_reports(db, now=now):
        if db.get(WeeklyReport, data["idempotency_key"]) is None:
            try:
                with db.begin_nested():
                    db.add(WeeklyReport(id=data["idempotency_key"], user_id=data["user_id"], week=data["week"],
                                        body=data["body"], status="pending" if data["email_allowed"] else "home"))
                    db.flush()
            except IntegrityError:
                pass
    db.commit()
    return [{"report_id": r.id} for r in db.scalars(select(WeeklyReport).where(
        WeeklyReport.status == "pending", WeeklyReport.week == week))]


def claim_report(db: Session, report_id: str) -> dict | None:
    report = db.get(WeeklyReport, report_id)
    week = week_start((datetime.now(UTC) + timedelta(hours=9)).date()).isoformat()
    if not report or report.status != "pending" or report.week != week:
        return None
    email = consent_still_valid(db, report.user_id)
    if not email:
        db.execute(update(WeeklyReport).where(WeeklyReport.id == report_id, WeeklyReport.status == "pending")
                   .values(status="cancelled"))
        db.commit()
        return None
    token = secrets.token_urlsafe(24)
    changed = db.execute(update(WeeklyReport).where(WeeklyReport.id == report_id, WeeklyReport.status == "pending")
                         .values(status="claimed", claim_token=token))
    db.commit()
    if changed.rowcount != 1:
        return None
    return {"report_id": report_id, "claim_token": token, "email": email,
            "subject": "사다리 이번 주 저축 체크인", "body": report.body}


def complete_report(db: Session, report_id: str, token: str) -> bool:
    changed = db.execute(update(WeeklyReport).where(WeeklyReport.id == report_id,
                         WeeklyReport.status == "claimed", WeeklyReport.claim_token == token).values(status="sent"))
    db.commit()
    return changed.rowcount == 1
