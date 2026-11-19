"""Site Kit으로 검색·방문 숫자를 읽을 수 있나 확인(읽기만, 2026-11-19).
GSC_* 키가 비어 있어도, 사이트에 연결된 Site Kit(Search Console·GA4)을 API 대리 호출로 읽을 수 있으면 사용자 일이 줄어든다.
  python site_pages/sitekit_probe.py   → 각 경로 상태 + 요약(키·토큰 값은 출력 안 함), lab/sitekit_probe.txt
"""
import datetime as dt
import json
import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_pages.pll_plugin import call  # noqa: E402

OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT.append(line)


def get_q(path):
    import requests
    from urllib.parse import parse_qsl
    from site_pages.pll_plugin import _auth
    h, S = _auth()
    route, q = path.split("?", 1)
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/jetpack-blogs/{S}/rest-api/", headers=h,
                     params={"path": route, "query": json.dumps(dict(parse_qsl(q))), "json": "true"}, timeout=40)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    if isinstance(j, dict) and "data" in j and set(j) <= {"data", "headers", "status"}:
        j = j["data"]
    return r.status_code, j


def main():
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=27)
    sc = urlencode({"startDate": start, "endDate": end, "dimensions": "page", "limit": 20})
    sc_q = urlencode({"startDate": start, "endDate": end, "dimensions": "query", "limit": 20})
    ga = urlencode({"startDate": start, "endDate": end, "metrics": "screenPageViews,averageSessionDuration,sessions",
                    "dimensions": "pagePath", "limit": 20})
    tests = [("연결 상태", "/google-site-kit/v1/core/site/data/connection"),
             ("모듈 목록", "/google-site-kit/v1/core/modules/data/list"),
             ("검색 성과(페이지)", f"/google-site-kit/v1/modules/search-console/data/searchanalytics?{sc}"),
             ("검색 성과(검색어)", f"/google-site-kit/v1/modules/search-console/data/searchanalytics?{sc_q}"),
             ("GA4 보고서", f"/google-site-kit/v1/modules/analytics-4/data/report?{ga}"),
             ("애드센스 설정", "/google-site-kit/v1/modules/adsense/data/settings")]
    for name, path in tests:
        try:
            code, j = call("GET", path)
            if "?" in path and (code != 200 or not j or (isinstance(j, dict) and j.get("code"))):
                code, j = get_q(path)          # 대리 호출이 '?' 뒤를 버리는 일이 있었음(11-19) → query 칸으로 따로
        except Exception as e:
            say(f"- {name}: 오류 {type(e).__name__}")
            continue
        txt = json.dumps(j, ensure_ascii=False)
        if name == "모듈 목록" and isinstance(j, list):
            txt = "; ".join(f"{m.get('slug')}(켜짐={m.get('active')},연결={m.get('connected')})" for m in j)
        say(f"- {name}: {code} | {txt[:1500]}")
    os.makedirs("lab", exist_ok=True)
    open("lab/sitekit_probe.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
