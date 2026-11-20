"""서치콘솔 연결(2026-11-20 사용자 '너가 연결해 줘') - Site Kit에 연결된 구글 계정으로:
1) 사이트 소유 확인 상태 보기 → 안 됐으면 확인(Site Verification, 메타 태그 방식 - Site Kit이 머리말에 넣음)
2) 서치콘솔에 'https://ondo99.com/' 속성 추가 → 3) 맞는 속성 목록·검색 성과 읽기로 확인.
비밀값(토큰)은 출력하지 않는다."""
import json
import os
import sys
from urllib.parse import parse_qsl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_pages.pll_plugin import call, _auth  # noqa: E402

SITE = "https://ondo99.com/"


def get(path):
    import requests
    h, S = _auth()
    route, _, q = path.partition("?")
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/jetpack-blogs/{S}/rest-api/", headers=h,
                     params={"path": route, "query": json.dumps(dict(parse_qsl(q))), "json": "true"}, timeout=40)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    if isinstance(j, dict) and "data" in j and set(j) <= {"data", "headers", "status"}:
        j = j["data"]
    return r.status_code, j


def show(name, code, j):
    print(f"- {name}: {code} {json.dumps(j, ensure_ascii=False)[:600]}")


def main():
    base = "/google-site-kit/v1/modules"
    show("소유 확인 상태", *get(f"{base}/site-verification/data/verification?siteURL={SITE}"))
    show("확인된 사이트 목록", *get(f"{base}/site-verification/data/verified-sites"))
    code, j = call("POST", f"{base}/site-verification/data/verification", {"data": {"siteURL": SITE}})
    show("소유 확인 요청", code, j)
    code, j = call("POST", f"{base}/search-console/data/site", {"data": {"siteURL": SITE}})
    show("서치콘솔 속성 추가", code, j)
    show("맞는 속성 목록", *get(f"{base}/search-console/data/matched-sites"))
    show("서치콘솔 설정", *get(f"{base}/search-console/data/settings"))
    code, j = get(f"{base}/search-console/data/searchanalytics?startDate=2026-10-23&endDate=2026-11-19&dimensions=query&limit=10")
    show("검색 성과(검색어)", code, j)
    return 0


if __name__ == "__main__":
    sys.exit(main())
