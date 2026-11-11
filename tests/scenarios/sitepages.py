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
