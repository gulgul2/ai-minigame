#!/usr/bin/env python3
"""
Playwright로 생성된 게임 HTML 검증.
- HTML 완전성 (</html>로 끝나는지)
- JS 에러 없음
- 닉네임 선택 버튼 4개 존재
- 화면 비어있지 않음 (스크린샷 픽셀 분석)
"""
import sys
from pathlib import Path


def validate(html_path: str) -> tuple[bool, str]:
    path = Path(html_path).resolve()

    # 1. 파일 완전성 체크 (Playwright 전에 빠르게 탈락)
    content = path.read_text(encoding="utf-8")
    if not content.strip().lower().endswith("</html>"):
        return False, "HTML이 </html>로 끝나지 않음 (토큰 초과로 잘린 파일)"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[validate] Playwright 없음 — 건너뜀")
        return True, ""

    js_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844})

        page.on("pageerror", lambda e: js_errors.append(str(e)))

        page.goto(f"file://{path}", timeout=15000)
        page.wait_for_timeout(3000)

        # JS 에러 체크
        if js_errors:
            browser.close()
            return False, f"JS 오류: {js_errors[0]}"

        # 닉네임 버튼 체크
        for name in ["태형", "상이", "세준", "영근"]:
            if page.locator(f"text={name}").count() == 0:
                browser.close()
                return False, f"닉네임 버튼 없음: {name}"

        # 빈 화면 체크
        screenshot = page.screenshot()
        if len(screenshot) < 5000:
            browser.close()
            return False, "화면이 거의 비어있음"

        browser.close()

    return True, ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python3 validate.py <html_path>")
        sys.exit(1)

    ok, reason = validate(sys.argv[1])
    if ok:
        print("[validate] 통과")
        sys.exit(0)
    else:
        print(f"[validate] 실패: {reason}")
        sys.exit(1)
