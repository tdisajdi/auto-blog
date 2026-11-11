"""워드프레스 사이트 내용 백업(2026-11-11 사용자 요청) - 읽기만 하고 아무것도 바꾸지 않는다.

글·페이지(공개·비공개 초안 모두), 머리·바닥글 등 템플릿, 메뉴를 site_backup/ 아래 JSON으로 저장한다.
깃허브 실행(site_pages=export)이 이 폴더를 저장소에 커밋해서, 사이트에서 직접 고친 것까지 날짜별로 남는다.
토큰 값은 출력하지 않는다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "site_backup")

POST_FIELDS = "ID,title,slug,status,type,date,modified,URL,content,excerpt,categories,tags,parent,menu_order,featured_image,metadata"


def _save(rel, data):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def _slim_terms(d):
    return sorted((d or {}).keys())


def fetch_items(get, base, kind):
    """kind='post'|'page' - 모든 상태를 쪽(page) 단위로 끝까지 받는다."""
    items, page = [], 1
    while page <= 50:  # 안전장치: 최대 5,000개
        r = get(f"{base}/posts", params={"type": kind, "status": "any", "number": 100, "page": page,
                                          "fields": POST_FIELDS, "order_by": "ID", "order": "ASC"})
        if r.status_code != 200:
            print(f"  {kind} {page}쪽: {r.status_code} {r.text[:200]}")
            break
        batch = r.json().get("posts") or []
        items += batch
        if len(batch) < 100:
            break
        page += 1
    return items


def main():
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    S = be.WP_SITE_ID
    v1 = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}"
    v2 = f"https://public-api.wordpress.com/wp/v2/sites/{S}"

    def get(url, params=None):
        return requests.get(url, headers=h, params=params, timeout=60)

    summary = {}
    for kind, folder in (("post", "posts"), ("page", "pages")):
        items = fetch_items(get, v1, kind)
        keep = set()
        for it in items:
            it["categories"] = _slim_terms(it.get("categories"))
            it["tags"] = _slim_terms(it.get("tags"))
            name = f"{folder}/{it['ID']}-{it.get('slug') or 'no-slug'}.json"
            keep.add(os.path.basename(name))
            _save(name, it)
        # 사이트에서 지워진 글은 백업 폴더에서도 지움(깃 이력에는 남음)
        d = os.path.join(OUT, folder)
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".json") and fn not in keep:
                    os.remove(os.path.join(d, fn))
        by_status = {}
        for it in items:
            by_status[it.get("status")] = by_status.get(it.get("status"), 0) + 1
        summary[folder] = by_status
        print(f"- {folder}: {len(items)}개 {by_status}")

    for label, url, rel in (("템플릿 파트(머리·바닥글)", f"{v2}/template-parts?context=edit&per_page=100", "templates/template-parts.json"),
                            ("템플릿(첫 화면 등)", f"{v2}/templates?context=edit&per_page=100", "templates/templates.json"),
                            ("메뉴", f"{v1}/menus", "menus.json"),
                            ("카테고리", f"{v1}/categories?number=100", "categories.json")):
        r = get(url)
        print(f"- {label}: {r.status_code}")
        if r.status_code == 200:
            _save(rel, r.json())
            summary[rel] = "ok"
        else:
            summary[rel] = r.status_code

    r = get(v1)
    if r.status_code == 200:
        j = r.json()
        opts = j.get("options") or {}
        _save("site.json", {"name": j.get("name"), "description": j.get("description"), "URL": j.get("URL"),
                            "theme_slug": opts.get("theme_slug"), "show_on_front": opts.get("show_on_front"),
                            "page_on_front": opts.get("page_on_front"), "timezone": opts.get("timezone")})
    _save("summary.json", summary)
    ok = bool(summary.get("posts") or summary.get("pages"))
    print("✅ 사이트 백업 저장: site_backup/" if ok else "❌ 사이트 백업 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
