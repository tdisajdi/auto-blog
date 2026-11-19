"""글 대표 이미지(표지) - 2026-11-19 사용자 '최선으로 해 줘' → 시안 A(종이)+B(숫자 주인공) 합침.

옛 남색·금색 제목 카드(media_engine.make_title_card, 10월 디자인)를 대신한다. 브라우저 없이 Pillow로 그린다
(발행 실행에는 브라우저가 없음). 사이트와 같은 글꼴: 큰 숫자·라벨 = Galmuri11 Bold(도트), 제목 = Wanted Sans.
- 제목에 단위 붙은 숫자가 있으면: 그 숫자를 크게(글 화면 '결론 카드'와 같은 규칙) + 제목은 아래 작게
- 없으면: 제목을 크게 + 오른쪽 도트 온도계
숫자는 제목에서만 가져온다(제목 = 자료에 있는 숫자만 쓰는 규칙) - 표지가 새 숫자를 만들지 않음.
글꼴은 처음 한 번 jsdelivr에서 받아 캐시(SIL OFL 1.1, 재배포 가능).
"""
import os
import re

W, H = 1200, 675
CACHE = os.environ.get("ONDO_FONT_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "ondo-fonts")
FONTS = {
    "pixel": ("Galmuri11-Bold.ttf", "https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/Galmuri11-Bold.ttf"),
    "title": ("WantedSans-ExtraBold.ttf", "https://cdn.jsdelivr.net/npm/wanted-sans@1.0.3/fonts/ttf/WantedSans-ExtraBold.ttf"),
    "sub": ("WantedSans-SemiBold.ttf", "https://cdn.jsdelivr.net/npm/wanted-sans@1.0.3/fonts/ttf/WantedSans-SemiBold.ttf"),
}
INK, PAPER, LINE, MUTED = (24, 32, 44), (255, 253, 247), (227, 220, 203), (74, 85, 104)
CAT = {  # 분야색(theme/DESIGN.md) - 한국어·영어 분류 slug 모두
    "etf": ((61, 109, 255), "ETF"), "etfs-investing": ((61, 109, 255), "ETF"),
    "energy": ((255, 138, 61), "ENERGY"), "energy-commodities": ((255, 138, 61), "ENERGY"),
    "society": ((43, 179, 192), "SOCIETY"), "population-society": ((43, 179, 192), "SOCIETY"),
    "biotech": ((139, 92, 246), "BIOTECH"), "biotech-drugs": ((139, 92, 246), "BIOTECH"),
    "patents": ((74, 85, 104), "TECH"), "technology-patents": ((74, 85, 104), "TECH"),
    "trend": ((236, 74, 55), "TREND"), "trends": ((236, 74, 55), "TREND"),
    "market": ((16, 32, 59), "MARKET"), "markets": ((16, 32, 59), "MARKET"),
}
TEMP = [(61, 109, 255), (43, 179, 192), (244, 196, 78), (255, 138, 61), (236, 74, 55)]
# 글 화면 결론 카드(single.html NUM)와 같은 규칙
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%p|%|만\s?원|억\s?원|조\s?원|원|만|억|조|million|billion)", re.I)


def key_number(title):
    m = NUM.search(title or "")
    if not m:
        return None
    n = re.sub(r"\s+", " ", m.group(0)).strip()
    if re.search(r"(KRW|US\$|\$)\s*$", (title or "")[:m.start()]):      # 영어 제목 'KRW 8.33 million' - 통화 같이
        n = re.search(r"(KRW|US\$|\$)\s*$", title[:m.start()]).group(1) + (" " if title[m.start() - 1] == " " else "") + n
    return n


def font_path(kind):
    name, url = FONTS[kind]
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        import requests
        os.makedirs(CACHE, exist_ok=True)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(path + ".part", "wb") as f:
            f.write(r.content)
        os.replace(path + ".part", path)
    return path


def _wrap(draw, text, font, width, max_lines):
    """띄어쓰기 단위로 줄바꿈(한국어 keep-all처럼), 넘치면 마지막 줄 끝을 …로."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
            continue
        if cur:
            lines.append(cur)
        cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=font) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def _thermo(draw, x, y, cell, level=0.62):
    """도트 온도계(8칸 x 18칸). level = 수은 높이 0~1."""
    glass = [(2, r) for r in range(0, 13)] + [(5, r) for r in range(0, 13)] + [(3, 0), (4, 0)]
    for c, r in glass:
        draw.rectangle([x + c * cell, y + r * cell, x + (c + 1) * cell - 1, y + (r + 1) * cell - 1], fill=INK)
    top = int(12 - level * 11)
    for r in range(top, 13):
        for c in (3, 4):
            draw.rectangle([x + c * cell, y + r * cell, x + (c + 1) * cell - 1, y + (r + 1) * cell - 1], fill=TEMP[4])
    bulb = [(c, r) for r in range(13, 18) for c in range(1, 7) if not (r in (13, 17) and c in (1, 6))]
    for c, r in bulb:
        edge = r == 17 or c in (1, 6) or (r == 13 and c in (2, 5))
        draw.rectangle([x + c * cell, y + r * cell, x + (c + 1) * cell - 1, y + (r + 1) * cell - 1],
                       fill=INK if edge else TEMP[4])


def make_cover(title, category="etf", kicker="GUIDE", out_path=None):
    """표지 PNG 경로를 돌려준다. 실패하면 None(부르는 쪽이 옛 카드로 대신)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        col, label = CAT.get(category, CAT["etf"])
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W - 1, H - 1], outline=INK, width=10)            # 잉크 테두리
        d.rectangle([10, 10, 32, H - 11], fill=col)                         # 분야색 띠
        for i in range(48):                                                  # 위쪽 도트 줄(온도색)
            d.rectangle([60 + i * 23, 10, 60 + i * 23 + 11, 21], fill=TEMP[min(4, i * 5 // 48)])
        f_lab = ImageFont.truetype(font_path("pixel"), 26)
        d.text((84, 62), f"{label} · {kicker}", font=f_lab, fill=col)
        num = key_number(title)
        f_brand = ImageFont.truetype(font_path("pixel"), 30)
        if num:
            size = 168
            f_num = ImageFont.truetype(font_path("pixel"), size)
            while d.textlength(num, font=f_num) > W - 180 and size > 90:
                size -= 8
                f_num = ImageFont.truetype(font_path("pixel"), size)
            d.text((80, 112), num, font=f_num, fill=INK)
            y0 = 112 + int(size * 1.12) + 18
            for i in range(20):                                              # 온도 막대(장식, 값 아님)
                d.rectangle([84 + i * 30, y0, 84 + i * 30 + 24, y0 + 22], fill=TEMP[i // 4])
            for x in range(84, W - 84, 18):                                  # 점선
                d.rectangle([x, H - 236, x + 9, H - 232], fill=LINE)
            f_t = ImageFont.truetype(font_path("title"), 44)
            lines = _wrap(d, title, f_t, W - 168 - 260, 2)
            if lines and lines[-1].endswith("…"):                           # 영어처럼 긴 제목은 조금 작게 3줄
                f_t = ImageFont.truetype(font_path("title"), 36)
                lines = _wrap(d, title, f_t, W - 168 - 260, 3)
            y = H - 206
            for ln in lines:
                d.text((84, y), ln, font=f_t, fill=INK)
                y += int(f_t.size * 1.36)
        else:
            f_t = ImageFont.truetype(font_path("title"), 70)
            lines = _wrap(d, title, f_t, 760, 4)
            y = 150 if len(lines) <= 2 else 124
            for ln in lines:
                d.text((84, y), ln, font=f_t, fill=INK)
                y += 94
            for i in range(20):                                              # 온도 막대(장식)
                d.rectangle([84 + i * 30, y + 26, 84 + i * 30 + 24, y + 48], fill=TEMP[i // 4])
            _thermo(d, 920, 118, 20)
        _thermo(d, W - 250, H - 128, 4, 0.5)
        d.text((W - 210, H - 106), "ONDO", font=f_brand, fill=INK)
        out_path = out_path or os.path.join(os.environ.get("TMPDIR", "/tmp"), f"cover_{abs(hash(title)) % 10**8}.png")
        img.save(out_path, "PNG", optimize=True)
        return out_path
    except Exception as e:
        print(f"ℹ️ 새 표지 만들기 실패(옛 카드로): {type(e).__name__}: {e}")
        return None
