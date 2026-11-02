"""주간 점검: 키별 상태(이름표), 워드프레스 권한, 실패해도 다른 점검은 계속."""
import os, sys
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
os.environ["GEMINI_API_KEY"] = "aa@gmail.com:K1,K2,K3"
os.environ["WP_OAUTH_TOKEN"] = "t"; os.environ["WP_SITE_ID"] = "1"
from ondo.checks import weekly
from ondo.writing import llm


class R:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text


codes = {"K1": R(403, "free tier not available"), "K2": R(200), "K3": R(429)}
llm._post = lambda url, payload, key: codes[key]
lines = weekly.check_keys()
assert lines[0] == "🔑 Gemini 키: 2개 정상, 1개 문제" and "aa@gmail.com" in lines[1] and "K1" not in "".join(lines), lines
weekly.requests.get = lambda url, **k: R(403 if "media" in url or "categories" in url else 200)
wp = weekly.check_wordpress()[0]
assert "글 목록 ✅" in wp and "그림(미디어) ❌ 403" in wp and "다시 받기" in wp, wp
weekly.check_sources = lambda: (_ for _ in ()).throw(RuntimeError("x"))
out = weekly.run_all()
assert any("check_keys" not in l and "Gemini" in l for l in out) and any("실패" in l for l in out), out
print("weekly ok")
