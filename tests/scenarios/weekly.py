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

# 11-22 성적표 품질·배움·확장 줄(기록 파일만 읽음)
import datetime as _dt, json as _json, pathlib as _pl
from site_pages import weekly_report as _wr
_r = _pl.Path(sys.argv[1]) / "fake"
(_r / "logs" / "2026-11").mkdir(parents=True); (_r / "lab").mkdir()
_json.dump({"started_at": "2026-11-20T10:00:00", "article_type": "guide",
            "steps": [{"step": "편집장 검토 1", "passed": False, "issues": ["[치명·사실 검증] x"]}, {"step": "편집장 검토 2", "passed": True}]},
           open(_r / "logs" / "2026-11" / "a.json", "w"))
(_r / "PROJECT_STATUS.txt").write_text("- [L1·11-22·재발 0] a\n- [L2·11-22·재발 2] b\n", encoding="utf-8")
(_r / "lab" / "BACKLOG.txt").write_text("[확장 효과 확인]  (x)\n- 11-20 | 기능A | 기준 | 11-23 | -\n- 11-10 | 기능B | 기준 | 11-15 | 유지\n[끝난 것]\n", encoding="utf-8")
_g = "\n".join(_wr.growth_section(_dt.date(2026, 11, 16), _dt.date(2026, 11, 22), root=str(_r), today=_dt.date(2026, 11, 23)))
assert "첫 판 통과 0 · 마지막 판 통과 1 · 사실 검증 치명 지적 1개" in _g and "guide 0/1" in _g, _g
assert "L2(2번)" in _g and "확장 1개" in _g and "확인 날이 된 확장: 기능A" in _g, _g
print("growth ok")
(_r / "lab" / "patches").mkdir(); (_r / "lab" / "recheck").mkdir()
_json.dump([{"old": "a", "new": "b"}] * 3, open(_r / "lab" / "patches" / "9.json", "w"))
_json.dump({"log": "a.json"}, open(_r / "lab" / "recheck" / "9.json", "w"))
_g = "\n".join(_wr.growth_section(_dt.date(2026, 11, 16), _dt.date(2026, 11, 22), root=str(_r), today=_dt.date(2026, 11, 23)))
assert "고친 글 1편, 글당 평균 3.0곳" in _g, _g
print("patch count ok")
