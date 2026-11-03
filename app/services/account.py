"""회원·동의·데모 계정·진단 결과 저장 (FR-01, FR-02, FR-22)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Consent, Profile, User
from app.security import hash_password, verify_password
from app.services import planner
from app.services.agent.memory import save_memory

REQUIRED_CONSENTS = {
    "terms": "서비스 이용약관 동의",
    "privacy": "개인정보 수집·이용 동의 (재무 진단 정보, 대화 내용)",
    "overseas": "AI 처리를 위한 개인정보 국외 이전 동의 (Anthropic, 미국)",
}
OPTIONAL_CONSENTS = {"weekly_email": "주간 체크인 리포트 이메일 수신 (선택)"}
CONSENT_VERSION = "2026-09-30"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    pass


def create_user(db: Session, email: str, password: str, nickname: str) -> User:
    email = email.strip().lower()
    nickname = nickname.strip()
    if not EMAIL_RE.match(email):
        raise AccountError("이메일 형식을 확인해 주세요.")
    if len(password) < 8:
        raise AccountError("비밀번호는 8자 이상이어야 해요.")
    if not 1 <= len(nickname) <= 20:
        raise AccountError("닉네임은 1~20자로 적어 주세요.")
    if db.scalar(select(User).where(User.email == email)):
        raise AccountError("이미 가입된 이메일이에요.")
    user = User(email=email, password_hash=hash_password(password), nickname=nickname)
    db.add(user)
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def record_consents(db: Session, user: User, agreed: dict[str, bool], version: str = CONSENT_VERSION) -> None:
    for kind in {**REQUIRED_CONSENTS, **OPTIONAL_CONSENTS}:
        db.add(Consent(user_id=user.id, kind=kind, agreed=bool(agreed.get(kind)), version=version))
    db.commit()
    db.refresh(user)


def consent_status(user: User) -> dict[str, bool]:
    latest: dict[str, bool] = {}
    for c in sorted(user.consents, key=lambda c: c.id):
        latest[c.kind] = c.agreed
    return latest


def has_required_consents(user: User) -> bool:
    status = consent_status(user)
    return all(status.get(kind) for kind in REQUIRED_CONSENTS)


def delete_account(db: Session, user: User) -> None:
    """탈퇴 시 모든 개인 데이터를 즉시 삭제한다 (NFR-06)."""
    db.delete(user)
    db.commit()


PROFILE_FIELDS = (
    "age", "region", "employment_type", "company_size", "monthly_income", "annual_income", "housing_type",
    "rent", "fixed_costs", "debt_total", "debt_monthly", "savings", "saving_monthly", "goal_text", "goal_amount",
    "goal_months",
)


def apply_profile(db: Session, user: User, answers: dict) -> Profile:
    """진단 결과를 프로필에 저장하고 목표·플랜을 만든다."""
    profile = user.profile or Profile(user_id=user.id)
    for key in PROFILE_FIELDS:
        if key in answers:
            setattr(profile, key, answers[key])
    profile.onboarding_done = True
    if user.profile is None:
        db.add(profile)
    db.commit()
    db.refresh(user)
    if profile.goal_amount and profile.goal_months:
        planner.upsert_goal(db, user, profile.goal_text or "나의 목표", profile.goal_amount, profile.goal_months)
    planner.create_plan(db, user)
    return profile


DEMO_PROFILE = {
    "age": 27, "region": "서울", "employment_type": "정규직", "company_size": "중소기업",
    "monthly_income": 2_450_000, "annual_income": 34_000_000, "housing_type": "월세", "rent": 500_000,
    "fixed_costs": 350_000, "debt_total": 7_000_000, "debt_monthly": 150_000, "savings": 3_000_000,
    "saving_monthly": 200_000, "goal_text": "2년 안에 전세보증금 3천만 원", "goal_amount": 30_000_000, "goal_months": 24,
}


def create_demo_user(db: Session) -> User:
    """가상 페르소나 '지우'로 전체 기능을 체험하는 데모 계정. 방문자마다 따로 만들어 서로 섞이지 않게 한다."""
    user = User(nickname="지우(데모)", is_demo=True)
    db.add(user)
    db.commit()
    record_consents(db, user, {k: True for k in REQUIRED_CONSENTS}, version="demo")
    apply_profile(db, user, DEMO_PROFILE)
    save_memory(db, user, "commitment", "배달 음식은 주 2회까지만 시키기로 함")
    save_memory(db, user, "preference", "원금이 보장되는 상품을 선호함")
    return user
