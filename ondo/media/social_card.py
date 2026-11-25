"""'계산노트' 카드(2026-11-25, 사용자 확정 디자인 v3 - 기준판 design/social_v3).

공유 미리보기(og:image) 가로판 1200×630: 링크를 스레드·카톡·X에 붙이면 뜨는 그림. 명화 표지 대신 질문 + 숫자 2개 + 픽셀 캐릭터.
(세로 1080×1350 SNS 카드는 lab/social/series.py·cards.py 시안 - 자동화 때 이리로 옮김)
글 하나의 내용은 lab/social/og/<글번호>.json: {"no":1,"theme":"leverage","q":[..2줄],"nums":[[이름,값,"red|accent|muted"],..2개],"say":"말풍선"}
숫자는 그 글(최신본)에 있는 값만 쓴다(카드가 새 숫자를 만들지 않음).
"""
import math
import os

from ondo.media import cover as C

W, H = 1200, 630
WHITE, PAPER, MUTED, RED = (255, 255, 255), C.PAPER, C.MUTED, (236, 74, 55)
THEMES = {   # 주제: 바탕·무늬색·강조·옅은 글자·무늬·캐릭터·이름표
    "leverage": dict(bg=(24, 32, 44), bg2=(40, 52, 70), accent=RED, soft=(170, 182, 200), motif="zigzag", char="ONDO", tag="레버리지"),
    "fx": dict(bg=(18, 110, 122), bg2=(30, 130, 142), accent=(245, 197, 66), soft=(190, 232, 236), motif="wave", char="TICK", tag="환율"),
    "fee": dict(bg=(36, 62, 140), bg2=(52, 80, 160), accent=(245, 197, 66), soft=(200, 212, 245), motif="steps", char="TICK", tag="보수"),
    "drawdown": dict(bg=(70, 30, 40), bg2=(92, 44, 56), accent=(255, 138, 61), soft=(235, 200, 205), motif="steps", char="ONDO", tag="낙폭"),
    "dividend": dict(bg=(30, 90, 60), bg2=(44, 110, 76), accent=(245, 197, 66), soft=(200, 235, 215), motif="coins", char="SOURCE", tag="배당"),
}


def _font(kind, size):
    from PIL import ImageFont
    return ImageFont.truetype(C.font_path(kind), size)


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def sprite(d, name, x, y, px):
    from site_pages import mascot as M
    body = next(c for c in M.CHARS if c[0] == name)[4] + M.LEGS_A
    for r, row in enumerate(body):
        for c, ch in enumerate(row):
            if ch in M.PAL:
                d.rectangle([x + c * px, y + r * px, x + (c + 1) * px - 1, y + (r + 1) * px - 1], fill=_rgb(M.PAL[ch]))


def motif(d, kind, color, area, cell=14):
    x0, y0, x1, y1 = area
    def dot(x, y):
        y = int(y) // cell * cell
        if y0 <= y < y1:
            d.rectangle([x, y, x + cell - 3, y + cell - 3], fill=color)
    for band in range(4):
        prev = None
        for x in range(x0, x1, cell):
            if kind == "wave":
                yy = y0 + 40 + band * 110 + 35 * math.sin(x / 130 + band) + (x - x0) * 0.08
            elif kind == "zigzag":
                t = (x % 120) / 120
                yy = y0 + 40 + band * 120 + (70 * t if (x // 120) % 2 else 70 * (1 - t))
            elif kind == "steps":
                yy = y0 + 20 + band * 120 + ((x - x0) // 90) * 22
            else:      # coins: 띄엄띄엄 동전
                if (x // cell + band * 3) % 7 == 0:
                    for dy in range(3):
                        dot(x, y0 + 60 + band * 120 + dy * cell)
                continue
            yy = int(yy) // cell * cell
            lo, hi = (yy, yy) if prev is None else (min(prev, yy), max(prev, yy))
            for yv in range(lo, hi + cell, cell):
                dot(x, yv)
            prev = yy


def og_card(spec, out_path):
    from PIL import Image, ImageDraw
    t = dict(THEMES[spec.get("theme", "fee")])
    im = Image.new("RGB", (W, H), t["bg"])
    d = ImageDraw.Draw(im)
    motif(d, t["motif"], t["bg2"], (0, 330, W, H))
    f = _font("pixel", 26)
    badge = f"계산노트 #{int(spec.get('no', 1)):02d}"
    bw = d.textlength(badge, font=f)
    d.rectangle([56, 44, 56 + bw + 32, 88], fill=t["accent"])
    d.text((72, 52), badge, font=f, fill=t["bg"])
    d.text((56 + bw + 52, 52), spec.get("tag") or t["tag"], font=f, fill=t["soft"])
    y = 116
    for ln in spec["q"][:2]:
        d.text((56, y), ln, font=_font("title", 58), fill=WHITE)
        y += 72
    py = y + 26                                   # 숫자 2개를 가로로 종이 패널에
    d.rectangle([56, py, 840, py + 210], fill=PAPER)
    cols = {"red": RED, "accent": t["bg"], "muted": MUTED}
    for k, (lab, val, col) in enumerate(spec["nums"][:2]):
        x = 88 + k * 380
        d.text((x, py + 26), lab, font=_font("sub", 28), fill=MUTED)
        size = 84
        while size > 44 and d.textlength(val, font=_font("pixel", size)) > 340:   # 칸(380) 안에 들어가게
            size -= 4
        d.text((x, py + 66 + (84 - size) // 2), val, font=_font("pixel", size), fill=cols.get(col, MUTED))
    px = 16
    sprite(d, t["char"], W - 56 - 12 * px, H - 30 - 15 * px, px)
    if spec.get("say"):
        fb = _font("title", 34)
        tw = d.textlength(spec["say"], font=fb)
        bx, by = W - int(tw) - 90, 120          # 오른쪽 위(캐릭터 위)
        d.rectangle([bx, by, bx + tw + 44, by + 66], fill=WHITE)
        for k in range(3):
            d.rectangle([bx + tw - 10 + k * 7, by + 66 + k * 7, bx + tw + 8 + k * 7, by + 73 + k * 7], fill=WHITE)
        d.text((bx + 22, by + 12), spec["say"], font=fb, fill=C.INK)
    d.text((56, H - 64), "ondo99.com", font=_font("pixel", 32), fill=t["soft"])
    im.save(out_path)
    return out_path
