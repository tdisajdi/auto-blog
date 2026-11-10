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

# 7) 작가가 시각 자료 숫자를 베껴 만든 표는 코드가 지운다(직접 쓴 다른 표는 남김). 꾸밈말은 참고만.
fx = []
vis = "해외 직접투자 524,983원 45,949,339원 10.2% 국내 32,707,032원 21,015,443원"
copied = "<p>a</p><table><tr><td>524,983원</td><td>45,949,339원</td><td>32,707,032원</td></tr></table><p>b</p>"
own = "<table><tr><td>2025-12-22</td><td>1.7710</td></tr></table>"
assert "<table" not in lint.drop_copied_tables(copied, [vis], fx) and fx
assert lint.drop_copied_tables(own, [vis], []) == own
_, iss7, _ = lint.fix_and_check("<h1>t</h1><p>막대한 자금을 정교하게 추종합니다.</p>\n태그: a")
assert any("꾸밈말" in i for i in iss7) and not any("꾸밈말" in i for i in lint.blocking(iss7))
print("copied table + puffery ok")

# 2026-11-06: 최대 낙폭의 경과 - 고점·바닥·회복 날짜와 걸린 기간
import pandas as _pd
import etf_auto as _ea
_long = _pd.Series(list(range(100, 130)) + list(range(130, 90, -2)) + list(range(90, 135, 3)),
                   index=_pd.date_range("2022-01-03", periods=30 + 20 + 15, freq="7D"), dtype=float)
m = _ea._drawdown_detail(_long)
assert m["peak"] == "2022-08-01" and m["recovered"] and m["recover_days"] > 0 and m["pct"] < 0, m
from ondo.writing import analysis as _an
st = _an._mdd_story(m)
assert "고점 가격을 되찾음" in st and "배당 제외" in st, st
m2 = _ea._drawdown_detail(_pd.Series(list(range(100, 140)) + list(range(140, 110, -1)), index=_pd.date_range("2022-01-03", periods=70, freq="7D"), dtype=float))
assert m2["recovered"] is None and "되찾지 못함" in _an._mdd_story(m2), m2
print("mdd recovery ok")

# 2026-11-07: 비교 글 - 같은 기간으로 맞춘 비교(가격 변화·연평균·최대 낙폭·해마다 승패·상관계수)
import numpy as _np
_d = _pd.date_range("2022-01-03", periods=750, freq="B")
_ra = _np.random.default_rng(1).normal(0.0004, 0.01, 750)
_A = _pd.Series(100 * _np.cumprod(1 + _ra), index=_d)
_B = _pd.Series(100 * _np.cumprod(1 + _ra * 1.5 + 0.0001), index=_d[0:]).iloc[100:]     # B는 늦게 상장
blk = _an.same_period_block(["VOO", "QQQ"], {"VOO": _A, "QQQ": _B})
assert blk.startswith("[같은 기간 비교") and _d[100].strftime("%Y-%m-%d") in blk and "더 오른 해" in blk and float(blk.split("상관계수 ")[1][:4]) >= 0.9, blk
assert _an.same_period_block(["VOO"], {"VOO": _A}) == ""
assert not _an.is_twin(blk), blk          # 1.5배로 움직이는 두 상품은 쌍둥이 아님
print("same period ok")
# 2026-11-08: 거의 같이 움직이는 두 상품(같은 지수 다른 운용사)은 쌍둥이 표시 → 필수 질문을 바꿈
_T = _A * (1 + _np.random.default_rng(2).normal(0, 0.0003, 750))
blk2 = _an.same_period_block(["360750.KS", "360200.KS"], {"360750.KS": _A, "360200.KS": _T})
assert _an.is_twin(blk2) and "거의 같이 움직였다" in blk2, blk2
assert "comparison_twin" in _an.MUST_ANSWER and any("억지로 차이를 만들지" in q for q in _an.MUST_ANSWER["comparison_twin"])
print("twin comparison ok")
# 2026-11-08: 국내 ETF 보수 - 네이버 모바일 종목 자료(JSON)에서 key/value 묶음을 모두 모음
_js = {"totalInfos": [{"code": "nav", "key": "NAV", "value": "24,708.04"}, {"code": "fundPay", "key": "펀드보수", "value": "0.007%"},
                      {"code": "etfBaseIdx", "key": "기초지수", "value": "S&P 500"}], "other": {"deep": [{"key": "시총", "value": "10조"}]}}
_pp = _ea._naver_kr_pairs(_js)
assert _pp["펀드보수"] == "0.007%" and _pp["기초지수"] == "S&P 500" and _pp["시총"] == "10조", _pp
print("naver kr pairs ok")

# 2026-11-08 운용사 비교 재시험: 쌍둥이 비교엔 '고를 때 남는 차이'(보수 원화 차이·거래대금·세금 같음)를 코드가 주고, 상장일 CAGR·0.1%p 가정은 뺌
import types as _ty
_ea = _ty.SimpleNamespace(_is_overseas_listed=lambda d: False, OVERSEAS_ACCOUNT_NOTE="x", TAX_US_DIVIDEND_WITHHOLDING=0.15,
                          TAX_DOMESTIC_DIVIDEND=0.154, OVERSEAS_CG_DEDUCTION=2_500_000, TAX_OVERSEAS_CAPITAL_GAINS=0.22,
                          ISA_TAX_FREE_LIMIT=2_000_000, ISA_SEPARATE_TAX=0.099)
_c = {"360750.KS": {"name": "TIGER", "expense_ratio": "0.007%", "trade_value": "7,188억", "listing": "국내 상장", "index": "S&P 500",
                    "cagr": 0.12, "fee_impact_100m_10y": "996,140원"},
      "360200.KS": {"name": "ACE", "expense_ratio": "0.005%", "trade_value": "1,200억", "listing": "국내 상장", "index": "S&P 500",
                    "cagr": 0.13, "fee_impact_100m_10y": "995,960원"}}
tb = _an.twin_choice_block(["360750.KS", "360200.KS"], _c, _ea)
assert "보수 360750 약 700원, 360200 약 500원 → 차이 약 200원" in tb and "10년이면 약 2,000원" in tb, tb
assert "360750이 약 6.0배(코드 계산)" in tb and "기초지수(S&P 500)가 같아" in tb and "세금 섹션을 따로 만들지 말고" in tb, tb
assert _an._won_amount("7,188억") == 7.188e11 and _an._won_amount("3.2조") == 3.2e12 and _an._won_amount("") is None
_orig = _an.same_period_block
_an.same_period_block = lambda pair, closes=None: f"[같은 기간 비교]\n- {_an.TWIN_MARK}: 거의 같이 움직였다"
fs = _an.fact_sheet(["360750.KS", "360200.KS"], _c, _ea, {}, [], {}, "11월 08일")
assert "[두 ETF를 고를 때 남는 차이" in fs and "연평균 수익률" not in fs and "0.1%p 더 높은" not in fs, fs
assert "매매차익 세금 예시" not in fs and "금융소득종합과세" not in fs and "- 계좌:" not in fs and "세금·계좌 조건" in fs, fs
_an.same_period_block = lambda pair, closes=None: "[같은 기간 비교]\n- 차이 큼"
fs2 = _an.fact_sheet(["360750.KS", "360200.KS"], _c, _ea, {}, [], {}, "11월 08일")
assert "[두 ETF를 고를 때 남는 차이" not in fs2 and "연평균 수익률" in fs2
# 11-10: CAGR은 최근 5년 창으로 재므로 이름표도 그 기간대로('상장 이후 2010-09-07부터'로 잘못 붙어 VOO 글이 틀리게 씀)
assert _an.cagr_label({"cagr_years": 5.0, "inception_date": "2010-09-07"}).startswith("최근 5년 연평균"), _an.cagr_label({"cagr_years": 5.0})
assert "약 2.3년치" in _an.cagr_label({"cagr_years": 2.3}) and "직접 비교 금지" in _an.cagr_label({"cagr_years": 2.3})
_an.same_period_block = _orig
print("twin choice block ok")

# 2026-11-09: 배당 같은 시기 비교 - 1년 전 같은 시기 대비, 지급 횟수가 같을 때만 1년 합계 비교
import pandas as _pd
from ondo.etf.data import _dividend_yoy
_idx = _pd.to_datetime(["2025-03-27", "2025-06-27", "2025-09-26", "2025-12-22", "2026-03-27", "2026-06-26", "2026-09-28"])
_y = _dividend_yoy(_pd.Series([1.81, 1.74, 1.74, 1.77, 1.87, 1.96, 1.82], index=_idx))
assert "1년 전 같은 시기(2025-09-26 1.7400) 대비 +4.60%" in _y and "합계" not in _y, _y      # 그 전 1년이 3회뿐 → 합계 비교 안 함
_idx2 = _pd.to_datetime(["2024-12-20", "2025-03-27", "2025-06-27", "2025-09-26", "2025-12-22", "2026-03-27", "2026-06-26", "2026-09-28"])
_y2 = _dividend_yoy(_pd.Series([1.70, 1.81, 1.74, 1.74, 1.77, 1.87, 1.96, 1.82], index=_idx2))
assert "최근 1년 배당 합계 7.4200는 그 전 1년 6.9900 대비 +6.15%" in _y2, _y2
assert _dividend_yoy(_pd.Series([1.0, 1.1], index=_idx[:2])) == ""
assert "최근 8회 지급 중 직전 회차보다 줄어든 적 2회" in _y2, _y2      # 1.81→1.74, 1.96→1.82 (같은 값은 안 셈)
assert "줄어든 적" not in _y                                            # 7회뿐이면 안 셈
print("dividend yoy ok")
