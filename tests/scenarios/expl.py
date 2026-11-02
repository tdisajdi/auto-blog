import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import explainer_engine as xe, topic_engine as te, types
got={}
te.produce_article=lambda **k: got.update(k) or ("publish","t","u")
xe._collect_facts=lambda *a, **k: ("facts", {"SPY":{}}, [{"title":"n","url":"http://u","source":"s"}])
json.dump({"ticker":"GUIDE:%s"%xe.GUIDE_TOPICS[0]["id"],"memo":"메모!"}, open("confirmed_topic_context.json","w"))
ea=types.SimpleNamespace(get_macro_data=lambda: {}, TAX_RULES_BASIS="2026년 10월 기준 세법",
    OVERSEAS_CG_DEDUCTION=2_500_000, TAX_OVERSEAS_CAPITAL_GAINS=0.22, TAX_DOMESTIC_DIVIDEND=0.154,
    ISA_TAX_FREE_LIMIT=2_000_000, ISA_SEPARATE_TAX=0.099, PENSION_TAX=0.055,
    get_macro_thermometer_indicators=lambda: {"volatility": 40}, _build_macro_thermometers_chart=lambda i: "<div>온도계</div>")
xe.price_chart=lambda *a: "<figure class='ondo-chart'>가격</figure>"
xe.run_explainer("GUIDE:"+xe.GUIDE_TOPICS[0]["id"], ea)
assert got["article_type"]=="guide" and got["memo"]=="메모!" and got["meta"]=={"example_tickers":["SPY"]} and got["category_label"].startswith("ETF/")
assert not os.path.exists("confirmed_topic_context.json")
tax_guide = next(g for g in xe.GUIDE_TOPICS if g.get("tax"))
got.clear(); xe.run_explainer("GUIDE:" + tax_guide["id"], ea)
assert "ondo-calc" in got["visual_html"] and "계산 예시" in got["facts_text"], got.get("visual_html", "")[:80]
plain = next((g for g in xe.GUIDE_TOPICS if not g.get("tax")), None)
if plain:
    got.clear(); xe.run_explainer("GUIDE:" + plain["id"], ea); assert "가격" in got["visual_html"]
got.clear(); xe.run_explainer("ISSUE:fx", ea); assert got["article_type"]=="issue" and got["memo"]=="" and "온도계" in got["visual_html"]
print("explainer ok")

# 환율 이슈: 원화 수익률 = (1+달러 수익률)×(1+환율 변화)-1, 국내 상장은 제외
import pandas as pd, yfinance as yf
yf.Ticker = lambda t: type("T", (), {"history": lambda s, period: pd.DataFrame({"Close": [1300.0] * 200 + [1365.0]})})()
f, v = xe.fx_effect({"SPY": {"returns": {"1년": 12.0}}, "GLD": {"returns": {"1년": 30.0}}, "360750.KS": {"returns": {"1년": 6.8}}})
assert "SPY: 달러 기준 1년 +12.0%, 원화 기준 +17.6%, 환율이 반대로 같은 폭 움직였다면 +6.4%" in f, f
assert "360750" not in f.split("[계산")[1].split("- 원/달러")[0] and "<table" in v and "cdn.plot.ly" in v
print("fx effect ok")

# 2026-11-02: 환율 변화 0.0%는 사실 자료에서 빠지고, 본문 영어 구절은 교열이 잡는다
assert xe._day_move({"usd_krw_diff_pct": 0.0}) == ""
assert "-0.42%" in xe._day_move({"usd_krw_diff_pct": -0.42, "usd_krw_direction": "하락"})
from ondo.checks import lint
assert lint.english_phrases("<p>환율 효과(calculated by ondo), VOO와 S&P 500</p><p>태그: etf, fx rate check</p>") == ["calculated by ondo"]
print("fx filler/english ok")

# 2026-11-03: 금리 이슈 - 금리가 0.1%p 오를 때 평균 반응을 실제 주간 자료로 계산(장기채는 음수, 단기채는 0에 가까움)
import numpy as np
idx = pd.date_range("2025-11-07", periods=260, freq="B")
rng = np.random.default_rng(0)
dy = rng.normal(0, 0.03, 260); dy[0] = 0
yld = 4.2 + np.cumsum(dy)
def _px(beta):   # 금리 1%p당 beta% 움직이는 가격
    return 100 * np.cumprod(1 + (beta * dy) / 100)
series = {"^TNX": yld, "TLT": _px(-16.0), "SHY": _px(-1.8)}
tz = {"^TNX": "America/Chicago"}   # 실제처럼 금리는 시카고, ETF는 뉴욕 시간
yf.Ticker = lambda t: type("T", (), {"history": lambda s, period: pd.DataFrame(
    {"Close": series[t]}, index=idx.tz_localize(tz.get(t, "America/New_York")))})()
f, v = xe.rates_effect({"TLT": {}, "SHY": {}, "360750.KS": {}})
tlt = float(f.split("TLT: 금리 0.1%p 오를 때 평균 ")[1].split("%")[0])
shy = float(f.split("SHY: 금리 0.1%p 오를 때 평균 ")[1].split("%")[0])
assert -1.8 < tlt < -1.4 and -0.25 < shy < -0.12 and "360750" not in f and "<table" in v, f
print("rates effect ok", tlt, shy)
