"""표지 시안 v5: 요즘 느낌(A 핀테크) + 픽셀 포인트. 보기 전용. 글자·숫자는 제목에서만."""
import os
S = os.path.dirname(os.path.abspath(__file__))
F = os.path.dirname(S) + "/fonts"
# 테두리 없는 '요즘 픽셀' 팔레트(밝은 면 + 그림자 면)
C = {"y": "#ffd34d", "Y": "#f0a91a", "z": "#fff3b8", "d": "#c97f05",
     "b": "#5b8cff", "B": "#3d6dff", "c": "#9cb8ff", "D": "#2a4fd6",
     "r": "#ff7a6b", "R": "#ec4a37", "q": "#ffc2b8", "E": "#c4362a",
     "g": "#e3e8f2", "G": "#c5cedd", "w": "#ffffff", "k": "#8a93a3", "n": "#191f28"}


def pix(rows, size):
    w = max(len(r) for r in rows)
    rects = "".join(f'<rect x="{x}" y="{y}" width="1.03" height="1.03" fill="{C[ch]}"/>'
                    for y, r in enumerate(rows) for x, ch in enumerate(r) if ch in C)
    return f'<svg width="{size}" height="{size * len(rows) / w:.0f}" viewBox="0 0 {w} {len(rows)}" shape-rendering="crispEdges">{rects}</svg>'


COIN = ["....yyyy....", "..yyzzyyyy..", ".yzzyyyyyYy.", ".yzyyddyyYy.", "yyyyddddyyYY", "yyyyddyyyyYY",
        "yyyyddddyyYY", "yyyyyyddyyYY", ".yyyddddyYY.", ".yyyyddyyYY.", "..YYyyyyYY..", "....YYYY...."]
ICONS = {
    "bars": ["..............rrrr..", "..............rqqR..", "..............rrrR..", "..............rrrR..", "....bbbb......rrrR..",
             "....bccB......rrrR..", "....bbbB......rrrR..", "....bbbB......rrrR..", "....bbbB......rrrR..", "....bbbB......rrrR..",
             "....bbbB......rrrR..", "....bbbB......rrrR..", "....DDDD......EEEE..", "gggggggggggggggggggg", "GGGGGGGGGGGGGGGGGGGG"],
    "drop": ["bb..................", "bbb.................", ".bbb................", "..bbb...............", "...bbb..............",
             "....bbb.............", ".....bbb.........rr.", "......bbb.......rr..", ".......bbb.....rr...", "........bbbrrrrr....",
             ".........rrrr.......", "....................", "gggggggggggggggggggg", "GGGGGGGGGGGGGGGGGGGG"],
    "building": [".......bbbbbb.......", ".......bccccB.......", "...bbbbbbbbbbbbbb...", "...bwwbwwbwwbwwbB...", "...bbbbbbbbbbbbbB...",
                 "...bwwbwwbwwbwwbB...", "...bbbbbbbbbbbbbB...", "...bwwbyybwwbwwbB...", "...bbbbbbbbbbbbbB...", "...bwwbwwbwwbwwbB...",
                 "...bbbbbbyyyybbbB...", "...bbbbbbyyyybbbB...", "gggggggggggggggggggg", "GGGGGGGGGGGGGGGGGGGG"],
}
THERMO = [".nn.", "nwwn", "nwwn", "nrrn", "nrrn", "nrrn", "rrrr", "rrrr", ".rr."]


def dots():
    # 오른쪽 위에서 흩어지는 픽셀 점(분야색, 점점 옅게)
    out = []
    import random
    random.seed(7)
    for gy in range(9):
        for gx in range(16):
            if random.random() < 0.55 - gx * 0.03 + gy * 0.0:
                op = max(0.0, 0.5 - gx * 0.03 - gy * 0.05)
                if op > 0.05:
                    out.append(f'<i style="right:{gx * 22}px;top:{gy * 22}px;opacity:{op:.2f}"></i>')
    return "".join(out)


def card(id_, *, chip, h1, sub, art, numfont=False):
    return f"""<div class="cv{' pn' if numfont else ''}" id="{id_}">
<div class="dots">{dots()}</div>
<span class="chip">{pix(['.ww.', 'wwww', 'wwww', '.ww.'], 14)}{chip}</span>
<h1>{h1}</h1>
<div class="art">{art}</div>
<div class="sub">{sub}</div>
<div class="logo">{pix(THERMO, 16)}<span>ONDO</span></div>
</div>"""


CSS = f"""
@font-face{{font-family:Pret;src:url({F}/pretendard-1.3.9/package/dist/web/variable/woff2/PretendardVariable.woff2);font-weight:100 900}}
@font-face{{font-family:WS;src:url({F}/wanted-sans-1.0.3/package/fonts/webfonts/variable/complete/woff2/WantedSansVariable.woff2);font-weight:100 1000}}
@font-face{{font-family:G11;src:url({F}/galmuri-2.40.3/package/dist/Galmuri11-Bold.woff2)}}
*{{margin:0;box-sizing:border-box}}body{{background:#ddd}}
.cv{{position:relative;width:1200px;height:675px;overflow:hidden;font-family:WS;letter-spacing:-.02em;background:#f4f6fb;color:#191f28;margin-bottom:20px}}
.dots i{{position:absolute;width:14px;height:14px;background:#3d6dff}}
.chip{{position:absolute;left:80px;top:72px;display:flex;align-items:center;gap:10px;font:700 24px Pret;color:#fff;background:#3d6dff;padding:10px 18px;border-radius:12px;letter-spacing:0}}
h1{{position:absolute;left:80px;top:150px;width:680px;font-weight:800;font-size:66px;line-height:1.28;word-break:keep-all}}
h1 em{{font-style:normal;color:#3d6dff;background:linear-gradient(transparent 82%,rgba(61,109,255,.18) 82%)}}
.pn h1 em{{font:700 74px/1 G11;letter-spacing:-.01em;color:#3d6dff;background:none}}
.art{{position:absolute;right:90px;top:150px;width:330px;height:330px;display:flex;align-items:flex-end;justify-content:center}}
.art svg{{filter:drop-shadow(0 18px 20px rgba(30,50,120,.18))}}
.sub{{position:absolute;left:80px;bottom:72px;font:500 26px Pret;color:#6b7684;letter-spacing:-.01em}}
.logo{{position:absolute;right:72px;bottom:66px;display:flex;align-items:center;gap:10px;font:700 26px G11;letter-spacing:.04em}}
"""

coins3 = f'<div style="position:relative;width:330px;height:300px">' \
         f'<div style="position:absolute;left:10px;top:120px">{pix(COIN, 170)}</div>' \
         f'<div style="position:absolute;left:150px;top:70px">{pix(COIN, 170)}</div>' \
         f'<div style="position:absolute;left:80px;top:0">{pix(COIN, 140)}</div></div>'
CARDS = [
    card("h701", chip="ETF 가이드", h1="해외 상장 vs 국내 상장,<br>한 해 이익 <em>833만 원</em>이<br>가르는 세금 차이",
         sub="한 해 이익 833만 원이 가르는 세금 차이", art=pix(ICONS["bars"], 320)),
    card("h705", chip="ETF 가이드", h1="ETF 총보수 <em>0.1%</em> 차이,<br>10년 뒤 내 계좌엔<br>얼마 차이날까?",
         sub="10년 뒤 내 계좌엔 얼마 차이날까?", art=coins3),
    card("hmdd", chip="ETF 가이드", h1="최대 낙폭(MDD)으로<br>내가 버틸 수 있는<br>ETF 고르기",
         sub="최대 낙폭(MDD)으로 내가 버틸 수 있는 ETF 고르기", art=pix(ICONS["drop"], 320)),
    card("haapl", chip="기업 소개 · AAPL", h1="애플은<br>어떤 회사인가",
         sub="매출·낙폭·배당, 그리고 ETF로 사면 담기는 비중", art=pix(ICONS["building"], 320)),
    card("p701", chip="ETF 가이드", h1="해외 상장 vs 국내 상장,<br>한 해 이익 <em>833만 원</em>이<br>가르는 세금 차이",
         sub="한 해 이익 833만 원이 가르는 세금 차이", art=pix(ICONS["bars"], 320), numfont=True),
    card("p705", chip="ETF 가이드", h1="ETF 총보수 <em>0.1%</em> 차이,<br>10년 뒤 내 계좌엔<br>얼마 차이날까?",
         sub="10년 뒤 내 계좌엔 얼마 차이날까?", art=coins3, numfont=True),
]
open(f"{S}/h.html", "w", encoding="utf-8").write(f"<!doctype html><meta charset=utf-8><style>{CSS}</style><body>{''.join(CARDS)}</body>")
print("ok")
