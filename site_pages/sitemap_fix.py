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
    """11-20: 전용 플러그인(1.2.0)으로 진단 → Rank Math 자체 함수로 캐시 비우기 → 확인. (예전 1~3단계 - 다시 저장·껐다 켜기·설정 저장 -
    는 효과 없었고 설정 저장은 500이라 뺌)"""
    print("고치기 전:")
    show()
    code, j = call("GET", "/ondo/v1/sitemap")
    print("진단:", code, json.dumps(j, ensure_ascii=False)[:1500])
    code, j = call("POST", "/ondo/v1/sitemap")
    print("캐시 비우기:", code, json.dumps(j, ensure_ascii=False)[:300])
    show()
    ok = not stale()
    print("정상이 됨" if ok else "아직 옛 사이트맵 - 진단 결과로 다음 방법 결정")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
