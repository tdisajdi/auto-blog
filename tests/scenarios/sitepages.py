"""2026-11-11: 사이트 기본 페이지 올리기 - 파일 머리(slug·title) 읽기, 운영자 주석 빼기, 같은 주소면 바꾸고 없으면 새로(type=page), 기본 비공개."""
import sys, os; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
sys.path.insert(0, os.path.join(sys.argv[1], "site_pages"))
import upload as up
pages = {p["slug"]: p for p in up.load_pages()}
assert set(pages) == {"about", "contact", "disclaimer", "privacy-policy"}, pages.keys()
assert "운영자 확인 필요" not in pages["about"]["html"] and "<!--" not in pages["about"]["html"]
assert "[contact-form" in pages["contact"]["html"] and "금융 전문가가 아닙니다" in pages["about"]["html"]
assert "증권사" not in pages["about"]["html"]          # 확인 안 된 이력은 쓰지 않음
assert "AI" not in pages["about"]["html"] and "사실 대조" in pages["about"]["html"]   # 11-11 사용자 결정: AI 언급은 빼고 사실만(1번)
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
ok, msg = up.upsert_page(pages["about"], "draft", S(False))
assert ok and calls[-1][1].endswith("/posts/new/") and calls[-1][2]["type"] == "page" and calls[-1][2]["status"] == "draft", calls[-1]
ok, msg = up.upsert_page(pages["about"], "draft", S(True))
assert ok and calls[-1][1].endswith("/posts/7") and "바꿈" in msg, (calls[-1], msg)
# 11-11 사고 재발 방지: 같은 주소의 '공개' 페이지는 건드리지 않음
class SP(S):
    def get(s, url, **k): calls.append(("get", url)); return R(200, {"ID": 1, "type": "page", "status": "publish", "URL": "u"})
n = len(calls); ok, msg = up.upsert_page(pages["about"], "draft", SP(True))
assert not ok and "건드리지 않음" in msg and not any(c[0] == "post" for c in calls[n:]), (msg, calls[n:])
assert up.main("public") == 1
print("site pages ok")
