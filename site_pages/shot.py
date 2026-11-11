"""사이트 화면 캡처(2026-11-11 전체 개편) - 공개 화면을 넓은 화면·휴대폰 두 크기로 찍어 lab/shots/에 저장한다.

Claude 작업 환경은 사이트에 직접 못 가서, 깃허브 실행이 찍어 저장소에 남기면 그것을 보고 고친다.
비공개 초안 글은 로그인 없이 안 보이므로, 글 화면은 '모형'으로 찍는다:
초안 1편의 본문을 API로 받아 theme/ondo.css 를 입힌 HTML로 그려서 캡처(실제 화면과 조금 다를 수 있음).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "lab", "shots")
SITE = "https://ondo99.com"
PAGES = [("home", "/"), ("insights", "/insights/"), ("etf", "/etf/"), ("energy", "/energy/"),
         ("society", "/society/"), ("category-etf", "/category/etf/"), ("404", "/no-such-page-ondo/"), ("bio", "/bio/")]
SIZES = [("desk", 1440, 900), ("mobile", 390, 844)]


def mock_post_html():
    """초안 글 1편 + theme/ondo.css 로 글 화면 모형을 만든다."""
    import requests
    import blog_engine as be
    from site_pages import theme_push
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts",
                     headers=h, timeout=30, params={"status": "draft", "number": 5, "fields": "ID,title,content"})
    posts = [p for p in (r.json().get("posts") or []) if len(p.get("content") or "") > 3000] if r.ok else []
    if not posts:
        return None
    p = posts[0]
    single = os.path.join(ROOT, "theme", "mock_single.html")
    shell = open(single, encoding="utf-8").read() if os.path.exists(single) else "{{TITLE}}{{CONTENT}}"
    css = theme_push.css_block().replace("<!-- wp:html -->", "").replace("<!-- /wp:html -->", "")
    import re
    def part(name):
        t = open(os.path.join(ROOT, "theme", "parts", name + ".html"), encoding="utf-8").read()
        return theme_push.fill(re.sub(r"<!-- /?wp:html -->", "", t))
    single_t = open(os.path.join(ROOT, "theme", "templates", "single.html"), encoding="utf-8").read()
    m = re.search(r'(<div class="o-byline">.*?</script>\s*<script>.*?</script>)', single_t, re.S)
    byline = theme_push.fill(m.group(1)) if m else ""
    body = (shell.replace("{{HEADER}}", part("header")).replace("{{FOOTER}}", part("footer")).replace("{{BYLINE}}", byline)
            .replace("{{TITLE}}", p["title"]).replace("{{CONTENT}}", p["content"]))
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>{css}</head><body class='single'>{body}</body></html>"


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    targets = [(n, SITE + p) for n, p in PAGES]
    mock = None
    try:
        mock = mock_post_html()
    except Exception as e:
        print("글 모형 만들기 실패:", type(e).__name__, e)
    if mock:
        mp = os.path.join(OUT, "_mock_post.html")
        open(mp, "w", encoding="utf-8").write(mock)
        targets.append(("post-mock", "file://" + mp))
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for size, w, hgt in SIZES:
            ctx = b.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
            page = ctx.new_page()
            for name, url in targets:
                try:
                    page.goto(url, wait_until=("domcontentloaded" if url.startswith("file:") else "networkidle"), timeout=45000)
                    page.wait_for_timeout(800)
                    path = os.path.join(OUT, f"{name}-{size}.png")
                    page.screenshot(path=path, full_page=True)
                    # 너무 긴 화면은 위 3화면만(저장소 크기 관리)
                    print(f"✅ {name}-{size}")
                except Exception as e:
                    print(f"❌ {name}-{size}: {type(e).__name__} {str(e)[:150]}")
            ctx.close()
        b.close()
    if mock:
        os.remove(os.path.join(OUT, "_mock_post.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
