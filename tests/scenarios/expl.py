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
