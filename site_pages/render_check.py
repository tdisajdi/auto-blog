"""공개 글 화면 점검(2026-11-25, 사용자 '왜 오류가 이렇게 많고 고쳐지는 게 없어?').

  python site_pages/render_check.py            공개 글 전부(한국어·영어)
  python site_pages/render_check.py 776 823    그 글만
왜: Claude의 '공개 전 읽기'는 글자만 뽑아 읽어(그래프·그림·상자를 지움) 화면에서만 보이는 오류를 못 봤다
(그래프 눈금 -2.7e-16, 글 끝 어수선, 휴대폰에서 옆 칸 겹침). 실제 브라우저로 열어 기계가 잡을 수 있는 것을 잡고,
휴대폰 화면 전체를 lab/shots/render/<글번호>.png로 남겨 Claude가 눈으로 본다.
잡는 것: 그래프 눈금의 지수 표기(e-16 등)·그래프가 안 그려짐 / 깨진 그림 / 휴대폰 가로 넘침 / 같은 상자 두 번(출처·함께 볼 글).
결과: lab/render_check.json. 문제가 있으면 끝 코드 1(실행이 ❌로 보임).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SITE = "https://ondo99.com"
OUT = os.path.join(ROOT, "lab", "shots", "render")

JS = r"""() => {
  const out = {issues: []};
  const plots = [...document.querySelectorAll('.js-plotly-plot')];
  const holders = [...document.querySelectorAll('figure.ondo-chart, .ondo-chart')];
  if (holders.length && !plots.length) out.issues.push('그래프 자리는 있는데 그래프가 안 그려짐');
  for (const t of document.querySelectorAll('.js-plotly-plot .ytick text, .js-plotly-plot .xtick text')) {
    if (/\d[eE][-+]?\d/.test(t.textContent)) { out.issues.push('그래프 눈금 지수 표기: ' + t.textContent); break; }
  }
  for (const im of document.querySelectorAll('img')) {
    if (im.complete && im.naturalWidth === 0 && im.offsetParent) { out.issues.push('깨진 그림: ' + (im.currentSrc || im.src).slice(0, 80)); }
  }
  const w = document.scrollingElement.scrollWidth;
  if (w > window.innerWidth + 2) out.issues.push('가로 넘침: ' + w + 'px > ' + window.innerWidth + 'px');
  const vis = el => el.offsetParent !== null;
  const count = re => [...document.querySelectorAll('strong, h2, h3, h4, .o-card-h, .o-side-h')].filter(e => vis(e) && re.test(e.textContent.trim())).length;
  const src = count(/^(📌\s*)?(데이터 출처|이 글의 자료 출처|Data sources|SOURCES)/i);
  const rel = count(/^(함께 읽을 글|READ NEXT)/i) + [...document.querySelectorAll('p')].filter(p => vis(p) && /함께 보면 좋은 글|Related:/.test(p.textContent)).length;
  out.counts = {sources: src, related: rel};
  if (src > 1) out.issues.push('출처 상자 ' + src + '번');
  if (rel > 1) out.issues.push('함께 볼 글 ' + rel + '번');
  return out;
}"""


def published(ids=None):
    import requests
    if ids:
        return [(i, requests.get(f"{SITE}/wp-json/wp/v2/posts/{i}", params={"_fields": "id,link"}, timeout=30).json().get("link")) for i in ids]
    r = requests.get(f"{SITE}/wp-json/wp/v2/posts", params={"per_page": 50, "_fields": "id,link"}, timeout=30).json()
    return [(p["id"], p["link"]) for p in r]


def check(page, url, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(url + ("&" if "?" in url else "?") + "rc=1", wait_until="load", timeout=60000)
    for _ in range(30):                       # 그래프는 화면을 내려야 그려짐
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(200)
    page.wait_for_timeout(5000)
    return page.evaluate(JS)


def main(ids):
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    report, bad = {}, 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        for pid, url in published(ids):
            if not url:
                continue
            res = {"url": url}
            for name, size in (("desk", (1440, 900)), ("mobile", (390, 844))):
                try:
                    r = check(page, url, size)
                except Exception as e:
                    r = {"issues": [f"열기 실패: {type(e).__name__}"]}
                res[name] = r
                if name == "mobile":
                    page.screenshot(path=os.path.join(OUT, f"{pid}.png"), full_page=True)
            issues = sorted(set(res["desk"].get("issues", []) + res["mobile"].get("issues", [])))
            res["issues"] = issues
            report[str(pid)] = res
            bad += bool(issues)
            print(f"{pid} {'문제 ' + str(len(issues)) + '개' if issues else '문제 없음'} {url}")
            for i in issues:
                print("  -", i)
        b.close()
    open(os.path.join(ROOT, "lab", "render_check.json"), "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"화면 점검: {len(report)}편 중 문제 있는 글 {bad}편")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if re.fullmatch(r"\d+", a)]))
