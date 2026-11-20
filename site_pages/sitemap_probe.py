"""사이트맵 원인 확인(읽기만, 2026-11-20) - 응답 헤더(캐시 여부)·끝부분 생성 정보·언어별 주소·글 언어를 본다."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_pages.pll_plugin import call  # noqa: E402


def main():
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ondo-audit/1.0)"}
    for path in ("/sitemap_index.xml", "/post-sitemap.xml", "/page-sitemap.xml", "/en/sitemap_index.xml",
                 "/post-sitemap.xml?lang=ko", "/post-sitemap2.xml", "/sitemap.xml?nc=1"):
        r = requests.get("https://ondo99.com" + path, headers=ua, timeout=25, allow_redirects=True)
        hd = {k: v for k, v in r.headers.items() if k.lower() in ("x-cache", "age", "cache-control", "last-modified", "x-ac", "x-nananana", "x-rq", "expires", "date", "x-robots-tag")}
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        lastmods = re.findall(r"<lastmod>([^<]+)</lastmod>", r.text)[:4]
        comments = re.findall(r"<!--(.*?)-->", r.text, re.S)
        print(f"- {path}: {r.status_code} → {r.url}\n   헤더 {json.dumps(hd, ensure_ascii=False)}\n   loc {len(locs)}개 {[l[:70] for l in locs[:6]]}\n   lastmod {lastmods}\n   주석 {[c.strip()[:160] for c in comments][:3]}")
    # 공개 글들의 언어(Polylang) - 글 사이트맵이 언어로 걸러지는지
    for pid in (701, 705, 703, 731):
        code, j = call("GET", f"/ondo/v1/lang/{pid}")
        print(f"- 글 {pid} 언어: {code} {json.dumps(j, ensure_ascii=False)[:160]}")
    code, j = call("GET", "/wp/v2/posts?per_page=10&status=publish&_fields=id,slug,status,date")
    print("- 공개 글(REST):", code, json.dumps(j, ensure_ascii=False)[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
