"""회원가입·로그인·데모·동의 (폼 기반)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, require_user
from app.models import User
from app.services import account
from app.web import render

router = APIRouter()


def next_step(user: User) -> str:
    if not account.has_required_consents(user):
        return "/consent"
    if user.profile is None or not user.profile.onboarding_done:
        return "/onboarding"
    return "/home"


def _login(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id


@router.get("/signup")
def signup_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse(next_step(user), status_code=303)
    return render(request, "auth.html", mode="signup")


@router.post("/signup")
def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user = account.create_user(db, email, password, nickname)
    except account.AccountError as exc:
        return render(request, "auth.html", status_code=400, mode="signup", error=str(exc),
                      form={"email": email, "nickname": nickname})
    _login(request, user)
    return RedirectResponse("/consent", status_code=303)


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse(next_step(user), status_code=303)
    return render(request, "auth.html", mode="login")


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = account.authenticate(db, email, password)
    if user is None:
        return render(request, "auth.html", status_code=400, mode="login",
                      error="이메일 또는 비밀번호가 맞지 않아요.", form={"email": email})
    _login(request, user)
    return RedirectResponse(next_step(user), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.post("/demo")
def demo(request: Request, db: Session = Depends(get_db)):
    user = account.create_demo_user(db)
    _login(request, user)
    return RedirectResponse("/home", status_code=303)


@router.get("/consent")
def consent_page(request: Request, user: User = Depends(require_user)):
    return render(request, "consent.html", user=user, required=account.REQUIRED_CONSENTS,
                  optional=account.OPTIONAL_CONSENTS, status=account.consent_status(user))


@router.post("/consent")
async def consent_submit(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    agreed = {kind: form.get(kind) == "on" for kind in {**account.REQUIRED_CONSENTS, **account.OPTIONAL_CONSENTS}}
    if not all(agreed[k] for k in account.REQUIRED_CONSENTS):
        return render(request, "consent.html", status_code=400, user=user, required=account.REQUIRED_CONSENTS,
                      optional=account.OPTIONAL_CONSENTS, status=agreed,
                      error="필수 항목에 모두 동의해야 서비스를 이용할 수 있어요.")
    account.record_consents(db, user, agreed)
    return RedirectResponse(next_step(user), status_code=303)
