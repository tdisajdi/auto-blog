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
