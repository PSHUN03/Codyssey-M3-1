"""발표 자료용 휴대폰 화면 캡처 (750×1624, headless Chrome).

준비: 서버 실행(uvicorn app.main:app) 후 `pip install playwright`
실행: python docs/presentation/capture_screens.py [http://localhost:8000]
결과: docs/presentation/screens/*.jpg → build_deck.py가 읽는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(__file__).resolve().parent / "screens"


def save(page, name: str) -> None:
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f"{name}.jpg"), type="jpeg", quality=88)
    print("저장:", name)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=2,
                                  locale="ko-KR", service_workers="block")
        page = ctx.new_page()

        # 진단 카드는 새 계정으로 (예시 계정은 진단이 끝나 있음)
        page.goto(BASE + "/signup")
        page.fill("input[name=email]", f"deck{id(page)}@example.com")
        page.fill("input[name=nickname]", "민준")
        page.fill("input[name=password]", "deck-password-123")
        page.click("button[type=submit]")
        page.check("#consent-all")
        page.click("#consent-form button[type=submit]")
        page.wait_for_selector("#ob-input")
        page.fill("#ob-input", "26")
        page.keyboard.press("Enter")
        page.click('.choice:text-is("정규직")')
        page.wait_for_timeout(300)
        page.click('.choice:text-is("중소기업")')
        page.wait_for_selector("#ob-input")
        page.fill("#ob-input", "238")
        page.evaluate("document.activeElement.blur()")
        save(page, "00_onboarding")

        ctx.clear_cookies()
        page.goto(BASE + "/")
        page.click("text=예시 계정으로 둘러보기")
        page.wait_for_url("**/home")
        save(page, "01_home")
        page.goto(BASE + "/plan")
        save(page, "02_plan")
        page.goto(BASE + "/benefits/youth-future-savings")
        save(page, "03_benefit")
        page.goto(BASE + "/coach")
        page.fill("#chat-input", "이번 달 30만 원 더 써도 될까요?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.msg.bot .msg-meta') && !document.querySelector('.status-line')")
        page.evaluate("document.activeElement.blur(); window.scrollTo(0, document.body.scrollHeight)")
        save(page, "04_coach")
        browser.close()


if __name__ == "__main__":
    main()
