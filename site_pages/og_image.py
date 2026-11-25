"""글 공유 미리보기 그림(og:image)을 '계산노트' 카드로(2026-11-25 사용자 확정).

  python site_pages/og_image.py 823 826
lab/social/og/<글번호>.json으로 가로 카드(ondo/media/social_card.og_card)를 그려 미디어로 올리고,
전용 플러그인(1.4.3) /ondo/v1/og-image 로 그 글의 Rank Math 공유 그림 칸에 넣는다. 블로그 화면의 대표 이미지·본문은 그대로.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(pid):
    import requests
    from ondo.media.social_card import og_card
    from site_pages.pll_plugin import _auth, call
    spec_f = os.path.join(ROOT, "lab", "social", "og", f"{pid}.json")
    if not os.path.exists(spec_f):
        print(f"{pid}: lab/social/og/{pid}.json 없음")
        return 1
    out = og_card(json.load(open(spec_f, encoding="utf-8")), os.path.join(tempfile.gettempdir(), f"ondo-og-{pid}.png"))
    h, S = _auth()
    with open(out, "rb") as f:
        up = requests.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{S}/media/new", headers=h, timeout=60,
                           files={"media[]": (f"ondo-og-{pid}.png", f, "image/png")})
    media = (up.json().get("media") or [{}])[0] if up.ok else {}
    if not media.get("ID"):
        print(f"{pid}: 그림 올리기 실패", up.status_code, up.text[:200])
        return 1
    code, j = call("POST", "/ondo/v1/og-image", {"post": int(pid), "media": media["ID"]})
    ok = code == 200 and isinstance(j, dict) and j.get("url")
    print(f"{pid}: 공유 그림 {'넣음' if ok else '실패'}", code, str(j)[:200])
    return 0 if ok else 1


if __name__ == "__main__":
    ids = [a for a in sys.argv[1:] if a.isdigit()]
    sys.exit(max(main(a) for a in ids) if ids else (print(__doc__) or 1))
