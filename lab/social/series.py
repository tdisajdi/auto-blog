"""ondo 계산노트 카드 시리즈 시안 v3 - 표지는 주제색 전면 + 큰 픽셀 캐릭터 + 말풍선 + 회차 번호."""
import sys, os, math
sys.path.insert(0, '/home/user/auto-blog')
from PIL import Image, ImageDraw, ImageFont
from ondo.media import cover as C
from site_pages import mascot as M
OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1350
WHITE, INK, PAPER, MUTED = (255,255,255), C.INK, C.PAPER, C.MUTED
YEL = (245,197,66)
def F(k, s): return ImageFont.truetype(C.font_path(k), s)
def hexrgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def sprite(d, name, x, y, px):
    body = next(c for c in M.CHARS if c[0]==name)[4] + M.LEGS_A
    for r, row in enumerate(body):
        for c, ch in enumerate(row):
            if ch in M.PAL:
                d.rectangle([x+c*px, y+r*px, x+(c+1)*px-1, y+(r+1)*px-1], fill=hexrgb(M.PAL[ch]))
def bubble(d, x, y, text, font, fg=INK, bg=WHITE, px=8):
    tw = d.textlength(text, font=font); w, h = int(tw)+60, 92
    d.rectangle([x, y, x+w, y+h], fill=bg)
    for k in range(4):   # 픽셀 모서리·꼬리
        d.rectangle([x-px, y+px, x, y+h-px], fill=bg); d.rectangle([x+w, y+px, x+w+px, y+h-px], fill=bg)
    for k in range(3):
        d.rectangle([x+w-80+k*px, y+h+k*px, x+w-80+(k+1)*px+16, y+h+(k+1)*px], fill=bg)
    d.text((x+30, y+18), text, font=font, fill=fg)
def motif(d, kind, color, area):
    x0, y0, x1, y1 = area; cell = 16
    if kind == "zigzag":      # 레버리지: 크게 오르내리는 선
        for band in range(4):
            pts = [(x, y0 + 120 + band*150 + (90 if (x//110) % 2 else -90) * ((x % 110)/110 if (x//110)%2 else 1-(x % 110)/110)) for x in range(x0, x1, cell)]
            for x, y in pts: d.rectangle([x, int(y)//cell*cell, x+cell-3, int(y)//cell*cell+cell-3], fill=color)
    if kind == "wave":        # 환율: 흐르는 물결
        for band in range(5):
            prev = None
            for x in range(x0, x1, cell):
                yy = int((y0 + 80 + band*120 + 45*math.sin(x/140+band*0.8) + (x-x0)*0.15)//cell*cell)
                lo, hi = (yy, yy) if prev is None else (min(prev, yy), max(prev, yy))
                for yv in range(lo, hi+cell, cell):
                    if y0 < yv < y1: d.rectangle([x, yv, x+cell-3, yv+cell-3], fill=color)
                prev = yy
def cover(t, path):
    im = Image.new('RGB', (W, H), t['bg']); d = ImageDraw.Draw(im)
    motif(d, t['motif'], t['bg2'], (0, 560, W, H))
    # 회차 배지
    badge = f"계산노트 #{t['no']:02d}"; f = F('pixel', 34)
    d.rectangle([80, 70, 80+d.textlength(badge, font=f)+40, 128], fill=t['accent'])
    d.text((100, 80), badge, font=f, fill=t['bg'])
    d.text((80+d.textlength(badge, font=f)+64, 80), t['tag'], font=f, fill=t['soft'])
    y = 190
    for ln in t['q']:
        d.text((80, y), ln, font=F('title', 84), fill=WHITE); y += 106
    # 숫자 두 개를 종이 패널에
    py = y + 50
    d.rectangle([80, py, W-80, py+380], fill=PAPER)
    for k, (lab, val, col) in enumerate(t['nums']):
        yy = py + 34 + k*178
        d.text((120, yy), lab, font=F('sub', 38), fill=MUTED)
        d.text((120, yy+44), val, font=F('pixel', 104), fill=col)
    # 캐릭터 + 말풍선
    px = 22; sx = W - 80 - 12*px; sy = H - 40 - 15*px
    sprite(d, t['char'], sx, sy, px)
    bubble(d, 80, sy + 40, t['say'], F('title', 50))
    d.text((80, H-110), "ondo99.com", font=F('pixel', 40), fill=t['soft'])
    im.save(path); print(path)
THEMES = {
  "tqqq": dict(no=1, tag="레버리지", bg=(24,32,44), bg2=(40,52,70), accent=(236,74,55), soft=(170,182,200),
               motif="zigzag", char="ONDO", say="3배라며...?",
               q=["TQQQ를 5년 들고", "있었다면?"],
               nums=[("단순히 QQQ × 3", "+176.5%", MUTED), ("실제 TQQQ", "+4.7%", (236,74,55))]),
  "fx":   dict(no=2, tag="환율", bg=(18,110,122), bg2=(30,130,142), accent=YEL, soft=(190,232,236),
               motif="wave", char="TICK", say="환율이 갈랐다",
               q=["같은 S&P500인데", "1년 수익이 왜 달라?"],
               nums=[("환노출 SPY (원화)", "-3.6%", (236,74,55)), ("환헤지 TIGER(H)", "+4.2%", (18,110,122))]),
}
for k, t in THEMES.items():
    cover(t, os.path.join(OUT, f"v3_{k}_1.png"))
