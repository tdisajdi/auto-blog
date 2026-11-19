"""플러그인 점검 - '읽기'로만(2026-11-19 사용자 요청). 아무것도 바꾸지 않는다. 토큰 값은 출력하지 않는다.

1) 공개 사이트가 실제로 내보내는 것: 머리말 메타(설명·OG·canonical·hreflang)가 겹치는지, 구조화 데이터, 사이트맵·robots·ads.txt
2) 플러그인 설정(API 대리 호출): Jetpack 모듈 켜짐/꺼짐, Polylang 언어, REST 이름공간 목록
결과는 lab/plugin_audit.txt에 남긴다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SITE = "https://ondo99.com"
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT.append(line)


def head_report(name, html):
    head = html.split("</head>")[0]
    def cnt(pat):
        return len(re.findall(pat, head, re.I))
    q = "[\"']"
    n = {k: cnt(p) for k, p in [("desc", r"<meta[^>]+name=" + q + "description"), ("og", r"property=" + q + "og:title"),
                                ("can", r"rel=" + q + "canonical"), ("hl", r"hreflang="), ("rob", r"<meta[^>]+name=" + q + "robots"),
                                ("tw", r"twitter:card")]}
    say(f"  [{name}] 메타 설명 {n['desc']}개 · og:title {n['og']}개 · canonical {n['can']}개 · hreflang {n['hl']}개 · robots 메타 {n['rob']}개 · twitter:card {n['tw']}개")
    for m in re.findall(r'<meta[^>]+name=["\']robots["\'][^>]*>', head, re.I)[:3]:
        say("    robots:", m[:160])
    for m in re.findall(r'<link[^>]+rel=["\']canonical["\'][^>]*>', head, re.I)[:3]:
        say("    canonical:", m[:160])
    for m in re.findall(r'<link[^>]+hreflang=[^>]*>', head, re.I)[:6]:
        say("    hreflang:", m[:160])
    types = re.findall(r'"@type"\s*:\s*"([^"]+)"', html)
    say("    구조화 데이터 종류:", sorted(set(types))[:20], "| JSON-LD 블록", cnt(r'application/ld\+json'), "개")
    gens = re.findall(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', head, re.I)
    say("    generator:", gens[:6])
    # 플러그인이 남기는 흔적
    marks = {"Rank Math": r"rank-math|rankmath", "Site Kit": r"google-site-kit|Site Kit by Google", "Jetpack 공유/관련글": r"jp-relatedposts|sharedaddy|jetpack-sharing",
             "Jetpack SEO": r"Jetpack Open Graph|jetpack-seo", "Polylang": r"polylang|pll_", "애드센스 코드": r"adsbygoogle|pagead2\.googlesyndication",
             "구글 태그(gtag)": r"googletagmanager\.com/gtag|gtag\(", "Crowdsignal": r"crowdsignal|polldaddy", "Gravatar": r"gravatar-enhanced|hovercards"}
    say("    흔적:", ", ".join(k for k, p in marks.items() if re.search(p, html, re.I)) or "없음")
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    lang = re.search(r"<html[^>]*lang=[\"']([^\"']+)", html)
    say("    title:", (title.group(1).strip()[:120] if title else "없음"), "| <html lang>:", lang.group(1) if lang else "없음")
    desc = re.findall(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', head, re.I)
    say("    설명 내용:", [d[:90] for d in desc])


def main():
    import requests
    import blog_engine as be
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ondo-audit/1.0)"}
    say("=== 1. 공개 사이트 ===")
    # 11-19 추가: 빈 분야 목록이 검색에서 빠지는지(noindex), 공개 글·영어 글에 hreflang(번역 짝)이 붙는지
    for path in ["/", "/about-ondo/", "/etf/", "/privacy-policy/", "/category/energy/", "/en/category/energy-commodities/",
                 "/2026/11/19/overseas-vs-domestic-etf-tax/", "/en/2026/11/19/overseas-vs-korea-listed-etf-tax/"]:
        try:
            r = requests.get(SITE + path, headers=ua, timeout=25)
            say(f"- {path}: {r.status_code} 최종주소 {r.url}")
            if r.ok:
                head_report(path, r.text)
        except Exception as e:
            say(f"- {path}: 오류 {type(e).__name__}")
    for path in ["/robots.txt", "/ads.txt", "/sitemap.xml", "/sitemap_index.xml", "/news-sitemap.xml", "/ko/", "/en/", "/feed/"]:
        try:
            r = requests.get(SITE + path, headers=ua, timeout=25, allow_redirects=True)
            body = r.text
            note = ""
            if path == "/robots.txt" and r.ok:
                note = " | " + " / ".join(l.strip() for l in body.splitlines() if l.strip())[:600]
            elif "sitemap" in path and r.ok:
                locs = re.findall(r"<loc>([^<]+)</loc>", body)
                note = f" | loc {len(locs)}개: " + "; ".join(locs[:8]) + (" | 생성: " + ("Rank Math" if "rank" in body.lower() else "Jetpack" if "jetpack" in body.lower() else "?"))
            elif path == "/ads.txt":
                note = " | " + body.strip()[:200].replace("\n", " / ")
            elif r.ok:
                note = f" | 길이 {len(body)}"
            say(f"- {path}: {r.status_code} → {r.url}{note}")
        except Exception as e:
            say(f"- {path}: 오류 {type(e).__name__}")

    say("=== 2. 플러그인 설정(API, 읽기) ===")
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    S = be.WP_SITE_ID
    proxy = f"https://public-api.wordpress.com/rest/v1.1/jetpack-blogs/{S}/rest-api/"

    def via(path):
        r = requests.get(proxy, headers=h, params={"path": path, "json": "true"}, timeout=30)
        try:
            j = r.json()
        except Exception:
            j = None
        if isinstance(j, dict) and "data" in j and len(j) <= 2:
            j = j["data"]
        return r.status_code, j

    try:
        code, j = via("/")
        ns = (j or {}).get("namespaces") if isinstance(j, dict) else None
        say(f"- REST 이름공간: {code} | {ns}")
    except Exception as e:
        say(f"- REST 이름공간: 오류 {type(e).__name__}")
    try:
        code, j = via("/jetpack/v4/module/all")
        if isinstance(j, dict):
            on = sorted(k for k, v in j.items() if isinstance(v, dict) and v.get("activated"))
            off = sorted(k for k, v in j.items() if isinstance(v, dict) and not v.get("activated"))
            say(f"- Jetpack 모듈: {code} | 켜짐 {len(on)}: {on}")
            say(f"  꺼짐 {len(off)}: {off}")
        else:
            say(f"- Jetpack 모듈: {code} | {str(j)[:200]}")
    except Exception as e:
        say(f"- Jetpack 모듈: 오류 {type(e).__name__}")
    for name, path in [("Polylang 언어", "/pll/v1/languages"), ("Polylang 설정", "/pll/v1/settings"),
                       ("Rank Math 이름공간", "/rankmath/v1"), ("Site Kit 연결", "/google-site-kit/v1/core/site/data/connection"),
                       ("Site Kit 모듈", "/google-site-kit/v1/core/modules/data/list"), ("사이트 설정", "/wp/v2/settings")]:
        try:
            code, j = via(path)
            txt = json.dumps(j, ensure_ascii=False)
            if name == "Site Kit 모듈" and isinstance(j, list):
                txt = "; ".join(f"{m.get('slug')}(켜짐={m.get('active')},연결={m.get('connected')})" for m in j)
            elif name == "Rank Math 이름공간" and isinstance(j, dict):
                txt = "경로 " + ", ".join(sorted((j.get("routes") or {}).keys())[:40])
            elif name == "사이트 설정" and isinstance(j, dict):
                txt = json.dumps({k: j.get(k) for k in ("title", "description", "language", "timezone", "date_format", "posts_per_page", "default_comment_status")}, ensure_ascii=False)
            say(f"- {name}: {code} | {txt[:900]}")
        except Exception as e:
            say(f"- {name}: 오류 {type(e).__name__}")

    say("=== 3. Polylang API로 글 언어 다룰 수 있나(읽기) ===")
    try:
        code, j = via("/")
        routes = (j or {}).get("routes", {}) if isinstance(j, dict) else {}
        for rt in ("/wp/v2/posts", "/wp/v2/pages"):
            args = set()
            for ep in (routes.get(rt) or {}).get("endpoints", []):
                args |= set((ep.get("args") or {}).keys())
            say(f"- {rt} 입력값 중 언어 관련:", sorted(a for a in args if a in ("lang", "translations", "pll_lang", "language")) or "없음")
        say("- pll 경로:", sorted(r for r in routes if r.startswith("/pll")))
    except Exception as e:
        say(f"- 경로 확인 오류 {type(e).__name__}")
    for name, path in [("페이지 언어 필드", "/wp/v2/pages?per_page=5&_fields=id,slug,lang,translations"),
                       ("en 페이지", "/wp/v2/pages?lang=en&per_page=5&_fields=id,slug,lang")]:
        try:
            code, j = via(path)
            say(f"- {name}: {code} | {json.dumps(j, ensure_ascii=False)[:500]}")
        except Exception as e:
            say(f"- {name}: 오류 {type(e).__name__}")
    os.makedirs("lab", exist_ok=True)
    with open("lab/plugin_audit.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
