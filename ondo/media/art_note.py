"""표지 그림 설명 상자(2026-11-21 사용자 '최선의 위치를 생각해서') - 글 끝 '📌 데이터 출처' 상자 바로 위.

왜 거기: 본문을 방해하지 않고 끝까지 읽은 독자에게 보이며, 출처 상자 옆이라 '이 글의 자료·출처 정보'로 읽힌다.
오른쪽 계기판은 휴대폰에서 안 보여 빼고, 글 첫머리는 본문보다 먼저 나와 방해가 됨.
설명은 picks.json 'about'(Claude가 그림을 보고 미술관 자료로 확인한 것만 - 작가·생몰년·그려진 것). 해석·평가는 쓰지 않음.
같은 글에 다시 넣으면 앞의 상자를 바꿔 끼움(class="ondo-art").
"""
import html as _h
import re

BOX_RE = re.compile(r'\s*<div class="ondo-art"[^>]*>.*?</div><!-- /ondo-art -->', re.S)


def note_html(art, en=False):
    if not art or not art.get("about"):
        return ""
    about = art["about"]["en" if en else "ko"]
    credit = art.get("credit") or ""
    link = ""
    if art.get("url"):
        link = (f' <a href="{_h.escape(art["url"])}" target="_blank" rel="noopener nofollow">'
                f'{"View the artwork" if en else "작품 보기"}</a>')
    label = "🖼 Cover art" if en else "🖼 표지 그림"
    return ('<div class="ondo-art" style="margin-top:30px;padding:14px 16px;background:#f8f9fa;border-left:3px solid #c9d2e3;'
            'border-radius:6px;font-size:13px;line-height:1.7;color:#3d4757;">'
            f'<strong>{label}</strong><br/>{_h.escape(about)}<br/>'
            f'<span style="color:#7a8597;">{_h.escape(credit)}</span>{link}</div><!-- /ondo-art -->')


def inject(content, box):
    """글 본문에 상자를 넣는다(있던 상자는 바꿈). 자리: 📌 출처 상자 앞 → 없으면 맨 끝 안내문 앞 → 없으면 끝."""
    content = BOX_RE.sub("", content or "")
    if not box:
        return content
    m = re.search(r'<div[^>]*>\s*<strong>📌', content)
    if not m:
        m = re.search(r'<p[^>]*>\s*(이 글은 공개 데이터|This article)', content)
    if m:
        return content[:m.start()] + box + content[m.start():]
    return content + box


def for_post(title, category="etf", tags=(), key=None, en=False):
    """그 글의 표지 그림 설명 상자 HTML(표지와 같은 그림 - key = 한국어 원글 제목)."""
    try:
        from ondo.media.cover import country_for, pick_art
        k = key or title
        return note_html(pick_art(country_for(k, tags, category), k), en)
    except Exception as e:
        print("ℹ️ 표지 그림 설명 실패:", type(e).__name__, e)
        return ""
