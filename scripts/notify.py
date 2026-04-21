#!/usr/bin/env python3
"""
매일 낮 12시 KST (03:00 UTC) GitHub Actions로 실행.
카카오 나에게 보내기로 오늘의 게임 링크 전송.
토큰 자동 갱신 + GitHub Secrets 업데이트.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

KAKAO_REST_KEY      = os.environ["KAKAO_REST_KEY"]
KAKAO_REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"]
PAGES_URL           = os.environ["PAGES_URL"]  # https://username.github.io/repo-name
GITHUB_TOKEN        = os.environ["GITHUB_TOKEN"]
GITHUB_REPO         = os.environ["GITHUB_REPOSITORY"]  # owner/repo (자동 제공)

DATA_DIR = Path(__file__).parent.parent / "data"


def refresh_tokens(refresh_token: str) -> dict:
    """refresh_token으로 새 access_token + refresh_token 발급."""
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_KEY,
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def update_github_secret(secret_name: str, secret_value: str):
    """GitHub Secrets 업데이트 (sodium 암호화 없이 gh CLI 사용)."""
    import subprocess
    result = subprocess.run(
        ["gh", "secret", "set", secret_name, "--body", secret_value, "--repo", GITHUB_REPO],
        capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": GITHUB_TOKEN}
    )
    if result.returncode != 0:
        print(f"[notify] Secret 업데이트 실패 ({secret_name}): {result.stderr}", file=sys.stderr)


def send_kakao(access_token: str, title: str, description: str, link: str):
    """카카오 나에게 보내기."""
    leaderboard = link.rsplit("/", 2)[0] + "/leaderboard.html"
    template = {
        "object_type": "text",
        "text": f"🎮 오늘의 게임: {title}\n{description}\n\n👉 게임: {link}\n🏆 전적: {leaderboard}",
        "link": {
            "web_url": link,
            "mobile_web_url": link
        }
    }
    data = urllib.parse.urlencode({
        "template_object": json.dumps(template, ensure_ascii=False)
    }).encode()
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {access_token}"
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        if result.get("result_code") != 0:
            raise Exception(f"카카오 전송 실패: {result}")


def load_today_game() -> dict:
    used_path = DATA_DIR / "used_games.json"
    if not used_path.exists():
        return {}
    games = json.loads(used_path.read_text())
    for g in reversed(games):
        if g["date"] == TODAY:
            return g
    return {}


def main():
    # 1. 토큰 갱신
    print("[notify] 카카오 토큰 갱신 중...")
    try:
        tokens = refresh_tokens(KAKAO_REFRESH_TOKEN)
    except Exception as e:
        print(f"[notify] 토큰 갱신 실패: {e}", file=sys.stderr)
        sys.exit(1)

    access_token = tokens["access_token"]
    new_refresh = tokens.get("refresh_token", KAKAO_REFRESH_TOKEN)

    # 2. 새 refresh_token GitHub Secrets 업데이트
    if tokens.get("refresh_token"):
        print("[notify] refresh_token 갱신됨 — Secrets 업데이트")
        update_github_secret("KAKAO_REFRESH_TOKEN", new_refresh)

    # 3. 오늘 게임 정보
    game = load_today_game()
    if not game:
        title = f"오늘의 게임 — {TODAY}"
        description = "AI가 만든 오늘의 미니게임!"
    else:
        title = game.get("title", f"{game.get('theme','')} {game.get('genre','')}")
        description = f"{game.get('genre', '')} × {game.get('theme', '')} | 태형, 상이, 세준, 영근 중 누가 1등?"

    link = f"{PAGES_URL}/games/{TODAY}.html"

    # 4. 카톡 전송
    print(f"[notify] 전송 중: {title}")
    try:
        send_kakao(access_token, title, description, link)
        print("[notify] 전송 완료")
    except Exception as e:
        print(f"[notify] 전송 실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
