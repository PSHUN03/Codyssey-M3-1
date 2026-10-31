"""FastAPI 앱 진입점. 실행: uvicorn app.main:app --reload"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, get_settings
from app.db import init_engine
from app.deps import ConsentRequired, LoginRequired, OnboardingRequired
from app.routers import api, auth, coach, internal, onboarding, pages, public
from app.web import render

STATIC_DIR = BASE_DIR / "static"


def _is_api(request: Request) -> bool:
    return request.url.path.startswith(("/api/", "/internal/"))


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_engine(settings.database_url)

    app = FastAPI(
        title="사다리 API",
        description="청년을 위한 개인별 자산관리 AI 코치",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="sadari_session",
        same_site="lax",
        https_only=settings.is_production,
        max_age=14 * 24 * 3600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for module in (auth, pages, onboarding, public, coach, api, internal):
        app.include_router(module.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "llm_provider": settings.llm_provider}

    # 서비스 워커는 루트 경로에서 제공해야 앱 전체를 범위로 가진다 (PWA)
    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(STATIC_DIR / "js" / "sw.js", media_type="text/javascript",
                            headers={"Service-Worker-Allowed": "/"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.exception_handler(LoginRequired)
    async def on_login_required(request: Request, exc: LoginRequired):
        if _is_api(request):
            return JSONResponse({"detail": "로그인이 필요해요."}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(ConsentRequired)
    async def on_consent_required(request: Request, exc: ConsentRequired):
        if _is_api(request):
            return JSONResponse({"detail": "필수 약관 동의가 필요해요."}, status_code=403)
        return RedirectResponse("/consent", status_code=303)

    @app.exception_handler(OnboardingRequired)
    async def on_onboarding_required(request: Request, exc: OnboardingRequired):
        if _is_api(request):
            return JSONResponse({"detail": "재무 진단을 먼저 마쳐 주세요."}, status_code=409)
        return RedirectResponse("/onboarding", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        if _is_api(request) or exc.status_code not in (404, 500):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return render(request, "error.html", status_code=exc.status_code, code=exc.status_code)

    return app


app = create_app()
