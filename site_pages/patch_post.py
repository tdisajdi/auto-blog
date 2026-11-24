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


def apply(content, patches, facts=""):
    """(새 본문, 문제 목록). facts: 그 글을 쓸 때 받은 계산 자료 - 여기 있는 숫자는 고칠 때 넣어도 됨(11-21 873)."""
    probs = []
    facts_nums = set(re.findall(r"\d[\d,.]*", facts or ""))
    def _done_later(k, text):
        """11-22: 나중 고침이 k번 고침의 새 문구를 통째로(11-24: 또는 그 일부를) 덮어썼고, 그 나중 고침도 이미 들어갔거나 또 덮어쓰였나(여러 번 겹쳐도 따라감)."""
        nk = patches[k].get("new")
        for j in range(k + 1, len(patches)):
            q = patches[j]
            if nk and (nk in q.get("old", "") or (len(q.get("old", "")) >= 8 and q["old"] in nk)) and q.get("new") and (q["new"] in text or _done_later(j, text)):
                return True
        return False
    for k, p in enumerate(patches):
        n = content.count(p["old"])
        if n == 0 and p.get("new") and p["new"] not in content and _done_later(k, content):
            continue        # 11-22: 나중 고침이 이 고침의 새 문구를 통째로 덮어씀(정리 섹션 새로 쓰기) - 이미 지나간 고침
        if n == 0 and p.get("new") and content.count(p["new"]) == 1:
            continue        # 이미 들어간 고침(11-21: 같은 파일에 다음 판 고침을 이어 붙일 수 있게)
        if p.get("new") and p["old"] in p["new"] and p["new"] in content:
            continue        # 11-21 873·857: 새 문구가 옛 문구를 품는 고침(앞뒤에 덧붙이기)은 다시 돌리면 또 덧붙음 → 이미 들어갔으면 건너뜀
        if n == 0 and not p.get("new"):
            continue        # 11-21 873: 지우기 고침이 이미 들어감(지운 덩어리는 다시 찾을 수 없음)
        if n != 1:
            probs.append(f"'{p['old'][:40]}…' 이 {n}번 있음(정확히 1번이어야 함)")
            continue
        _nohref = lambda t: re.sub(r'href="[^"]*"', "", t)    # 11-21: 링크 주소 속 날짜(2026/11/19)는 글 숫자가 아님
        new_nums = set(re.findall(r"\d[\d,.]*", _nohref(p["new"]))) - set(re.findall(r"\d[\d,.]*", _nohref(content))) - facts_nums
        if new_nums:   # 11-22 852: '1,080,000원' → '108만 원'처럼 단위만 바꾼 같은 값은 새 숫자가 아님
            have = re.sub(r"[,\s]", "", _nohref(content) + " " + (facts or ""))
            def _same_value(x):
                m = re.search(re.escape(x) + r"\s*(만|억)", p["new"])
                if not m:
                    return False
                v = float(x.replace(",", "")) * (10000 if m.group(1) == "만" else 100000000)
                return v.is_integer() and str(int(v)) in have
            new_nums = {x for x in new_nums if not _same_value(x)}
        if new_nums:
            probs.append(f"새 숫자가 들어감: {sorted(new_nums)} - 고치기에서 숫자를 더하지 않음")
            continue
        content = content.replace(p["old"], p["new"])
    return content, probs


def _facts_for(pid):
    """11-21: 그 글의 계산 자료(실행 기록 facts). 사실 다시 검증 기록(lab/recheck/<번호>.json)의 log 이름으로 찾음. 없으면 ""."""
    import glob
    try:
        log = json.load(open(os.path.join(ROOT, "lab", "recheck", f"{pid}.json"), encoding="utf-8")).get("log")
        for f in glob.glob(os.path.join(ROOT, "logs", "*", log or "-")):
            return json.load(open(f, encoding="utf-8")).get("facts") or ""
    except Exception:
        pass
    return ""


def main(slug):
    import requests
    import blog_engine as be
    patches = json.load(open(os.path.join(ROOT, "lab", "patches", f"{slug}.json"), encoding="utf-8"))
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/"
    ref = slug if slug.isdigit() else "slug:" + slug        # 글번호 또는 글 주소
    r = requests.get(base + ref, headers=h, params={"context": "edit", "fields": "ID,status,content,excerpt,URL,title"}, timeout=30)
    if not r.ok:
        print("글 받기 실패:", r.status_code, r.text[:200])
        return 1
    j = r.json()
    # 11-19: "field": "excerpt"면 요약문(첫 화면 카드·검색 설명에 보이는 글)을 고침 - 본문만 고치고 요약문에 깨진 표기가 남았던 일
    body_p = [p for p in patches if p.get("field", "content") == "content"]
    ex_p = [p for p in patches if p.get("field") == "excerpt"]
    ti_p = [p for p in patches if p.get("field") == "title"]          # 11-21: 제목도 고칠 수 있게(새 숫자 금지 같음)
    facts = _facts_for(str(j["ID"]))
    new, probs = apply(j["content"], body_p, facts) if body_p else (j["content"], [])
    new_ex, probs2 = apply(j.get("excerpt") or "", ex_p) if ex_p else (None, [])
    new_ti, probs3 = apply(j.get("title") or "", ti_p) if ti_p else (None, [])
    probs += probs2 + probs3
    if probs:
        print("고치지 않음:")
        for p in probs:
            print(" -", p)
        return 1
    data = {}
    if body_p:
        data["content"] = new
    if ex_p:
        data["excerpt"] = new_ex
    if ti_p:
        data["title"] = new_ti
    r2 = requests.post(base + str(j["ID"]), headers=h, data=data, timeout=60)
    after = (r2.json() or {}).get("status") if r2.ok else r2.text[:200]
    print(f"고침 {len(patches)}곳: {r2.status_code} 상태 {j['status']}→{after} {j.get('URL')}")
    for p in patches:
        print(" -", p.get("why", ""))
    return 0 if r2.ok and after == j["status"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and re.fullmatch(r"\d+(-\d+)+", sys.argv[1]):   # 11-24: 여러 글 한 번에(patch:701-705-756)
        sys.exit(max(main(s) for s in sys.argv[1].split("-")))
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else (print(__doc__) or 1))
