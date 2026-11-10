"""2026-11-09: ETF 분석 글 경로(write_etf_article) - 파일을 나눈 뒤에도 자료 → 시각 자료 서랍 → 편집국까지 이어지는지, 운영자 메모·드라이버 정리."""
import sys,os; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from datetime import datetime
import etf_auto as ea, topic_engine as te
from ondo.writing import analysis
got={}
ea.get_tistory_rss_links=lambda u: []
ea._get_previous_analysis=lambda l,t,rss_posts=None: {}
ea.get_macro_data=lambda: {"usd_krw":"1,400원","us_10y":"4.1%","fear_greed":"50"}
class D:
    def quit(s): got["quit"]=1
ea._create_chrome_driver=lambda: D()
ea.get_etf_real_data=lambda t,d,m: {"name":t}
ea._create_widget_html=lambda *a: "<div>w</div>"
ea._create_backtest_simulation_chart=lambda *a: ("<div>b</div>",{})
ea._create_return_calendar_heatmap=lambda *a: "<div>c</div>"
ea._get_recent_news_for_etfs=lambda c,m: [{"title":"n","url":"http://x","source":"s"}]
ea.get_macro_thermometer_indicators=lambda: {}
ea._add_competitive_comparison=lambda c: "<table>c</table>"
ea._add_risk_scenarios=lambda c: ("<div>r</div>",{})
ea._add_sector_deep_analysis=lambda c,m: ""
ea._add_scenario_analysis=lambda c,t: "<div>s</div>"
ea._build_macro_thermometers_chart=lambda i: ""
analysis.fact_sheet=lambda *a,**k: "[사실 자료]"
te.produce_article=lambda **k: got.update(k)
open("confirmed_topic_context.json","w").write('{"ticker":"VOO","memo":"메모"}')
ea.write_etf_article(["VOO"],"오늘",datetime.now())
assert got["quit"] and got["article_type"]=="analysis" and got["memo"]=="메모" and got["drawer"], got.keys()
assert not os.path.exists("confirmed_topic_context.json")
print("etf write path ok")
# 11-10 사람 읽기(VOO): '$1,735.73B'를 독자가 못 읽음 → 한국 단위로
from ondo.etf.data import usd_amount_ko
assert usd_amount_ko(1735.73e9)=="약 1조 7,357억 달러" and usd_amount_ko(12.3e9)=="약 123억 달러", usd_amount_ko(1735.73e9)
# 공포·탐욕 지수는 단일 분석 자료에서도 뺌(상관없는 일반론 문단을 끌어냄)
assert "공포·탐욕 지수 {" not in open(os.path.join(sys.argv[1],"ondo/writing/analysis.py")).read()
print("aum unit ok")
# 11-10 이름표 점검: 보수 차이는 '보수만 떼는' 식, 5년이 안 된 ETF는 '5년 전'이라 하지 않음
from ondo.etf.data import _estimate_fee_impact, _window_label
fi = _estimate_fee_impact(100_000_000, "0.03%")
assert fi.startswith("약 992,") and "수익률 0% 가정" in fi, fi
assert _window_label(5.0) == "5년 전" and _window_label(2.3) == "상장 직후(약 2.3년 전)"
from ondo.writing import analysis as _an2
assert _an2._mdd_window({"cagr_years": 2.3}) == "상장 이후 약 2.3년" and _an2._mdd_window({"cagr_years": 5.0}) == "최근 5년"
assert "'연평균 배당 증가율'로만 언급" not in open(os.path.join(sys.argv[1], "ondo/writing/analysis.py")).read()
print("label audit ok")
# 11-10: 10년물 금리는 금리 글에만(환율·단일 분석 글에서 원인 단정·일반론을 끌어냄)
assert "미국 10년물 국채 금리 {" not in open(os.path.join(sys.argv[1], "ondo/writing/analysis.py")).read()
_ee_src = open(os.path.join(sys.argv[1], "explainer_engine.py")).read()
assert 'rt = "금리" in str(news_query' in _ee_src and "if rt else" in _ee_src
print("rate line only for rates ok")
