"""2026-11-20: 공개 두 번째 길(Claude 고침 + 좋은 모델 다시 검증) 판정 - 네트워크 없음, 임시 폴더."""
import json, os, sys, tempfile
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from site_pages import publish_passed as pp
from ondo.writing import llm

tmp = tempfile.mkdtemp()
pp.ROOT = tmp
os.makedirs(f"{tmp}/lab/patches"); os.makedirs(f"{tmp}/lab/recheck")
strong = llm.models_for("strong_only")[0]
d = {"steps": [{"step": "편집장 검토 3", "score": 0.94, "passed": False, "issues": ["[사소·독자 편집] 반복"]}]}
text = "앞 문장. 새 문구가 들어간 본문. 뒤 문장."
json.dump([{"old": "옛 문구", "new": "새 문구가 들어간 본문."}], open(f"{tmp}/lab/patches/9.json", "w"))

def rc(**k):
    base = {"post": "9", "model": strong, "log": "x.json", "issues": [], "patch_applied": True}
    base.update(k)
    json.dump(base, open(f"{tmp}/lab/recheck/9.json", "w"))

rc()
assert pp.claude_route("9", "/a/x.json", d, text) == (True, "Claude 고침 + 좋은 모델 다시 검증 통과")
assert not pp.claude_route("9", "/a/x.json", d, "옛 문구 본문")[0]                   # 고침이 글에 없음
assert not pp.claude_route("9", "/a/y.json", d, text)[0]                            # 다른 기록 기준
rc(patch_applied=False); assert "patch_applied" in pp.claude_route("9", "/a/x.json", d, text)[1]
rc(model="gemini-lite"); assert not pp.claude_route("9", "/a/x.json", d, text)[0]
rc(issues=[{"severity": "중요"}]); assert not pp.claude_route("9", "/a/x.json", d, text)[0]
rc()
d2 = {"steps": [{"step": "편집장 검토 3", "passed": False, "issues": ["[중요·사실 검증] 틀림"]}]}
assert not pp.claude_route("9", "/a/x.json", d2, text)[0]                           # 자동 검토 중요 지적 남음
os.remove(f"{tmp}/lab/patches/9.json"); assert not pp.claude_route("9", "/a/x.json", d, text)[0]
json.dump([{"old": "<td>A S&amp;P 500 ETF T</td>", "new": "<td>S&amp;P 500 ETF Trust</td>"},
           {"field": "excerpt", "old": "x", "new": "요약"}], open(f"{tmp}/lab/patches/9.json", "w"))
json.dump([{"old": ">A S&amp;P 500 ETF T</td>", "new": ">S&amp;P 500 ETF Trust</td>"}], open(f"{tmp}/lab/patches/9.json", "w"))
assert pp.patches_in("9", "표 S&P 500 ETF Trust 끝")
json.dump([{"old": "<td>A S&amp;P 500 ETF T</td>", "new": "<td>S&amp;P 500 ETF Trust</td>"}, {"field": "excerpt", "old": "x", "new": "요약"}], open(f"{tmp}/lab/patches/9.json", "w"))
assert pp.patches_in("9", "표 S&P 500 ETF Trust 끝") and not pp.patches_in("9", "표 A S&P 500 ETF T 끝")
assert pp.plain("<p>a&amp;b<!-- x --></p>").strip() == "a&b"
from site_pages.patch_post import apply
assert apply("가 나 다", [{"old": "가", "new": "라"}, {"old": "x", "new": "나"}]) == ("라 나 다", [])   # 이미 들어간 고침은 건너뜀
from site_pages.fact_recheck import strip_system
assert "표글" not in strip_system('앞<div class="ondo-calc" s><table><tr><td>표글</td></tr></table><p>주</p></div>뒤')
assert "그래프" not in strip_system('앞<figure class="ondo-chart" s><div></div><figcaption>그래프</figcaption></figure>뒤')
print("publishroute ok")
