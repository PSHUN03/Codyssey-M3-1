"""Jinja2 템플릿 렌더링 공통부."""

from __future__ import annotations

import re
import time

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.config import BASE_DIR, get_settings
from app.services.agent.guardrails import AI_NOTICE
from app.services.finance.money import fmt_won

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def render_md(text: str | None) -> Markup:
    """AI 답변용 최소 마크다운(굵게·줄바꿈). HTML은 먼저 이스케이프해 XSS를 막는다. static/js/app.js의 renderMd와 동일."""
    safe = str(escape(text or ""))
    safe = _BOLD_RE.sub(r"<strong>\1</strong>", safe)
    return Markup(safe.replace("\n", "<br>"))


templates.env.filters["won"] = fmt_won
templates.env.filters["md"] = render_md
templates.env.globals["AI_NOTICE"] = AI_NOTICE
# 정적 파일 주소에 붙이는 버전. 배포(재시작)마다 바뀌어 브라우저·서비스 워커 캐시를 무효화한다.
templates.env.globals["asset_version"] = str(int(time.time()))


def render(request: Request, name: str, status_code: int = 200, **context):
    context.setdefault("user", None)
    return templates.TemplateResponse(
        request, name, {"settings": get_settings(), **context}, status_code=status_code
    )
