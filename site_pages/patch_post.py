"""공개 글의 문장 몇 개만 정확히 고치기(2026-11-19) - 사람 읽기에서 찾은 사실 오류·설명 부족을 글 전체 다시 쓰기(Gemini 20번 넘게) 없이 고친다.

  python site_pages/patch_post.py <글주소slug>
lab/patches/<slug>.json = [{"old": "원문 그대로", "new": "바꿀 문장", "why": "이유"}, ...]
- old는 글 본문에 정확히 한 번 있어야 한다(없거나 여러 번이면 아무것도 안 바꾸고 멈춤).
- 공개 상태·제목·주소는 그대로, 본문만 바꾼다. 새 숫자를 넣으면 멈춤(고치기에서 숫자를 지어내지 않게).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def apply(content, patches):
    """(새 본문, 문제 목록)."""
    probs = []
    for p in patches:
        n = content.count(p["old"])
        if n != 1:
            probs.append(f"'{p['old'][:40]}…' 이 {n}번 있음(정확히 1번이어야 함)")
            continue
        new_nums = set(re.findall(r"\d[\d,.]*", p["new"])) - set(re.findall(r"\d[\d,.]*", content))
        if new_nums:
            probs.append(f"새 숫자가 들어감: {sorted(new_nums)} - 고치기에서 숫자를 더하지 않음")
            continue
        content = content.replace(p["old"], p["new"])
    return content, probs


def main(slug):
    import requests
    import blog_engine as be
    patches = json.load(open(os.path.join(ROOT, "lab", "patches", f"{slug}.json"), encoding="utf-8"))
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/"
    ref = slug if slug.isdigit() else "slug:" + slug        # 글번호 또는 글 주소
    r = requests.get(base + ref, headers=h, params={"context": "edit", "fields": "ID,status,content,URL"}, timeout=30)
    if not r.ok:
        print("글 받기 실패:", r.status_code, r.text[:200])
        return 1
    j = r.json()
    new, probs = apply(j["content"], patches)
    if probs:
        print("고치지 않음:")
        for p in probs:
            print(" -", p)
        return 1
    r2 = requests.post(base + str(j["ID"]), headers=h, data={"content": new}, timeout=60)
    after = (r2.json() or {}).get("status") if r2.ok else r2.text[:200]
    print(f"고침 {len(patches)}곳: {r2.status_code} 상태 {j['status']}→{after} {j.get('URL')}")
    for p in patches:
        print(" -", p.get("why", ""))
    return 0 if r2.ok and after == j["status"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else (print(__doc__) or 1))
