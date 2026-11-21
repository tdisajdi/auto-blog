"""주간 성적표 (2026-11-21, 백로그 70): Site Kit(GA4)으로 지난 7일 글별 조회·머문 시간을 읽어 앞 7일과 비교.
읽기만 한다(사이트를 바꾸지 않음). 키·토큰 값은 출력하지 않는다.
  python site_pages/weekly_report.py   → lab/weekly_report.md + 텔레그램 요약
서치콘솔(검색 노출·클릭)은 Site Kit 권한이 열리면 같이 넣는다(11-19 확인 때 403).
"""
import datetime as dt
import json
import os
import sys
from urllib.parse import unquote, urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _get(path):
    from site_pages.sitekit_probe import get_q
    from site_pages.pll_plugin import call
    code, j = call("GET", path)
    if code != 200 or not j or (isinstance(j, dict) and j.get("code")):
        code, j = get_q(path)
    return code, j


def ga_pages(start, end, limit=50):
    q = urlencode({"startDate": start, "endDate": end, "metrics": "screenPageViews,averageSessionDuration,sessions",
                   "dimensions": "pagePath", "limit": limit})
    code, j = _get(f"/google-site-kit/v1/modules/analytics-4/data/report?{q}")
    return code, rows_of(j)


def ga_by(dim, start, end, limit=10):
    q = urlencode({"startDate": start, "endDate": end, "metrics": "sessions", "dimensions": dim, "limit": limit})
    code, j = _get(f"/google-site-kit/v1/modules/analytics-4/data/report?{q}")
    return code, rows_of(j)


def search_pages(start, end, limit=20):
    q = urlencode({"startDate": start, "endDate": end, "dimensions": "page", "limit": limit})
    code, j = _get(f"/google-site-kit/v1/modules/search-console/data/searchanalytics?{q}")
    return code, j if isinstance(j, list) else []


def rows_of(j):
    """GA4 보고서 → [(차원값, [숫자...])]."""
    out = []
    for r in (j or {}).get("rows", []) if isinstance(j, dict) else []:
        dims = [unquote(d.get("value", "")) for d in r.get("dimensionValues", [])]
        mets = [float(m.get("value") or 0) for m in r.get("metricValues", [])]
        out.append((dims[0] if dims else "", mets))
    return out


def compare(now, before):
    """두 주의 글별 [조회, 평균 머문 초, 세션] → 이번 주 조회 순 표 줄."""
    prev = {p: m for p, m in before}
    lines = []
    for p, m in sorted(now, key=lambda x: -x[1][0]):
        b = prev.get(p, [0, 0, 0])
        lines.append({"page": p, "views": int(m[0]), "prev_views": int(b[0]), "avg_sec": round(m[1]), "sessions": int(m[2])})
    return lines


def render(lines, total_now, total_prev, countries, search, period):
    md = [f"# 주간 성적표 ({period})", "",
          f"- 전체 조회 {total_now}회 (앞 주 {total_prev}회)",
          "- 나라별 방문(세션): " + (", ".join(f"{c} {int(v[0])}" for c, v in countries) or "자료 없음"), "",
          "| 페이지 | 조회 | 앞 주 | 평균 머문 시간(초) |", "|---|---|---|---|"]
    for r in lines[:20]:
        md.append(f"| {r['page'][:70]} | {r['views']} | {r['prev_views']} | {r['avg_sec']} |")
    md += ["", "## 검색(서치콘솔)", search or "- 권한 없음(403) 또는 아직 숫자 없음"]
    return "\n".join(md) + "\n"


def main():
    end = dt.date.today() - dt.timedelta(days=1)
    s1, s0, e0 = end - dt.timedelta(days=6), end - dt.timedelta(days=13), end - dt.timedelta(days=7)
    c1, now = ga_pages(s1, end)
    c0, before = ga_pages(s0, e0)
    _, countries = ga_by("country", s1, end)
    sc, srows = search_pages(s1, end)
    search = ""
    if sc == 200 and srows:
        search = "\n".join(f"- {unquote(r.get('keys', [''])[0])[:70]}: 노출 {int(r.get('impressions', 0))}, 클릭 {int(r.get('clicks', 0))}"
                           for r in srows[:10])
    if c1 != 200:
        print("GA4 읽기 실패:", c1)
        return 1
    lines = compare(now, before)
    tn, tp = int(sum(m[0] for _, m in now)), int(sum(m[0] for _, m in before))
    period = f"{s1} ~ {end}"
    md = render(lines, tn, tp, countries, search, period)
    os.makedirs(os.path.join(ROOT, "lab"), exist_ok=True)
    open(os.path.join(ROOT, "lab", "weekly_report.md"), "w", encoding="utf-8").write(md)
    print(md)
    try:
        from blog_engine import _telegram_send_message
        top = "\n".join(f"· {r['page'][:40]} {r['views']}회({r['avg_sec']}초)" for r in lines[:5])
        _telegram_send_message(f"📊 주간 성적표 {period}\n전체 조회 {tn}회(앞 주 {tp}회)\n{top}\n서치콘솔: {'있음' if search else '권한·숫자 없음'}")
    except Exception as e:
        print("텔레그램 실패:", type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
