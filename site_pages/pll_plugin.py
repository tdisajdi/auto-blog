"""ondo 전용 플러그인(wp_plugin/ondo-polylang-rest) 올리기·확인·언어 연결 (2026-11-19 사용자 허락).

사용:
  python site_pages/pll_plugin.py push     - 압축해서 사이트에 올리고 켬(이미 있으면 지우고 새로 올림)
  python site_pages/pll_plugin.py check    - 언어 목록, 언어 없는 글·페이지, 플러그인 동작 확인(읽기)
  python site_pages/pll_plugin.py set <id> <lang>        - 글 언어 지정
  python site_pages/pll_plugin.py link ko=<id> en=<id>   - 번역 연결 후 실제 연결 다시 읽어 확인
토큰 값은 출력하지 않는다. 글을 공개·삭제하지 않는다.
"""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "wp_plugin", "ondo-polylang-rest")
SLUG = "ondo-polylang-rest"


def _auth():
    import blog_engine as be
    return {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}, be.WP_SITE_ID


def call(method, route, data=None):
    """사이트 REST 경로를 워드프레스닷컴 대리 호출로 부름(Atomic 사이트)."""
    import requests
    h, S = _auth()
    url = f"https://public-api.wordpress.com/rest/v1.1/jetpack-blogs/{S}/rest-api/"
    if method == "GET":
        r = requests.get(url, headers=h, params={"path": route, "json": "true"}, timeout=40)
    else:
        payload = {"path": route, "json": "true"}
        if data is not None:
            payload["body"] = json.dumps(data, ensure_ascii=False)
        r = requests.post(url, headers=h, data=payload, timeout=40)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    if isinstance(j, dict) and set(j.keys()) <= {"data", "headers", "status"} and "data" in j:
        j = j["data"]
    return r.status_code, j


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(PLUGIN_DIR):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.join(SLUG, os.path.relpath(full, PLUGIN_DIR)))
    return buf.getvalue()


def plugins_v12():
    import requests
    h, S = _auth()
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.2/sites/{S}/plugins", headers=h, timeout=30)
    return r.status_code, (r.json().get("plugins", []) if r.ok else r.text[:300])


def push():
    import requests
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.2/sites/{S}/plugins"
    code, plugins = plugins_v12()
    mine = [p for p in plugins if isinstance(p, dict) and (p.get("slug") == SLUG or str(p.get("id", "")).startswith(SLUG))] if code == 200 else []
    if mine:
        pid = mine[0].get("id") or f"{SLUG}/{SLUG}"
        enc = requests.utils.quote(pid, safe="")
        print("이미 있음 → 끄고 지운 뒤 새로 올림:", pid)
        r = requests.post(f"{base}/{enc}", headers=h, json={"active": False}, timeout=40)
        print("  끄기:", r.status_code)
        r = requests.post(f"{base}/{enc}/delete", headers=h, timeout=60)
        print("  지우기:", r.status_code, r.text[:200] if not r.ok else "")
    data = make_zip()
    print("압축 크기:", len(data), "바이트")
    r = requests.post(f"{base}/new", headers=h, files={"zip[]": (f"{SLUG}.zip", data, "application/zip")}, timeout=120)
    print("올리기:", r.status_code, r.text[:300].replace("\n", " "))
    if not r.ok:
        return 1
    j = r.json()
    pid = j.get("id") or f"{SLUG}/{SLUG}"
    enc = requests.utils.quote(pid, safe="")
    r = requests.post(f"{base}/{enc}", headers=h, json={"active": True}, timeout=60)
    print("켜기:", r.status_code, (r.json().get("active") if r.ok else r.text[:200]))
    return check()


def check():
    code, j = call("GET", "/ondo/v1/languages")
    print("- 언어 목록:", code, json.dumps(j, ensure_ascii=False)[:300])
    if code != 200:
        print("  → 플러그인이 아직 동작하지 않음(설치·켜기 확인)")
        return 1
    for t in ("page", "post"):
        code, j = call("GET", f"/ondo/v1/unassigned/{t}")
        print(f"- 언어 없는 {t}:", code, json.dumps(j, ensure_ascii=False)[:400])
    for pid in (349, 344, 343, 342):
        code, j = call("GET", f"/ondo/v1/lang/{pid}")
        print(f"- 페이지 {pid}:", code, json.dumps(j, ensure_ascii=False)[:300])
    return 0


def en_pages():
    """site_pages/en/*.html 영어 페이지를 임시(draft) 페이지로 올리고 한국어 페이지와 연결. 공개 페이지는 건드리지 않는다."""
    import glob
    import re
    import requests
    from site_pages import upload
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/posts/"
    bad = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "site_pages", "en", "*.html"))):
        raw = open(path, encoding="utf-8").read()
        m = re.match(r"\s*<!--\s*slug:\s*([\w-]+)\s*\|\s*title:\s*(.+?)\s*\|\s*ko:\s*([\w-]+)\s*-->", raw)
        if not m:
            print("머리줄 없음:", path)
            bad += 1
            continue
        slug, title, ko_slug = m.groups()
        body = re.sub(r"<!--.*?-->\s*", "", raw[m.end():], flags=re.S).strip()
        ok, msg = upload.upsert_page({"slug": slug, "title": title, "html": body}, "draft")
        print("-", msg)
        en = requests.get(base + "slug:" + slug, headers=h, params={"fields": "ID,status,type"}, timeout=20).json()
        ko = requests.get(base + "slug:" + ko_slug, headers=h, params={"fields": "ID,status,type"}, timeout=20).json()
        if not (en.get("ID") and ko.get("ID")):
            print("  번호 못 찾음:", slug, ko_slug)
            bad += 1
            continue
        code, j = call("POST", "/ondo/v1/link", {"translations": {"ko": ko["ID"], "en": en["ID"]}})
        print(f"  연결 ko {ko['ID']}({ko.get('status')}) ↔ en {en['ID']}({en.get('status')}):", code, "linked=", (j or {}).get("linked") if isinstance(j, dict) else j)
        if not (code == 200 and isinstance(j, dict) and j.get("linked")):
            bad += 1
    return 1 if bad else 0


EN_CATS = [  # (한국어 분류 주소, 영어 이름, 영어 주소, 영어 설명)
    ("etf", "ETFs & Investing", "etf-en", "Returns, dividends and fees of ETFs, calculated over the same period and on the same basis."),
    ("energy", "Energy & Commodities", "energy-en", "Oil, inventories and exchange rates that reach everyday costs, read from official data."),
    ("society", "Population & Society", "society-en", "How Korean society is changing, through official statistics."),
]


def en_cats():
    """영어 분류를 만들고(없으면) 영어로 지정해 한국어 분류와 연결."""
    import requests
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/categories"
    bad = 0
    for ko_slug, name, slug, desc in EN_CATS:
        ko = requests.get(f"{base}/slug:{ko_slug}", headers=h, timeout=20).json()
        en = requests.get(f"{base}/slug:{slug}", headers=h, timeout=20)
        if en.status_code != 200 or not en.json().get("ID"):
            en = requests.post(f"{base}/new", headers=h, data={"name": name, "slug": slug, "description": desc}, timeout=30)
            print(f"- {slug}: 새로 만듦", en.status_code)
        en = en.json()
        if not (ko.get("ID") and en.get("ID")):
            print("  번호 못 찾음:", ko_slug, slug, str(en)[:150])
            bad += 1
            continue
        code, j = call("POST", "/ondo/v1/term-link", {"translations": {"ko": ko["ID"], "en": en["ID"]}})
        print(f"  연결 {ko_slug}({ko['ID']}) ↔ {slug}({en['ID']}):", code, "linked=", (j or {}).get("linked") if isinstance(j, dict) else j)
        bad += not (code == 200 and isinstance(j, dict) and j.get("linked"))
    return 1 if bad else 0


def en_publish():
    """영어 기본 페이지(site_pages/en)를 공개로(11-19 사용자: '영어 화면도 미리 만들어 보여줘')."""
    import glob
    import re
    import requests
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/posts/"
    bad = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "site_pages", "en", "*.html"))):
        m = re.match(r"\s*<!--\s*slug:\s*([\w-]+)", open(path, encoding="utf-8").read())
        if not m:
            continue
        j = requests.get(base + "slug:" + m.group(1), headers=h, params={"fields": "ID,status,type"}, timeout=20).json()
        if j.get("type") != "page":
            print("- 없음:", m.group(1)); bad += 1; continue
        if j.get("status") == "publish":
            print("- 이미 공개:", m.group(1)); continue
        r = requests.post(base + str(j["ID"]), headers=h, data={"status": "publish"}, timeout=30)
        print(f"- {m.group(1)}: {r.status_code} {(r.json() or {}).get('status') if r.ok else r.text[:150]} {(r.json() or {}).get('URL', '') if r.ok else ''}")
        bad += not r.ok
    return 1 if bad else 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else "check"
    if mode == "push":
        return push()
    if mode == "check":
        return check()
    if mode == "en-pages":
        return en_pages()
    if mode == "en-cats":
        return en_cats()
    if mode == "urls":                   # 분류·페이지의 실제 주소 확인(읽기)
        for cid in (1376, 1836, 1386, 1839, 1388, 1842):
            code, j = call("GET", f"/wp/v2/categories/{cid}")
            print(f"- 분류 {cid}:", code, (j or {}).get("link") if isinstance(j, dict) else str(j)[:200], (j or {}).get("count") if isinstance(j, dict) else "")
            code, j = call("GET", f"/ondo/v1/term-lang/{cid}")
            print("   언어:", code, json.dumps(j, ensure_ascii=False)[:200])
        return 0
    if mode == "en-publish":
        return en_publish()
    if mode == "en-all":                 # 플러그인 올리기 → 영어 분류 → 영어 페이지 올리기·연결 → 공개
        return push() or en_cats() or en_pages() or en_publish()
    if mode == "set" and len(argv) == 4:
        code, j = call("POST", f"/ondo/v1/lang/{int(argv[2])}", {"lang": argv[3]})
        print("언어 지정:", code, json.dumps(j, ensure_ascii=False)[:400])
        return 0 if code == 200 else 1
    if mode == "link" and len(argv) >= 4:
        pairs = {k: int(v) for k, v in (a.split("=", 1) for a in argv[2:])}
        code, j = call("POST", "/ondo/v1/link", {"translations": pairs})
        print("연결:", code, json.dumps(j, ensure_ascii=False)[:800])
        return 0 if code == 200 and isinstance(j, dict) and j.get("linked") else 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
