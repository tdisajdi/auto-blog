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


def test_art_note_box_place_and_replace():
    """11-21 표지 그림 설명: 📌 출처 상자 앞, 다시 넣으면 바꿔 끼움, 영어 라벨."""
    from ondo.media import art_note
    art = {"about": {"ko": "설명", "en": "About"}, "credit": "C", "url": "https://x.org/a"}
    c = '<p>본문</p><div style="a"><strong>📌 데이터 출처</strong></div><p>이 글은 공개 데이터</p>'
    x = art_note.inject(c, art_note.note_html(art))
    assert x.index("ondo-art") < x.index("📌") and x.count("ondo-art") == 1
    assert art_note.inject(x, art_note.note_html(art)) == x
    assert "Cover art" in art_note.note_html(art, en=True) and "nofollow" in x
    assert art_note.note_html({}) == "" and art_note.inject(x, "").count("ondo-art") == 0
    assert art_note.inject("<p>a</p>", "B") == "<p>a</p>B"


def test_reader_note_strips_writer_directives():
    """11-21 표 아래 설명(독자에게 보임)에 작가용 지시문이 섞이면 뺀다."""
    from ondo.media.charts import reader_note, table_html
    n = reader_note("평균일 뿐. 조금 다를 수 있음 - 둘을 같은 숫자처럼 나란히 쓰지 말 것. '같이'는 상관계수.")
    assert "말 것" not in n and "조금 다를 수 있음." in n and "상관계수" in n
    plain = "가정: 세금 제외. 과거 자료로 계산한 값일 뿐 앞으로도 같다는 보장은 없음."
    assert reader_note(plain) == plain
    assert "쓰지 말" not in table_html("t", ["a"], [["1"]], "값 - 표로 다시 쓰지 말 것.")


def test_country_market_calc():
    """11-21 나라별 시장: 달러·환율·원화 환산이 맞고, 국내 ETF는 상장 기간이 짧으면 그 창을 비움."""
    import pandas as pd
    import numpy as np
    import guide_calcs as gc
    idx = pd.bdate_range("2020-01-01", periods=1600)
    u = pd.Series(np.linspace(50, 80, 1600), idx)
    fx = pd.Series(np.linspace(1100, 1400, 1600), idx)
    kr = pd.Series(np.linspace(10000, 13000, 500), idx[-500:])
    r = gc.calc_country(u, fx, None, kr)
    one = r["rows"][0]
    assert abs((1 + one["usd"] / 100) * (1 + one["fx"] / 100) - (1 + one["krw"] / 100)) < 1e-6
    assert one["kr"] is not None and r["rows"][2]["kr"] is None
    facts, table = gc.render_country(r, gc.COUNTRIES["india"])
    assert "원화로 환산하면" in facts and "전망" in facts and "<table" in table and "최대 낙폭" not in facts


def test_market_map_page():
    """11-21 세계 주식시장 지도: 연도 다르면 세계 대비 비움, 대만은 '자료 없음', 출처 링크."""
    from site_pages import market_map as m
    rows = [{"code": "USA", "ko": "미국", "etf": "SPY", "kr": "", "link": "", "cap": (2024, 62e12), "gdp": (2024, 200.0), "usd": 5.0},
            {"code": "JPN", "ko": "일본", "etf": "EWJ", "kr": "TIGER 일본니케이225", "link": "", "cap": (2023, 6e12), "gdp": None},
            {"code": "TWN", "ko": "대만", "etf": "EWT", "kr": "", "link": "", "cap": None, "gdp": None}]
    h = m.build_html({"world": (2024, 124e12), "rows": rows})
    assert "50.0%" in h and "세계은행 자료 없음" in h and "data.worldbank.org" in h and "world-exchanges.org" in h
    assert "TIGER 일본니케이225" in h and "권유하지 않습니다" in h
