"""사이트 틀(템플릿·머리/바닥글 부품)을 저장소 파일에서 워드프레스로 올리거나, 백업으로 되돌린다(2026-11-11 전체 개편).

  python site_pages/theme_push.py push      theme/templates/*.html, theme/parts/*.html 을 올림
  python site_pages/theme_push.py restore   site_backup/templates/*.json 의 원문으로 되돌림(개편 전 상태)

- 테마(bute)의 같은 이름 틀을 덮어쓴다(워드프레스가 '사용자 고친 판'으로 저장 → 관리자 화면에서 '초기화'도 가능).
- theme/ondo.css 내용을 부품 'header' 맨 앞 <style>에 넣어, 모든 화면이 같은 CSS를 쓴다
  (추가 CSS·전체 스타일은 API가 없어서 - 11-11 권한 확인 404).
- 토큰 값은 출력하지 않는다.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
THEME = "bute"
CSS_MARK = "<!-- ondo-css -->"


def css_block():
    path = os.path.join(ROOT, "theme", "ondo.css")
    if not os.path.exists(path):
        return ""
    css = open(path, encoding="utf-8").read()
    try:   # 11-12 글 소제목 장식(분야색 줄 + 말랑 아이콘)
        sys.path.insert(0, os.path.join(ROOT, "theme"))
        import icons
        css += "\n" + icons.css_rules()
    except Exception as e:
        print("소제목 장식 CSS 못 만듦:", type(e).__name__, e)
    from site_pages import mascot   # 11-24 캐릭터 띠·404
    css += mascot.CSS
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Silkscreen:wght@400;700&display=swap">'
             '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">'
             # 11-12 한국어 제목 도트 글꼴 Galmuri(SIL OFL 1.1, 무료 공개)
             '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/galmuri.css">'
             # 11-19 소제목·카드 제목 글꼴 Wanted Sans(SIL OFL 1.1) - 나눠 받기(split)라 쓰는 글자 묶음만 내려받음
             '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/wanted-sans@1.0.3/fonts/webfonts/variable/split/WantedSansVariable.css">')
    return f"<!-- wp:html -->\n{CSS_MARK}{fonts}<style>{css}</style>\n<!-- /wp:html -->\n"


def svg(ink=False):
    path = os.path.join(ROOT, "theme", "snippets", "thermo.svg")
    t = open(path, encoding="utf-8").read().strip()
    # 밝은 바탕용: 외곽선을 그림의 어두운 단계로(--t-lit/--t-shade), 유리 안쪽도 밝게
    if ink:
        t = t.replace("<svg ", '<svg style="--t-lit:#3a4a66;--t-shade:#18202c" ', 1)
        t = t.replace("#22365e", "#e9eef7").replace("#34507f", "#ffffff").replace("#18284a", "#cfd8e8")
    return t


BOARD_URL = "https://ondo99.com/ondo-board/"
BOARD_LIVE = True    # 11-12 사용자 결정으로 온도판(353) 공개. 다시 비공개로 돌리면 False(방문자 404 막기).


def board_links(content, live=None):
    """온도판이 공개 전이면 그 링크를 '준비 중' 표시(링크 아님)로 바꾼다."""
    import re
    if BOARD_LIVE if live is None else live:
        return content

    def soon(m):
        attrs, label = m.group(1), m.group(2)
        cls = re.search(r'class="([^"]*)"', attrs)
        suffix = " SOON" if re.fullmatch(r"[A-Z ]+", label.strip()) else " (준비 중)"
        return f'<span class="{(cls.group(1) + " ") if cls else ""}o-soon" aria-disabled="true">{label}{suffix}</span>'
    return re.sub(r'<a([^>]*?)href="' + re.escape(BOARD_URL) + r'"[^>]*>(.*?)</a>', soon, content)


def icon_js():
    try:
        sys.path.insert(0, os.path.join(ROOT, "theme"))
        import icons
        return icons.js()
    except Exception:
        return ""


_EMPTY = None
MIN_POSTS = 3     # 11-24: 분야 메뉴는 글 3편부터(심사 중 '글 1편짜리 분야'가 보이지 않게 - 11-21 허브 원칙, 사용자 위임으로 Claude 결정)


def empty_categories():
    """공개 글이 0편인 분야 slug 목록(11-19: 메뉴에서 빈 화면으로 가는 링크 숨기기). 확인 못 하면 빈 목록(아무것도 안 숨김)."""
    global _EMPTY
    if _EMPTY is not None:
        return _EMPTY
    _EMPTY = []
    try:
        import requests
        import blog_engine as be
        r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/categories",
                         headers={"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}, params={"number": 200}, timeout=30)
        cats = r.json().get("categories") or []
        _EMPTY = sorted(c["slug"] for c in cats if c.get("post_count", MIN_POSTS) < MIN_POSTS and c.get("slug"))
        print(f"글 {MIN_POSTS}편 안 되는 분야(메뉴에서 숨김):", _EMPTY)
    except Exception as e:
        print("분야 글 수 확인 실패 - 메뉴 그대로:", type(e).__name__)
    return _EMPTY


def hide_empty(content, slugs=None):
    """머리글·바닥글 메뉴의 빈 분야 링크는 지우고, 첫 화면 분야 카드는 링크 없는 'COMING SOON' 카드로.
    분야에 첫 글이 공개되면 theme-push를 다시 하면 돌아온다."""
    import re
    for slug in (empty_categories() if slugs is None else slugs):
        href = re.escape(f"/category/{slug}/")
        content = re.sub(r'<a([^>]*class="[^"]*o-cat[^"]*")[^>]*href="[^"]*' + href + r'"([^>]*)>(.*?)</a>',
                         lambda m: f'<div{m.group(1).replace("o-cat", "o-cat o-cat-soon", 1)}{m.group(2)}>{m.group(3)}</div>', content, flags=re.S)
        content = re.sub(r'\s*<a[^>]*href="[^"]*' + href + r'"[^>]*>[^<]*</a>', "", content)
    return content


def glossary_json():
    """용어 풍선용 용어집(11-21) - ondo/writing/glossary.py TERMS를 [정규식, 이름, 뜻]으로. JS 정규식과 같은 문법만 씀."""
    import json
    from ondo.writing.glossary import TERMS
    return json.dumps([[pat, name, meaning] for pat, name, meaning in TERMS], ensure_ascii=False)


def fill(content):
    from site_pages import mascot   # 11-24 바닥글 위 걷는 캐릭터·404 캐릭터
    content = content.replace("{{MASCOT_STRIP}}", mascot.strip_html()).replace("{{MASCOT_404}}", mascot.not_found_html())
    content = content.replace("{{ICON_JS}}", icon_js()).replace("{{GLOSSARY_JSON}}", glossary_json())
    return hide_empty(board_links(content.replace("{{THERMO_INK}}", svg(True)).replace("{{THERMO}}", svg())))


def local_items():
    """(kind, slug, content) - kind는 templates 또는 template-parts."""
    out = []
    for kind, folder in (("templates", "templates"), ("template-parts", "parts")):
        for f in sorted(glob.glob(os.path.join(ROOT, "theme", folder, "*.html"))):
            slug = os.path.splitext(os.path.basename(f))[0]
            content = fill(open(f, encoding="utf-8").read())
            if kind == "template-parts" and slug == "header":
                content = css_block() + content
            out.append((kind, slug, content))
    return out


def backup_items():
    out = []
    for kind, fn in (("templates", "templates.json"), ("template-parts", "template-parts.json")):
        path = os.path.join(ROOT, "site_backup", "templates", fn)
        for t in json.load(open(path, encoding="utf-8")):
            c = t.get("content")
            raw = c.get("raw") if isinstance(c, dict) else c
            if raw is not None:
                out.append((kind, t["slug"], raw))
    return out


def main(mode):
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/wp/v2/sites/{be.WP_SITE_ID}"
    items = local_items() if mode == "push" else backup_items()
    if not items:
        print("올릴 것이 없음")
        return 1
    bad = 0
    for kind, slug, content in items:
        url = f"{base}/{kind}/{THEME}//{slug}"
        r = requests.post(url, headers=h, json={"content": content}, timeout=60)
        if r.status_code == 404:  # 테마에 없는 새 틀 → 새로 만들기
            r = requests.post(f"{base}/{kind}", headers=h, timeout=60,
                              json={"slug": slug, "theme": THEME, "content": content, "title": slug})
        ok = r.status_code in (200, 201)
        bad += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} {kind}/{slug}: {r.status_code} {'' if ok else r.text[:300]}")
    print("끝" if not bad else f"실패 {bad}개")
    return 0 if not bad else 1


OK_FILE = os.path.join(ROOT, "lab", "theme_ok.json")


def theme_hash():
    """테마 원본 파일(theme/ 전체 + 마스코트) 지문 - 모양을 바꾸면 달라짐."""
    import hashlib
    h = hashlib.sha256()
    files = sorted(os.path.join(dp, f) for dp, _d, fs in os.walk(os.path.join(ROOT, "theme")) for f in fs
                   if not f.endswith(".pyc"))
    files.append(os.path.join(ROOT, "site_pages", "mascot.py"))
    for f in files:
        h.update(os.path.relpath(f, ROOT).encode())
        h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


def gate():
    """11-25 사용자 '규칙 왜 무시해?' - 디자인을 시안·확인 없이 두 번 올림(L21) → 확인 기록이 있는 테마만 올림.
    올리기 전에: python site_pages/theme_push.py approve "사용자 확인: 무엇(날짜)" 또는 "버그 고침: 무엇(모양 안 바뀜)"."""
    import json
    try:
        ok = json.load(open(OK_FILE, encoding="utf-8"))
    except Exception:
        ok = {}
    if ok.get("hash") != theme_hash():
        print("❌ 테마 확인 기록이 지금 테마와 다름 - 올리지 않음. 모양이 바뀌었으면 시안을 보이고 사용자 확인을 받은 뒤 approve.")
        return False
    print(f"확인 기록: {ok.get('note')}")
    return True


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else ""
    if m == "approve":
        import json
        args = sys.argv[2:]
        shots = []
        if "--shots" in args:      # 11-25: 시안을 PC·휴대폰 둘 다 만들어 보였는지
            k = args.index("--shots")
            shots, args = args[k + 1:], args[:k]
        note = " ".join(args).strip()
        sys.path.insert(0, os.path.join(ROOT, "site_pages"))
        import design_lint
        if design_lint.run():
            print("❌ 디자인 규칙 검사에 걸림 - 확인 기록 안 남김(고치거나, 사용자 확인 받은 새 색이면 그 줄에 /* 색 허용: 이유 */)")
            sys.exit(1)
        if note.startswith("사용자 확인:") and (len(shots) < 2 or not all(os.path.exists(f) for f in shots)):
            print("❌ 사용자 확인 기록엔 사용자에게 보인 시안 그림 2장(PC·휴대폰)이 필요: approve \"사용자 확인: …\" --shots pc.png 휴대폰.png")
            sys.exit(2)
        if not (note.startswith("사용자 확인:") or note.startswith("버그 고침:")):
            print("사용: theme_push.py approve \"사용자 확인: …\" 또는 \"버그 고침: …(모양 안 바뀜)\"")
            sys.exit(2)
        open(OK_FILE, "w", encoding="utf-8").write(json.dumps({"hash": theme_hash(), "note": note, "shots": [os.path.basename(f) for f in shots]}, ensure_ascii=False, indent=1) + "\n")
        print("기록함:", note)
        sys.exit(0)
    if m not in ("push", "restore"):
        print("사용: theme_push.py push|restore|approve")
        sys.exit(2)
    if m == "push" and not gate():
        sys.exit(1)
    sys.exit(main(m))
