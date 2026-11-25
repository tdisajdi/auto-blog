import sys, os
sys.path.insert(0, '/home/user/auto-blog')
from PIL import Image, ImageDraw, ImageFont
from ondo.media import cover as C
OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1000, 1500
BLUE, RED, INK, PAPER, MUTED, LINE = (61,109,255), (236,74,55), C.INK, C.PAPER, C.MUTED, C.LINE
def F(kind, size): return ImageFont.truetype(C.font_path(kind), size)
def dotbar(d, x, y, w, h, color, cell=10):
    for yy in range(y, y+h, cell):
        for xx in range(x, x+w, cell):
            d.rectangle([xx, yy, xx+cell-2, yy+cell-2], fill=color)
def ondo_mark(d, x, y, cell=8):   # 작은 도트 온도계(사이트 마스코트 결)
    for r in range(10):
        d.rectangle([x+cell, y+r*cell, x+2*cell-2, y+r*cell+cell-2], fill=INK)
    for r in range(5, 10):
        d.rectangle([x+cell, y+r*cell, x+2*cell-2, y+r*cell+cell-2], fill=RED)
    for dx in range(3):
        for dy in range(2):
            d.rectangle([x+dx*cell, y+(10+dy)*cell, x+dx*cell+cell-2, y+(10+dy)*cell+cell-2], fill=RED)
def pin(name, question, sub, bars, foot, note, fmt="{:+.1f}%"):
    im = Image.new('RGB', (W, H), PAPER); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=BLUE)
    d.text((70, 70), "ETF · DATA", font=F('pixel', 34), fill=BLUE)
    y = 130
    for part in question.split("\n"):
        for line in C._wrap(d, part, F('title', 80), W-140, 3):
            d.text((70, y), line, font=F('title', 80), fill=INK); y += 96
    y += 10
    for line in C._wrap(d, sub, F('sub', 38), W-140, 3):
        d.text((70, y), line, font=F('sub', 38), fill=MUTED); y += 50
    y += 40
    top = max(v for _, v, _ in bars); bw = W - 140
    for label, v, color in bars:
        d.text((70, y), label, font=F('sub', 36), fill=INK)
        txt = fmt.format(v)
        f = F('pixel', 60); tw = d.textlength(txt, font=f)
        d.text((W-70-tw, y-14), txt, font=f, fill=color)
        y += 72
        dotbar(d, 70, y, max(20, int(bw * v / top)), 60, color)
        y += 130
    d.line([70, y, W-70, y], fill=LINE, width=3); y += 30
    for line in C._wrap(d, note, F('sub', 30), W-140, 4):
        d.text((70, y), line, font=F('sub', 30), fill=MUTED); y += 42
    ondo_mark(d, 70, H-170)
    d.text((120, H-150), "ondo99.com", font=F('pixel', 46), fill=INK)
    d.text((120, H-92), foot, font=F('sub', 28), fill=MUTED)
    p = os.path.join(OUT, name); im.save(p); print(p)
pin("pin_tqqq.png", "Holding TQQQ\nfor 5 years?",
    "\"3× the index\" is not what you get over long periods. Real prices, same 5-year window:",
    [("QQQ (the index fund)", 58.8, BLUE), ("Simple \"3 × QQQ\" math", 176.5, MUTED), ("TQQQ actual", 4.7, RED)],
    "Every number calculated the same way",
    "Nov 2021 – Nov 2026, Yahoo Finance prices, dividends included. TQQQ's worst drop in that window: -81.4% (QQQ: -35.5%).")
pin("pin_fee.png", "A 0.1% fee gap:\nwhat it costs you",
    "Two ETFs, same 5% yearly return, fees 0.1 percentage point apart. The pricier one ends up smaller by:",
    [("Gap after 10 years", "1.0% of balance", BLUE), ("Gap after 20 years", "2.0% of balance", RED)] if False else
    [("After 10 years", 1.0, BLUE), ("After 20 years", 2.0, RED)],
    "Every number calculated the same way",
    "Share of the final balance. Fees come out of the fund every day, so you never see a bill - they show up as a lower return. Real SPY / VOO fees inside.", fmt="{:.1f}%")
