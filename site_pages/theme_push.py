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
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Silkscreen:wght@400;700&display=swap">'
             '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">')
    return f"<!-- wp:html -->\n{CSS_MARK}{fonts}<style>{css}</style>\n<!-- /wp:html -->\n"


def local_items():
    """(kind, slug, content) - kind는 templates 또는 template-parts."""
    out = []
    for kind, folder in (("templates", "templates"), ("template-parts", "parts")):
        for f in sorted(glob.glob(os.path.join(ROOT, "theme", folder, "*.html"))):
            slug = os.path.splitext(os.path.basename(f))[0]
            content = open(f, encoding="utf-8").read()
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


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else ""
    if m not in ("push", "restore"):
        print("사용: theme_push.py push|restore")
        sys.exit(2)
    sys.exit(main(m))
