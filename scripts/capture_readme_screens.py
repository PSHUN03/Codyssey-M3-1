"""README용 실제 구동 화면 캡처 (모바일 375×812, 2배, headless Chrome).

배포본에서 예시 계정으로 찍는다. 가입은 하지 않는다.
코치 화면은 실제 AI에 질문 1개, 영수증 화면은 가상 영수증 r01을 실제 인식 API에 보낸다.

    python scripts/capture_readme_screens.py [https://sadari.onrender.com]

결과: docs/images/screens/*.jpg
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://sadari.onrender.com").rstrip("/")
OUT = ROOT / "docs" / "images" / "screens"
CSV = "거래일,적요,출금액,입금액\n2026-10-01,스타벅스 둔산점,5800,\n2026-10-02,월세 이체,500000,\n2026-10-03,가짜회사 급여,,2450000\n2026-10-04,넷플릭스,13500,\n2026-10-06,배달의민족,23000,\n2026-10-08,지하철,1450,\n2026-10-11,쿠팡,38900,\n2026-10-15,가짜통신 요금,55000,\n"


def save(page, name: str, full: bool = False) -> None:
    page.wait_for_timeout(700)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.screenshot(path=str(OUT / f"{name}.jpg"), type="jpeg", quality=85, full_page=full)
    print("저장:", name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_sample.csv"
    tmp.write_text("﻿" + CSV, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=2,
                                  locale="ko-KR", service_workers="block")
        page = ctx.new_page()
        page.set_default_timeout(120_000)

        page.goto(BASE + "/", wait_until="domcontentloaded")
        save(page, "01_landing")

        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.click("text=예시 계정으로 둘러보기")
        page.wait_for_url("**/home")
        save(page, "02_home")

        page.goto(BASE + "/plan", wait_until="domcontentloaded")
        save(page, "03_plan")

        page.goto(BASE + "/benefits", wait_until="domcontentloaded")
        save(page, "04_benefits")

        page.goto(BASE + "/coach", wait_until="domcontentloaded")
        page.fill("#chat-input", "이번 달 30만 원 더 써도 될까요?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.msg.bot .msg-meta') && !document.querySelector('.status-line')",
                               timeout=120_000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        save(page, "05_coach")

        page.goto(BASE + "/spending", wait_until="domcontentloaded")
        page.set_input_files("[data-file-input]", str(tmp))
        page.click("[data-analyze]")
        page.wait_for_selector("[data-analysis]:not([hidden])")
        page.evaluate("document.querySelector('[data-analysis]').scrollIntoView({block: 'start'})")
        save(page, "06_spending")

        page.goto(BASE + "/plan/receipts", wait_until="domcontentloaded")
        page.set_input_files("[data-photo-input]", str(ROOT / "eval" / "receipts" / "r01.jpg"))
        page.click("[data-scan]")
        page.wait_for_function("document.querySelector('#receipt-amount') && document.querySelector('#receipt-amount').value === '6150'",
                               timeout=120_000)
        page.evaluate("document.querySelector('[data-result-panel]').scrollIntoView({block: 'start'})")
        save(page, "07_receipt")

        page.goto(BASE + "/progress", wait_until="domcontentloaded")
        page.wait_for_function("!/불러오고/.test(document.querySelector('[data-fe01-percent]').textContent)")
        save(page, "08_progress")
        browser.close()
    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
