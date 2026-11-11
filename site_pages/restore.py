"""2026-11-11 사고 되돌리기: upload.py가 기존 공개 페이지(about, 번호 1)를 초안 내용으로 덮고 비공개로 바꿈.
워드프레스가 남긴 이전 판(revisions)에서 사고 시각(01:30 UTC) 이전 마지막 판의 제목·내용을 되살리고 공개로 돌린다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CUTOFF = "2026-11-11T01:30:00"


def main(page_id="1"):
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    url = f"https://public-api.wordpress.com/wp/v2/sites/{be.WP_SITE_ID}/pages/{page_id}/revisions"
    r = requests.get(url, headers=h, params={"per_page": 50, "context": "edit"}, timeout=30)
    print("이전 판 목록:", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        return 1
    revs = sorted(r.json(), key=lambda x: x.get("date_gmt", ""))
    for x in revs:
        t = (x.get("title") or {}).get("raw") or (x.get("title") or {}).get("rendered")
        print(" -", x.get("id"), x.get("date_gmt"), str(t)[:40], len(((x.get("content") or {}).get("raw") or (x.get("content") or {}).get("rendered") or "")))
    before = [x for x in revs if (x.get("date_gmt") or "") < CUTOFF]
    if not before:
        print("사고 이전 판이 없음 - 되돌릴 수 없음(사용자에게 보고)")
        return 1
    old = before[-1]
    title = (old.get("title") or {}).get("raw") or (old.get("title") or {}).get("rendered") or "About"
    content = (old.get("content") or {}).get("raw") or (old.get("content") or {}).get("rendered") or ""
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{page_id}"
    r2 = requests.post(base, headers=h, data={"title": title, "content": content, "status": "publish"}, timeout=60)
    print("되돌리기:", r2.status_code, (r2.json() or {}).get("status") if r2.status_code in (200, 201) else r2.text[:300],
          "| 판", old.get("id"), old.get("date_gmt"), "| 제목", title[:40], "| 길이", len(content))
    return 0 if r2.status_code in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["1"])))
