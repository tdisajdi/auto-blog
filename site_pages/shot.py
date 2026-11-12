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
         ("society", "/society/"), ("category-etf", "/category/etf/"), ("404", "/no-such-page-ondo/"), ("bio", "/bio/"), ("board", "/ondo-board/")]
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
    body = theme_push.fill(shell.replace("{{HEADER}}", part("header")).replace("{{FOOTER}}", part("footer")).replace("{{BYLINE}}", byline)
            .replace("{{TITLE}}", p["title"]).replace("{{CONTENT}}", p["content"]))
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>{css}</head><body class='single'>{body}</body></html>"


CHECK_JS = """() => {
  const out = {overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, lowContrast: []};
  const lum = c => { const m = c.match(/[\\d.]+/g); if (!m) return null; const [r,g,b,a] = m.map(Number);
    if (a === 0) return null; const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b); };
  const bgOf = el => { while (el) { const c = getComputedStyle(el).backgroundColor; const l = lum(c); if (l !== null) return l; el = el.parentElement; } return 1; };
  const seen = new Set();
  document.querySelectorAll('p,li,a,h1,h2,h3,h4,td,th,span,small,button').forEach(el => {
    const t = (el.childNodes.length && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1));
    if (!t || !el.offsetParent) return;
    const fg = lum(getComputedStyle(el).color), bg = bgOf(el); if (fg === null) return;
    const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
    const size = parseFloat(getComputedStyle(el).fontSize); const need = size >= 18 ? 3 : 4.5;
    if (ratio < need) { const k = el.textContent.trim().slice(0, 30); if (!seen.has(k)) { seen.add(k); out.lowContrast.push([k, Math.round(ratio*10)/10]); } }
  });
  out.lowContrast = out.lowContrast.slice(0, 12);
  out.links = [...new Set([...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => h.startsWith('https://ondo99.com/') && !h.includes('#')))];
  return out;
}"""


def make_sheet(names):
    """개편 확인용 한 장 비교판: 줄마다 화면 하나, 왼쪽 넓은 화면·오른쪽 휴대폰(첫 화면 높이만)."""
    from PIL import Image, ImageDraw
    rows = []
    for n in names:
        d, m = os.path.join(OUT, f"{n}-desk.png"), os.path.join(OUT, f"{n}-mobile.png")
        if not (os.path.exists(d) and os.path.exists(m)):
            continue
        di = Image.open(d).convert("RGB"); mi = Image.open(m).convert("RGB")
        di = di.crop((0, 0, di.width, min(di.height, 1400))).resize((480, int(min(di.height, 1400) * 480 / di.width)))
        mi = mi.crop((0, 0, mi.width, min(mi.height, 1600))).resize((156, int(min(mi.height, 1600) * 156 / mi.width)))
        rows.append((n, di, mi))
    if not rows:
        return
    W = 480 + 156 + 48
    H = sum(max(r[1].height, r[2].height) + 34 for r in rows) + 16
    sheet = Image.new("RGB", (W, H), (247, 244, 236))
    dr = ImageDraw.Draw(sheet)
    y = 8
    for n, di, mi in rows:
        dr.text((16, y), n, fill=(24, 32, 44))
        sheet.paste(di, (16, y + 18)); sheet.paste(mi, (16 + 480 + 16, y + 18))
        y += max(di.height, mi.height) + 34
    sheet.save(os.path.join(OUT, "_sheet.png"), optimize=True)
    print("✅ 한 장 비교판 lab/shots/_sheet.png")


def main():
    import json
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
    report, links = {}, set()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for size, w, hgt in SIZES:
            ctx = b.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
            page = ctx.new_page()
            for name, url in targets:
                try:
                    page.goto(url, wait_until=("domcontentloaded" if url.startswith("file:") else "networkidle"), timeout=45000)
                    page.wait_for_timeout(800)
                    page.screenshot(path=os.path.join(OUT, f"{name}-{size}.png"), full_page=True)
                    chk = page.evaluate(CHECK_JS)
                    links.update(chk.pop("links", []))
                    report[f"{name}-{size}"] = chk
                    warn = []
                    if chk["overflow"] > 2:
                        warn.append(f"가로 넘침 {chk['overflow']}px")
                    if chk["lowContrast"]:
                        warn.append(f"글자 대비 낮음 {len(chk['lowContrast'])}곳")
                    print(f"{'⚠️' if warn else '✅'} {name}-{size} {' / '.join(warn)}")
                except Exception as e:
                    print(f"❌ {name}-{size}: {type(e).__name__} {str(e)[:150]}")
            ctx.close()
        # 깨진 링크: 우리 사이트 안 주소만 상태 확인(방문자 기준 - 로그인 없음)
        broken = []
        req = pw.request.new_context()
        for u in sorted(links):
            try:
                r = req.get(u, timeout=30000, max_redirects=5)
                if r.status >= 400:
                    broken.append([u, r.status])
            except Exception as e:
                broken.append([u, type(e).__name__])
        req.dispose()
        b.close()
    report["_broken_links"] = broken
    for u, st in broken:
        print(f"⚠️ 깨진 링크 {st}: {u}")
    print(f"링크 {len(links)}개 확인, 깨진 것 {len(broken)}개")
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    if mock:
        os.remove(os.path.join(OUT, "_mock_post.html"))
    try:
        make_sheet([n for n, _ in targets])
    except Exception as e:
        print("비교판 실패:", type(e).__name__, e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
