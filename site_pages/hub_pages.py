"""예전 허브·분야 페이지(공개 중)를 새 디자인으로 바꾼다(2026-11-11 전체 개편).

예전 페이지는 어두운 자체 디자인 + 자체 바닥글에 실제로 없는 링크(이용약관·제휴 문의·파트너십)와
'프리미엄 정보 플랫폼' 같은 과장 문구가 있었다(11-11 캡처). 심사관에게 나쁜 신호라 새로 쓴다.
내용 = 짧은 소개 + 그 분야 글 목록(워드프레스 목록 블록, 글이 늘면 자동으로 채워짐).
공개 상태는 그대로 두고 제목·내용만 바꾼다. 원문은 site_backup/pages/에 있다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 페이지 slug → (새 제목, 분야 slug 또는 None(전체), 영어 라벨, 소개)
HUBS = {
    "etf": ("ETF·투자", "etf", "ETF", "ETF의 수익률·배당·보수를 같은 기간, 같은 기준으로 계산해 비교합니다. 투자 권유가 아니라, 숫자를 스스로 읽는 데 필요한 것만 정리합니다."),
    "energy": ("에너지·원자재", "energy", "ENERGY", "유가·원유 재고처럼 생활비에 닿는 숫자를 미국 에너지정보청(EIA) 같은 공식 자료로 읽습니다. 가격 전망은 하지 않습니다."),
    "society": ("인구·사회", "society", "SOCIETY", "통계청(KOSIS)·행정안전부 통계로 1인 가구, 외국인 주민처럼 우리 사회가 어떻게 바뀌는지 봅니다."),
    "insights": ("전체 글", None, "ALL", "ondo의 모든 글입니다. 시장 가격과 공식 통계를 코드로 계산하고, 그 숫자가 무슨 뜻인지 풀어 씁니다."),
    "bio": ("바이오·신약", "biotech", "BIO", "임상 시험 결과와 승인 일정을 공개 자료로 정리하는 분야입니다. 지금은 글을 준비하고 있습니다."),
    "patents": ("기술·특허", "patents", "TECH", "새 기술과 특허 소식을 정리하는 분야입니다. 지금은 글을 준비하고 있습니다."),
    "trend": ("트렌드", "trend", "TREND", "검색 관심이 커진 주제를 자료로 살펴보는 분야입니다. 지금은 글을 준비하고 있습니다."),
}


def content_for(label, intro, cat_id):
    q = {"queryId": 7, "query": {"perPage": 12, "pages": 0, "offset": 0, "postType": "post", "order": "desc",
                                 "orderBy": "date", "inherit": False}, "className": "o-list"}
    if cat_id:
        q["query"]["taxQuery"] = {"category": [cat_id]}
    return (
        f'<!-- wp:html -->\n<div id="ondo-hub" class="o-hub-intro"><div><span class="o-px">{label}</span><p>{intro}</p></div>'
        f'<div class="o-scale" aria-hidden="true" style="width:120px"></div></div>\n<!-- /wp:html -->\n'
        f'<!-- wp:query {json.dumps(q, ensure_ascii=False)} -->\n<div class="wp-block-query o-list"><!-- wp:post-template -->\n'
        '<!-- wp:post-featured-image {"isLink":true} /-->\n<!-- wp:post-terms {"term":"category"} /-->\n'
        '<!-- wp:post-title {"isLink":true,"level":3} /-->\n<!-- wp:post-excerpt {"excerptLength":36} /-->\n<!-- wp:post-date /-->\n'
        '<!-- /wp:post-template -->\n<!-- wp:query-no-results -->\n<!-- wp:html -->\n'
        '<div class="o-empty"><span class="o-px">COMING SOON</span>아직 공개된 글이 없습니다. 곧 이 분야의 첫 글이 올라옵니다.</div>\n'
        '<!-- /wp:html -->\n<!-- /wp:query-no-results --></div>\n<!-- /wp:query -->'
    )


def main():
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    v1 = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}"
    bad = 0
    for slug, (title, cat, label, intro) in HUBS.items():
        cat_id = None
        if cat:
            r = requests.get(f"{v1}/categories/slug:{cat}", headers=h, timeout=20)
            cat_id = r.json().get("ID") if r.ok else None
        r = requests.get(f"{v1}/posts/slug:{slug}", headers=h, params={"type": "page", "fields": "ID,status"}, timeout=20)
        if r.status_code != 200:
            print(f"❌ {slug}: 페이지 못 찾음 {r.status_code}")
            bad += 1
            continue
        pid = r.json()["ID"]
        r = requests.post(f"{v1}/posts/{pid}", headers=h, timeout=60,
                          data={"title": title, "content": content_for(label, intro, cat_id)})
        ok = r.status_code == 200
        bad += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} /{slug}/ → {title} (분야 ID {cat_id}) {r.status_code}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
