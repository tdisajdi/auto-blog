"""사이트 설정 정리(2026-11-19 사용자 허락: '4번은 알아서 최선으로').

  python site_pages/site_tune.py apply   - 아래 Jetpack 기능 끄기 + 사이트 한 줄 소개(태그라인) 넣기 + 사이트 아이콘(11-24)
  python site_pages/site_tune.py undo    - 끈 기능 다시 켜기 + 태그라인 비우기(되돌리기)

끄는 것과 이유(lab/THINKING.txt 11-19 플러그인 최적화):
- infinite-scroll: 목록을 내려도 바닥글(개인정보처리방침·문의)이 안 보일 수 있음 - 심사관
- sitemaps: Rank Math 사이트맵과 두 벌 - 하나로(Rank Math)
- seo-tools: Rank Math와 메타·OG 담당 겹침
- likes·comment-likes·gravatar-hovercards: 안 쓰는 기능인데 외부 스크립트를 더 부름 - 속도
- post-by-email·latex: 안 쓰는 기능
유지: related-posts(함께 읽을 글)·sharedaddy(공유)·stats·protect·subscriptions 등.
토큰 값은 출력하지 않는다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_pages.pll_plugin import call, _auth  # noqa: E402

OFF = ["infinite-scroll", "sitemaps", "seo-tools", "likes", "comment-likes", "gravatar-hovercards", "post-by-email", "latex"]
TAGLINE = "ETF·배당·환율 숫자를 같은 기준으로 계산하는 블로그"   # 11-24 추상적 자랑(직접 계산) → 무엇을 계산하는지
ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab", "mascot", "site-icon-512.png")  # 11-24 W 마크 대신 온도 캐릭터


def modules():
    code, j = call("GET", "/jetpack/v4/module/all")
    if code != 200 or not isinstance(j, dict):
        return {}
    return {k: bool(v.get("activated")) for k, v in j.items() if isinstance(v, dict)}


def set_tagline(text):
    import requests
    h, S = _auth()
    r = requests.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/settings", headers=h,
                      data={"blogdescription": text}, timeout=30)
    ok = r.ok
    after = (r.json().get("updated") or {}).get("blogdescription") if ok else r.text[:200]
    print("- 태그라인:", r.status_code, json.dumps(after, ensure_ascii=False))
    return ok


def set_icon():
    """사이트 아이콘(검색 결과·탭에 보이는 작은 그림)을 온도 캐릭터로. 이미 같은 이름 파일이 아이콘이면 건너뜀."""
    import requests
    h, S = _auth()
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{S}"
    cur = requests.get(f"{base}/settings", headers=h, timeout=30)
    cur_id = (cur.json().get("settings") or {}).get("site_icon") if cur.ok else None
    if cur_id:
        m = requests.get(f"{base}/media/{cur_id}", headers=h, timeout=30)
        if m.ok and "ondo-site-icon" in (m.json().get("file") or ""):
            print("- 사이트 아이콘: 이미 온도 캐릭터")
            return True
    with open(ICON, "rb") as f:
        up = requests.post(f"{base}/media/new", headers=h, timeout=60,
                           files={"media[]": ("ondo-site-icon.png", f, "image/png")})
    media = (up.json().get("media") or [{}])[0] if up.ok else {}
    if not media.get("ID"):
        print("- 사이트 아이콘 올리기 실패:", up.status_code, up.text[:200])
        return False
    r = requests.post(f"{base}/settings", headers=h, data={"site_icon": media["ID"]}, timeout=30)
    after = (r.json().get("updated") or {}).get("site_icon") if r.ok else r.text[:200]
    print("- 사이트 아이콘:", r.status_code, after)
    return r.ok and str(after) == str(media["ID"])


def run(active):
    before = modules()
    print("바꾸기 전:", {m: before.get(m) for m in OFF})
    bad = 0
    for m in OFF:
        if m not in before:
            print(f"- {m}: 이 사이트에 없는 기능 - 건너뜀")
            continue
        if before[m] == active:
            print(f"- {m}: 이미 {'켜짐' if active else '꺼짐'}")
            continue
        code, j = call("POST", f"/jetpack/v4/module/{m}/active", {"active": active})
        print(f"- {m}: {code} {json.dumps(j, ensure_ascii=False)[:160]}")
        bad += code != 200
    after = modules()
    print("바꾼 뒤:", {m: after.get(m) for m in OFF})
    wrong = [m for m in OFF if m in after and after[m] != active]
    if wrong:
        print("뜻대로 안 바뀐 것:", wrong)
    if not set_tagline(TAGLINE if not active else ""):
        bad += 1
    if not active and not set_icon():
        bad += 1
    return 1 if (bad or wrong) else 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "apply":
        return run(False)
    if mode == "undo":
        return run(True)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
