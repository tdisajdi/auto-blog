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
# 배치 규칙 - 이미지가 중구난방으로 들어가지 않게
#  - 한 글에 사진 최대 1장, 차트 최대 1개 (표는 글쓰기 규칙에서 Part3에 1개로 제한)
#  - 사진은 도입부 끝(첫 번째 대제목 바로 앞): 글 분위기를 잡는 자리
#  - 차트는 숫자를 다루는 본문 중간(세 번째 대제목 앞, 대제목이 적으면 두 번째 앞)
#  - 둘이 같은 자리에 붙지 않게, 그리고 표 바로 뒤에 차트가 붙지 않게 한 칸 뒤로 미룬다
# ------------------------------------------------------------
def place_media(body, photo_block="", chart_block=""):
    import re
    heads = [m.start() for m in re.finditer(r"<h3[\s>]", body)]
    inserts = []
    if photo_block and heads:
        inserts.append((heads[0], photo_block))
    if chart_block and heads:
        idx = 2 if len(heads) >= 3 else min(1, len(heads) - 1)
        if photo_block and idx == 0:
            idx = 1 if len(heads) > 1 else None
        # 바로 앞 구간이 표로 끝나면(표 → 차트가 연달아 보이면 답답함) 다음 대제목 앞으로
        while idx is not None and idx < len(heads) and body[:heads[idx]].rstrip().endswith("</table>"):
            idx = idx + 1 if idx + 1 < len(heads) else None
        if idx is not None:
            inserts.append((heads[idx], chart_block))
        else:
            inserts.append((len(body), chart_block))
    if chart_block and not heads:
        inserts.append((len(body), chart_block))
    for pos, block in sorted(inserts, key=lambda x: x[0], reverse=True):
        body = body[:pos] + block + "\n" + body[pos:]
    return body


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
IMAGE_REQUEST_KEEP_DAYS = 14
IMAGE_SIZE_TEXT = "1216 x 640 (가로형, 안 되면 1024 x 544)"
# FLUX 계열은 부정 프롬프트를 거의 안 쓰므로 하지 말아야 할 것도 문장 안에 넣는다.
IMAGE_STYLE = ("Editorial illustration for a data-focused blog, cinematic soft lighting, deep navy blue and warm "
               "gold color palette, clean minimal composition, the main subject placed on the right side with calm "
               "empty dark space on the left, no text, no letters, no numbers, no logos, no watermark, "
               "no recognizable real people.")


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


def send_image_prompt(post_id, title, category_code, url):
    """발행 직후 텔레그램으로 프롬프트를 보내고, 답장을 기다리는 목록에 저장한다."""
    if not post_id:
        return
    from datetime import datetime
    from blog_engine import _telegram_send_message, _load_json_file, _save_json_file
    prompt = image_prompt(title, category_code)
    head_id = _telegram_send_message(
        f"🎨 썸네일 이미지를 만들어 주세요 (선택)\n글: {title}\n{url}\n\n"
        f"• ComfyUI 모델: FLUX.2 [klein] 4B\n• 크기: {IMAGE_SIZE_TEXT}\n"
        "• 다음 메시지(프롬프트)를 복사해서 쓰고, 만든 그림을 그 메시지나 이 메시지에 '답장'으로 보내주세요.\n"
        "• 그림 위에 제목·분야·사이트 이름은 자동으로 얹어요. 안 보내면 지금 썸네일(제목 카드)이 그대로 남아요.")
    prompt_id = _telegram_send_message(prompt)
    if not (head_id or prompt_id):
        return
    reqs = _load_json_file(IMAGE_REQUESTS_FILE, {}) or {}
    now = datetime.now()
    # 오래된 요청은 정리
    for k in [k for k, v in reqs.items() if (now - datetime.fromisoformat(v["created_at"])).days > IMAGE_REQUEST_KEEP_DAYS]:
        reqs.pop(k)
    entry = {"post_id": post_id, "title": title, "category": category_code, "url": url, "created_at": now.isoformat()}
    for mid in (head_id, prompt_id):
        if mid and mid is not True:
            reqs[str(mid)] = entry
    _save_json_file(IMAGE_REQUESTS_FILE, reqs)


def pending_image_requests():
    from blog_engine import _load_json_file
    return _load_json_file(IMAGE_REQUESTS_FILE, {}) or {}


def handle_image_reply(update):
    """텔레그램 메시지가 썸네일 이미지 답장이면 처리하고 True. 아니면 False.
    답장이 아니어도 기다리는 글이 하나뿐이면 그 글로 처리한다."""
    msg = update.get("message") or {}
    file_id = None
    if msg.get("photo"):
        file_id = max(msg["photo"], key=lambda p: p.get("file_size", 0) or p.get("width", 0)).get("file_id")
    elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
        file_id = msg["document"].get("file_id")
    if not file_id:
        return False
    from blog_engine import (_telegram_send_message, _telegram_download_file, _save_json_file,
                             wp_set_featured_image)
    reqs = pending_image_requests()
    reply_id = str(((msg.get("reply_to_message") or {}).get("message_id")) or "")
    entry = reqs.get(reply_id)
    if not entry:
        posts = {v["post_id"]: v for v in reqs.values()}
        if len(posts) == 1:
            entry = next(iter(posts.values()))
        else:
            _telegram_send_message("🖼️ 사진을 받았는데 어느 글 썸네일인지 모르겠어요. 썸네일 요청 메시지에 '답장'으로 다시 보내주세요."
                                   if posts else "🖼️ 사진을 받았는데 지금 썸네일을 기다리는 글이 없어요.")
            return True
    src = _tmp_png("tg_")
    if not _telegram_download_file(file_id, src):
        _telegram_send_message("⚠️ 사진을 내려받지 못했어요. 잠시 뒤 다시 보내주세요.")
        return True
    card = make_title_card(entry["title"], entry["category"], background=src)
    try:
        os.remove(src)
    except OSError:
        pass
    media_id, _ = upload_png(card)
    if media_id and wp_set_featured_image(entry["post_id"], media_id):
        for k in [k for k, v in reqs.items() if v["post_id"] == entry["post_id"]]:
            reqs.pop(k)
        _save_json_file(IMAGE_REQUESTS_FILE, reqs)
        _telegram_send_message(f"✅ 썸네일을 바꿨어요: {entry['title']}\n{entry['url']}")
    else:
        _telegram_send_message("⚠️ 썸네일 바꾸기에 실패했어요. 잠시 뒤 다시 답장으로 보내주세요.")
    return True
