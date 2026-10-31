import os, sys, json, types
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import pandas as pd
import topic_engine as te
te.google_news=lambda q,n=5:[{"title":f"{q} 뉴스{i} <b>","url":f"http://n/{i}","source":"매체","date":""} for i in range(n)]
te.scrape_text=lambda u, limit=3000: "본문"*100
te.fetch_feed=lambda url,d=3:[{"title":"FDA approves new drug X","url":"http://f/1","summary":"approval","source":"FDA"},
                             {"title":"Company hires CEO","url":"http://f/2","summary":"","source":"Fierce"}]
te._ask_json=lambda p, thinking_budget=0: {"index":0,"title_ko":"신약 X 승인","keywords_ko":"신약 X","why":"승인"}
b=te.discover_bio(); assert b[0]["score"]==2.0 and b[0]["topic_key"].startswith("bio:"), b
t=te.discover_tech(); assert t and t[0]["category"]=="tech"
te._ask_json=lambda *a, **k: {"index":-1}
assert te.discover_bio()==[] and te.discover_tech()==[] and te.discover_society()==[]
te._ask_json=lambda *a, **k: {"index":2,"title_ko":"출생아 수","keywords_ko":"출생아 수","why":"발표"}
s=te.discover_society(); assert s and s[0]["score"]==1.1
# energy
import yfinance as yf
class T:
    def __init__(s,t): s.t=t
    def history(s, period):
        n=250; base=[100.0]*n
        if s.t=="KC=F": base=[100.0]*(n-22)+[100+i for i in range(22)]   # +21% month
        return pd.DataFrame({"Close":base})
yf.Ticker=T
e=te.discover_energy(); assert e and e[0]["topic_key"]=="energy:KC=F", e
print(e[0]["title_seed"], e[0]["score"])
yf.Ticker=lambda t: type("X",(),{"history":lambda s,period: pd.DataFrame({"Close":[100.0]*250})})()
assert te.discover_energy()==[]
# trend
import trend_engine
trend_engine.get_trending_searches=lambda geo: ["단풍 명소","홍길동","공기 튀김기"]
trend_engine.get_interest=lambda kws, geo, timeframe: {kws[0]:{"momentum_pct":50.0,"latest":80}}
te._ask_json=lambda *a, **k: {"picks":[{"keyword":"단풍 명소","why":"계절"},{"keyword":"없는말","why":""}]}
tr=te.discover_trend(); assert len(tr)==1 and tr[0]["score"]==1.5, tr
cb=te.closing_block("출처", te.google_news("x",2))
assert "<b>" not in cb and "&lt;b&gt;" in cb
print("adapters ok")
