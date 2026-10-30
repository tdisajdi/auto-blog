"""media_engine.py — 글에 들어가는 이미지 3종.

1) 대표 이미지 카드: 사이트 색(남색 + 금색)에 분야와 제목을 넣은 1200x630 썸네일.
   모든 글의 워드프레스 대표 이미지가 되어 허브·카테고리 페이지 카드에 보인다.
2) 데이터 차트: 글에 쓴 숫자(원자재 가격, 공식 통계, 검색 관심도)로 직접 그린 그래프.
   다른 곳에 없는 자료라 "가치 있는 콘텐츠"에 가장 도움이 된다.
3) 사진(Unsplash): 주제에 맞는 실제 사진. Unsplash 규칙대로 사진 주소를 그대로 쓰고
   (내려받아 다시 올리지 않음) 사진가 이름과 출처를 사진 아래에 밝힌다.

어느 것이든 실패하면 조용히 건너뛰고 글은 그대로 발행된다(이미지 때문에 멈추지 않음).
디자인을 바꾸기 전에는 design/DESIGN_NOTES.txt를 먼저 읽을 것.
"""

import html
import os
import tempfile

import requests

# 사이트 색 (design/hub.html, post-dark-theme.css와 같은 값)
NAVY = "#0e1a30"
NAVY_DEEP = "#0b1428"
NAVY_LIGHT = "#16244a"
GOLD = "#e8b944"
TEXT = "#e8ecf4"
MUTED = "#8a96b0"

SITE_NAME = "DATA-DRIVEN INSIGHTS"
SITE_HOST = "ondo99.com"
UNSPLASH_APP_NAME = "ondo_blog"   # Unsplash 출처 링크의 utm_source (규칙상 필요)

CATEGORY_EN = {"etf": "ETF", "trend": "TREND", "tech": "TECH & PATENTS", "bio": "BIOTECH",
               "energy": "ENERGY & CLIMATE", "society": "POPULATION & SOCIETY"}


# ------------------------------------------------------------
# 한글 글꼴 (koreanize-matplotlib 패키지에 들어 있는 나눔고딕을 쓴다 - pip만으로 설치됨)
# ------------------------------------------------------------
def _font_path(weight="Bold"):
    names = {"Bold": "NanumGothicBold.ttf", "ExtraBold": "NanumGothicExtraBold.ttf", "Regular": "NanumGothic.ttf"}
    try:
        import koreanize_matplotlib
        p = os.path.join(os.path.dirname(koreanize_matplotlib.__file__), "fonts", names[weight])
        if os.path.exists(p):
            return p
    except Exception:
        pass
    for p in ["/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]:
        if os.path.exists(p):
            return p
    return None


def _tmp_png(prefix):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".png")
    os.close(fd)
    return path


# ------------------------------------------------------------
# 1) 대표 이미지 카드
# ------------------------------------------------------------
def _wrap(draw, text, font, max_width, max_lines):
    """한글은 띄어쓰기 단위로, 한 단어가 너무 길면 글자 단위로 줄을 나눈다."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while draw.textlength(cur, font=font) > max_width:
            cut = len(cur)
            while cut > 1 and draw.textlength(cur[:cut], font=font) > max_width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def make_title_card(title, category_code, out_path=None):
    """제목 카드 PNG 경로를 돌려준다. 실패하면 None."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        bold, xbold = _font_path("Bold"), _font_path("ExtraBold")
        if not bold:
            print("ℹ️ 한글 글꼴을 못 찾아 대표 이미지 카드를 건너뜁니다.")
            return None
        W, H = 1200, 630
        img = Image.new("RGB", (W, H), NAVY)
        d = ImageDraw.Draw(img)
        # 위→아래로 아주 옅은 남색 그라데이션
        top, bottom = (22, 36, 74), (11, 20, 40)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        # 오른쪽 아래 얇은 금색 격자선(데이터 느낌, 과하지 않게)
        for i in range(6):
            x = 760 + i * 80
            d.line([(x, 360), (x, H)], fill=(40, 56, 96), width=1)
        for i in range(4):
            y = 400 + i * 70
            d.line([(760, y), (W, y)], fill=(40, 56, 96), width=1)
        pts = [(760, 590), (840, 560), (920, 575), (1000, 500), (1080, 520), (1160, 440)]
        d.line(pts, fill=(232, 185, 68), width=4)

        pad = 80
        d.rectangle([pad, 92, pad + 64, 98], fill=GOLD)
        f_cat = ImageFont.truetype(bold, 26)
        d.text((pad, 116), CATEGORY_EN.get(category_code, category_code.upper()), font=f_cat, fill=GOLD)

        f_title = ImageFont.truetype(xbold or bold, 60)
        lines = _wrap(d, title, f_title, W - pad * 2, 3)
        if len(lines) == 3:
            f_title = ImageFont.truetype(xbold or bold, 52)
            lines = _wrap(d, title, f_title, W - pad * 2, 3)
        y = 190
        for line in lines:
            d.text((pad, y), line, font=f_title, fill=TEXT)
            y += int(f_title.size * 1.32)

        f_foot = ImageFont.truetype(bold, 24)
        d.text((pad, H - 78), SITE_NAME, font=f_foot, fill=GOLD)
        d.text((pad + d.textlength(SITE_NAME, font=f_foot) + 18, H - 78), f"· {SITE_HOST}", font=f_foot, fill=MUTED)

        out_path = out_path or _tmp_png("card_")
        img.save(out_path, "PNG", optimize=True)
        return out_path
    except Exception as e:
        print(f"ℹ️ 대표 이미지 카드 만들기 실패: {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------
# 2) 데이터 차트
#    spec = {"title": 제목, "labels": [x축 라벨], "values": [값], "unit": 단위,
#            "source": 출처 문구, "kind": "line" | "bar"}
# ------------------------------------------------------------
def make_chart(spec, out_path=None):
    try:
        labels, values = list(spec.get("labels") or []), list(spec.get("values") or [])
        if len(values) < 2 or len(labels) != len(values):
            return None
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        reg, bold = _font_path("Regular"), _font_path("Bold")
        if not reg:
            print("ℹ️ 한글 글꼴을 못 찾아 차트를 건너뜁니다.")
            return None
        font_manager.fontManager.addfont(reg)
        if bold:
            font_manager.fontManager.addfont(bold)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=reg).get_name()
        plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(10, 5.4), dpi=120)
        fig.patch.set_facecolor(NAVY)
        ax.set_facecolor(NAVY)
        kind = spec.get("kind") or ("bar" if len(values) <= 6 else "line")
        x = list(range(len(values)))
        if kind == "bar":
            colors = [NAVY_LIGHT] * (len(values) - 1) + [GOLD]
            bars = ax.bar(x, values, color=colors, edgecolor=GOLD, linewidth=1, width=0.55)
            for b, v in zip(bars, values):
                ax.annotate(_short(v, spec.get("unit", "")), (b.get_x() + b.get_width() / 2, b.get_height()),
                            ha="center", va="bottom", fontsize=11, color=TEXT, xytext=(0, 4), textcoords="offset points")
        else:
            ax.plot(x, values, color=GOLD, linewidth=2.4)
            ax.fill_between(x, values, min(values), color=GOLD, alpha=0.08)
            ax.scatter([x[-1]], [values[-1]], color=GOLD, s=36, zorder=3)
            ax.annotate(_short(values[-1], spec.get("unit", "")), (x[-1], values[-1]), color=TEXT, fontsize=11,
                        xytext=(-8, 10), textcoords="offset points", ha="right")
        step = max(1, len(labels) // 8)
        ax.set_xticks(x[::step])
        ax.set_xticklabels(labels[::step], color=MUTED, fontsize=10)
        ax.tick_params(axis="y", colors=MUTED, labelsize=10)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _short(v, "")))
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#2a3a60")
        ax.grid(axis="y", color="#1f2e52", linewidth=0.8)
        ax.set_axisbelow(True)
        unit = spec.get("unit", "")
        fig.text(0.06, 0.94, spec.get("title", ""), color=TEXT, fontsize=16, fontweight="bold", ha="left")
        if unit:
            fig.text(0.06, 0.885, f"단위: {unit}", color=MUTED, fontsize=10, ha="left")
        fig.text(0.06, 0.03, f"자료: {spec.get('source', '')}", color=MUTED, fontsize=9.5, ha="left")
        fig.text(0.94, 0.03, SITE_HOST, color=GOLD, fontsize=9.5, ha="right")
        fig.subplots_adjust(left=0.08, right=0.96, top=0.82, bottom=0.14)
        out_path = out_path or _tmp_png("chart_")
        fig.savefig(out_path, facecolor=NAVY)
        plt.close(fig)
        return out_path
    except Exception as e:
        print(f"ℹ️ 차트 만들기 실패: {type(e).__name__}: {e}")
        return None


def _short(v, unit):
    """축·라벨용 숫자: 254341 → 25.4만, 51082431 → 5,108만, 0.799 → 0.799"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    a = abs(v)
    if a >= 1e8:
        txt = f"{v / 1e8:,.1f}억"
    elif a >= 1e4:
        txt = f"{v / 1e4:,.1f}만" if a < 1e6 else f"{v / 1e4:,.0f}만"
    elif a >= 100 or float(v).is_integer():
        txt = f"{v:,.0f}"
    else:
        txt = f"{v:,.3f}".rstrip("0").rstrip(".")
    return txt + (unit if unit in ("%", "%p") else "")


def chart_html(img_url, spec):
    alt = html.escape(spec.get("title", "데이터 차트"))
    src = html.escape(spec.get("source", ""))
    return (f'<figure class="ondo-chart" style="margin:28px 0;"><img src="{html.escape(img_url)}" alt="{alt}" '
            f'style="width:100%;height:auto;border-radius:10px;" loading="lazy" />'
            f'<figcaption style="font-size:13px;color:#8a96b0;margin-top:6px;">{alt} · 자료: {src}</figcaption></figure>')


# ------------------------------------------------------------
# 3) Unsplash 사진 (UNSPLASH_ACCESS_KEY가 없으면 건너뜀)
# ------------------------------------------------------------
def unsplash_photo(query, used=None):
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not key or not query:
        return None
    try:
        r = requests.get("https://api.unsplash.com/search/photos", timeout=12,
                         headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
                         params={"query": query, "per_page": 8, "orientation": "landscape", "content_filter": "high"})
        results = r.json().get("results", []) if r.ok else []
    except Exception as e:
        print(f"ℹ️ Unsplash 검색 실패: {type(e).__name__}")
        return None
    used = used or set()
    pick = next((p for p in results if p.get("id") not in used), None)
    if not pick:
        return None
    # Unsplash 규칙: 사진을 쓸 때 다운로드 집계 주소를 한 번 호출해야 한다.
    try:
        dl = (pick.get("links") or {}).get("download_location")
        if dl:
            requests.get(dl, timeout=8, headers={"Authorization": f"Client-ID {key}"})
    except Exception:
        pass
    user = pick.get("user") or {}
    utm = f"utm_source={UNSPLASH_APP_NAME}&utm_medium=referral"
    return {"id": pick.get("id"), "url": (pick.get("urls") or {}).get("regular"),
            "alt": pick.get("alt_description") or query,
            "author": user.get("name") or "Unsplash",
            "author_url": f"{(user.get('links') or {}).get('html', 'https://unsplash.com')}?{utm}",
            "unsplash_url": f"https://unsplash.com/?{utm}"}


def photo_html(photo, alt_ko=""):
    if not photo or not photo.get("url"):
        return ""
    alt = html.escape(alt_ko or photo.get("alt") or "")
    return (f'<figure class="ondo-photo" style="margin:24px 0;"><img src="{html.escape(photo["url"])}" alt="{alt}" '
            f'style="width:100%;height:auto;border-radius:10px;" loading="lazy" />'
            f'<figcaption style="font-size:12px;color:#8a96b0;margin-top:6px;">사진: '
            f'<a href="{html.escape(photo["author_url"])}" target="_blank" rel="noopener">{html.escape(photo["author"])}</a>'
            f' / <a href="{html.escape(photo["unsplash_url"])}" target="_blank" rel="noopener">Unsplash</a></figcaption></figure>')
