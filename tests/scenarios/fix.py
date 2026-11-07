import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import pandas as pd, yfinance as yf
import topic_engine as te, blog_engine as be
te.google_news=lambda q,n=5:[]
class T:
    def __init__(s,t): s.t=t
    def history(s, period):
        c=[100.0]*250
        if s.t=="NG=F": c=[104.0]*249+[106.0]; c[-2]=100.0      # 하루만 튐(+6%) - 1주·한 달은 거의 그대로
        if s.t=="ZW=F" and MODE == "week": c=[106.0]*244+[100.0, 101.0, 103.0, 105.0, 107.0, 108.0]   # 1주 +8%, 한 달 +1.9%
        return pd.DataFrame({"Close":c})
yf.Ticker=T
MODE = "day"
assert te.discover_energy() == [], "하루만 튄 것으로는 주제를 만들지 않음(선물 만기 교체 등 왜곡 가능)"
MODE = "week"
e=te.discover_energy(); print(e[0]["title_seed"]); assert "일주일 새 8% 오른" in e[0]["title_seed"] and "배경" not in e[0]["title_seed"], e[0]["title_seed"]
assert "옥수수" in e[0]["facts_text"] and "커피" not in e[0]["facts_text"] and "센트/부셸" in e[0]["facts_text"]
# 2026-11-03: 가스 글은 1년 범위·3개월 변화와 유럽 가스 비교 가격까지 받는다(숫자 한 줄뿐이라 되풀이했음)
class G:
    def __init__(s,t): s.t=t
    def history(s, period):
        idx=pd.date_range("2025-11-03", periods=250, freq="B")
        c=[100.0]*250
        if s.t=="NG=F": c=[4.0]*200+[3.0]*44+[2.6,2.6,2.7,2.8,2.9,2.9]   # 1주 +11.5%
        if s.t=="TTF=F": c=[30.0]*240+[40.0]*10
        return pd.DataFrame({"Close":c}, index=idx)
yf.Ticker=G
g=te.discover_energy()[0]
assert g["topic_key"]=="energy:NG=F" and "1년 최고 4.00(2025-11-03)" in g["facts_text"] and "3개월" in g["facts_text"], g["facts_text"]
assert "유럽 천연가스(네덜란드 TTF)" in g["facts_text"] and "유로/MWh" in g["facts_text"], g["facts_text"]
yf.Ticker=T
# failed send -> no pending
te.choose_topic=lambda: e[0]; te._telegram_send_message=lambda *a, **k: False
te.run_discover_and_notify(); assert not os.path.exists("pending_topic.json")
# gemini 400 -> skip to next model
class R:
    def __init__(s,c): s.status_code=c; s.text='{"error":"x"}'
    def json(s): return {"candidates":[{"content":{"parts":[{"text":"{\"ok\":1}"}]}}]}
calls=[]
def post(url, json=None, timeout=0):
    m=url.split("/models/")[1].split(":")[0]; calls.append(m)
    return R(400 if m=="gemini-3.5-flash-lite" else 200)
be.requests.post=post; be.time.sleep=lambda s: None
be.GEMINI_API_KEYS[:]=[f"k{i}" for i in range(5)]
r=be.get_gemini_response("hi"); print(calls, r)
assert calls.count("gemini-3.5-flash-lite")==1 and r
print("fix ok")

# 2026-11-03: 사회 글은 2년치만이 아니라 긴 흐름과 그 기간 최고·최저를 받는다
births = {"2016": 406243, "2017": 357771, "2018": 326822, "2019": 302676, "2020": 272337,
          "2021": 260562, "2022": 249186, "2023": 230028, "2024": 238317, "2025": 254341}
te.kosis_data = lambda *a, **k: ([{"C1": "T1", "C1_NM": "출생아수(명)", "ITM_NM": "건수", "UNIT_NM": "",
                                   "PRD_DE": p, "DT": str(v), "TBL_NM": "인구동태"} for p, v in births.items()], None)
blk, sm = te.kosis_fact_block(te.KOSIS_TABLES[0])
assert "출생아수(명) 흐름: 2016년 406,243" in blk and "최고 2016년 406,243" in blk and "최저 2023년 230,028" in blk, blk
print("kosis trend ok")
from ondo.checks import lint
_, iss, _ = lint.fix_and_check("<h1>t</h1><p>지polit적 변수와 MMBtu는 단위, ondo의 기준</p><p>태그: a</p>")
assert [i for i in iss if "깨진 단어 '지polit'" in i] and not [i for i in iss if "ondo의" in i or "MMBtu" in i], iss
print("broken word ok")

# 2026-11-03: 고령 비율 글은 판단 기준선(7/14/20%)과 처음 넘은 해, 가장 크게 변한 해를 받는다
aged = {"2016": 13.5, "2017": 14.2, "2018": 14.8, "2019": 15.5, "2020": 16.4, "2021": 17.1, "2022": 18.0,
        "2023": 19.0, "2024": 20.0, "2025": 21.2}
te.kosis_data = lambda *a, **k: ([{"C1": "00", "C1_NM": "전국", "ITM_NM": "고령인구비율", "UNIT_NM": "%",
                                   "PRD_DE": p, "DT": str(v), "TBL_NM": "고령인구비율"} for p, v in aged.items()], None)
blk, _ = te.kosis_fact_block(next(t for t in te.KOSIS_TABLES if t["key"] == "aged"))
assert "고령사회 기준(14%)을 처음 넘은 해: 2017년" in blk and "초고령사회 기준(20%)을 처음 넘은 해: 2024년" in blk, blk
assert "고령화사회 기준(7%)은 이 자료 기간 시작(2016년) 전에 이미 넘음" in blk and "가장 컸던 때 2025년(+1.2%p)" in blk, blk
print("aged thresholds ok")
_, iss, _ = lint.fix_and_check("<h1>t</h1><p>2016년 6,995,652명에서 2017년 7,356,106명, 2018년 7,650,408명, 2019년 8,026,915명, "
                               "2020년 8,496,077명으로 늘었다.</p><p>2016년 13.5%에서 2025년 21.2%로 올랐다.</p><p>태그: a</p>")
assert [i for i in iss if "연도별 숫자 줄글 나열(5개" in i] and lint.blocking([i for i in iss if "연도별" in i]), iss
assert te._kosis_position({"series": [("2016", 13.5), ("2024", 20.0), ("2025", 21.2)], "value": 21.2, "prev": 20.0}) == "최근 3년 중 가장 높음"
assert te._kosis_position({"series": [("2023", 5), ("2024", 3), ("2025", 4)], "value": 4, "prev": 3}) == "전년보다 늘어"
print("year list / kosis title ok")
h2, iss, fx = lint.fix_and_check('<h1>2025년 1인가구비율 역대 최고</h1><p><a href="x">세무사신문</a> 의 보도처럼</p><p>태그: a</p>')
assert [i for i in iss if "역대/사상" in i] and '</a>의 보도' in h2, (iss, h2)
print("overclaim / particle ok")
assert lint.text_of('<p><a href="x">코인리더스</a>에 따르면 <strong>3%</strong>다</p><p>다음</p>') == "코인리더스에 따르면 3%다 다음"
import explainer_engine as xe2
assert "코인" in xe2._OFF_TOPIC_NEWS
print("inline tags ok")
_, iss, _ = lint.fix_and_check("<h1>t</h1><p>10월 2일 기준 424,134천 배럴이었던 재고는 10월 9일 415,577천 배럴, 10월 16일 412,517천 배럴로 줄었고 "
                               "10월 23일에는 410,625천 배럴이었다.</p><p>태그: a</p>")
assert [i for i in iss if "날짜별 숫자 줄글 나열(4개" in i], iss
print("date list ok")
te.get_wordpress_recent_posts = lambda *a, **k: [{"title": "나스닥 100 대장주 QQQ", "link": "u1", "date": "2026-07-20"},
                                                {"title": "브렌트유 1년 범위", "link": "u2", "date": "2026-11-05"}]
assert [p["link"] for p in te._link_candidates("시장 심리")] == ["u2"], "7월 시험 글은 내부 링크로 추천 안 함"
print("link min date ok")
h3, _, fx3 = lint.fix_and_check("<h1>t</h1><h3>정리</h3>\n기준은 다음과 같습니다.\n\n* 추세: +5.50%\n* 일드갭: -3.84%\n\n<p>끝</p><p>태그: a</p>")
assert "<ul><li>추세: +5.50%</li><li>일드갭: -3.84%</li></ul>" in h3 and "* " not in h3, h3
print("md list ok")
# 2026-11-06: 맨 글자 정리 문단도 감싸서, 도입부와 똑같은 문장은 자동 삭제
dup = "미국 10년물 금리가 4.837%인 상황에서 금리가 0.1%p 상승할 때 TLT는 -1.29%로 크게 하락했습니다."
h4, iss4, fx4 = lint.fix_and_check(f"<h1>t</h1><p>도입 설명입니다. {dup}</p>\n<h3>정리</h3>\n\n{dup} 확인할 기준은 세 가지로 정리할 수 있습니다.\n<p>태그: a</p>")
assert "<p>" + dup in h4 or h4.count(dup) == 1, h4
assert h4.count(dup) == 1 and not [i for i in iss4 if "같은 문장 반복" in i], (h4, iss4)
assert "<p>확인할 기준은" in h4.replace(dup + " ", "").replace("<p> ", "<p>") or "확인할 기준은" in h4
print("bare line wrap ok")
# 2026-11-07: 링크 없이 쓴 매체명에 자료의 기사 주소로 링크(첫 번째만, 이미 링크된 건 그대로)
facts_n = "[관련 뉴스]\n- 제목 - TradingKey (TradingKey) https://news.example/t\n- 다른 제목 - 연합뉴스 (연합뉴스) https://news.example/y"
fx5 = []
h5 = lint.link_sources('<p>TradingKey 보도에서도 언급됐다. TradingKey는</p><p><a href="https://news.example/y">연합뉴스</a>에 따르면</p>', facts_n, fx5)
assert h5.count('href="https://news.example/t"') == 1 and h5.count("news.example/y") == 1 and fx5 == ["매체명 링크 추가: TradingKey"], (h5, fx5)
print("source autolink ok")
# 2026-11-07: 날짜(○년 ○월 ○일)는 연도별 나열로 세지 않음
_, iss6, _ = lint.fix_and_check("<h1>t</h1><p>VOO는 2022년 1월 3일 고점에서 2022년 10월 12일 바닥까지 떨어졌고 2023년 12월 13일에 회복했다. "
                                "QQQ는 2021년 12월 27일 고점에서 2022년 11월 3일 바닥까지 떨어진 뒤 2023년 12월 13일에 되찾았다.</p><p>태그: a</p>")
assert not [i for i in iss6 if "숫자 줄글 나열" in i], iss6
print("dates not year list ok")
# 2026-11-08: KOSIS 표가 objL 단계를 더 요구하면 한 단계씩 늘려 다시 요청
_calls = []
class _KR:
    def __init__(self, j): self._j = j
    def json(self): return self._j
def _kget(url, params=None, **k):
    _calls.append(dict(params))
    if "objL2" not in params:
        return _KR({"err": "20", "errMsg": "필수요청변수값이 누락되었습니다. (objL)"})
    return _KR([{"PRD_DE": "2024", "DT": "1"}])
import importlib
te = importlib.reload(te)          # 앞에서 kosis_data를 가짜로 바꿔 둬서 원래 함수로 되돌림
_oldget = te.requests.get
te.requests.get = _kget
_oldkey = os.environ.get("KOSIS_API_KEY"); os.environ["KOSIS_API_KEY"] = "x"
rows, err = te.kosis_data("110", "T", "Y", 3)
assert rows and not err and len(_calls) == 2 and _calls[1]["objL2"] == "ALL", (rows, err, _calls)
te.requests.get = _oldget
print("kosis objL retry ok")
