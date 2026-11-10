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
