import os, sys, json, types
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import pandas as pd
import topic_engine as te
te.google_news=lambda q,n=5:[{"title":f"{q} 뉴스{i} <b>","url":f"http://n/{i}","source":"매체","date":""} for i in range(n)]
te.scrape_text=lambda u, limit=3000: "본문"*100
te.fetch_feed=lambda url,d=3:[{"title":"FDA approves new drug X","url":"http://f/1","summary":"approval","source":"FDA"},
                             {"title":"Company hires CEO","url":"http://f/2","summary":"","source":"Fierce"}]
te._ask_json=lambda p, thinking_budget=0: {"index":0,"title_ko":"신약 X 승인","keywords_ko":"신약 X","why":"승인"}
# 2026-11-08: 공식 자료(임상 등록·논문 수)가 없으면 뉴스·기사 발췌만으로는 쓰지 않음
_ct, _ax = te.clinical_trials_block, te.papers_block
te.clinical_trials_block = lambda c, i="": ""
te.papers_block = lambda k: ""
assert te.discover_bio() == [] and te.discover_tech() == []
te.clinical_trials_block = lambda c, i="": "[공식 자료 - 임상]\n- 등록된 임상시험 전체: 10건\n"
te.papers_block = lambda k: "[공식 자료 - 논문]\n- 논문 10편\n"
b=te.discover_bio(); assert b[0]["score"]==2.0 and b[0]["topic_key"].startswith("bio:") and "[공식 자료 - 임상]" in b[0]["facts_text"], b
t=te.discover_tech(); assert t and t[0]["category"]=="tech" and "[공식 자료 - 논문]" in t[0]["facts_text"]
# 자료 블록 계산이 맞는지(인터넷 대신 가짜 건수)
te.clinical_trials_block, te.papers_block = _ct, _ax
def fake_ct(**p):
    adv = p.get("filter.advanced", "")
    if "PHASE3" in adv: return 50
    if "StartDate" in adv: return 100 + (int(adv.split("[")[2][:4]) - 2000)
    if p.get("filter.overallStatus"): return 25
    if p.get("query.intr"): return 7
    return 200
te._ct_count = fake_ct
blk = te.clinical_trials_block("obesity", "semaglutide")
assert "등록된 임상시험 전체: 200건" in blk and "모집 중인 임상: 25건(전체의 12.5%, 코드 계산)" in blk and "3상(허가 신청 직전 단계) 임상: 50건(전체의 25.0%" in blk, blk
assert "(코드 계산)" in blk.split("해마다")[1] and "'semaglutide')이 들어간 임상: 7건" in blk, blk
te._ct_count = lambda **p: None
assert te.clinical_trials_block("obesity") == "" and te.clinical_trials_block("") == ""
import datetime as _dt
_y = _dt.datetime.now().year
def fake_oa(params):
    if params.get("group_by"):
        return {"group_by": [{"key": str(yy), "count": 100 + 25 * (yy - (_y - 5))} for yy in range(_y - 6, _y + 1)]}
    return {"meta": {"count": 60 if f"from_publication_date:{_y}-" in params["filter"] else 40}}
te._openalex = fake_oa
ab = te.papers_block("solid-state battery")
assert "해마다 나온 논문 수" in ab and "+100.0%(코드 계산)" in ab and "+50.0%(코드 계산)" in ab, ab
te._openalex = lambda p: None
assert te.papers_block("x") == "" and te.papers_block("") == ""
tb = te.trend_interest_block("단풍", {"series": [10.0] * 76 + [50.0] * 14})
assert "최고점의 100%" in tb and "+400%" in tb and "배(코드 계산)" in tb, tb
assert te.trend_interest_block("단풍", {"series": [1.0] * 5}) == "" and te.trend_interest_block("x", None) == ""
te._ask_json=lambda *a, **k: {"index":-1}
assert te.discover_bio()==[] and te.discover_tech()==[] and te.discover_society()==[]
te._ask_json=lambda *a, **k: {"index":2,"title_ko":"출생아 수","keywords_ko":"출생아 수","why":"발표"}
assert te.discover_society()==[]          # 공식 통계 표가 없으면 뉴스 제목만으로는 쓰지 않음(2026-11-08)
te._kosis_table_for=lambda q: {"name":"출생"}
te.kosis_fact_block=lambda tb: ("[공식 통계 - KOSIS]\n- 출생아 수: 2025년 1명", {"series":[]})
te._kosis_chart=lambda tb, sm: None
s=te.discover_society(); assert s and s[0]["score"]==1.1 and s[0]["facts_text"].startswith("[공식 통계"), s
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
trend_engine.get_interest=lambda kws, geo, timeframe: {kws[0]:{"momentum_pct":50.0,"latest":80,"series":[10.0]*60+[80.0]*30}}
te._ask_json=lambda *a, **k: {"picks":[{"keyword":"단풍 명소","why":"계절"},{"keyword":"없는말","why":""}]}
tr=te.discover_trend(); assert len(tr)==1 and tr[0]["score"]==1.5 and "검색 관심도 - 구글 트렌드" in tr[0]["facts_text"], tr
trend_engine.get_interest=lambda kws, geo, timeframe: {}
assert te.discover_trend()==[]           # 관심도 자료가 없으면 쓰지 않음
cb=te.closing_block("출처", te.google_news("x",2))
assert "<b>" not in cb and "&lt;b&gt;" in cb
print("adapters ok")
