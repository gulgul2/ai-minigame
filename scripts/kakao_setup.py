#!/usr/bin/env python3
"""
카카오 토큰 최초 발급 헬퍼.
한 번만 실행하면 됨. 발급된 토큰을 GitHub Secrets에 등록.

실행: python3 scripts/kakao_setup.py
"""
import json, urllib.request, urllib.parse, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

REDIRECT_URI = "http://localhost:9999/callback"
auth_code = None


def get_rest_key():
    key = input("카카오 REST API 키를 입력하세요: ").strip()
    return key


def open_auth_page(rest_key: str):
    params = urllib.parse.urlencode({
        "client_id": rest_key,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "talk_message"
    })
    url = f"https://kauth.kakao.com/oauth/authorize?{params}"
    print(f"\n브라우저가 열립니다. 카카오 로그인 후 인증하세요.")
    webbrowser.open(url)


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>인증 완료! 터미널로 돌아가세요.</h2>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


def get_tokens(rest_key: str, code: str) -> dict:
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }).encode()
    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    rest_key = get_rest_key()
    open_auth_page(rest_key)

    print("로컬 콜백 서버 시작 (포트 9999)...")
    server = HTTPServer(("localhost", 9999), CallbackHandler)
    server.handle_request()

    if not auth_code:
        print("인증 코드를 받지 못했습니다.")
        return

    print("토큰 발급 중...")
    tokens = get_tokens(rest_key, auth_code)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    print("\n" + "="*50)
    print("GitHub Secrets에 아래 값들을 등록하세요:")
    print("="*50)
    print(f"KAKAO_REST_KEY     = {rest_key}")
    print(f"KAKAO_REFRESH_TOKEN = {refresh_token}")
    print("="*50)
    print(f"\naccess_token (참고용): {access_token}")
    print("\n* access_token은 Secrets 불필요. notify.py가 매번 refresh_token으로 갱신함.")


if __name__ == "__main__":
    main()
