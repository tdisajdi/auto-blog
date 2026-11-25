import sys, os
sys.path.insert(0, '/home/user/auto-blog')
from PIL import Image, ImageDraw, ImageFont
from ondo.media import cover as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import series as SR
OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1350
BLUE, RED, INK, PAPER, MUTED, LINE = (61,109,255), (236,74,55), C.INK, C.PAPER, C.MUTED, C.LINE
def F(k, s): return ImageFont.truetype(C.font_path(k), s)
def dots(d, x, y, w, h, color, cell=12):
    for yy in range(y, y+h, cell):
        for xx in range(x, x+w, cell):
            d.rectangle([xx, yy, xx+cell-2, yy+cell-2], fill=color)
def base(n, t=None):
    t = t or SR.THEMES['tqqq']
    im = Image.new('RGB', (W, H), PAPER); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 150], fill=t['bg'])
    badge = f"계산노트 #{t['no']:02d}"; f = F('pixel', 34)
    d.rectangle([80, 50, 80+d.textlength(badge, font=f)+40, 108], fill=t['accent'])
    d.text((100, 60), badge, font=f, fill=t['bg'])
    d.text((80+d.textlength(badge, font=f)+64, 60), t['tag'], font=f, fill=t['soft'])
    tt = f"{n}/3"; d.text((W-80-d.textlength(tt, font=f), 60), tt, font=f, fill=t['soft'])
    SR.sprite(d, t['char'], W-80-12*9, H-40-15*9, 9)
    d.text((80, H-120), "ondo99.com", font=F('pixel', 44), fill=INK)
    return im, d
def lines(d, x, y, text, font, color, width, gap):
    for part in text.split("\n"):
        for ln in C._wrap(d, part, font, width, 4):
            d.text((x, y), ln, font=font, fill=color); y += gap
    return y
# 1장: 질문 + 충격 숫자
im, d = base(1)
y = lines(d, 80, 200, "TQQQ를 5년 들고 있었다면\n얼마나 벌었을까?", F('title', 84), INK, W-160, 106)
y = lines(d, 80, y+40, "나스닥100(QQQ)의 3배를 따라가는 ETF.\n그럼 수익도 3배였을까?", F('sub', 44), MUTED, W-160, 60)
d.text((80, y+70), "3배 계산", font=F('sub', 40), fill=MUTED); d.text((80, y+118), "+176.5%", font=F('pixel', 110), fill=MUTED)
d.text((80, y+270), "실제 TQQQ", font=F('sub', 40), fill=RED); d.text((80, y+318), "+4.7%", font=F('pixel', 110), fill=RED)
im.save(os.path.join(OUT, "_old1.png"))
# 2장: 같은 기간 숫자
im, d = base(2)
y = lines(d, 80, 210, "같은 5년, 실제 가격으로 계산", F('title', 66), INK, W-160, 84)
y += 60
for label, v, col in [("QQQ (지수 ETF)", 58.8, BLUE), ("단순히 QQQ × 3", 176.5, MUTED), ("TQQQ 실제", 4.7, RED)]:
    d.text((80, y), label, font=F('sub', 42), fill=INK)
    t = f"{v:+.1f}%"; f = F('pixel', 66); d.text((W-80-d.textlength(t, font=f), y-16), t, font=f, fill=col)
    y += 78; dots(d, 80, y, max(24, int((W-160)*v/176.5)), 64, col); y += 140
y = lines(d, 80, y+10, "가장 크게 떨어졌을 때: TQQQ -81.4% (QQQ -35.5%)", F('sub', 40), INK, W-160, 56)
lines(d, 80, y+20, "2021년 11월 ~ 2026년 11월, Yahoo Finance 종가(배당 반영), ondo 계산", F('sub', 30), MUTED, W-160, 44)
im.save(os.path.join(OUT, "v3_tqqq_2.png"))
# 3장: 왜 - 100원으로 시작한 이틀 (1·2장과 같은 '제목 + 큰 숫자' 구조)
im, d = base(3)
y = lines(d, 80, 210, "왜 3배가 안 될까?", F('title', 80), INK, W-160, 100)
y = lines(d, 80, y+20, "100원으로 시작해 이틀 동안 오르고 내리면", F('sub', 44), MUTED, W-160, 60)
y += 70
def path(y, label, color, vals, end_color):
    d.text((80, y), label, font=F('sub', 42), fill=color)
    y += 64
    f = F('pixel', 92); x = 80
    for k, v in enumerate(vals):
        c = end_color if k == len(vals)-1 else INK
        d.text((x, y), v, font=f, fill=c); x += d.textlength(v, font=f)
        if k < len(vals)-1:
            d.text((x+18, y+8), "→", font=F('pixel', 70), fill=MUTED); x += 110
    return y + 150
y = path(y, "지수 (+10% → -9.09%)", BLUE, ["100", "110", "100"], INK)
y = path(y, "3배 ETF (+30% → -27.27%)", RED, ["100", "130", "94.5"], RED)
y = lines(d, 80, y+10, "제자리로 돌아와도 3배 ETF는 -5.45%.\n매일 '하루의 3배'를 다시 맞추기 때문입니다.", F('title', 46), INK, W-160, 64)
d.text((80, H-210), "구간별 차이·계산 방법 → 첫 댓글 링크", font=F('sub', 38), fill=BLUE)
im.save(os.path.join(OUT, "v3_tqqq_3.png"))
print("ok")
