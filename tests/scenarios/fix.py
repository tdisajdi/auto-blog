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
e=te.discover_energy(); print(e[0]["title_seed"]); assert "일주일 새 8% 오른" in e[0]["title_seed"], e[0]["title_seed"]
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
