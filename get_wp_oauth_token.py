"""
WordPress.com OAuth2 access token 발급 도우미 (딱 한 번만 실행하면 됩니다)

이 스크립트를 실행하면:
  1) CLIENT_ID / CLIENT_SECRET을 입력받고
  2) 브라우저 승인용 URL을 보여준 뒤, 승인 후 리다이렉트된 URL에서 code를 붙여넣게 하고
  3) code를 access_token으로 교환하고
  4) 사이트 ID(WP_SITE_ID)까지 자동으로 조회해서
  5) .env에 그대로 붙여넣을 수 있는 형태로 출력해줍니다.

사전 준비 (딱 한 번, 브라우저에서):
  https://developer.wordpress.com/apps/ 접속 -> "Create New Application" 클릭
  - Redirect URLs: http://localhost  (그대로 입력)
  - 나머지 항목은 대충 채워도 무방
  - 저장 후 나오는 Client ID / Client Secret을 복사해둔다

실행:
  python get_wp_oauth_token.py
"""
import os
import urllib.parse

TOKEN_URL = "https://public-api.wordpress.com/oauth2/token"
AUTHORIZE_URL = "https://public-api.wordpress.com/oauth2/authorize"
REDIRECT_URI = "http://localhost"


def _code_flow(client_id, client_secret):
    # 권한 범위: 예전엔 scope=posts(글만)였는데, 그러면 그림 올리기(media)와 카테고리 찾기가 403으로 막혔다
    # (2026-10-31 실제 확인). 기본값은 scope를 비워서 "승인 화면에서 고른 블로그 1개"의 전체 권한을 받는 방식.
    # 다른 블로그에는 접근 못 한다. 안 되면 "posts media"를 입력해 다시 시도.
    scope = input("권한 범위 (그냥 Enter = 블로그 1개 전체 권한 / 예: posts media): ").strip()
    auth_url = (
        f"{AUTHORIZE_URL}?"
        f"client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
        + (f"&scope={urllib.parse.quote(scope)}" if scope else "")
    )

    print("\n1) 아래 URL을 브라우저에 붙여넣어 열고, 로그인 후 Approve(승인)를 누르세요:\n")
    print(auth_url)
    print("\n2) 승인하면 http://localhost/?code=XXXXXXXX 같은 페이지로 이동합니다")
    print("   (페이지 자체는 '연결할 수 없음' 에러가 떠도 정상입니다 - 주소창의 URL만 보면 됩니다)")

    import requests  # 없으면 _run이 설치 안내를 보여 줌
    # code는 한 번만 쓸 수 있고 몇 분 안에 써야 한다. 실패하면 창을 닫지 않고 같은 ID·Secret으로 다시 받게 한다(2026-11-11).
    for attempt in range(1, 4):
        redirected = input("\n3) 리다이렉트된 전체 URL(또는 code= 뒤의 값만)을 붙여넣으세요: ").strip().strip('"\'')
        if "code=" in redirected:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query).get("code", [""])[0]
        else:
            code = redirected  # code 값만 붙여넣은 경우
        code = code.strip()
        if not code:
            print("❌ code를 추출하지 못했습니다. 주소창의 localhost/?code=... 주소 전체를 붙여넣으세요.")
            continue
        # 값 전체는 보이지 않게 앞 4글자와 길이만 - 주소창의 code와 같은지 눈으로 대조용
        print(f"   (읽은 code: {code[:4]}… 길이 {len(code)}자 / Client ID 길이 {len(client_id)}자 / Secret 길이 {len(client_secret)}자)")
        resp = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code",
        })
        if resp.status_code == 200:
            break
        print(f"❌ 토큰 교환 실패: HTTP {resp.status_code} - {resp.text[:500]}")
        if attempt < 3:
            print("   → 위 1)의 주소를 브라우저에서 다시 열어 Connect → 새 localhost 주소를 바로 붙여넣으세요(이 창은 닫지 마세요).")
    else:
        return None

    return resp


def _password_flow(client_id, client_secret):
    # 승인 주소 방식에서 code가 계속 'Invalid authorization_code'로 거절될 때의 예비 방식(2026-11-11).
    # WordPress.com은 앱 주인 본인에 한해 아이디·비밀번호로 토큰을 주고, 이 토큰은 계정 전체(global) 권한이다.
    # 2단계 인증을 켰다면 비밀번호 자리에 '애플리케이션 비밀번호'(WordPress.com 보안 설정에서 만듦)를 넣는다.
    import getpass
    import requests
    username = input("WordPress.com 아이디(또는 이메일): ").strip()
    password = getpass.getpass("비밀번호(입력해도 화면에 안 보입니다): ")
    print(f"   (Client ID 길이 {len(client_id)}자 / Secret 길이 {len(client_secret)}자 / 비밀번호 길이 {len(password)}자)")
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "password",
        "username": username,
        "password": password,
    })
    if resp.status_code != 200:
        print(f"❌ 토큰 발급 실패: HTTP {resp.status_code} - {resp.text[:500]}")
        return None
    return resp


def main():
    print("=" * 60)
    print("WordPress.com OAuth2 토큰 발급 도우미")
    print("=" * 60)

    client_id = input("Client ID를 입력하세요: ").strip()
    client_secret = input("Client Secret을 입력하세요: ").strip()

    mode = input("방식 선택 (그냥 Enter = 승인 주소 방식 / 2 = 아이디·비밀번호 방식): ").strip()
    resp = _password_flow(client_id, client_secret) if mode == "2" else _code_flow(client_id, client_secret)
    if resp is None:
        return

    data = resp.json()
    access_token = data.get("access_token")
    blog_id = data.get("blog_id")
    blog_url = data.get("blog_url")

    if not access_token:
        print(f"❌ 응답에 access_token이 없습니다: {data}")
        return

    print("\n✅ 토큰 발급 성공!")
    print(f"   블로그: {blog_url} (site id: {blog_id})")

    print("\n" + "=" * 60)
    print("아래 두 줄을 .env 파일에 그대로 추가하세요:")
    print("=" * 60)
    print(f"WP_OAUTH_TOKEN={access_token}")
    if blog_id:
        print(f"WP_SITE_ID={blog_id}")
    else:
        print("(WP_SITE_ID는 이번 응답에 없음 - .env의 기존 값을 그대로 두세요)")
    print("=" * 60)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wp_token_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"WP_OAUTH_TOKEN={access_token}\n" + (f"WP_SITE_ID={blog_id}\n" if blog_id else ""))
    print(f"\n(같은 내용을 {out} 에도 저장했습니다 - .env에 옮긴 뒤 이 파일은 지우세요)")
    print("\n참고: 기존 .env의 WP_USERNAME / WP_APP_PASSWORD 줄은 이제 필요 없으니 지워도 됩니다.")
    print("      WP_SITE_URL은 RSS 수집/URL 추정용으로 계속 필요하니 그대로 두세요.")


def _run():
    # 더블클릭으로 실행하면 끝나자마자 창이 닫혀 결과(토큰·오류)를 못 본다(2026-11-11 실제). 끝에서 멈추고,
    # 결과는 같은 폴더의 wp_token_result.txt에도 남긴다.
    try:
        main()
    except Exception as e:  # requests 미설치·네트워크 오류 등도 화면에 남김
        print(f"\n❌ 오류: {type(e).__name__}: {e}")
        if isinstance(e, ModuleNotFoundError):
            print("   → 명령 창에서 'pip install requests' 실행 후 다시 시도하세요.")
    input("\n창을 닫으려면 Enter를 누르세요...")


if __name__ == "__main__":
    _run()
