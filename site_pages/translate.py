"""한국어 글 → 영어판 (2026-11-19 사용자 결정: 사람 읽기를 통과한 글만 Claude가 번역해 영어판으로 연결).

  python site_pages/translate.py export <글번호>   한국어 글 원문을 lab/translate/<번호>.ko.html 로 받음(Claude가 읽고 번역)
  python site_pages/translate.py check <글번호>    lab/translate/<번호>.en.html 이 원문과 숫자·링크·표·소제목 수가 같은지 대조(사이트 접속 없음)
  python site_pages/translate.py push <글번호>     대조 통과 시 영어 글로 올리고(공개) 한국어 글과 연결, 영어 분야에 넣음

영어 파일 첫 줄: <!-- title: ... | slug: ... | excerpt: ... -->
대조가 하나라도 어긋나면 올리지 않는다(번역 실수로 숫자가 바뀌는 것 방지). Gemini를 쓰지 않는다.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DIR = os.path.join(ROOT, "lab", "translate")
_HEAD = re.compile(r"^\s*<!--\s*title:\s*(.+?)\s*\|\s*slug:\s*([\w-]+)\s*\|\s*excerpt:\s*(.*?)\s*-->\s*", re.S)

_EN_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%p|%|percentage points?|trillion|billion|million|thousand|times\b)?", re.I)   # times = 한국어 '배'(11-19)
_EN_SCALE = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}
_KO_SCALE = {"조": 1e12, "억": 1e8, "만": 1e4}


def _text(html):
    """태그·스크립트 밖 글자만(차트 데이터는 따로 비교)."""
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", html or "", flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"&nbsp;|&#160;", " ", t)


def _scripts(html):
    return re.findall(r"<script\b[^>]*>(.*?)</script>", html or "", flags=re.S | re.I)


def _significant(v, decimals, unit):
    """비교할 숫자만: 소수·%·큰 수. 날짜·순서 같은 작은 정수(≤31)와 연도는 언어마다 쓰는 법이 달라 뺀다."""
    if unit or decimals:
        return True
    if 1990 <= v <= 2100:
        return False
    return v > 31


def ko_values(html):
    from ondo.checks.numbers import _numbers
    out = []
    for raw, v, d, unit in _numbers(_text(html)):
        if unit in _KO_SCALE:
            v = v * _KO_SCALE[unit]
        if _significant(v, d, unit if unit not in ("원", "달러", "명", "가구", "건", "개국", "배럴") else ""):
            out.append(round(v, 6))
    return out


def en_values(html):
    out = []
    for m in _EN_NUM.finditer(_text(html)):
        whole, frac, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        v = float(whole.replace(",", "") + (f".{frac}" if frac else ""))
        if unit in _EN_SCALE:
            v *= _EN_SCALE[unit]
        if _significant(v, len(frac or ""), unit if unit not in _EN_SCALE else "x"):
            out.append(round(v, 6))
    return out


def _close(a, b):
    return abs(a - b) <= max(1e-6, abs(a) * 0.005)


def _missing(src, dst):
    """src에 있는 숫자 중 dst에 없는 것(개수까지 맞춤)."""
    pool = list(dst)
    miss = []
    for v in src:
        for i, w in enumerate(pool):
            if _close(v, w):
                pool.pop(i)
                break
        else:
            miss.append(v)
    return miss


def compare(ko_html, en_html):
    """어긋난 점 목록(비면 통과)."""
    probs = []
    kv, ev = ko_values(ko_html), en_values(en_html)
    m1, m2 = _missing(kv, ev), _missing(ev, kv)
    if m1:
        probs.append(f"원문 숫자가 번역에 없음: {m1[:10]}")
    if m2:
        probs.append(f"번역에만 있는 숫자: {m2[:10]}")
    # 우리 사이트 안 링크는 번역판 주소(영어 글)로 바뀔 수 있어 비교에서 뺀다(11-19, 705 → 703 영어 세금 글)
    links = lambda h: sorted(u for u in re.findall(r'href="(https?://[^"]+)"', h or "") if "ondo99.com" not in u)
    if links(ko_html) != links(en_html):
        a, b = set(links(ko_html)), set(links(en_html))
        probs.append(f"링크 다름 - 빠짐 {sorted(a - b)[:5]} / 더해짐 {sorted(b - a)[:5]}")
    for tag in ("table", "tr", "td", "th", "h2", "h3", "img", "iframe", "script"):
        n1 = len(re.findall(rf"<{tag}\b", ko_html or "", re.I))
        n2 = len(re.findall(rf"<{tag}\b", en_html or "", re.I))
        if n1 != n2:
            probs.append(f"<{tag}> 개수 다름: 원문 {n1} / 번역 {n2}")
    # 차트 숫자 데이터: 스크립트 안 '숫자만 든 배열'(그래프 값)은 그대로여야 함(이름표·축 글자는 번역하며 단위 표기가 바뀔 수 있음)
    arrays = lambda s: re.findall(r"\[\s*-?\d[\d.,\s-]*\]", s)
    for i, (a, b) in enumerate(zip(_scripts(ko_html), _scripts(en_html))):
        if arrays(a) != arrays(b):
            probs.append(f"{i + 1}번째 스크립트(차트 등)의 숫자 배열이 다름")
    if re.search(r"[가-힣]", en_html or ""):            # 본문·속성·차트 이름표·숨은 요약 어디든
        left = sorted(set(re.findall(r"[가-힣]+", en_html)))[:8]
        probs.append(f"번역에 한글이 남음: {left}")
    return probs


def _auth():
    import blog_engine as be
    return {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}, be.WP_SITE_ID


def export(pid):
    import requests
    h, S = _auth()
    ref = pid if str(pid).isdigit() else f"slug:{pid}"   # 글번호 또는 글 주소(slug)
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/posts/{ref}", headers=h,
                     params={"context": "edit", "fields": "ID,title,slug,status,excerpt,content,categories,URL"}, timeout=30)
    if not r.ok:
        print("받기 실패:", r.status_code, r.text[:200])
        return 1
    j = r.json()
    pid = j["ID"]
    os.makedirs(DIR, exist_ok=True)
    cats = [c.get("slug") for c in (j.get("categories") or {}).values()]
    meta = {"ID": j["ID"], "title": j["title"], "slug": j["slug"], "status": j["status"], "URL": j.get("URL"),
            "excerpt": re.sub(r"<[^>]+>", "", j.get("excerpt") or "").strip(), "categories": cats}
    open(os.path.join(DIR, f"{pid}.ko.html"), "w", encoding="utf-8").write(j["content"])
    open(os.path.join(DIR, f"{pid}.ko.json"), "w", encoding="utf-8").write(json.dumps(meta, ensure_ascii=False, indent=1))
    print("받음:", meta["title"], meta["status"], cats, len(j["content"]), "글자")
    return 0


def load_en(pid):
    path = os.path.join(DIR, f"{pid}.en.html")
    raw = open(path, encoding="utf-8").read()
    m = _HEAD.match(raw)
    if not m:
        raise ValueError("영어 파일 첫 줄 <!-- title: | slug: | excerpt: --> 없음")
    return {"title": m.group(1), "slug": m.group(2), "excerpt": m.group(3), "html": raw[m.end():].strip()}


def check(pid):
    ko = open(os.path.join(DIR, f"{pid}.ko.html"), encoding="utf-8").read()
    en = load_en(pid)
    probs = compare(ko, en["html"])
    if re.search(r"[가-힣]", en["title"] + en["excerpt"]):
        probs.append("제목·요약에 한글이 남음")
    print("대조:", "통과" if not probs else "어긋남")
    for p in probs:
        print(" -", p)
    return 1 if probs else 0


def push(pid):
    import requests
    from site_pages.pll_plugin import call
    if check(pid):
        print("대조가 어긋나 올리지 않음")
        return 1
    meta = json.load(open(os.path.join(DIR, f"{pid}.ko.json"), encoding="utf-8"))
    if meta.get("status") != "publish":
        print("한국어 원문이 공개 글이 아니라 올리지 않음(사람 읽기 통과·공개 글만 번역)")
        return 1
    en = load_en(pid)
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}"
    cat_ids = []
    for slug in meta.get("categories") or []:
        c = requests.get(f"{base}/categories/slug:{slug}", headers=h, timeout=20).json()
        if c.get("ID"):
            code, t = call("GET", f"/ondo/v1/term-lang/{c['ID']}")
            en_id = ((t or {}).get("translations") or {}).get("en") if isinstance(t, dict) else None
            if en_id:
                cat_ids.append(str(en_id))
    if not cat_ids:
        print("이 글 분야의 영어 분류가 없음 - pll:en-cats 먼저")
        return 1
    existing = requests.get(f"{base}/posts/slug:{en['slug']}", headers=h, params={"fields": "ID,status"}, timeout=20)
    data = {"title": en["title"], "content": en["html"], "excerpt": en["excerpt"], "slug": en["slug"],
            "categories": ",".join(cat_ids), "status": "publish"}
    if existing.ok and existing.json().get("ID"):
        r = requests.post(f"{base}/posts/{existing.json()['ID']}", headers=h, data=data, timeout=60)
        verb = "바꿈"
    else:
        r = requests.post(f"{base}/posts/new/", headers=h, data=data, timeout=60)
        verb = "새로 올림"
    if not r.ok:
        print("올리기 실패:", r.status_code, r.text[:200])
        return 1
    j = r.json()
    code, l = call("POST", "/ondo/v1/link", {"translations": {"ko": meta["ID"], "en": j["ID"]}})
    linked = isinstance(l, dict) and l.get("linked")
    print(f"영어 글 {verb}: {j.get('status')} {j.get('URL')} (번호 {j['ID']}) / 연결 {linked}")
    return 0 if linked else 1


def main(argv):
    if len(argv) == 3 and argv[1] == "export":
        return export(argv[2])
    if len(argv) == 3 and argv[1] in ("check", "push") and argv[2].isdigit():
        return {"check": check, "push": push}[argv[1]](int(argv[2]))
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
