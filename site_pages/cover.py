"""글 대표 이미지(표지) 만들기 - 2026-11-19 시안. AI 그림 없이 코드로: 사이트 디자인(픽셀·온도색)과 같은 글꼴·색.

  python site_pages/cover.py demo            시안 3종 x 예시 글 → lab/covers/*.png
표지 = 1200x675(16:9, 구글 디스커버·공유 미리보기 권장 크기 이상). HTML을 그려 브라우저(Playwright)로 찍는다.
"""
import html
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "lab", "covers")

CAT = {  # 분야색(theme/DESIGN.md): (진한 색, 옅은 바탕, 영어 라벨)
    "etf": ("#3d6dff", "#eaf0ff", "ETF"), "energy": ("#ff8a3d", "#fff0e5", "ENERGY"),
    "society": ("#2bb3c0", "#e5f6f7", "SOCIETY"), "biotech": ("#8b5cf6", "#f1ebff", "BIOTECH"),
    "patents": ("#4a5568", "#eef1f6", "TECH"), "trend": ("#ec4a37", "#fdecea", "TREND"), "market": ("#10203b", "#eef1f6", "MARKET"),
}
TEMP = ["#3d6dff", "#2bb3c0", "#f4c44e", "#ff8a3d", "#ec4a37"]


def fonts_css(local_dir=None):
    if local_dir:   # 이 작업 환경(외부 글꼴 주소가 막힘)에서 시안 찍을 때
        g = f"file://{local_dir}/galmuri-2.40.3/package/dist/Galmuri11-Bold.woff2"
        p = f"file://{local_dir}/pretendard-1.3.9/package/dist/web/variable/woff2/PretendardVariable.woff2"
    else:
        g = "https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/Galmuri11-Bold.woff2"
        p = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/woff2/PretendardVariable.woff2"
    return ("@import url('https://fonts.googleapis.com/css2?family=Silkscreen:wght@400;700&display=block');"   # @import는 맨 앞이어야 함
            f"@font-face{{font-family:G11;src:url({g}) format('woff2');font-weight:700}}"
            f"@font-face{{font-family:Pret;src:url({p}) format('woff2');font-weight:100 900}}")


def thermo(level=0.6):
    """도트 온도계(사이트 thermo.svg). level 0~1 = 수은 높이."""
    from site_pages import theme_push
    return theme_push.svg(True)


def pixel_row(color, n=60):
    return "".join(f'<i style="background:{color if i % 2 == 0 else "transparent"}"></i>' for i in range(n))


def temp_bar(pos):
    cells = []
    for i in range(20):
        c = TEMP[min(4, i // 4)] if i * 5 <= pos else "#e3dccb"
        cells.append(f'<i style="background:{c}"{" class=now" if i == min(19, int(pos) // 5) else ""}></i>')
    return "".join(cells)


BASE_CSS = """
*{box-sizing:border-box;margin:0}body{width:1200px;height:675px;overflow:hidden}
.c{width:1200px;height:675px;position:relative;overflow:hidden;font-family:Pret,sans-serif}
.px{font-family:'Silkscreen',monospace;letter-spacing:.08em}
.title{font-family:G11,Pret,sans-serif;font-weight:700;line-height:1.28;word-break:keep-all}
.dots{display:grid;grid-template-columns:repeat(60,1fr);height:12px}.dots i{display:block}
.brand{display:flex;align-items:center;gap:12px}.brand b{font-family:'Silkscreen';font-size:30px;letter-spacing:.12em}
.brand small{display:block;font-family:'Silkscreen';font-size:13px;letter-spacing:.14em;color:#c2410c}
.tb{display:grid;grid-template-columns:repeat(20,1fr);gap:5px}.tb i{display:block;height:26px}.tb i.now{outline:4px solid #18202c;outline-offset:2px}
"""


def variant_a(title, cat, kicker, **_):
    """A '종이 카드': 밝은 종이 바탕 + 분야색 도트 줄 + 큰 한국어 제목 + 오른쪽 큰 도트 온도계."""
    col, soft, lab = CAT.get(cat, CAT["etf"])
    return f"""<div class="c" style="background:#f7f4ec">
<div class="dots" style="position:absolute;top:0;left:0;right:0">{pixel_row(col)}</div>
<div style="position:absolute;inset:12px 0 0 0;background:linear-gradient(90deg,#f7f4ec 60%,{soft})"></div>
<div style="position:absolute;left:72px;top:84px;width:760px">
 <div class="px" style="font-size:22px;color:{col};margin-bottom:26px">{html.escape(lab)} · {html.escape(kicker)}</div>
 <div class="title" style="font-size:62px;color:#18202c">{html.escape(title)}</div>
</div>
<div style="position:absolute;right:110px;top:110px;width:190px">{thermo()}</div>
<div class="brand" style="position:absolute;left:72px;bottom:56px;color:#18202c"><div style="width:26px">{thermo()}</div><div><b>ONDO</b><small>DATA · TEMPERATURE</small></div></div>
<div class="px" style="position:absolute;right:72px;bottom:62px;font-size:16px;color:#5c6575">ONDO99.COM</div>
</div>"""


def variant_b(title, cat, kicker, number=None, number_label=None, pos=None, **_):
    """B '숫자 주인공': 글의 핵심 숫자를 크게 + 1년 범위 도트 막대(있을 때) + 제목은 아래."""
    col, soft, lab = CAT.get(cat, CAT["etf"])
    bar = f'<div class="tb" style="width:560px;margin-top:22px">{temp_bar(pos)}</div>' if pos is not None else ""
    return f"""<div class="c" style="background:#fffdf7;border:10px solid #18202c">
<div style="position:absolute;left:0;top:0;bottom:0;width:22px;background:{col}"></div>
<div style="position:absolute;left:84px;top:62px">
 <div class="px" style="font-size:22px;color:{col}">{html.escape(lab)} · {html.escape(kicker)}</div>
 <div style="font-family:Pret;font-weight:800;font-size:150px;line-height:1.05;color:#18202c;font-variant-numeric:tabular-nums;margin-top:18px">{html.escape(number or "")}</div>
 <div style="font-size:26px;color:#4a5568;margin-top:6px">{html.escape(number_label or "")}</div>{bar}
</div>
<div style="position:absolute;left:84px;right:84px;bottom:64px;border-top:4px dashed #e3dccb;padding-top:26px;display:flex;justify-content:space-between;align-items:flex-end;gap:40px">
 <div class="title" style="font-size:40px;color:#18202c;max-width:820px">{html.escape(title)}</div>
 <div class="brand" style="color:#18202c"><div style="width:22px">{thermo()}</div><b style="font-size:24px">ONDO</b></div>
</div></div>"""


def variant_c(title, cat, kicker, **_):
    """C '남색 띠': 사이트 머리·바닥처럼 남색 바탕 + 도트 격자 + 흰 제목 + 분야색 라벨 상자."""
    col, soft, lab = CAT.get(cat, CAT["etf"])
    grid = ("background-color:#10203b;background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),"
            "linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:24px 24px")
    return f"""<div class="c" style="{grid}">
<div class="dots" style="position:absolute;bottom:0;left:0;right:0">{''.join(f'<i style="background:{TEMP[i * 5 // 60]}"></i>' for i in range(60))}</div>
<div style="position:absolute;left:72px;top:80px;width:800px">
 <span class="px" style="display:inline-block;background:{col};color:#fff;font-size:20px;padding:10px 16px;box-shadow:6px 6px 0 #000">{html.escape(lab)}</span>
 <span class="px" style="font-size:18px;color:#f4c44e;margin-left:16px">{html.escape(kicker)}</span>
 <div class="title" style="font-size:60px;color:#fff;margin-top:40px">{html.escape(title)}</div>
</div>
<div style="position:absolute;right:120px;top:120px;width:170px;filter:drop-shadow(8px 8px 0 rgba(0,0,0,.35))">{thermo()}</div>
<div class="brand" style="position:absolute;left:72px;bottom:62px;color:#fff"><b>ONDO</b></div>
<div class="px" style="position:absolute;right:72px;bottom:66px;font-size:16px;color:#9fb0cc">ONDO99.COM</div>
</div>"""


VARIANTS = {"a": variant_a, "b": variant_b, "c": variant_c}


def page(inner, local_fonts=None):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{fonts_css(local_fonts)}{BASE_CSS}</style></head>"
            f"<body>{inner}</body></html>")


def _render_node(htmls, out_paths):
    """파이썬 Playwright가 없는 환경(이 작업 환경)용: HTML 파일을 쓰고 Node Playwright로 찍는다."""
    import json, subprocess, tempfile
    tmp = tempfile.mkdtemp()
    jobs = []
    for i, (h, out) in enumerate(zip(htmls, out_paths)):
        f = os.path.join(tmp, f"{i}.html")
        open(f, "w", encoding="utf-8").write(h)
        jobs.append([f, os.path.abspath(out)])
    js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();"
          "const p=await b.newPage({viewport:{width:1200,height:675}});for(const [f,o] of " + json.dumps(jobs) +
          "){await p.goto('file://'+f,{waitUntil:'networkidle'});await p.waitForTimeout(300);"
          "await p.screenshot({path:o,clip:{x:0,y:0,width:1200,height:675}});}await b.close();})();")
    subprocess.run(["node", "-e", js], check=True)


def render(htmls, out_paths):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _render_node(htmls, out_paths)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=1)
        for h, out in zip(htmls, out_paths):
            pg.set_content(h, wait_until="networkidle")
            pg.wait_for_timeout(300)
            pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": 1200, "height": 675})
        b.close()


DEMO = [
    dict(title="해외 상장 ETF vs 국내 상장 ETF, 세금은 얼마나 다를까", cat="etf", kicker="GUIDE", number="15.4%", number_label="국내 상장 해외 ETF 배당소득세율"),
    dict(title="원/달러 환율, 지난 1년 범위에서 지금은 어디쯤일까", cat="energy", kicker="DATA", number="1,330.7원", number_label="원/달러 환율 · 1년 범위 4°", pos=4),
    dict(title="달성군 출생아 수, 왜 전국 1위가 됐나", cat="society", kicker="ISSUE", number="1위", number_label="시군구 합계출산율"),
]


def main(argv):
    if len(argv) >= 2 and argv[1] == "demo":
        local = argv[2] if len(argv) > 2 else None
        os.makedirs(OUT, exist_ok=True)
        hs, outs = [], []
        for i, d in enumerate(DEMO, 1):
            for k, fn in VARIANTS.items():
                hs.append(page(fn(**d), local))
                outs.append(os.path.join(OUT, f"demo{i}-{k}.png"))
        render(hs, outs)
        print("\n".join(outs))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
