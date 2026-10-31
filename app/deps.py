"""라우터 공통 의존성: 로그인 → 필수 동의 → 재무 진단 순서로 접근을 제한한다."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.services.account import has_required_consents


class LoginRequired(Exception):
    pass


class ConsentRequired(Exception):
    pass


class OnboardingRequired(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None:
        request.session.clear()
    return user


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_member(user: User = Depends(require_user)) -> User:
    if not has_required_consents(user):
        raise ConsentRequired()
    return user


def require_onboarded(user: User = Depends(require_member)) -> User:
    if user.profile is None or not user.profile.onboarding_done:
        raise OnboardingRequired()
    return user
