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


def korea_split(countries):
    """11-22: 한국 / 그 외 세션 합계. 체코·네덜란드처럼 데이터센터 많은 나라가 상위라 봇일 수 있음 - 거르지 않고 나눠만 보임."""
    kr = sum(int(v[0]) for c, v in countries if c in ("South Korea", "Korea", "대한민국"))
    other = sum(int(v[0]) for c, v in countries) - kr
    return f"- 한국 {kr}세션 / 그 외 {other}세션 (그 외에는 봇·데이터센터가 섞일 수 있음)"


def growth_section(start, end, root=ROOT, today=None):
    """11-22 사용자 요청(배움·확장): 기록 파일에서만 셈(인터넷 없음) - 품질 숫자(글 종류별 첫 판 통과율·사실 검증 치명),
    원칙 재발(PROJECT_STATUS 12번 L번호), 확장 효과 확인(BACKLOG - 확인 날이 됐거나 지난 것)."""
    import glob
    import json
    import re
    today = today or dt.date.today()
    kinds, crit = {}, 0
    for f in glob.glob(os.path.join(root, "logs", "*", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
            day = dt.date.fromisoformat(str(d.get("started_at", ""))[:10])
        except Exception:
            continue
        if not (start <= day <= end):
            continue
        revs = [x for x in d.get("steps", []) if str(x.get("step", "")).startswith("편집장 검토")]
        if not revs:
            continue
        k = str(d.get("article_type") or d.get("category") or "기타")
        a = kinds.setdefault(k, [0, 0, 0])
        a[0] += 1
        a[1] += bool(revs[0].get("passed"))
        a[2] += bool(revs[-1].get("passed"))
        crit += sum(1 for x in revs for i in (x.get("issues") or []) if str(i).startswith("[치명·사실"))
    out = ["", "## 품질·배움·확장 (기록에서 자동 셈)"]
    if kinds:
        tot = [sum(v[i] for v in kinds.values()) for i in range(3)]
        out.append(f"- 실행 {tot[0]}번: 첫 판 통과 {tot[1]} · 마지막 판 통과 {tot[2]} · 사실 검증 치명 지적 {crit}개")
        out.append("- 글 종류별 첫 판 통과: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(kinds.items())))
    else:
        out.append("- 이번 주 실행 기록 없음")
    try:   # 11-22: 공개 전 Claude가 고친 곳 수(lab/patches) - 글 만드는 장치가 배울수록 줄어야 함
        cnt = []     # 날짜 = 그 글을 쓴 실행 기록(lab/recheck의 log)의 시작일 - 파일 시각은 깃허브에서 모두 같아 못 씀
        for f in glob.glob(os.path.join(root, "lab", "patches", "*.json")):
            rc = os.path.join(root, "lab", "recheck", os.path.basename(f))
            if not os.path.exists(rc):
                continue
            logn = json.load(open(rc, encoding="utf-8")).get("log") or "-"
            for lf in glob.glob(os.path.join(root, "logs", "*", logn)):
                day = dt.date.fromisoformat(str(json.load(open(lf, encoding="utf-8")).get("started_at", ""))[:10])
                if start <= day <= end:
                    cnt.append(len(json.load(open(f, encoding="utf-8"))))
                break
        if cnt:
            out.append(f"- Claude 고침: 이번 주 고친 글 {len(cnt)}편, 글당 평균 {sum(cnt) / len(cnt):.1f}곳 (줄수록 좋음)")
    except Exception:
        pass
    try:
        st = open(os.path.join(root, "PROJECT_STATUS.txt"), encoding="utf-8").read()
        les = re.findall(r"\[(L\d+)·[^·\]]*·재발 (\d+)\]", st)
        rec = [f"{l}({n}번)" for l, n in les if int(n) > 0]
        out.append(f"- 원칙 {len(les)}개 중 재발: " + (", ".join(rec) if rec else "없음") + " (2번이면 코드로 막기)")
    except Exception:
        pass
    try:
        bl = open(os.path.join(root, "lab", "BACKLOG.txt"), encoding="utf-8").read()
        sec = bl.split("[확장 효과 확인]", 1)[1].split("\n[", 1)[0]
        due = []
        for line in sec.splitlines():
            parts = [x.strip() for x in line.lstrip("- ").split("|")]
            if len(parts) < 5:
                continue
            m = re.search(r"(\d{1,2})-(\d{1,2})", parts[3])
            done = parts[4] not in ("-", "")
            if m and not done:
                try:
                    yy = today.year if int(m.group(1)) >= today.month - 1 else today.year + 1
                    if dt.date(yy, int(m.group(1)), int(m.group(2))) <= today:
                        due.append(parts[1])
                except ValueError:
                    pass
        made = [x for x in sec.splitlines() if re.match(r"- (\d{1,2})-(\d{1,2})", x.strip())
                and start <= dt.date(today.year, *map(int, re.match(r"- (\d{1,2})-(\d{1,2})", x.strip()).groups())) <= end]
        out.append(f"- 이번 주 확장 {len(made)}개" + (" (주 1개 넘음 - 다음 주 줄이기)" if len(made) > 1 else ""))
        out.append("- 확인 날이 된 확장: " + (", ".join(due) if due else "없음"))
    except Exception:
        pass
    return out


def render(lines, total_now, total_prev, countries, search, period):
    md = [f"# 주간 성적표 ({period})", "",
          f"- 전체 조회 {total_now}회 (앞 주 {total_prev}회)",
          "- 나라별 방문(세션): " + (", ".join(f"{c} {int(v[0])}" for c, v in countries) or "자료 없음"),
          korea_split(countries), "",
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
    md += "\n".join(growth_section(s1, end)) + "\n"
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
