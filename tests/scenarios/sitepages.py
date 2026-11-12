"""2026-11-11: 사이트 기본 페이지 올리기 - 파일 머리(slug·title) 읽기, 운영자 주석 빼기, 같은 주소면 바꾸고 없으면 새로(type=page), 기본 비공개."""
import sys, os; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
sys.path.insert(0, os.path.join(sys.argv[1], "site_pages"))
import upload as up
pages = {p["slug"]: p for p in up.load_pages()}
assert set(pages) == {"about-ondo", "contact", "disclaimer", "privacy-policy"}, pages.keys()
assert "운영자 확인 필요" not in pages["about-ondo"]["html"] and "<!--" not in pages["about-ondo"]["html"]
assert "[contact-form" in pages["contact"]["html"] and "금융 전문가가 아닙니다" in pages["about-ondo"]["html"]
assert "증권사" not in pages["about-ondo"]["html"]          # 확인 안 된 이력은 쓰지 않음
assert "AI" not in pages["about-ondo"]["html"] and "사실 대조" in pages["about-ondo"]["html"]   # 11-11 사용자 결정: AI 언급은 빼고 사실만(1번)
import blog_engine as be
be.WP_OAUTH_TOKEN, be.WP_SITE_ID = "t", "1"
calls = []
class R:
    def __init__(s, code, js): s.status_code, s._j, s.text = code, js, ""
    def json(s): return s._j
class S:
    def __init__(s, exists): s.exists = exists
    def get(s, url, **k): calls.append(("get", url)); return R(200, {"ID": 7, "type": "page"}) if s.exists else R(404, {})
    def post(s, url, data=None, **k): calls.append(("post", url, data)); return R(200, {"ID": 7, "status": data["status"], "URL": "u"})
ok, msg = up.upsert_page(pages["about-ondo"], "draft", S(False))
assert ok and calls[-1][1].endswith("/posts/new/") and calls[-1][2]["type"] == "page" and calls[-1][2]["status"] == "draft", calls[-1]
ok, msg = up.upsert_page(pages["about-ondo"], "draft", S(True))
assert ok and calls[-1][1].endswith("/posts/7") and "바꿈" in msg, (calls[-1], msg)
# 11-11 사고 재발 방지: 같은 주소의 '공개' 페이지는 건드리지 않음
class SP(S):
    def get(s, url, **k): calls.append(("get", url)); return R(200, {"ID": 1, "type": "page", "status": "publish", "URL": "u"})
n = len(calls); ok, msg = up.upsert_page(pages["about-ondo"], "draft", SP(True))
assert not ok and "건드리지 않음" in msg and not any(c[0] == "post" for c in calls[n:]), (msg, calls[n:])
assert up.main("public") == 1
print("site pages ok")
# 11-11: 온도판 시제품 - 1년 범위 위치 계산, 사실 묘사, 카드·계산 방법 들어감, 권유 말 없음
import pandas as pd
from ondo import board
idx = pd.bdate_range("2025-11-10", periods=250)
st = board.card_stats(pd.Series([100.0 + i * 0.2 for i in range(249)] + [160.0], index=idx))
assert st["pos"] == 100 and st["lo"] == 100.0 and abs(st["w1"] - (160 / 148.8 - 1) * 100) < 1e-6 and board.band(st["pos"]) == "지난 1년 중 아주 높은 편", st
st2 = board.card_stats(pd.Series([100.0] * 125 + [200.0] * 124 + [150.0], index=idx))
assert st2["pos"] == 50 and board.band(50) == "지난 1년 중간쯤"
assert board.card_stats(pd.Series([1.0] * 10)) is None
pg = board.render([(board.ITEMS[0], st)], "2026-11-11")
assert "100°" in pg and "계산 방법" in pg and "1년 최저" in pg and "/disclaimer" in pg
assert not any(w in pg for w in ("매수", "매도", "추천", "사세요", "적기")), pg
print("board ok")

# 11-12 백로그 21·31) 초안 종합 온도 띠 지우기 / 비공개 글 링크 찾기
from site_pages.drafts_fix import strip_market_temp, find_private_links
TEMP = ('<div class="ondo-thermo" style="x"><span>ONDO MARKET TEMP</span> <strong>51°</strong> '
        '<span>(변동성 64°)</span> <span>· 자체 지표</span></div>\n')
OTHER = '<div class="ondo-thermo"><b>다른 상자</b></div>'
new, n = strip_market_temp(TEMP + "<p>본문</p>" + OTHER)
assert n == 1 and new == "<p>본문</p>" + OTHER, new
assert strip_market_temp("<p>없음</p>") == ("<p>없음</p>", 0)
items = [
    {"ID": 1, "slug": "pub", "status": "publish", "title": "공개", "content": '<a href="https://ondo99.com/?p=2">a</a> <a href="https://ondo99.com/etf/">허브</a> <a href="https://example.com/?p=2">밖</a>'},
    {"ID": 2, "slug": "dr", "status": "draft", "title": "초안", "content": '<a href="https://ondo99.com/pub/">b</a> <a href="https://ondo99.com/dr/">c</a>'},
]
rep = find_private_links(items)
assert [(r["ID"], r["status"]) for r in rep] == [(1, "publish"), (2, "draft")], rep
assert rep[0]["links"] == [["https://ondo99.com/?p=2", "draft", 2]] and rep[1]["links"] == [["https://ondo99.com/dr/", "draft", 2]], rep
print("drafts_fix ok")

# 11-12) 온도판이 공개 전이면 머리·바닥·첫 화면의 온도판 링크는 '준비 중' 표시(방문자 404 막기)
sys.path.insert(0, sys.argv[1])
from site_pages import theme_push as tp
html = '<a class="o-nav-board" href="https://ondo99.com/ondo-board/">BOARD</a><a href="https://ondo99.com/ondo-board/">온도판</a><a href="https://ondo99.com/etf/">ETF</a>'
out = tp.board_links(html, live=False)
assert "ondo-board" not in out and "BOARD SOON" in out and "온도판 (준비 중)" in out and 'href="https://ondo99.com/etf/"' in out, out
assert tp.board_links(html, live=True) == html
print("board soon ok")

# 11-12) 온도판 매일 갱신: 본문만 보내고 공개 여부는 그대로(status를 보내지 않음), 페이지 없으면 아무것도 안 함
class SR:
    def __init__(s, st): s.st = st; s.posted = []
    def get(s, url, **k): return R(200, {"ID": 353, "type": "page", "status": s.st}) if s.st else R(404, {})
    def post(s, url, data=None, **k): s.posted.append(data); return R(200, {"ID": 353, "status": s.st})
sr = SR("publish"); ok, msg = up.refresh_page({"slug": "ondo-board", "html": "<p>새 숫자</p>"}, sr)
assert ok and sr.posted == [{"content": "<p>새 숫자</p>"}], (msg, sr.posted)
sr = SR(None); ok, msg = up.refresh_page({"slug": "ondo-board", "html": "x"}, sr)
assert not ok and sr.posted == [], msg
print("board refresh ok")
