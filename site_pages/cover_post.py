"""이미 올라간 글의 대표 이미지를 새 표지로 바꾸기(2026-11-19).
  python site_pages/cover_post.py <글번호> [라벨] [원글번호]   라벨 예: GUIDE·COMPARE·ANALYSIS·ISSUE (없으면 DATA)
  원글번호: 영어판이면 한국어 원글 번호 - 원글 제목으로 그림을 골라 같은 명화가 붙음(11-21)
제목·분야는 글에서 읽고, 표지 숫자는 제목에서만 가져온다(ondo/media/cover.py). 옛 카드 파일은 지우지 않는다(미디어에 남음)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(pid, kicker="DATA", src=None):
    import html
    import requests
    import blog_engine as be
    from ondo.media.cover import cover_for
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}"
    j = requests.get(base, headers=h, params={"fields": "ID,title,categories,status,URL"}, timeout=30).json()
    title = html.unescape(j.get("title") or "")
    cats = [c.get("slug") for c in (j.get("categories") or {}).values()]
    if not title:
        print("글 받기 실패")
        return 1
    key = title
    if src:                                                          # 영어판: 원글 제목을 그림 고르는 열쇠로
        k = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{src}", headers=h,
                         params={"fields": "title"}, timeout=30).json()
        key = html.unescape(k.get("title") or "") or title
    path = cover_for(title, cats[0] if cats else "etf", kicker.upper(), key=key)
    if not path:
        return 1
    mid, url = be._upload_media(path, "image/png")
    if not mid:
        return 1
    ok = be.wp_set_featured_image(pid, mid)
    print(f"표지 {'바꿈' if ok else '바꾸기 실패'}: {j.get('URL')} ← {url} (분야 {cats}, 라벨 {kicker})")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(main(int(a[0]), *(a[1:3])) if a and a[0].isdigit() else (print(__doc__) or 1))
