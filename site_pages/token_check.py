"""워드프레스 토큰으로 어디까지 할 수 있는지 '읽기'로만 확인(2026-11-11 사용자 요청). 아무것도 바꾸지 않는다. 토큰 값은 출력하지 않는다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import requests
    import blog_engine as be
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    S = be.WP_SITE_ID
    v1, v2, wpcom = "https://public-api.wordpress.com/rest/v1.1", "https://public-api.wordpress.com/wp/v2/sites/" + str(S), \
        "https://public-api.wordpress.com/wpcom/v2/sites/" + str(S)
    r = requests.get(f"{v1}/sites/{S}", headers=h, timeout=20)
    print("사이트 정보:", r.status_code)
    if r.ok:
        j = r.json()
        print("  요금제:", (j.get("plan") or {}).get("product_name_short"), "| 테마:", ((j.get("options") or {}).get("theme_slug")),
              "| 대문:", (j.get("options") or {}).get("show_on_front"), (j.get("options") or {}).get("page_on_front"))
        caps = j.get("capabilities") or {}
        print("  내 권한(true만):", sorted(k for k, v in caps.items() if v))
        print("  없는 권한:", sorted(k for k, v in caps.items() if not v))
    probes = [
        ("글 목록", f"{v1}/sites/{S}/posts?number=1&fields=ID"),
        ("페이지 목록(전체 상태)", f"{v1}/sites/{S}/posts?type=page&status=any&number=50&fields=ID,title,status,slug,URL"),
        ("카테고리", f"{v1}/sites/{S}/categories?number=20&fields=ID,name,slug,post_count"),
        ("메뉴", f"{v1}/sites/{S}/menus"),
        ("미디어 읽기", f"{v1}/sites/{S}/media?number=1"),
        ("위젯(바닥글 등)", f"{v2}/widgets"),
        ("사이트 설정", f"{v2}/settings"),
        ("템플릿 파트(머리·바닥글)", f"{v2}/template-parts?per_page=20"),
        ("전체 스타일(테마 디자인)", f"{v2}/global-styles/themes/" + "x"),
        ("추가 CSS(wpcom)", f"{wpcom}/custom-css"),
        ("추가 CSS(커스터마이저)", f"{v1}/sites/{S}/customcss"),
    ]
    for name, url in probes:
        try:
            r = requests.get(url, headers=h, timeout=20)
            note = ""
            if r.ok:
                j = r.json()
                if name.startswith("페이지 목록"):
                    note = " | " + "; ".join(f"{p['ID']} {p['status']} {p.get('slug')}" for p in j.get("posts", []))
                elif name == "카테고리":
                    note = " | " + "; ".join(f"{c['slug']}({c.get('post_count')})" for c in j.get("categories", []))
                elif name == "메뉴":
                    note = " | " + "; ".join(f"{m.get('id')} {m.get('name')} 항목 {len(m.get('items') or [])}" for m in j.get("menus", []))
                    note += " | 위치: " + ", ".join(l.get("name", "") for l in j.get("locations", []))
                elif name.startswith("템플릿"):
                    note = " | " + "; ".join(str(t.get("slug")) for t in (j if isinstance(j, list) else []))
            else:
                note = " | " + r.text[:120].replace("\n", " ")
            print(f"- {name}: {r.status_code}{note}")
        except Exception as e:
            print(f"- {name}: 오류 {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
