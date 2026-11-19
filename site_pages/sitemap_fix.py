"""사이트맵 캐시 비우기(2026-11-19) - Rank Math '임시 캐시(transients) 비우기'만 실행하고 사이트맵을 다시 받아 확인.
글·설정은 바꾸지 않는다. 왜: 글 사이트맵이 11-09에 비공개로 내린 옛 글 2개를 보여 주고 11-19 공개 글 4편이 빠져 있었음(캐시가 안 바뀜)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_pages.pll_plugin import call  # noqa: E402


def show():
    import requests
    for path in ("/sitemap_index.xml", "/post-sitemap.xml"):
        r = requests.get("https://ondo99.com" + path, params={"nc": os.urandom(3).hex()}, timeout=25,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; ondo-audit/1.0)"})
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        print(f"- {path}: {r.status_code} loc {len(locs)}개: " + "; ".join(l[:90] for l in locs[:8]))


def stale():
    import requests
    r = requests.get("https://ondo99.com/post-sitemap.xml", params={"nc": os.urandom(3).hex()}, timeout=25)
    return "/2026/07/11/hello/" in r.text or "overseas-vs-domestic-etf-tax" not in r.text


def main():
    import requests
    import blog_engine as be
    print("고치기 전:")
    show()
    if not stale():
        print("이미 정상")
        return 0
    # 1) 공개 글 하나 다시 저장(내용 그대로) - Rank Math가 저장 때 사이트맵 캐시를 지움
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/701"
    ex = requests.get(base, headers=h, params={"context": "edit", "fields": "excerpt"}, timeout=30).json().get("excerpt", "")
    r = requests.post(base, headers=h, data={"excerpt": ex}, timeout=30)
    print("1) 701 다시 저장:", r.status_code)
    show()
    if not stale():
        print("정상이 됨(1단계)")
        return 0
    # 2) Rank Math 사이트맵 기능 껐다 켜기(캐시를 새로 만듦) - 켜는 것은 반드시
    c1, j1 = call("POST", "/rankmath/v1/saveModule", {"module": "sitemap", "state": "off"})
    c2, j2 = call("POST", "/rankmath/v1/saveModule", {"module": "sitemap", "state": "on"})
    print("2) 사이트맵 끄기:", c1, json.dumps(j1, ensure_ascii=False)[:120], "/ 켜기:", c2, json.dumps(j2, ensure_ascii=False)[:120])
    show()
    ok = not stale()
    print("정상이 됨(2단계)" if ok else "아직 옛 사이트맵 - 워드프레스닷컴 화면 캐시일 수 있음(사용자에게 보고)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
