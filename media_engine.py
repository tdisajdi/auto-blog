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


def make_title_card(title, category_code, out_path=None, background=None):
    """제목 카드 PNG 경로를 돌려준다. 실패하면 None.
    background(이미지 파일 경로)를 주면 그 그림을 배경으로 깔고 왼쪽을 어둡게 덮어 글씨가 잘 보이게 한다
    (ComfyUI로 만든 이미지를 텔레그램으로 받았을 때)."""
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
        if background:
            img = _background_with_shade(background, W, H, Image)
            d = ImageDraw.Draw(img)
        else:
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


def _background_with_shade(path, W, H, Image):
    """배경 그림을 1200x630에 꽉 차게 자르고, 왼쪽부터 남색으로 덮어 제목이 잘 읽히게 한다."""
    bg = Image.open(path).convert("RGB")
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * scale + 0.5), int(bg.height * scale + 0.5)), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H))
    # 왼쪽 0~45%는 진하게(글씨 자리), 오른쪽으로 갈수록 그림이 드러나게. 한 줄짜리 투명도를 만들어 늘린다.
    alpha_row = [int(235 if x / W < 0.45 else max(40, 235 - (x / W - 0.45) * 350)) for x in range(W)]
    mask = Image.new("L", (W, 1))
    mask.putdata(alpha_row)
    shade = Image.new("RGBA", (W, H), (11, 20, 40, 255))
    shade.putalpha(mask.resize((W, H)))
    return Image.alpha_composite(bg.convert("RGBA"), shade).convert("RGB")


# ------------------------------------------------------------
# 2) 데이터 차트
#    spec = {"title": 제목, "labels": [x축 라벨], "values": [값], "unit": 단위,
#            "source": 출처 문구, "kind": "line" | "bar"}
# ------------------------------------------------------------
def make_chart(spec, out_path=None):
    try:
        labels, values = list(spec.get("labels") or []), list(spec.get("values") or [])
        # 점이 2개뿐이면 차트가 주는 정보가 거의 없어서(본문 문장으로 충분) 그리지 않는다.
        if len(values) < 3 or len(labels) != len(values):
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
        txt = f"{v / 1e8:,.1f}".rstrip("0").rstrip(".") + "억"
    elif a >= 1e4:
        txt = (f"{v / 1e4:,.1f}".rstrip("0").rstrip(".") if a < 1e6 else f"{v / 1e4:,.0f}") + "만"
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


# ------------------------------------------------------------
# 배치 규칙 - 이미지가 중구난방으로 들어가지 않게 (사용자 요청)
#  - 이미지가 들어갈 수 있는 곳은 "대제목(<h3>) 바로 앞", 즉 앞 구간의 글이 완전히 끝난 자리뿐.
#    문단 중간·표 안·목록 안에는 절대 안 들어간다.
#  - 바로 앞이 표나 다른 이미지로 끝나는 자리는 건너뛴다(표 → 이미지가 연달아 붙지 않게).
#  - 앞 구간의 글이 충분히 긴(약 250자 이상) 자리만 쓴다.
#  - 한 자리에 하나씩. 사진은 도입부 끝, 차트는 본문 중간, 본문 그림(최대 2장)은 중간·후반에 흩어서.
#    가능하면 이미지끼리 사이에 구간이 하나 이상 있게 한다.
# ------------------------------------------------------------
MAX_BODY_IMAGES = 2
MIN_SECTION_TEXT = 250


def _plain(html_text):
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text)).strip()


def plan_layout(body, photo_block="", chart_block="", n_slots=0):
    """이미지 자리를 정해서 넣는다. 반환: (새 본문, 본문 그림 자리 목록[{slot, heading, text}]).
    본문 그림 자리는 빈 표시(<div id="ondo-slot-N">)만 넣어 두고, 사용자가 그림을 보내면 그 자리를 채운다."""
    import re
    heads = [m.start() for m in re.finditer(r"<h3[\s>]", body)]
    if not heads:
        return (body + ("\n" + chart_block if chart_block else "")), []

    def section(i):          # i번 자리(대제목 i 앞)의 바로 앞 구간
        return body[(heads[i - 1] if i > 0 else 0):heads[i]]

    def heading(i):
        if i <= 0:
            return ""
        m = re.match(r"<h3[^>]*>(.*?)</h3>", body[heads[i - 1]:], re.S)
        return _plain(m.group(1)) if m else ""

    def good(i):
        before = body[:heads[i]].rstrip()
        if re.search(r"</(table|figure)>$", before, re.I):
            return False
        return i == 0 or len(_plain(section(i))) >= MIN_SECTION_TEXT

    used = {}
    if photo_block and good(0):
        used[0] = photo_block

    def pick(prefer, strict=False):
        cands = [i for i in range(len(heads)) if i not in used and good(i)]
        far = [i for i in cands if all(abs(i - u) >= 2 for u in used)]
        # 본문 그림(strict)은 다른 이미지와 사이에 구간이 하나 이상 있을 때만. 차트는 자리가 없으면 붙여서라도.
        pool = far if strict else (far or cands)
        return min(pool, key=lambda i: (abs(i - prefer), i)) if pool else None

    if chart_block:
        idx = pick(2 if len(heads) >= 3 else 1)
        if idx is None:
            body = body + "\n" + chart_block
        else:
            used[idx] = chart_block

    slots = []
    for k, frac in enumerate([0.45, 0.8][:min(n_slots, MAX_BODY_IMAGES)], start=1):
        idx = pick(max(1, round(len(heads) * frac)), strict=True)
        if idx is None or idx == 0:
            break
        used[idx] = f'<div id="ondo-slot-{k}" class="ondo-slot"></div>'
        slots.append({"slot": k, "heading": heading(idx), "text": _plain(section(idx))[:400]})

    for pos, block in sorted(((heads[i], b) for i, b in used.items()), key=lambda x: x[0], reverse=True):
        body = body[:pos] + block + "\n" + body[pos:]
    return body, slots


def place_media(body, photo_block="", chart_block=""):
    """(예전 이름 유지) 사진·차트만 배치."""
    return plan_layout(body, photo_block, chart_block, 0)[0]


def body_image_html(img_url, slot, alt):
    return (f'<figure id="ondo-slot-{slot}" class="ondo-illust" style="margin:28px 0;">'
            f'<img src="{html.escape(img_url)}" alt="{html.escape(alt)}" style="width:100%;height:auto;border-radius:10px;" '
            f'loading="lazy" /><figcaption style="font-size:12px;color:#8a96b0;margin-top:6px;">AI로 만든 일러스트</figcaption>'
            f'</figure>')


def shrink_for_web(src, max_side=1200):
    """본문 그림은 휴대폰에서도 빨리 열리게 긴 변 1200px, JPEG로 줄인다. 반환: 새 파일 경로 또는 None."""
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.thumbnail((max_side, max_side))
        fd, out = tempfile.mkstemp(prefix="illust_", suffix=".jpg")
        os.close(fd)
        img.save(out, "JPEG", quality=85, optimize=True, progressive=True)
        return out
    except Exception as e:
        print(f"ℹ️ 그림 줄이기 실패: {type(e).__name__}")
        return None


def upload_png(path):
    """만든 PNG를 워드프레스 미디어에 올리고 (ID, URL). 임시 파일은 지운다."""
    if not path:
        return None, None
    try:
        from blog_engine import _upload_media
        return _upload_media(path, "image/png")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def featured_card_id(title, category_code):
    """제목 카드를 만들어 올리고 첨부파일 ID를 돌려준다(대표 이미지용). 실패하면 None."""
    media_id, _ = upload_png(make_title_card(title, category_code))
    return media_id


# ------------------------------------------------------------
# 4) ComfyUI 썸네일 (사용자 PC의 ComfyUI + FLUX.2 [klein] 4B, Apache 2.0 → 상업적 이용 가능)
#  - 글을 발행하면 텔레그램으로 이미지 프롬프트를 보낸다.
#  - 사용자가 ComfyUI로 만든 그림을 그 메시지에 "답장"으로 보내면, 10분 점검 때
#    그 그림에 제목·분야·사이트 이름을 얹어서 그 글의 대표 이미지로 바꾼다.
#  - 안 보내면 제목 카드가 그대로 남는다(아무것도 멈추지 않음).
# ------------------------------------------------------------
IMAGE_REQUESTS_FILE = "pending_images.json"
IMAGE_REQUEST_KEEP_DAYS = 90   # 이 기간 안에는 요청 메시지에 답장하면 언제든(여러 번) 썸네일을 바꿀 수 있음
IMAGE_SIZE_TEXT = "1216 x 640 (가로형, 안 되면 1024 x 544)"
# FLUX 계열은 부정 프롬프트를 거의 안 쓰므로 하지 말아야 할 것도 문장 안에 넣는다.
IMAGE_STYLE = ("Editorial illustration for a data-focused blog, cinematic soft lighting, deep navy blue and warm "
               "gold color palette, clean minimal composition, the main subject placed on the right side with calm "
               "empty dark space on the left, no text, no letters, no numbers, no logos, no watermark, "
               "no recognizable real people.")


# 본문 그림: 같은 색감, 글씨를 얹지 않으므로 주제를 가운데 둬도 된다.
IMAGE_STYLE_BODY = ("Editorial illustration for a data-focused blog article, cinematic soft lighting, deep navy blue "
                    "and warm gold color palette, clean minimal composition, no text, no letters, no numbers, "
                    "no logos, no watermark, no recognizable real people.")


def _ask_scene(instruction):
    try:
        import json as _json
        import re as _re
        from blog_engine import get_gemini_response
        res = get_gemini_response(
            instruction + " 실제 인물·유명인·회사 로고·제품 상표·의료 시술 장면·글자는 넣지 말고, 사실처럼 보이는 "
            "뉴스 사진 장면도 피하세요.\n" + 'JSON으로만: {"scene": "영어 한 문장(25단어 이내)"}')
        return str((_json.loads(_re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip()) or {}).get("scene", "")).strip().rstrip(".")
    except Exception:
        return ""


def body_image_prompt(title, heading, text):
    scene = _ask_scene(f"블로그 글 '{title}'의 한 단락입니다.\n단락 제목: {heading}\n단락 내용: {text}\n"
                       "이 단락 내용을 상징하는 일러스트 장면을 영어 한 문장으로 묘사하세요.")
    return f"{scene or 'an abstract illustration that symbolizes ' + (heading or title)}. {IMAGE_STYLE_BODY}"


def image_prompt(title, category_code):
    """글 제목으로 ComfyUI용 영어 프롬프트를 만든다. AI가 실패하면 분야별 기본 장면을 쓴다."""
    fallback = {"etf": "abstract stock market chart lines glowing over a calm city skyline at dusk",
                "trend": "a cozy everyday scene with objects related to a popular new lifestyle trend",
                "tech": "a sleek futuristic technology lab with glowing circuit patterns",
                "bio": "abstract molecules and a laboratory glass flask with soft light",
                "energy": "industrial energy landscape with pipelines, wind turbines and power lines at dusk",
                "society": "an aerial view of a modern city neighborhood with small houses and parks"}
    scene = ""
    try:
        import json as _json
        import re as _re
        from blog_engine import get_gemini_response
        res = get_gemini_response(
            f"블로그 글 제목: {title}\n이 글의 썸네일 그림을 그릴 장면을 영어 한 문장(25단어 이내)으로 묘사하세요. "
            "글의 주제를 상징하는 사물·풍경·추상적 장면으로만 표현하고, 실제 인물·유명인·회사 로고·제품 상표·"
            "의료 시술 장면·글자는 넣지 마세요. 사실처럼 보이는 뉴스 사진 장면도 피하세요.\n"
            'JSON으로만: {"scene": "영어 한 문장"}')
        scene = (_json.loads(_re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip()) or {}).get("scene", "")
    except Exception:
        scene = ""
    scene = str(scene).strip().rstrip(".") or fallback.get(category_code, fallback["trend"])
    return f"{scene}. {IMAGE_STYLE}"


def send_image_prompt(post_id, title, category_code, url, slots=None):
    """발행 직후 텔레그램으로 썸네일 + 본문 그림(최대 2장) 프롬프트를 보내고, 답장을 기다리는 목록에 저장한다."""
    if not post_id:
        return
    from datetime import datetime
    from blog_engine import _telegram_send_message, _load_json_file, _save_json_file
    slots = (slots or [])[:MAX_BODY_IMAGES]
    body_note = (f"• 본문 그림 {len(slots)}장 자리도 비워 뒀어요(단락이 끝나는 곳).\n" if slots else "")
    head_id = _telegram_send_message(
        f"🎨 그림을 만들어 주세요 (모두 선택)\n글: {title}\n{url}\n\n"
        f"• ComfyUI 모델: FLUX.2 [klein] 4B · 크기: {IMAGE_SIZE_TEXT}\n"
        "• 아래 프롬프트 상자를 눌러 복사해서 쓰세요.\n"
        "• 만든 그림 보내는 법 (편한 것 아무거나):\n"
        "  ① 그 프롬프트 메시지에 '답장'으로 → 그 자리에 바로\n"
        "  ② 그냥 보내기 → 봇이 '어디에 넣을까요?' 버튼으로 물어봐요\n"
        "  ③ 그림 설명에 '썸네일' 또는 '본문 그림 1'이라고 쓰기 → 그 자리에 바로\n"
        "• 썸네일은 그림 위에 제목·분야·사이트 이름을 자동으로 얹어요. 본문 그림은 그대로 들어가요.\n"
        + body_note +
        "• 넣고 나면 결과 그림을 보여드려요. 안 보낸 건 그냥 비어 있어요(글은 그대로).\n"
        f"• {IMAGE_REQUEST_KEEP_DAYS}일 안에는 나중에 보내도, 여러 번 바꿔도 돼요.")
    msgs = [("thumb", 0, "🖼️ 썸네일용", image_prompt(title, category_code))]
    for sl in slots:
        msgs.append(("slot", sl["slot"], f"🖼️ 본문 그림 {sl['slot']} ('{sl['heading'] or '단락'}' 단락 뒤)",
                     body_image_prompt(title, sl["heading"], sl["text"])))
    reqs = _load_json_file(IMAGE_REQUESTS_FILE, {}) or {}
    now = datetime.now()
    for k in [k for k, v in reqs.items() if (now - datetime.fromisoformat(v["created_at"])).days > IMAGE_REQUEST_KEEP_DAYS]:
        reqs.pop(k)
    base = {"post_id": post_id, "title": title, "category": category_code, "url": url, "created_at": now.isoformat()}
    if head_id and head_id is not True:
        reqs[str(head_id)] = dict(base, kind="thumb")
    for kind, slot, label, prompt in msgs:
        mid = _telegram_send_message(f"{label} — 이 메시지에 답장\n<pre>{html.escape(prompt)}</pre>", parse_mode="HTML")
        if mid and mid is not True:
            entry = dict(base, kind=kind)
            if kind == "slot":
                entry.update(slot=slot, heading=next((x["heading"] for x in slots if x["slot"] == slot), ""))
            reqs[str(mid)] = entry
    _save_json_file(IMAGE_REQUESTS_FILE, reqs)


def pending_image_requests():
    from blog_engine import _load_json_file
    return _load_json_file(IMAGE_REQUESTS_FILE, {}) or {}


# ------------------------------------------------------------
# 그림 받기 - 사용자가 2장을 보내도 "어느 그림이 어디로 가는지" 헷갈리지 않게 (사용자 요청)
#  ① 프롬프트 메시지에 답장 → 그 자리로 바로
#  ② 그림 설명에 "썸네일" / "본문 그림 1" (+글 주소) → 그 자리로 바로
#  ③ 그냥 보낸 그림 → 봇이 그 그림에 답장으로 "어디에 넣을까요?" 버튼을 보냄 → 누르면 그 자리로
#  처리되면 들어간 결과 그림을 다시 보내서 눈으로 확인할 수 있게 한다.
# ------------------------------------------------------------
IMAGE_INBOX_FILE = "image_inbox.json"   # 버튼 선택을 기다리는 그림
IMAGE_INBOX_KEEP_DAYS = 7


def _posts_index(reqs):
    """요청 목록을 글 단위로 정리: {글번호: {title, category, url, created_at, thumb_done, slots{n: {heading, done}}}}"""
    posts = {}
    for v in reqs.values():
        p = posts.setdefault(v["post_id"], {"post_id": v["post_id"], "title": v["title"], "category": v["category"],
                                            "url": v["url"], "created_at": v["created_at"], "thumb_done": False,
                                            "slots": {}})
        p["created_at"] = max(p["created_at"], v["created_at"])
        if v.get("kind", "thumb") == "thumb":
            p["thumb_done"] = p["thumb_done"] or bool(v.get("replaced_at"))
        else:
            sl = p["slots"].setdefault(v["slot"], {"heading": v.get("heading", ""), "done": False})
            sl["done"] = sl["done"] or bool(v.get("replaced_at"))
    return posts


def _latest_post(posts):
    return max(posts.values(), key=lambda p: p["created_at"]) if posts else None


def _file_id(msg):
    if msg.get("photo"):
        return max(msg["photo"], key=lambda p: p.get("file_size", 0) or p.get("width", 0)).get("file_id")
    if (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
        return msg["document"].get("file_id")
    return None


def _caption_target(caption):
    import re
    c = caption or ""
    m = re.search(r"본문\s*(?:그림)?\s*([12])", c)
    if m:
        return "slot", int(m.group(1))
    if "썸네일" in c:
        return "thumb", None
    return None, None


def _target_label(kind, slot):
    return "썸네일" if kind == "thumb" else f"본문 그림 {slot}"


def handle_image_reply(update):
    """그림 메시지나 그림 위치 버튼이면 처리하고 True. 아니면 False."""
    import re
    cb = update.get("callback_query")
    if cb and str(cb.get("data", "")).startswith("img:"):
        _handle_image_callback(cb)
        return True
    msg = update.get("message") or {}
    file_id = _file_id(msg)
    if not file_id:
        return False
    from blog_engine import _telegram_send_message, wp_find_post_by_url
    reqs = pending_image_requests()
    posts = _posts_index(reqs)
    post, kind, slot = None, None, None
    m = re.search(r"https?://\S+", msg.get("caption") or "")
    if m:
        found = wp_find_post_by_url(m.group(0))
        if not found:
            _telegram_send_message("🖼️ 그림 설명에 있는 주소로 글을 찾지 못했어요. 글 주소를 다시 확인해 주세요.",
                                   reply_to=msg.get("message_id"))
            return True
        post = posts.get(found[0]) or {"post_id": found[0], "title": found[1], "category": found[2],
                                       "url": m.group(0), "thumb_done": False, "slots": {}}
    entry = reqs.get(str(((msg.get("reply_to_message") or {}).get("message_id")) or ""))
    if entry:
        post = post or posts.get(entry["post_id"])
        kind, slot = entry.get("kind", "thumb"), entry.get("slot")
    ck, cs = _caption_target(msg.get("caption"))
    if ck:
        kind, slot = ck, cs
        post = post or _latest_post(posts)
    if kind and post:
        _apply_image(file_id, post, kind, slot, reply_to=msg.get("message_id"))
        return True
    _ask_where(file_id, msg.get("message_id"), post or _latest_post(posts))
    return True


def _where_buttons(iid, post):
    rows = [[("썸네일" + (" ✅넣음·바꾸기" if post.get("thumb_done") else ""), f"img:{iid}:t")]]
    for n, sl in sorted(post.get("slots", {}).items()):
        head = (sl.get("heading") or "단락")[:14]
        rows.append([(f"본문 그림 {n} ('{head}' 뒤)" + (" ✅넣음·바꾸기" if sl.get("done") else ""), f"img:{iid}:s{n}")])
    rows.append([("다른 글", f"img:{iid}:o"), ("취소", f"img:{iid}:x")])
    return rows


def _ask_where(file_id, photo_msg_id, post):
    from datetime import datetime
    from blog_engine import _telegram_send_message, _load_json_file, _save_json_file
    if not post:
        _telegram_send_message("🖼️ 그림을 받았는데 지금 그림을 기다리는 글이 없어요. 넣을 글이 있으면 그림 설명(캡션)에 "
                               "글 주소를 붙여서 다시 보내주세요.", reply_to=photo_msg_id)
        return
    inbox = _load_json_file(IMAGE_INBOX_FILE, {}) or {}
    now = datetime.now()
    for k in [k for k, v in inbox.items() if (now - datetime.fromisoformat(v["created_at"])).days > IMAGE_INBOX_KEEP_DAYS]:
        inbox.pop(k)
    iid = str(photo_msg_id)
    ask_id = _telegram_send_message(f"🖼️ 이 그림은 어디에 넣을까요?\n글: {post['title']}",
                                    buttons=_where_buttons(iid, post), reply_to=photo_msg_id)
    inbox[iid] = {"file_id": file_id, "post": post, "ask_id": ask_id, "created_at": now.isoformat()}
    _save_json_file(IMAGE_INBOX_FILE, inbox)


def _handle_image_callback(cb):
    from blog_engine import (_telegram_send_message, _telegram_edit_text, _telegram_answer_callback,
                             _load_json_file, _save_json_file)
    _telegram_answer_callback(cb.get("id"), "처리 중이에요")
    try:
        _, iid, act = str(cb["data"]).split(":", 2)
    except ValueError:
        return
    ask_id = (cb.get("message") or {}).get("message_id")
    inbox = _load_json_file(IMAGE_INBOX_FILE, {}) or {}
    item = inbox.get(iid)
    if not item:
        _telegram_edit_text(ask_id, "이미 처리했거나 오래된 버튼이에요. 그림을 다시 보내주세요.")
        return
    posts = _posts_index(pending_image_requests())
    if act == "x":
        inbox.pop(iid)
        _save_json_file(IMAGE_INBOX_FILE, inbox)
        _telegram_edit_text(ask_id, "취소했어요. 이 그림은 넣지 않았어요.")
        return
    if act == "o":
        others = sorted(posts.values(), key=lambda p: p["created_at"], reverse=True)[:6]
        if not others:
            _telegram_edit_text(ask_id, "고를 수 있는 다른 글이 없어요. 그림 설명에 글 주소를 붙여 다시 보내주세요.")
            return
        _telegram_edit_text(ask_id, "어느 글에 넣을까요? (아래 새 메시지에서 골라주세요)")
        item["ask_id"] = _telegram_send_message(
            "🗂️ 글을 골라주세요 (최근 순)",
            buttons=[[(p["title"][:30], f"img:{iid}:p{p['post_id']}")] for p in others] + [[("취소", f"img:{iid}:x")]],
            reply_to=int(iid))
        _save_json_file(IMAGE_INBOX_FILE, inbox)
        return
    if act.startswith("p"):
        post = posts.get(int(act[1:])) if act[1:].isdigit() else None
        if not post:
            _telegram_edit_text(ask_id, "그 글을 찾지 못했어요. 그림 설명에 글 주소를 붙여 다시 보내주세요.")
            return
        item["post"] = post
        _telegram_edit_text(ask_id, f"글을 골랐어요: {post['title']}")
        item["ask_id"] = _telegram_send_message(f"🖼️ 이 그림은 어디에 넣을까요?\n글: {post['title']}",
                                                buttons=_where_buttons(iid, post), reply_to=int(iid))
        _save_json_file(IMAGE_INBOX_FILE, inbox)
        return
    post = posts.get(item["post"]["post_id"]) or item["post"]
    kind, slot = ("thumb", None) if act == "t" else ("slot", int(act[1:]) if act[1:].isdigit() else None)
    if kind == "slot" and not slot:
        return
    if _apply_image(item["file_id"], post, kind, slot, reply_to=int(iid)):
        inbox.pop(iid)
        _save_json_file(IMAGE_INBOX_FILE, inbox)
        _telegram_edit_text(ask_id, f"✅ {_target_label(kind, slot)}에 넣었어요: {post['title']}")


def _mark_done(post_id, kind, slot):
    from datetime import datetime
    from blog_engine import _save_json_file
    reqs = pending_image_requests()
    stamp = datetime.now().isoformat()
    for v in reqs.values():
        if v["post_id"] == post_id and v.get("kind", "thumb") == kind and (kind == "thumb" or v.get("slot") == slot):
            v["replaced_at"] = stamp
    _save_json_file(IMAGE_REQUESTS_FILE, reqs)


def _cleanup(*paths):
    for p in paths:
        if p:
            try:
                os.remove(p)
            except OSError:
                pass


def _apply_image(file_id, post, kind, slot, reply_to=None):
    """받은 그림을 썸네일 또는 본문 그림 자리에 넣고, 결과를 텔레그램으로 보여준다. 성공하면 True."""
    import re
    from blog_engine import (_telegram_send_message, _telegram_send_photo, _telegram_download_file, _upload_media,
                             wp_set_featured_image, wp_get_post_content, wp_update_post_content)
    src = _tmp_png("tg_")
    if not _telegram_download_file(file_id, src):
        _cleanup(src)
        _telegram_send_message("⚠️ 그림을 내려받지 못했어요. 잠시 뒤 다시 보내주세요.", reply_to=reply_to)
        return False
    if kind == "thumb":
        card = make_title_card(post["title"], post["category"], background=src)
        media_id = _upload_media(card, "image/png")[0] if card else None
        ok = bool(media_id) and wp_set_featured_image(post["post_id"], media_id)
        if ok:
            _mark_done(post["post_id"], "thumb", None)
            _telegram_send_photo(path=card, caption=f"✅ 썸네일을 바꿨어요: {post['title']}\n{post['url']}",
                                 reply_to=reply_to)
        else:
            _telegram_send_message("⚠️ 썸네일 바꾸기에 실패했어요. 잠시 뒤 다시 보내주세요.", reply_to=reply_to)
        _cleanup(src, card)
        return ok
    # 본문 그림
    small = shrink_for_web(src)
    url = _upload_media(small, "image/jpeg")[1] if small else None
    content = wp_get_post_content(post["post_id"]) if url else None
    if not url or content is None:
        _cleanup(src, small)
        _telegram_send_message("⚠️ 본문 그림을 넣지 못했어요. 잠시 뒤 다시 보내주세요.", reply_to=reply_to)
        return False
    heading = (post.get("slots", {}).get(slot) or {}).get("heading", "")
    block = body_image_html(url, slot, f"{post['title']} - {heading or '본문'} 일러스트")
    pattern = re.compile(r'<(div|figure)[^>]*id="ondo-slot-%s"[^>]*>.*?</\1>' % slot, re.S)
    if pattern.search(content):
        new_content = pattern.sub(lambda m: block, content, count=1)
    else:
        # 자리 표시가 사라졌으면(워드프레스가 빈 칸을 지웠거나 글을 고친 경우) 같은 단락이 끝나는 곳,
        # 즉 그 단락 제목 다음에 오는 대제목 바로 앞에 넣는다.
        heads = [(m.start(), _plain(m.group(1))) for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", content, re.S)]
        idx = next((i for i, (_, t) in enumerate(heads) if heading and t == heading), None)
        if idx is None or idx + 1 >= len(heads):
            _cleanup(src, small)
            _telegram_send_message("⚠️ 이 글에서 본문 그림 자리를 찾지 못했어요(글을 직접 고치면서 단락 제목이 "
                                   "바뀌었을 수 있어요).", reply_to=reply_to)
            return False
        pos = heads[idx + 1][0]
        new_content = content[:pos] + block + "\n" + content[pos:]
    ok = wp_update_post_content(post["post_id"], new_content)
    if ok:
        _mark_done(post["post_id"], "slot", slot)
        where = f" ('{heading}' 단락 뒤)" if heading else ""
        _telegram_send_photo(path=small, caption=f"✅ 본문 그림 {slot}을 넣었어요{where}: {post['title']}\n{post['url']}",
                             reply_to=reply_to)
    else:
        _telegram_send_message("⚠️ 본문 그림을 넣지 못했어요. 잠시 뒤 다시 보내주세요.", reply_to=reply_to)
    _cleanup(src, small)
    return ok
