"""종목 분석 글(4단계): 시각 자료 서랍 → 기획이 고른 것 검사 → 섹션 뒤 배치 → 온도 띠 → 기록."""
import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import topic_engine as te, media_engine as me
from ondo.writing import analysis as an, desk
from ondo.media import charts

# 1) 서랍: 빈 자료는 빠지고, 안의 제목 태그는 굵은 글씨로
drawer, html_by_id = an.build_drawer({"basic": "<div><h3>VOO 기본</h3><p>보수 0.03% 배당 1.07%</p></div>",
                                      "backtest": "<div id='c'></div><script>draw()</script>", "risk": "", "fees": "<p> </p>"})
assert [d["id"] for d in drawer] == ["basic", "backtest"], drawer
assert "<h3" not in html_by_id["basic"] and "ondo-figtitle" in html_by_id["basic"]

# 2) 기획이 고른 것 검사: 서랍에 없는 id·중복 버림, 최대 3개, 섹션 번호 범위, 최근 조합 피하기
big = [{"id": i, "name": i, "desc": "d", "fits": "f"} for i in ["basic", "backtest", "competition", "risk", "fees"]]
picks = desk.choose_visuals([{"id": "basic", "after_section": 1}, {"id": "nope", "after_section": 2},
                             {"id": "basic", "after_section": 2}, {"id": "risk", "after_section": 9},
                             {"id": "fees", "after_section": 2}, {"id": "competition", "after_section": 3}], big, 4)
assert [(p["id"], p["after_section"]) for p in picks] == [("basic", 1), ("risk", 4), ("fees", 2)], picks
again = desk.choose_visuals([{"id": "basic", "after_section": 1}, {"id": "risk", "after_section": 2}], big, 4,
                            avoid=[["risk", "basic"]])
assert {p["id"] for p in again} != {"basic", "risk"}, again
assert [p["id"] for p in desk.choose_visuals(None, big, 3)] == ["basic", "backtest"]
print("drawer ok")

# 3) 배치: '섹션 k 뒤' = 다음 <h3> 바로 앞(구분선보다 앞)
DIV = '<div style="width:100%; height:1px; background-color:#ddd; margin:40px 0;"></div>'
body = f"<p>도입</p>{DIV}<h3>A</h3><p>a</p>{DIV}<h3>B</h3><p>b</p>{DIV}<h3>자주 묻는 질문</h3><p>q</p>"
out = an.insert_visuals(body, [{"id": "x", "after_section": 1}, {"id": "y", "after_section": 2}], {"x": "[X]", "y": "[Y]"})
assert out.index("[X]") < out.index(f"{DIV}<h3>B") and out.index("[Y]") < out.index(f"{DIV}<h3>자주"), out
assert out.index("[X]") > out.index("<p>a</p>")
print("placement ok")

# 4) 온도 띠: 숫자만, 판단 문구 없음, 영어 브랜드 글자
strip = charts.thermo_strip({"volatility": 40, "valuation": 60, "fx": 50, "inflation": 30}, "10월 31일")
assert "ONDO MARKET TEMP" in strip and "46°" in strip and "매수" not in strip, strip
assert charts.thermo_strip({}) == ""
assert "매수" not in an.strip_advice("[투자 온도계]\n- 해석: 현재 매수하기에 비교적 좋은 시점입니다.\n[다음]\n- x")
print("thermo ok")

# 5) produce_article: 기획이 고른 자료가 그 섹션 뒤에, 온도 띠는 맨 위, 기록부에 시리즈용 숫자 + 고른 자료
calls = {}
te.get_wordpress_recent_posts = lambda *a, **k: []
te.write_article = lambda **k: calls.update(drawer=k.get("drawer")) or {
    "html": "<h1>VOO 제목</h1><p>도입 문단</p><h3>보수와 배당</h3><p>본문1</p><h3>하락장</h3><p>본문2</p>"
            "<h3>자주 묻는 질문</h3><p>q</p>\n태그: a b",
    "plan": {"slug": "voo", "visuals": [{"id": "backtest", "after_section": 1}]}, "score": 0.9, "issues": [], "clean": True}
te._check_duplicate = lambda *a: False
me.upload_png = lambda p: (None, None)
te._register_article = lambda *a, **k: calls.update(reg=k)
te.publish_to_wordpress = lambda title, body, **k: calls.update(body=body) or (True, "https://ondo99.com/?p=9")
te._telegram_send_message = lambda *a, **k: 1
st, title, url = te.produce_article(kind_label="ETF 분석", title_seed="VOO", facts_text="f", rules=an.ANALYSIS_RULES,
                                    category_label="ETF/종목 분석", article_type="analysis", topic_id="VOO",
                                    drawer=drawer, drawer_html=html_by_id, top_html=strip,
                                    extra_data={"VOO": {"yield": "1.07%"}}, meta={"tickers": ["VOO"]})
b = calls["body"]
assert calls["drawer"] == drawer
assert b.startswith(strip) or b.find("ONDO MARKET TEMP") < b.find("도입 문단"), b[:300]
assert b.find("본문1") < b.find('data-visual="backtest"') < b.find('<h3 id="하락장"'), b
assert 'data-visual="basic"' not in b
reg = calls["reg"]["extra_data"]
assert reg["VOO"]["yield"] == "1.07%" and reg["_meta"]["visuals"] == ["backtest"] and reg["_meta"]["article_type"] == "analysis"
print("analysis article ok")

# 6) 금지 표현은 코드가 막는다(발행 막는 지적), 자료표는 이름표에 기준을 붙이고 빈 값은 뺀다
from ondo.checks import lint
_, iss, _ = lint.fix_and_check("<h1>t</h1><p>VOO는 장기 투자자의 핵심 자산으로 적합합니다. 보수는 업계 최저 수준입니다.</p>\n태그: a")
bad = [i for i in iss if i.startswith("금지 표현")]
assert len(bad) == 3 and lint.blocking(bad) == bad, iss
import types
ea = types.SimpleNamespace(_is_overseas_listed=lambda d: d.get("listing") == "해외 상장", OVERSEAS_ACCOUNT_NOTE="직접 못 삼",
                           TAX_US_DIVIDEND_WITHHOLDING=0.15, TAX_DOMESTIC_DIVIDEND=0.154, OVERSEAS_CG_DEDUCTION=2_500_000,
                           TAX_OVERSEAS_CAPITAL_GAINS=0.22, ISA_TAX_FREE_LIMIT=2_000_000, ISA_SEPARATE_TAX=0.099)
d = {"name": "Vanguard S&P 500 ETF", "listing": "해외 상장", "yield": "1.07%", "expense_ratio": "0.03%", "website": "정보 없음",
     "returns": {"1년": 12.08}, "custom_attractiveness_score": 6.9, "fee_impact_100m_10y": "약 998,204원 (0.1% 포인트 차이로)"}
fs = an.fact_sheet(["VOO"], {"VOO": d}, ea, {"usd_krw": "1,335원"}, [], {"basic": "<p>보수 0.03%</p>"}, "10월 31일")
assert "투자금 1억 원 × 배당수익률 1.07% = 연 배당 약 107만 원 → 세금 약 16만 원" in fs, fs
assert "양도소득세 약 165만 원" in fs and "6.9" not in fs and "정보 없음" not in fs and "basic: 보수 0.03%" in fs
assert "운용보수가 0.1%p 더 높은 ETF와 비교하면 1억 원을 10년 둘 때 차이 약 998,204원" in fs
print("fact sheet + banned ok")
