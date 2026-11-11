"""사용자가 준 링크(예: Threads 글)의 내용을 받아 lab/links/에 저장(2026-11-11).

Claude 작업 환경은 외부 사이트가 막혀 있어, 깃허브 실행이 대신 받아 저장소에 남긴다.
각 링크마다: 최종 주소, og 제목·설명·이미지 주소, 화면에 보이는 글(앞부분), 화면 캡처.
  python site_pages/fetch_links.py URL1,URL2,...
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lab", "links")


def main(urls):
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    result = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 430, "height": 932}, locale="ko-KR",
                            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
        page = ctx.new_page()
        for i, u in enumerate(urls, 1):
            item = {"url": u}
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                item["final"] = page.url
                meta = page.evaluate("""() => { const o = {}; document.querySelectorAll('meta[property^="og:"],meta[name="description"]').forEach(m => o[m.getAttribute('property') || m.getAttribute('name')] = m.content); return o; }""")
                item["meta"] = meta
                txt = page.evaluate("() => document.body ? document.body.innerText : ''")
                item["text"] = re.sub(r"\n{3,}", "\n\n", txt or "")[:6000]
                imgs = page.evaluate("() => [...document.images].map(i => [i.src, i.naturalWidth, i.alt]).filter(x => x[1] > 200).slice(0, 12)")
                item["images"] = imgs
                page.screenshot(path=os.path.join(OUT, f"link{i}.png"), full_page=False)
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1500)
                page.screenshot(path=os.path.join(OUT, f"link{i}-2.png"), full_page=False)
                print(f"✅ {i} {item['final'][:80]} | {(meta.get('og:description') or '')[:80]}")
            except Exception as e:
                item["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                print(f"❌ {i} {u}: {item['error']}")
            result.append(item)
        b.close()
    with open(os.path.join(OUT, "links.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    us = [x.strip() for x in arg.split(",") if x.strip().startswith("http")]
    if not us:
        print("링크 없음")
        sys.exit(2)
    sys.exit(main(us))
