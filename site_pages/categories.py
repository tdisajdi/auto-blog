"""분야(카테고리) 정리(2026-11-11 전체 개편).

1) 분야 이름·설명을 새로 정한다(주소 slug는 그대로 - 코드·링크가 slug로 찾음).
2) '분류 없음'으로 들어가 있는 글(초안 포함)에 제목·본문 낱말로 분야를 붙인다.
   예전 토큰에 카테고리 권한이 없어 발행 때 분야가 빠졌다(11-11 확인: 49편 모두 Uncategorized).
   애매한 글은 건드리지 않고 목록만 보여 준다.
글 내용·공개 상태는 바꾸지 않는다.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CATS = {
    "etf": ("ETF·투자", "ETF의 수익률·배당·보수를 같은 기간, 같은 기준으로 계산해 비교합니다. 투자 권유가 아니라 숫자를 읽는 법을 정리합니다."),
    "energy": ("에너지·원자재", "유가·원유 재고·환율처럼 생활비에 닿는 숫자를 미국 에너지정보청(EIA) 같은 공식 자료로 읽습니다."),
    "society": ("인구·사회", "통계청(KOSIS)·행정안전부 통계로 1인 가구, 외국인 주민처럼 우리 사회가 어떻게 바뀌는지 봅니다."),
    "biotech": ("바이오·신약", "임상 시험 결과와 승인 일정을 공개 자료로 정리합니다."),
    "patents": ("기술·특허", "새 기술과 특허 소식을 정리합니다."),
    "trend": ("트렌드", "검색 관심이 커진 주제를 자료로 살펴봅니다."),
    "market": ("시장", "시장 전반의 숫자를 정리합니다."),
}

# (분야, 낱말 정규식) - 위에서부터 먼저 맞는 것
RULES = [
    ("energy", r"브렌트|WTI|유가|원유|천연가스|휘발유|에너지"),
    ("society", r"외국인\s*주민|1인\s*가구|인구|출생|고령|가구|KOSIS|통계청"),
    ("biotech", r"임상|신약|바이오|FDA|치료제"),
    ("patents", r"착륙|우주|위성|특허|로봇"),
    ("trend", r"검색량|검색\s*관심"),
    ("etf", r"ETF|VOO|QQQ|SCHD|IVV|SPLG|S&P\s*500|나스닥|배당|환율|원/달러|TIGER|KODEX|ACE"),
]


def classify(title, content):
    t = title or ""
    for cat, pat in RULES:
        if re.search(pat, t, re.I):
            return cat
    body = re.sub(r"<[^>]+>", " ", content or "")[:3000]
    hits = [(len(re.findall(pat, body, re.I)), cat) for cat, pat in RULES]
    hits.sort(reverse=True)
    if hits[0][0] >= 3 and (len(hits) < 2 or hits[0][0] >= 2 * max(1, hits[1][0])):
        return hits[0][1]
    return None


def main():
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    v1 = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}"
    ids = {}
    for slug, (name, desc) in CATS.items():
        r = requests.post(f"{v1}/categories/slug:{slug}", headers=h, data={"name": name, "description": desc}, timeout=30)
        ok = r.status_code == 200
        if ok:
            ids[slug] = r.json().get("ID")
        print(f"{'✅' if ok else '❌'} 분야 {slug} → {name} ({r.status_code})")
    page, moved, skipped = 1, 0, []
    while page <= 10:
        r = requests.get(f"{v1}/posts", headers=h, timeout=60, params={
            "status": "any", "number": 100, "page": page, "fields": "ID,title,content,categories,status"})
        if r.status_code != 200:
            print("글 목록 실패", r.status_code)
            break
        posts = r.json().get("posts") or []
        for p in posts:
            cats = [c.get("slug") for c in (p.get("categories") or {}).values()]
            if cats and cats != ["uncategorized"]:
                continue
            cat = classify(p.get("title"), p.get("content"))
            if not cat or cat not in ids:
                skipped.append(f"{p['ID']} {p.get('title', '')[:40]}")
                continue
            r2 = requests.post(f"{v1}/posts/{p['ID']}", headers=h, data={"categories": str(ids[cat])}, timeout=30)
            if r2.status_code == 200:
                moved += 1
                print(f"  {p['ID']} [{p.get('status')}] → {cat} | {p.get('title', '')[:40]}")
            else:
                print(f"  ❌ {p['ID']} {r2.status_code}")
        if len(posts) < 100:
            break
        page += 1
    print(f"분야 붙임 {moved}편, 애매해서 그대로 {len(skipped)}편")
    for s in skipped:
        print("   ?", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
