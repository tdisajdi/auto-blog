"""사이트 기본 페이지(소개·개인정보처리방침·문의·면책 안내)를 워드프레스 '페이지'로 올린다(2026-11-11 사용자 결정).
- 글(post)이 아니라 페이지(page)라 카테고리에 안 들어간다.
- 같은 주소(slug)의 페이지가 있으면 새로 만들지 않고 내용만 바꾼다(여러 번 돌려도 하나).
- 기본은 비공개 초안(draft). 공개(publish)는 사용자가 초안을 보고 "공개해"라고 한 뒤에만 - 깃허브 입력 site_pages=publish.
파일 첫 줄: <!-- slug: about | title: ondo 소개 --> 처럼 주소와 제목을 적는다. <!-- 운영자 확인 필요 ... --> 주석은 올리기 전에 뺀다."""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
_HEAD = re.compile(r"^\s*<!--\s*slug:\s*([\w-]+)\s*\|\s*title:\s*(.+?)\s*-->\s*", re.S)


def load_pages():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "*.html"))):
        s = open(p, encoding="utf-8").read()
        m = _HEAD.match(s)
        if not m:
            continue
        body = re.sub(r"<!--.*?-->\s*", "", s[m.end():], flags=re.S).strip()
        out.append({"slug": m.group(1), "title": m.group(2), "html": body})
    return out


def upsert_page(page, status, session=None):
    import requests
    import blog_engine as be
    s = session or requests
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/"
    r = s.get(base + "slug:" + page["slug"], headers=h, params={"fields": "ID,status,URL,type"}, timeout=20)
    data = {"title": page["title"], "content": page["html"], "type": "page", "status": status, "slug": page["slug"],
            "comment_status": "closed"}
    if r.status_code == 200 and (r.json() or {}).get("type") == "page" and (r.json() or {}).get("status") == "publish":
        # 2026-11-11 사고: 기존 공개 'About'(번호 1)을 초안으로 덮고 비공개로 바꿈 → 이미 공개된 페이지는 절대 건드리지 않는다
        return False, f"{page['slug']}: 같은 주소의 공개 페이지가 이미 있어 건드리지 않음({r.json().get('URL')}) - 사용자에게 물을 것"
    if r.status_code == 200 and (r.json() or {}).get("type") == "page":
        pid = r.json()["ID"]
        r2 = s.post(base + str(pid), headers=h, data=data, timeout=60)
        verb = "바꿈"
    else:
        r2 = s.post(base + "new/", headers=h, data=data, timeout=60)
        verb = "새로 만듦"
    if r2.status_code not in (200, 201):
        return False, f"{page['slug']}: 실패 {r2.status_code} {r2.text[:160]}"
    j = r2.json()
    return True, f"{page['slug']}: {verb} - {j.get('status')} {j.get('URL', '')} (번호 {j.get('ID')})"


def main(status="draft"):
    if status not in ("draft", "publish"):
        print("status는 draft 또는 publish")
        return 1
    import blog_engine as be
    if not (be.WP_OAUTH_TOKEN and be.WP_SITE_ID):
        print("WP_OAUTH_TOKEN/WP_SITE_ID 없음")
        return 1
    ok_all = True
    for p in load_pages():
        ok, msg = upsert_page(p, status)
        ok_all &= ok
        print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "draft"))
