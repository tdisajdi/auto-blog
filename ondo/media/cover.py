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


# ------------------------------------------------------------
# 명화 도트 표지(2026-11-21 사용자 결정: '자산의 나라 명화 × 80칸 고정 모자이크')
# ------------------------------------------------------------
ART_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lab", "art", "pool")
CELLS = 80          # 가로 칸 수 고정(11-20 사용자: 56칸은 세밀한 그림이 안 보임, 110칸은 사진 같음)


def country_for(title, tags=(), category="etf"):
    """글이 다루는 자산의 나라 → 그림 나라. 한국 종목·코스피·인구 같은 한국 이야기는 한국, 일본·엔화는 일본,
    유럽·프랑스는 프랑스, 나머지(미국 ETF·미국 기업 대부분)는 미국."""
    t = " ".join([title or ""] + list(tags or []))
    if re.search(r"일본|엔화|닛케이|도쿄|Japan|yen|Nikkei", t, re.I):
        return "japan"
    if re.search(r"유럽|프랑스|독일|Europe|France|euro\b", t, re.I):
        return "france"
    if (category in ("society", "population-society") or re.search(r"\b\d{6}\b|코스피|코스닥|삼성|한국|국내 상장|KOSPI|Samsung|Korea", t)) \
            and not re.search(r"해외 상장|미국|S&P|나스닥|Overseas|US-listed", t):
        return "korea"
    return "usa"


def pick_art(country, key):
    """picks.json(Claude가 직접 본 그림과 자를 곳)에서 그 나라 그림 하나.
    key(글 번호·제목)마다 한 번 정하면 assigned.json에 남겨 늘 같은 그림 - 새 글은 그 나라에서 가장 적게 쓴 그림
    (11-21: 해시로만 고르면 글 여러 편이 같은 그림을 받음)."""
    import hashlib
    import json
    try:
        picks = json.load(open(os.path.join(ART_DIR, "picks.json"), encoding="utf-8"))
    except Exception:
        return None
    lst = picks.get(country) or picks.get("usa") or []
    if not lst:
        return None
    ap = os.path.join(ART_DIR, "assigned.json")
    try:
        assigned = json.load(open(ap, encoding="utf-8"))
    except Exception:
        assigned = {}
    key = str(key)
    by_file = {a["file"]: a for a in lst}
    if assigned.get(key) in by_file:
        return by_file[assigned[key]]
    used = {}
    for f in assigned.values():
        used[f] = used.get(f, 0) + 1
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    best = min(range(len(lst)), key=lambda i: (used.get(lst[i]["file"], 0), (i - h) % len(lst)))
    assigned[key] = lst[best]["file"]
    try:
        json.dump(assigned, open(ap, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    return lst[best]


def _restore(im):
    """바랜 그림 살리기(11-21 비교): 대비가 아주 낮은 그림(비단 그림처럼 누렇게 바랜 것, 밝기 표준편차 < 30)만
    채널별 자동 대비로 누런 기를 걷어 원래 색에 가깝게 + 채도 조금. 상태 좋은 그림(호쿠사이·처치 등)은 채널별로 펴면
    색조가 바뀌므로(하늘이 보라, 후지산이 주황) 손대지 않고, 색이 약할 때만 채도를 살짝."""
    from PIL import ImageEnhance, ImageOps, ImageStat
    st = ImageStat.Stat(im.convert("L")).stddev[0]
    a = ImageStat.Stat(im.convert("RGB").resize((64, 64)))
    r, g, b = a.mean
    col = (abs(r - g) + abs((r + g) / 2 - b)) / 2 + sum(a.stddev) / 6      # 대략의 채도
    if st < 30:
        return ImageEnhance.Color(ImageOps.autocontrast(im, cutoff=1.5)).enhance(1.2)
    return ImageEnhance.Color(im).enhance(1.15 if col < 30 else 1.05)


def _mosaic(im, cells=CELLS, size=470):
    """정사각 그림 → 타일 모자이크 size px. 11-20 사용자가 고른 80칸 시안과 같은 방식: 1000px에 틈 있는 둥근 타일로
    그린 뒤 줄임(작게 그리면 틈이 점무늬처럼 보이거나 사라짐 - 11-21 비교)."""
    from PIL import Image, ImageDraw
    small = im.convert("RGB").resize((cells, cells), Image.BOX)
    px = small.load()
    S = 1000
    out = Image.new("RGB", (S, S), PAPER)
    d = ImageDraw.Draw(out)
    t = S / cells
    g = t * 0.04
    for y in range(cells):
        for x in range(cells):
            x0, y0 = x * t + g, y * t + g
            d.rounded_rectangle([x0, y0, x0 + t - 2 * g, y0 + t - 2 * g], radius=t * 0.12, fill=px[x, y])
    return out.resize((size, size), Image.LANCZOS)


def make_art_cover(title, category="etf", kicker="GUIDE", art=None, out_path=None, tags=(), key=None):
    """명화 도트 표지. art = picks.json 항목({file, crop:[x0,y0,x1,y1](0~1), credit}). 없으면 나라에 맞게 고름.
    그림이 없거나 실패하면 None(부르는 쪽이 make_cover로 대신)."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageEnhance
        art = art or pick_art(country_for(title, tags, category), key or title)
        if not art:
            return None
        src = Image.open(os.path.join(ART_DIR, art["file"])).convert("RGB")
        w, h = src.size
        x0, y0, x1, y1 = art.get("crop") or (0, 0, 1, 1)
        box = [int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)]
        s = min(box[2] - box[0], box[3] - box[1])                       # 정사각으로
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        sq = src.crop((cx - s // 2, cy - s // 2, cx - s // 2 + s, cy - s // 2 + s))
        sq = _restore(sq)
        col, label = CAT.get(category, CAT["etf"])
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W - 1, H - 1], outline=INK, width=10)          # 잉크 테두리(지금 표지와 같은 틀)
        d.rectangle([10, 10, 32, H - 11], fill=col)                       # 분야색 띠
        P = 470
        px_, py_ = W - P - 62, 58
        img.paste(_mosaic(sq, CELLS, P), (px_, py_))
        f_cap = ImageFont.truetype(font_path("sub"), 15)
        cap = art.get("credit") or ""
        while cap and d.textlength(cap, font=f_cap) > P:
            cap = cap[:-2].rstrip() + "…" if not cap.endswith("…") else cap[:-3].rstrip() + "…"
        d.text((px_, py_ + P + 12), cap, font=f_cap, fill=MUTED)
        f_lab = ImageFont.truetype(font_path("pixel"), 24)
        d.text((80, 64), f"{label} · {kicker}", font=f_lab, fill=col)
        tw = px_ - 80 - 44
        size = 56
        f_t = ImageFont.truetype(font_path("title"), size)
        lines = _wrap(d, title, f_t, tw, 4)
        while lines and lines[-1].endswith("…") and size > 40:          # 영어처럼 긴 제목은 조금씩 줄임
            size -= 4
            f_t = ImageFont.truetype(font_path("title"), size)
            lines = _wrap(d, title, f_t, tw, 5)
        num = key_number(title)
        y = 120
        for ln in lines:
            if num and num in ln:                                         # 제목 속 숫자만 분야색(새 숫자 안 만듦)
                a, b = ln.split(num, 1)
                d.text((80, y), a, font=f_t, fill=INK)
                xa = 80 + d.textlength(a, font=f_t)
                d.text((xa, y), num, font=f_t, fill=col)
                d.text((xa + d.textlength(num, font=f_t), y), b, font=f_t, fill=INK)
            else:
                d.text((80, y), ln, font=f_t, fill=INK)
            y += int(size * 1.32)
        for i in range(5):                                                # 온도 다섯 칸 + 서명
            d.rectangle([80 + i * 22, H - 96, 80 + i * 22 + 15, H - 81], fill=TEMP[i])
        d.text((80 + 5 * 22 + 12, H - 103), "ONDO", font=ImageFont.truetype(font_path("pixel"), 26), fill=INK)
        out_path = out_path or os.path.join(os.environ.get("TMPDIR", "/tmp"), f"cover_art_{abs(hash(title)) % 10**8}.png")
        img.save(out_path, "PNG", optimize=True)
        return out_path
    except Exception as e:
        print(f"ℹ️ 명화 표지 실패(지금 표지로): {type(e).__name__}: {e}")
        return None
