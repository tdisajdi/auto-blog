"""IndexNow - 새 글·바뀐 글 주소를 빙 등 참여 검색엔진에 바로 알림(2026-11-22 다시 살림, 계정 불필요).
- 키는 공개 값(규격상 사이트에 걸어 둠): 전용 플러그인(wp_plugin/ondo-polylang-rest)이 https://ondo99.com/<KEY>.txt 로 돌려줌.
- 실패해도 공개·번역은 그대로(덧붙이는 알림일 뿐).
- 구글은 IndexNow를 안 받음(사이트맵·서치콘솔로). 네이버·다음은 사용자 계정 등록이 따로 필요할 수 있음.
"""
HOST = "ondo99.com"
KEY = "6816a36f143a41b8a683b233a22b322f"
KEY_URL = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"


def payload(urls):
    urls = [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith(f"https://{HOST}/")]
    return {"host": HOST, "key": KEY, "keyLocation": KEY_URL, "urlList": urls[:10000]}


def submit(urls, post=None):
    """(성공?, 한 줄). post: 시험에서 바꿔 끼움."""
    body = payload(urls)
    if not body["urlList"]:
        return False, "보낼 주소 없음(우리 사이트 주소만)"
    try:
        if post is None:
            import requests
            post = requests.post
        r = post(ENDPOINT, json=body, timeout=20)
        ok = r.status_code in (200, 202)
        return ok, f"IndexNow {r.status_code} - 주소 {len(body['urlList'])}개" + ("" if ok else f" {str(getattr(r, 'text', ''))[:150]}")
    except Exception as e:
        return False, f"IndexNow 오류(무시): {type(e).__name__}"


def sitemap_urls(get=None):
    """사이트맵(색인 목록)의 모든 주소 - 처음 한 번 전체 보내기용."""
    import re
    if get is None:
        import requests
        get = lambda u: requests.get(u, timeout=20)
    out = []
    idx = get(f"https://{HOST}/sitemap_index.xml").text
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx):
        if sm.endswith(".xml"):
            out += re.findall(r"<loc>([^<]+)</loc>", get(sm).text)
    return [u for u in out if not u.endswith(".xml")]


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "all":
        urls = sitemap_urls()
        print("사이트맵 주소", len(urls))
        ok, msg = submit(urls)
    elif len(sys.argv) >= 2 and sys.argv[1] == "check":
        import requests
        r = requests.get(KEY_URL, timeout=20)
        ok = r.status_code == 200 and r.text.strip() == KEY
        msg = f"키 파일 {r.status_code} {'맞음' if ok else '다름: ' + r.text[:60]}"
    else:
        ok, msg = submit(sys.argv[1:])
    print(("✅ " if ok else "❌ ") + msg)
    sys.exit(0 if ok else 1)
