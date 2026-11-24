"""ondo 캐릭터(픽셀) - 2026-11-24 사용자 요청으로 바닥글 위 띠·404에 적용(글 본문엔 넣지 않음).

  python site_pages/mascot.py     lab/mascot/mascot_preview.html 시안 다시 만들기
캐릭터를 더하려면 CHARS에 한 줄 추가(몸 13줄 × 12칸, 다리는 공통 2프레임).
디자인 원칙(DESIGN_NOTES): 브랜드 층(도트) 글자는 영어만 → 걷는 띠 이름표는 영어(ONDO·TICK·SOURCE).
가볍게: 색마다 path 하나(가로로 이어진 칸은 한 덩어리), 몸은 한 번만 그리고 다리 두 프레임만 번갈아 보임.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAL = {"K": "#2b2b3a", "W": "#ffffff", "R": "#e8504a", "B": "#4a7fd8", "L": "#cfe0fb",
       "Y": "#f5c542", "O": "#f08a3c", "G": "#4fb286", "g": "#bfe8d3", "r": "#ffd9d6"}
LEGS_A = ["...K....K...", "..KK....KK.."]
LEGS_B = ["....K..K....", "...KK..KK..."]
# 누르면 가는 곳(11-24 사용자 요청): 역할에 맞는 페이지 - 소개 / 계산 방법(온도판) / 법령 원문 확인
LINKS = {"ONDO": ("https://ondo99.com/about-ondo/", "온도: ondo 소개"),
         "TICK": ("https://ondo99.com/ondo-board/", "눈금: 숫자 계산 방법(온도판)"),
         "SOURCE": ("https://ondo99.com/tax-account-numbers/", "출처: 법령 원문으로 확인한 숫자")}
# (영어 이름표, 한국어 이름, 역할, 설명, 몸 13줄)
CHARS = [
    ("ONDO", "온도", "길잡이 · 시장의 '온도'를 재요",
     "지금 시장이 뜨거운지 차가운지 숫자로 알려 주는 대표 캐릭터.", [
         ".....KK.....", "....KWWK....", "....KWWKK...", "....KWWK....", "....KRRKK...", "....KRRK....",
         "...KKRRKK...", "..KRRRRRRK..", ".KRKRRRRKRK.", ".KrRRRRRRrK.", ".KRRRKKRRRK.", "..KRRRRRRK..",
         "...KKKKKK..."]),
    ("TICK", "눈금", "계산 담당 · 숫자는 코드로",
     "수익률·배당·낙폭을 공개 자료로 직접 계산하는 캐릭터.", [
         "............", "..KKKKKKKK..", ".KBBBBBBBBK.", ".KBWKBBWKBK.", ".KBBBBBBBBK.", ".KBBBKKBBBK.",
         ".KLLLLLLLLK.", ".KLLLLLLRLK.", ".KLLLLOLRLK.", ".KLYLLOLRLK.", ".KLYLLOLRLK.", ".KLLLLLLLLK.",
         "..KKKKKKKK.."]),
    ("SOURCE", "출처", "확인 담당 · 안경 쓰고 근거부터",
     "숫자의 출처와 법령 원문을 먼저 확인하는 캐릭터.", [
         "..K......K..", "..KKKKKKKK..", ".KGGGGGGGGK.", ".KWWWKKWWWK.", ".KWKWGGWKWK.", ".KWWWGGWWWK.",
         ".KGGGOOGGGK.", ".KGGggggGGK.", ".KKggggggKK.", ".KKggggggKK.", ".KGggggggGK.", "..KggggggK..",
         "...KKKKKK..."]),
]


def _paths(rows, y0=0):
    """색마다 path 하나 - 가로로 이어진 같은 색 칸은 한 사각형."""
    d = {}
    for y, r in enumerate(rows):
        x = 0
        while x < len(r):
            c = r[x]
            n = 1
            while x + n < len(r) and r[x + n] == c:
                n += 1
            if c in PAL:
                d.setdefault(c, []).append(f"M{x} {y + y0}h{n}v1h-{n}z")
            x += n
    return "".join(f'<path fill="{PAL[c]}" d="{"".join(v)}"/>' for c, v in d.items())


def sprite(body, px=4, walk=True):
    """한 캐릭터 SVG. walk면 다리 두 프레임(.o-la/.o-lb)을 CSS로 번갈아 보임."""
    h = len(body) + 2
    legs = (f'<g class="o-la">{_paths(LEGS_A, len(body))}</g><g class="o-lb">{_paths(LEGS_B, len(body))}</g>'
            if walk else _paths(LEGS_A, len(body)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 {h}" width="{12 * px}" height="{h * px}" '
            f'shape-rendering="crispEdges" aria-hidden="true">{_paths(body)}{legs}</svg>')


def strip_html():
    """바닥글 바로 위 걷는 띠."""
    walkers = []
    for i, c in enumerate(CHARS):
        url, label = LINKS.get(c[0], ("https://ondo99.com/about-ondo/", c[1]))
        walkers.append(f'<a class="o-walker" href="{url}" title="{label}" aria-label="{label}" '
                       f'style="animation-delay:-{i * 9}s">{sprite(c[4])}<span>{c[0]}</span></a>')
    return f'<div class="o-mascots">{"".join(walkers)}</div>'


def not_found_html():
    """404: 출처 캐릭터가 서 있음(녹는 온도계는 그대로)."""
    src = next(c for c in CHARS if c[0] == "SOURCE")
    return f'<div class="o-404-mascot">{sprite(src[4], px=5, walk=False)}<span>SOURCE: NOT FOUND</span></div>'


CSS = """
/* 11-24 캐릭터 띠(site_pages/mascot.py) */
.o-mascots { position: relative; height: 92px; overflow: hidden; background: var(--o-paper, #f6f7f9); }
.o-walker { position: absolute; bottom: 4px; left: -80px; animation: o-walk 27s linear infinite; }
.o-walker span, .o-404-mascot span { position: absolute; top: -20px; left: 50%; transform: translateX(-50%); font-family: var(--o-px); font-size: 11px; letter-spacing: .05em; background: #2b2b3a; color: #fff; padding: 1px 7px; border-radius: 8px; white-space: nowrap; }
.o-walker svg { display: block; }
a.o-walker { text-decoration: none !important; cursor: pointer; padding-top: 22px; }
.o-walker span { top: 0; }
.o-mascots:hover .o-walker, .o-mascots:focus-within .o-walker { animation-play-state: paused; }
.o-walker:hover span, .o-walker:focus span { background: #e8504a; }
.o-walker .o-lb { visibility: hidden; }
.o-walker .o-la { animation: o-step .5s steps(1) infinite; }
.o-walker .o-lb { animation: o-step .5s steps(1) infinite reverse; }
@keyframes o-step { 0% { visibility: visible; } 50% { visibility: hidden; } }
@keyframes o-walk { from { left: -80px; } to { left: 100%; } }
.o-404-mascot { position: relative; display: inline-block; margin: 36px 0 8px; }
.o-404-mascot svg { display: block; }
@media (prefers-reduced-motion: reduce) {
  .o-walker, .o-walker .o-la, .o-walker .o-lb { animation: none; }
  .o-walker .o-lb { visibility: hidden; }
  .o-walker:nth-child(1) { left: 12%; } .o-walker:nth-child(2) { left: 46%; } .o-walker:nth-child(3) { left: 80%; }
}
"""


def preview():
    cards = "".join(
        f'<div class="card">{sprite(c[4], px=10, walk=False)}<h2>{c[1]} <small>{c[0]}</small></h2>'
        f'<p class="role">{c[2]}</p><p>{c[3]}</p></div>' for c in CHARS)
    html = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ondo 캐릭터</title><style>
:root{{--o-paper:#f6f7f9;--ink:#22252e;--sub:#5b6170;--card:#fff;--line:#e3e6ee;--o-px:monospace}}
body{{margin:0;background:var(--o-paper);color:var(--ink);font-family:system-ui,sans-serif;line-height:1.6}}
main{{max-width:880px;margin:0 auto;padding:24px 16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;text-align:center}}
.card h2 small{{font-size:12px;color:var(--sub)}} .role{{color:#e8504a;font-weight:600;margin:2px 0 8px;font-size:14px}}
.card p{{font-size:14px;color:var(--sub);margin:0}} .foot{{height:60px;background:#1d2a44}}
{CSS}</style><main><h1>ondo 캐릭터</h1><div class="grid">{cards}</div></main>
{strip_html()}<div class="foot"></div>"""
    path = os.path.join(ROOT, "lab", "mascot", "mascot_preview.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(html)
    print("시안:", path)


if __name__ == "__main__":
    preview()
