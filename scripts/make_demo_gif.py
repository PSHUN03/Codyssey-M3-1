"""시연 GIF 만들기: 랜딩 계산기 → 질문 카드 진단 → 플랜 → 혜택 → 코치 (모바일 화면, headless Chrome).

준비: 서버 실행(uvicorn app.main:app) 후 `pip install playwright pillow`
실행: python scripts/make_demo_gif.py [http://localhost:8000]
결과: docs/images/demo.gif
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "demo.gif"
WIDTH = 360  # GIF 폭(px). 375px 화면을 살짝 줄여 용량을 낮춘다


def main() -> None:
    frames: list[tuple[Image.Image, int]] = []

    def snap(page, ms: int = 1600) -> None:
        page.wait_for_timeout(350)
        img = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
        frames.append((img, ms))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 375, "height": 760}, device_scale_factor=1,
                                  locale="ko-KR", service_workers="block")
        page = ctx.new_page()

        # 1. 랜딩과 월급 계산기
        page.goto(BASE + "/")
        page.wait_for_selector("#calc-legend li")
        snap(page, 1800)
        page.evaluate("document.querySelector('.calc').scrollIntoView({block: 'start'})")
        snap(page)
        page.fill("input[name=monthly_income]", "300")
        page.wait_for_timeout(700)
        snap(page)

        # 2. 가입 → 질문 카드 진단
        page.goto(BASE + "/signup")
        page.fill("input[name=email]", f"demo{int(time.time() * 1000)}@example.com")
        page.fill("input[name=nickname]", "민준")
        page.fill("input[name=password]", "demo-password-123")
        page.click("button[type=submit]")
        page.check("#consent-all")
        page.click("#consent-form button[type=submit]")
        page.wait_for_selector("#ob-input")
        page.fill("#ob-input", "26")
        snap(page, 1200)
        page.keyboard.press("Enter")
        page.wait_for_selector(".choice")
        page.click('.choice:text-is("정규직")')
        snap(page, 1000)
        page.click('.choice:text-is("중소기업")')
        page.wait_for_selector("#ob-input")
        page.fill("#ob-input", "238")
        page.evaluate("document.activeElement.blur()")
        snap(page, 1400)
        page.click("[data-ob=next]")
        page.click("[data-ob=skip]")
        page.click('.choice:text-is("월세")')
        page.wait_for_selector("#ob-input")
        page.fill("#ob-input", "45")
        page.click("[data-ob=next]")
        page.wait_for_function("document.querySelector('#ob-title').textContent.includes('꼭 나가는')")
        page.fill("#ob-input", "30")
        page.click("[data-ob=next]")
        page.click('.choice:text-is("없어요")')
        page.wait_for_function("document.querySelector('#ob-title').textContent.includes('모아둔')")
        page.fill("#ob-input", "150")
        page.click("[data-ob=next]")
        page.wait_for_selector(".choices.cols-3")
        page.click('.choice:text-is("경기")')
        page.wait_for_selector("#ob-text")
        page.fill("#ob-text", "1년 반 안에 비상금 500만 원")
        page.click("[data-ob=next]")
        page.wait_for_selector("#goal-amount")
        page.evaluate("document.activeElement.blur()")
        snap(page, 1800)
        page.click("[data-ob=goal-ok]")
        page.wait_for_selector(".summary-list")
        snap(page, 1800)
        page.click("[data-ob=submit]")
        page.wait_for_url("**/plan")

        # 3. 플랜 → 혜택 → 코치
        snap(page, 2200)
        page.goto(BASE + "/benefits")
        snap(page, 2000)
        page.goto(BASE + "/coach")
        page.fill("#chat-input", "이번 달 30만 원 더 써도 될까요?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.msg.bot .msg-meta') && !document.querySelector('.status-line')")
        page.evaluate("document.activeElement.blur(); window.scrollTo(0, document.body.scrollHeight)")
        snap(page, 3000)
        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f, _ in frames]
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=[ms for _, ms in frames],
                   loop=0, optimize=True, disposal=1)
    print(f"저장: {OUT} ({OUT.stat().st_size // 1024} KB, {len(frames)}장면)")


if __name__ == "__main__":
    main()
