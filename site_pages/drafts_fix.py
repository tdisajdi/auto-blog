"""초안 정리·링크 확인(2026-11-12, 백로그 21·31).

  python site_pages/drafts_fix.py check   읽기만: 비공개 글을 가리키는 링크 목록 → lab/link_check.json
  python site_pages/drafts_fix.py fix     비공개 초안의 'ONDO MARKET TEMP'(종합 온도, 임의 가중치) 띠를 지우고, check도 함

- 고치는 것은 status가 draft인 글뿐. 공개 글·페이지는 건드리지 않고 상태(공개 여부)도 바꾸지 않는다.
- 띠 div 하나만 지운다: 지운 뒤 길이 차이가 그 div 길이와 정확히 같을 때만 올림.
- 원본은 같은 실행에서 먼저 돈 site_pages/export.py 백업(site_backup/)에 남는다.
- 토큰 값은 출력하지 않는다.
"""
import json
import os
import re
import sys
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SITE_HOSTS = ("ondo99.com", "www.ondo99.com")
TEMP_RE = re.compile(r'<div class="ondo-thermo"[^>]*>(?:(?!</div>).)*ONDO MARKET TEMP(?:(?!</div>).)*</div>\s*', re.S)


def strip_market_temp(content):
    """종합 온도 띠를 지운 본문과 지운 개수. 띠가 아닌 다른 ondo-thermo 상자는 그대로 둔다."""
    content = content or ""
    m = list(TEMP_RE.finditer(content))
    if not m:
        return content, 0
    new = TEMP_RE.sub("", content)
    assert len(content) - len(new) == sum(len(x.group(0)) for x in m)
    return new, len(m)


def _target(href, by_id, by_slug):
    u = urlparse(href)
    if u.netloc.lower() not in SITE_HOSTS:
        return None
    q = parse_qs(u.query)
    for k in ("p", "page_id"):
        if q.get(k) and q[k][0].isdigit():
            return by_id.get(int(q[k][0]), {"status": "없음"})
    slug = [s for s in u.path.split("/") if s]
    if not slug or slug[0] in ("category", "tag", "author", "wp-content", "feed"):
        return None
    return by_slug.get(slug[-1])     # 허브 등 모르는 주소는 None(판단 안 함)


def find_private_links(items):
    """items: [{ID, slug, status, title, content}]. 공개 글이 아닌 글을 가리키는 우리 사이트 링크."""
    by_id = {int(i["ID"]): i for i in items}
    by_slug = {i.get("slug"): i for i in items if i.get("slug")}
    out = []
    for it in items:
        bad = []
        for href in set(re.findall(r'href="([^"]+)"', it.get("content") or "")):
            t = _target(href, by_id, by_slug)
            if t is not None and t.get("status") != "publish":
                bad.append([href, t.get("status"), int(t["ID"]) if t.get("ID") else None])
        if bad:
            out.append({"ID": int(it["ID"]), "title": it.get("title", ""), "status": it.get("status"), "links": sorted(bad)})
    return sorted(out, key=lambda x: (x["status"] != "publish", x["ID"]))


def main(mode):
    import requests
    import blog_engine as be
    from site_pages.export import fetch_items
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    v1 = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}"
    get = lambda url, params=None: requests.get(url, headers=h, params=params, timeout=60)
    items = fetch_items(get, v1, "post") + fetch_items(get, v1, "page")
    print(f"글·페이지 {len(items)}개")
    if mode == "fix":
        done = 0
        for it in items:
            if it.get("status") != "draft":
                continue
            new, n = strip_market_temp(it.get("content"))
            if not n:
                continue
            r = requests.post(f"{v1}/posts/{it['ID']}", headers=h, json={"content": new}, timeout=60)
            ok = r.status_code == 200 and (r.json().get("status") == "draft")
            done += ok
            print(f"{'✅' if ok else '❌'} {it['ID']} 종합 온도 띠 {n}개 지움 ({r.status_code})")
            if ok:
                it["content"] = new
        print(f"종합 온도 띠 정리: {done}편")
    report = find_private_links(items)
    pub = [r for r in report if r["status"] == "publish"]
    print(f"비공개 글을 가리키는 링크가 있는 글: 공개 {len(pub)}편(방문자 404) / 초안 {len(report) - len(pub)}편(공개할 때 확인)")
    for r in pub:
        print(f"⚠️ 공개 {r['ID']} {r['title'][:30]} → {[l[0] for l in r['links']]}")
    os.makedirs(os.path.join(ROOT, "lab"), exist_ok=True)
    with open(os.path.join(ROOT, "lab", "link_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else ""
    if m not in ("check", "fix"):
        print("사용: drafts_fix.py check|fix")
        sys.exit(2)
    sys.exit(main(m))
