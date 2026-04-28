#!/usr/bin/env python3
"""
매일 오전 6시 KST (21:00 UTC 전날) GitHub Actions로 실행.
장르×테마 조합으로 HTML 미니게임 생성 후 GitHub Pages에 배포.
"""
import json, os, re, sys, subprocess, time
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

GENRES = ["슈팅", "퍼즐", "아케이드", "디펜스", "레이싱", "리듬", "생존", "클리커", "플랫폼", "달리기", "매치3", "낚시", "블록깨기", "퀴즈"]
THEMES = ["우주", "바다", "숲", "도시", "판타지", "음식", "동물", "스포츠", "복고", "미래"]

MAX_RETRIES = 3

# 3번 다 실패했을 때 쓸 폴백 템플릿 (우주 슈터, 날짜만 바꿔서 사용)
FALLBACK_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>우주 슈터 {date}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#000; overflow:hidden; font-family:-apple-system,sans-serif; }}
canvas {{ position:fixed; top:0; left:0; width:100%; height:100%; z-index:1; touch-action:none; }}
#overlay {{
  position:fixed; top:0; left:0; width:100%; height:100%;
  z-index:10; display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  background:radial-gradient(ellipse at center, #0a0a2e 0%, #000 100%);
}}
#overlay h1 {{ color:#fff; font-size:clamp(28px,7vw,48px); font-weight:900; letter-spacing:2px; margin-bottom:8px; }}
#overlay p {{ color:#aaa; font-size:14px; margin-bottom:40px; }}
.nick-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:28px; width:min(320px,80vw); }}
.nick-btn {{
  padding:16px 28px; font-size:18px; font-weight:700; color:#fff;
  background:rgba(255,255,255,0.05); border:2px solid rgba(255,255,255,0.2);
  border-radius:14px; cursor:pointer; transition:all .2s;
}}
.nick-btn.selected {{ border-color:#7b7bff; background:rgba(123,123,255,0.2); color:#7b7bff; }}
#startBtn {{
  display:none; padding:16px 56px; font-size:20px; font-weight:900;
  background:linear-gradient(135deg,#7b7bff,#00d4ff); color:#fff;
  border:none; border-radius:50px; cursor:pointer;
  box-shadow:0 0 30px rgba(123,123,255,0.5);
}}
#hud {{
  position:fixed; top:0; left:0; width:100%; padding:14px 20px;
  display:none; justify-content:space-between; align-items:center;
  z-index:5; background:linear-gradient(to bottom,rgba(0,0,0,.6),transparent);
  pointer-events:none;
}}
#hud.on {{ display:flex; }}
#hud span {{ color:#fff; font-size:16px; font-weight:700; }}
#hud .score {{ font-size:24px; }}
#gameover {{
  position:fixed; top:0; left:0; width:100%; height:100%;
  z-index:10; display:none; flex-direction:column;
  align-items:center; justify-content:center;
  background:rgba(0,0,0,.85);
}}
#gameover.on {{ display:flex; }}
#gameover h2 {{ color:#fff; font-size:clamp(28px,8vw,48px); font-weight:900; margin-bottom:8px; }}
#gameover .myscore {{ color:#7b7bff; font-size:clamp(20px,5vw,32px); margin-bottom:28px; }}
#board {{ color:#eee; font-size:15px; margin-bottom:28px; line-height:2; text-align:center; }}
#retryBtn {{
  padding:14px 48px; font-size:18px; font-weight:900;
  background:linear-gradient(135deg,#7b7bff,#00d4ff); color:#fff;
  border:none; border-radius:50px; cursor:pointer;
}}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="overlay">
  <h1>🚀 우주 슈터</h1>
  <p>화면을 누른 채 움직이면 조종됩니다</p>
  <div class="nick-grid">
    <button class="nick-btn" onclick="pick('태형')">태형</button>
    <button class="nick-btn" onclick="pick('상이')">상이</button>
    <button class="nick-btn" onclick="pick('세준')">세준</button>
    <button class="nick-btn" onclick="pick('영근')">영근</button>
  </div>
  <button id="startBtn" onclick="startGame()">🚀 START</button>
</div>
<div id="hud">
  <span id="nickLabel"></span>
  <span class="score" id="scoreLabel">0</span>
  <span id="livesLabel">❤️❤️❤️</span>
</div>
<div id="gameover">
  <h2>GAME OVER</h2>
  <div class="myscore" id="myScoreLabel"></div>
  <div id="board">리더보드 불러오는 중...</div>
  <button id="retryBtn" onclick="retry()">다시하기</button>
</div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
const SB = window.supabase.createClient('{supabase_url}', '{supabase_key}');
const GAME_DATE = '{date}';
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
let W, H;
function resize() {{ W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; }}
window.addEventListener('resize', resize); resize();
let nickname='', score=0, lives=3, running=false, raf=null, frame=0;
let player, bullets, enemies, particles, stars;
let tx=-1, ty=-1, touching=false, fireTimer=0;
canvas.addEventListener('touchstart', e=>{{ e.preventDefault(); const t=e.touches[0]; touching=true; tx=t.clientX; ty=t.clientY; }}, {{passive:false}});
canvas.addEventListener('touchmove',  e=>{{ e.preventDefault(); const t=e.touches[0]; tx=t.clientX; ty=t.clientY; }}, {{passive:false}});
canvas.addEventListener('touchend',   e=>{{ e.preventDefault(); touching=false; tx=-1; ty=-1; }}, {{passive:false}});
canvas.addEventListener('mousedown',  e=>{{ touching=true; tx=e.clientX; ty=e.clientY; }});
canvas.addEventListener('mousemove',  e=>{{ if(touching){{ tx=e.clientX; ty=e.clientY; }} }});
canvas.addEventListener('mouseup',    ()=>{{ touching=false; tx=-1; ty=-1; }});
function pick(name) {{
  nickname=name;
  document.querySelectorAll('.nick-btn').forEach(b=>b.classList.remove('selected'));
  document.querySelector(`.nick-btn[onclick="pick('${{name}}')"]`).classList.add('selected');
  document.getElementById('startBtn').style.display='block';
}}
function init() {{
  score=0; lives=3; frame=0; fireTimer=0;
  player={{x:W/2, y:H-100, r:20, speed:6}};
  bullets=[]; enemies=[]; particles=[];
  stars=Array.from({{length:80}},()=>{{
    return {{x:Math.random()*W, y:Math.random()*H, s:Math.random()*2+.5, v:Math.random()*1.5+.5}};
  }});
  document.getElementById('scoreLabel').textContent='0';
  document.getElementById('livesLabel').textContent='❤️❤️❤️';
  document.getElementById('nickLabel').textContent='✦ '+nickname;
}}
function startGame() {{
  if(!nickname) return;
  document.getElementById('overlay').style.display='none';
  document.getElementById('gameover').classList.remove('on');
  document.getElementById('hud').classList.add('on');
  init(); running=true;
  if(raf) cancelAnimationFrame(raf); loop();
}}
function retry() {{
  document.getElementById('gameover').classList.remove('on');
  document.getElementById('hud').classList.add('on');
  init(); running=true;
  if(raf) cancelAnimationFrame(raf); loop();
}}
function loop() {{ if(!running) return; update(); draw(); raf=requestAnimationFrame(loop); }}
function update() {{
  frame++;
  stars.forEach(s=>{{ s.y+=s.v; if(s.y>H){{ s.y=0; s.x=Math.random()*W; }} }});
  if(touching && tx>=0) {{
    const dx=tx-player.x, dy=ty-player.y, dist=Math.sqrt(dx*dx+dy*dy);
    if(dist>4) {{ player.x+=(dx/dist)*Math.min(player.speed,dist); player.y+=(dy/dist)*Math.min(player.speed,dist); }}
    player.x=Math.max(player.r,Math.min(W-player.r,player.x));
    player.y=Math.max(player.r,Math.min(H-player.r,player.y));
  }}
  if(touching) fireTimer++; else fireTimer=15;
  if(touching && fireTimer>=15) {{ bullets.push({{x:player.x, y:player.y-player.r, vy:-12}}); fireTimer=0; }}
  bullets=bullets.filter(b=>{{ b.y+=b.vy; return b.y>-10; }});
  const spawnRate=Math.max(28,60-Math.floor(score/100)*3);
  if(frame%spawnRate===0) {{
    const cols=Math.min(3,1+Math.floor(score/200));
    for(let i=0;i<cols;i++) enemies.push({{x:40+Math.random()*(W-80),y:-20,r:18+Math.random()*8,vx:(Math.random()-.5)*2,vy:1.5+Math.random()*1.5+score/500}});
  }}
  enemies.forEach(e=>{{ e.x+=e.vx; e.y+=e.vy; if(e.x<e.r||e.x>W-e.r) e.vx*=-1; }});
  for(let bi=bullets.length-1;bi>=0;bi--) {{
    for(let ei=enemies.length-1;ei>=0;ei--) {{
      const b=bullets[bi], e=enemies[ei];
      if(!b||!e) continue;
      const dx=b.x-e.x, dy=b.y-e.y;
      if(Math.sqrt(dx*dx+dy*dy)<5+e.r) {{
        for(let i=0;i<6;i++) particles.push({{x:e.x,y:e.y,vx:(Math.random()-.5)*5,vy:(Math.random()-.5)*5,life:20,color:`hsl(${{Math.random()*60+10}},100%,60%)`}});
        score+=10; document.getElementById('scoreLabel').textContent=score;
        enemies.splice(ei,1); bullets.splice(bi,1); break;
      }}
    }}
  }}
  for(let ei=enemies.length-1;ei>=0;ei--) {{
    const e=enemies[ei];
    const dx=e.x-player.x, dy=e.y-player.y;
    if(Math.sqrt(dx*dx+dy*dy)<e.r+player.r-6) {{ enemies.splice(ei,1); loseLife(); continue; }}
    if(e.y>H+30) {{ enemies.splice(ei,1); loseLife(); }}
  }}
  particles=particles.filter(p=>{{ p.x+=p.vx; p.y+=p.vy; p.life--; return p.life>0; }});
}}
function loseLife() {{
  lives--;
  const h=['','❤️','❤️❤️','❤️❤️❤️'];
  document.getElementById('livesLabel').textContent=h[Math.max(0,lives)]||'';
  if(lives<=0) gameOver();
}}
function draw() {{
  ctx.fillStyle='#000010'; ctx.fillRect(0,0,W,H);
  stars.forEach(s=>{{ ctx.globalAlpha=s.s/3; ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(s.x,s.y,s.s,0,Math.PI*2); ctx.fill(); }});
  ctx.globalAlpha=1;
  particles.forEach(p=>{{ ctx.globalAlpha=p.life/20; ctx.fillStyle=p.color; ctx.beginPath(); ctx.arc(p.x,p.y,4,0,Math.PI*2); ctx.fill(); }});
  ctx.globalAlpha=1;
  ctx.shadowBlur=8; ctx.shadowColor='#00d4ff'; ctx.fillStyle='#00d4ff';
  bullets.forEach(b=>{{ ctx.beginPath(); ctx.arc(b.x,b.y,5,0,Math.PI*2); ctx.fill(); }});
  ctx.shadowBlur=0;
  ctx.shadowBlur=10; ctx.shadowColor='#ff0000'; ctx.fillStyle='#ff4444';
  enemies.forEach(e=>{{ ctx.beginPath(); ctx.moveTo(e.x,e.y+e.r); ctx.lineTo(e.x-e.r,e.y-e.r); ctx.lineTo(e.x+e.r,e.y-e.r); ctx.closePath(); ctx.fill(); }});
  ctx.shadowBlur=0;
  ctx.shadowBlur=14; ctx.shadowColor='#7b7bff'; ctx.fillStyle='#7b7bff';
  ctx.beginPath(); ctx.moveTo(player.x,player.y-player.r); ctx.lineTo(player.x-player.r,player.y+player.r); ctx.lineTo(player.x+player.r,player.y+player.r); ctx.closePath(); ctx.fill();
  ctx.shadowBlur=0;
  if(touching) {{
    ctx.fillStyle=`hsla(${{frame*10%60+10}},100%,60%,.8)`;
    ctx.beginPath(); ctx.moveTo(player.x-8,player.y+player.r); ctx.lineTo(player.x+8,player.y+player.r); ctx.lineTo(player.x,player.y+player.r+12+Math.random()*8); ctx.closePath(); ctx.fill();
  }}
}}
async function gameOver() {{
  running=false;
  document.getElementById('hud').classList.remove('on');
  document.getElementById('gameover').classList.add('on');
  document.getElementById('myScoreLabel').textContent=`${{nickname}}의 점수: ${{score}}점`;
  try {{ await SB.from('scores').insert({{game_date:GAME_DATE, nickname, score}}); }} catch(e) {{}}
  try {{
    const {{data}} = await SB.from('scores').select('nickname, score').eq('game_date',GAME_DATE).order('score',{{ascending:false}}).limit(5);
    if(data && data.length) {{
      document.getElementById('board').innerHTML='<b style="color:#7b7bff">오늘의 리더보드</b><br>'+data.map((r,i)=>`${{['🥇','🥈','🥉','4️⃣','5️⃣'][i]}} ${{r.nickname}} — ${{r.score}}점`).join('<br>');
    }} else {{ document.getElementById('board').textContent='아직 기록 없음'; }}
  }} catch(e) {{ document.getElementById('board').textContent='리더보드 오류'; }}
}}
</script>
</body>
</html>"""


def load_used_games() -> list:
    if USED_GAMES_FILE.exists():
        return json.loads(USED_GAMES_FILE.read_text())
    return []


def save_used_games(used: list):
    USED_GAMES_FILE.write_text(json.dumps(used, ensure_ascii=False, indent=2))


def pick_combo(used: list) -> tuple[str, str]:
    import random
    used_set = {(g["genre"], g["theme"]) for g in used}
    remaining = [(g, t) for g in GENRES for t in THEMES if (g, t) not in used_set]
    if not remaining:
        # 전부 사용했으면 초기화
        save_used_games([])
        remaining = [(g, t) for g in GENRES for t in THEMES]
    return random.choice(remaining)


def is_html_complete(html: str) -> bool:
    """HTML이 정상적으로 끝났는지 확인 (잘린 파일 감지)."""
    stripped = html.strip().lower()
    return stripped.endswith("</html>")


def generate_game(genre: str, theme: str, attempt: int = 1) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""HTML5 모바일 게임을 만들어줘. 단일 파일, 300줄 이내로 간결하게 작성해.

장르: {genre} / 테마: {theme} / 날짜: {TODAY}

## 필수 구조 (이 순서 그대로)

1. 닉네임 선택 화면: 태형/상이/세준/영근 버튼 → START 버튼
2. 게임 화면: canvas + 점수 HUD
3. 게임 오버 화면: 점수 + 리더보드 + 다시하기

## 기술 규칙
- canvas: position:fixed; top:0; left:0; z-index:1; width:100%; height:100%;
- 닉네임/게임오버 화면: position:fixed; z-index:10;
- canvas에 touchstart/touchmove/touchend + mousedown/mousemove/mouseup 이벤트 등록 (필수)
- 외부 라이브러리 금지 (Supabase CDN 제외)

## Supabase (그대로 붙여넣기)
```
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
const SB = window.supabase.createClient('{SUPABASE_URL}', '{SUPABASE_ANON_KEY}');
// 점수 저장: SB.from('scores').insert({{game_date:'{TODAY}', nickname, score}})
// 리더보드: SB.from('scores').select('nickname,score').eq('game_date','{TODAY}').order('score',{{ascending:false}}).limit(5)
```

코드만 출력. <!DOCTYPE html>부터 </html>까지. 마크다운 블록 없이."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}]
    )

    html = message.content[0].text.strip()
    # 마크다운 블록 제거
    if html.startswith("```"):
        lines = html.split("\n")
        html = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return html


def validate_game(html_path: Path) -> tuple[bool, str]:
    """HTML 완전성 체크 → Playwright 검증 순서로 실행."""
    # 1. 파일 레벨 완전성 체크 (잘린 파일 즉시 탈락)
    content = html_path.read_text(encoding="utf-8")
    if not is_html_complete(content):
        return False, "HTML이 </html>로 끝나지 않음 (토큰 초과로 잘린 파일)"

    # 2. Playwright 브라우저 검증
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


def make_fallback(genre: str, theme: str) -> str:
    """AI 생성 실패 시 폴백 우주 슈터 반환."""
    return FALLBACK_TEMPLATE.format(
        date=TODAY,
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_ANON_KEY,
    )


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
    # 오늘 게임이 이미 존재하면 재생성 금지
    game_path = GAMES_DIR / f"{TODAY}.html"
    if game_path.exists():
        print(f"[generate] 오늘 게임 이미 존재 ({TODAY}.html) — 스킵")
        used = load_used_games()
        today_game = next((g for g in reversed(used) if g["date"] == TODAY), None)
        title = today_game["title"] if today_game else f"게임 {TODAY}"
        env_file = os.environ.get("GITHUB_ENV", "")
        if env_file:
            with open(env_file, "a") as f:
                f.write(f"GAME_TITLE={title}\n")
                f.write(f"GAME_DATE={TODAY}\n")
        sys.exit(0)

    used = load_used_games()
    genre, theme = pick_combo(used)
    print(f"[generate] 오늘의 게임: {genre} × {theme}")

    html = None
    last_error = ""
    used_fallback = False

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[generate] 생성 시도 {attempt}/{MAX_RETRIES}...")
        try:
            html = generate_game(genre, theme, attempt)
        except Exception as e:
            last_error = str(e)
            print(f"[generate] API 오류: {e}")
            time.sleep(10)
            continue

        # 완전성 체크 (잘린 파일 즉시 재시도)
        if not is_html_complete(html):
            last_error = "HTML이 </html>로 끝나지 않음"
            print(f"[generate] 잘린 파일 감지 — 재시도")
            html = None
            continue

        # 게임 파일 저장 후 Playwright 검증
        game_path.write_text(html, encoding="utf-8")
        ok, reason = validate_game(game_path)
        if ok:
            print(f"[generate] 검증 통과")
            break
        else:
            print(f"[generate] 검증 실패: {reason}")
            last_error = reason
            html = None

    # 3번 다 실패 → 폴백 사용
    if html is None:
        print(f"[generate] AI 생성 {MAX_RETRIES}번 실패 — 폴백 사용 (우주 슈터)")
        html = make_fallback(genre, theme)
        game_path.write_text(html, encoding="utf-8")
        used_fallback = True

    # 제목 추출
    title = f"{theme} {genre}"
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
    if used_fallback:
        title = f"우주 슈터 ({theme})"

    # used_games 업데이트
    used.append({"date": TODAY, "genre": genre, "theme": theme, "title": title})
    save_used_games(used)

    # index.html 업데이트
    update_index(genre, theme)

    print(f"[generate] 완료: {title}{' (폴백)' if used_fallback else ''}")
    env_file = os.environ.get("GITHUB_ENV", "")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"GAME_TITLE={title}\n")
            f.write(f"GAME_DATE={TODAY}\n")
            f.write(f"GAME_GENRE={genre}\n")
            f.write(f"GAME_THEME={theme}\n")


if __name__ == "__main__":
    main()
