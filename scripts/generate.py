#!/usr/bin/env python3
"""
매일 오전 7시 KST (22:00 UTC 전날) GitHub Actions로 실행.
장르×테마 조합으로 HTML 미니게임 생성 후 GitHub Pages에 배포.
"""
import json, os, sys, subprocess, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

ROOT = Path(__file__).parent.parent
USED_GAMES_FILE = ROOT / "data" / "used_games.json"
GAMES_DIR = ROOT / "games"
INDEX_HTML = ROOT / "index.html"

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

GENRES = ["슈팅", "퍼즐", "아케이드", "디펜스", "레이싱", "리듬", "생존", "클리커", "플랫폼", "캐주얼"]
THEMES = ["우주", "바다", "숲", "도시", "판타지", "음식", "동물", "스포츠", "복고", "미래"]

MAX_RETRIES = 3


def load_used_games() -> list:
    if USED_GAMES_FILE.exists():
        return json.loads(USED_GAMES_FILE.read_text())
    return []


def save_used_games(used: list):
    USED_GAMES_FILE.write_text(json.dumps(used, ensure_ascii=False, indent=2))


def pick_combo(used: list) -> tuple[str, str]:
    used_set = {(g["genre"], g["theme"]) for g in used}
    for genre in GENRES:
        for theme in THEMES:
            if (genre, theme) not in used_set:
                return genre, theme
    # 전부 사용했으면 초기화
    save_used_games([])
    return GENRES[0], THEMES[0]


def generate_game(genre: str, theme: str, attempt: int = 1) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""다음 스펙에 맞는 HTML5 모바일 게임을 만들어줘.

## 게임 정보
- 장르: {genre}
- 테마: {theme}
- 날짜: {TODAY}
- 시도: {attempt}번째 (품질 높게)

## 필수 화면 구성

### 1. 닉네임 선택 화면 (시작 시)
- 게임 제목 표시
- 버튼 4개: 태형, 상이, 세준, 영근
- 풀스크린, 깔끔한 디자인

### 2. 게임 화면
- 점수 실시간 표시 (우상단)
- 개인 최고기록 표시
- 터치로 조작

### 3. 게임 오버 화면
- 내 점수
- 오늘의 리더보드 상위 5명
- 다시하기 버튼

## 기술 요구사항
- 단일 HTML 파일 (CSS/JS 인라인, Supabase CDN 제외 외부 라이브러리 금지)
- 반드시 포함: <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
- 게임 캔버스 CSS 반드시: position:fixed; top:0; left:0; z-index:2; (터치 이벤트가 캔버스에 닿으려면 필수)
- 터치 이벤트 addEventListener('touchstart'), addEventListener('touchmove'), addEventListener('touchend') 반드시 canvas에 등록할 것 — 변수만 선언하고 등록 안 하면 절대 안 됨
- 마우스 이벤트 addEventListener('mousedown'), addEventListener('mousemove'), addEventListener('mouseup')도 병행 등록
- localStorage로 개인 최고기록 저장 (key: "best_{TODAY}")
- 점수는 정수

## Supabase 연동 코드 (그대로 사용)
```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
const _supabase = window.supabase.createClient('{SUPABASE_URL}', '{SUPABASE_ANON_KEY}');

async function saveScore(nickname, score) {{
  await _supabase.from('scores').insert({{
    game_date: '{TODAY}',
    nickname: nickname,
    score: score
  }});
}}

async function getLeaderboard() {{
  const {{ data }} = await _supabase
    .from('scores')
    .select('nickname, score')
    .eq('game_date', '{TODAY}')
    .order('score', {{ ascending: false }})
    .limit(5);
  return data || [];
}}
</script>
```

## 게임 디자인 원칙
- 점점 어려워지는 난이도 곡선
- 즉각적인 시각 피드백 (파티클, 색상 변화 등)
- 명확한 게임 오버 조건
- 5~10분 플레이 가능한 중독성

HTML 코드만 출력해. ```html 블록 없이 <!DOCTYPE html>부터 바로 시작해."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    html = message.content[0].text.strip()
    # 혹시 마크다운 블록으로 감싸진 경우 제거
    if html.startswith("```"):
        lines = html.split("\n")
        html = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return html


def validate_game(html_path: Path) -> tuple[bool, str]:
    """Playwright로 게임 HTML 검증. (True, "") 또는 (False, 이유) 반환."""
    try:
        result = subprocess.run(
            ["python3", str(Path(__file__).parent / "validate.py"), str(html_path)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return False, str(e)


def update_index(genre: str, theme: str):
    used = load_used_games()
    games = sorted(used, key=lambda x: x["date"], reverse=True)

    rows = "\n".join(
        f'      <tr>'
        f'<td><a href="games/{g["date"]}.html">{g["date"]}</a></td>'
        f'<td>{g["genre"]}</td>'
        f'<td>{g["theme"]}</td>'
        f'<td>{g["title"]}</td>'
        f'</tr>'
        for g in games
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI 미니게임 아카이브</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0f0f0f; color: #eee; }}
    h1 {{ color: #fff; }}
    .today {{ background: #1a1a2e; border: 1px solid #4a4a8a; border-radius: 12px; padding: 20px; margin-bottom: 30px; }}
    .today a {{ color: #7b7bff; font-size: 1.2em; text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: 10px; border-bottom: 1px solid #333; color: #888; }}
    td {{ padding: 10px; border-bottom: 1px solid #222; }}
    td a {{ color: #7b7bff; text-decoration: none; }}
    td a:hover {{ color: #fff; }}
  </style>
</head>
<body>
  <h1>AI 미니게임 아카이브</h1>
  {'<div class="today"><strong>오늘의 게임</strong><br><a href="games/' + TODAY + '.html">▶ ' + (games[0]["title"] if games else "") + '</a></div>' if games else ""}
  <table>
    <thead><tr><th>날짜</th><th>장르</th><th>테마</th><th>제목</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>"""

    INDEX_HTML.write_text(html, encoding="utf-8")


def main():
    used = load_used_games()
    genre, theme = pick_combo(used)
    print(f"[generate] 오늘의 게임: {genre} × {theme}")

    html = None
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[generate] 생성 시도 {attempt}/{MAX_RETRIES}...")
        try:
            html = generate_game(genre, theme, attempt)
        except Exception as e:
            last_error = str(e)
            print(f"[generate] API 오류: {e}")
            time.sleep(10)
            continue

        # 게임 파일 임시 저장
        game_path = GAMES_DIR / f"{TODAY}.html"
        game_path.write_text(html, encoding="utf-8")

        # 검증
        ok, reason = validate_game(game_path)
        if ok:
            print(f"[generate] 검증 통과")
            break
        else:
            print(f"[generate] 검증 실패: {reason}")
            last_error = reason
            html = None

    if html is None:
        print(f"[generate] FAILED: {last_error}", file=sys.stderr)
        sys.exit(1)

    # 제목 추출 (title 태그)
    title = f"{theme} {genre}"
    import re
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    if m:
        title = m.group(1).strip()

    # used_games 업데이트
    used.append({"date": TODAY, "genre": genre, "theme": theme, "title": title})
    save_used_games(used)

    # index.html 업데이트
    update_index(genre, theme)

    print(f"[generate] 완료: {title}")
    # GitHub Actions 환경변수로 제목 전달
    env_file = os.environ.get("GITHUB_ENV", "")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"GAME_TITLE={title}\n")
            f.write(f"GAME_DATE={TODAY}\n")
            f.write(f"GAME_GENRE={genre}\n")
            f.write(f"GAME_THEME={theme}\n")


if __name__ == "__main__":
    main()
