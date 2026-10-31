import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import topic_engine as te, media_engine as me
calls={}
me.make_chart=lambda spec, out_path=None: calls.setdefault("chart_spec", spec) and "/tmp/x.png"
me.make_title_card=lambda t,c,out_path=None: calls.update(card=(t,c)) or "/tmp/c.png"
up=iter([(22,"https://ondo99.com/card.png")])   # 그래프는 업로드하지 않음(움직이는 그래프) → 업로드는 대표 카드 하나
me.upload_png=lambda p: next(up)
me.unsplash_photo=lambda q, used=None: calls.update(q=q) or {"url":"https://images.unsplash.com/p","author":"A","author_url":"u","unsplash_url":"v","alt":"x"}
te._ask_json=lambda *a,**k: {"query_en":"emergency food supplies","alt_ko":"비상식량 사진"}
te.get_wordpress_recent_posts=lambda *a, **k: []
te.write_article=lambda **k: {"html":"<h1>제목</h1><p>intro</p><h3>A</h3><p>a</p><h3>B</h3><p>b</p><h3>C</h3><table></table><h3>D</h3><p>d</p>\n태그: t",
    "plan":{"slug":"x"},"score":0.9,"issues":[]}
te._check_duplicate=lambda *a: False
def pub(title, body, tags=None, status="publish", slug=None, category_slug=None, featured_image=None):
    calls.update(body=body, featured=featured_image); return True,"https://ondo99.com/p"
te.publish_to_wordpress=pub
te._register_article=lambda *a,**k: None
te._telegram_send_message=lambda *a,**k: 1
os.environ["BLOG_CATEGORY"]="trend"; os.environ["UNSPLASH_ACCESS_KEY"]="k"
spec={"title":"t","labels":["a","b","c"],"values":[1,2,3],"unit":"","source":"s"}
json.dump({"category":"trend","topic_key":"trend:x","title_seed":"비상식량","facts_text":"f","news":[],"chart":spec},open("confirmed_topic2_context.json","w"))
te.run_confirmed()
b=calls["body"]
assert calls["featured"]==22 and calls["card"]==("제목","trend")
assert b.count("ondo-photo")==1 and b.count("ondo-chart")==1
assert b.index("ondo-photo")<b.index(">A</h3>") and b.index("ondo-chart")>b.index(">B</h3>")
assert "</table><figure" not in b.replace("\n","")
assert "cdn.plot.ly" in b and "&&" not in b.split("ondo-chart")[1][:3000], "움직이는 그래프로 들어가야 함"
print("trend ok")
# ETF explainer: no photo, card yes
calls.clear(); up=iter([(33,"https://ondo99.com/card.png")]); me.upload_png=lambda p: next(up)
os.environ["BLOG_CATEGORY"]="etf"
te.produce_article(kind_label="기초 가이드", title_seed="s", facts_text="f", rules="", category_label="ETF/기초 가이드", article_type="guide", topic_id="g")
assert "ondo-photo" not in calls["body"] and calls["featured"]==33
print("etf ok")
# no unsplash key, media failures -> still publishes
calls.clear(); del os.environ["UNSPLASH_ACCESS_KEY"]; me.upload_png=lambda p:(None,None)
os.environ["BLOG_CATEGORY"]="society"
s,_,_=te.produce_article(kind_label="k", title_seed="s", facts_text="f", rules="", category_label="인구·사회", article_type="society", topic_id="x", chart=spec)
assert s=="publish" and calls["featured"] is None and "ondo-chart" in calls["body"]   # 업로드가 막혀도 움직이는 그래프는 들어감
print("fallback ok")

# 세금 계산표: 코드가 세율로 계산(1,000만 원 이익이면 해외 직투 165만, 국내 상장 154만, ISA 79만, 연금 55만)
import types, explainer_engine as xe
xe.ea = types.SimpleNamespace(OVERSEAS_CG_DEDUCTION=2_500_000, TAX_OVERSEAS_CAPITAL_GAINS=0.22, TAX_DOMESTIC_DIVIDEND=0.154,
                              ISA_TAX_FREE_LIMIT=2_000_000, ISA_SEPARATE_TAX=0.099, PENSION_TAX=0.055, TAX_RULES_BASIS="기준")
f, v = xe.tax_scenarios()
assert "1,000만 원: 해외 상장 ETF (일반계좌) 165만 원, 국내 상장 해외지수 ETF (일반계좌) 154만 원, ISA 일반형 (3년 유지) 79만 원, 연금저축 (연금 수령) 55만 원" in f, f
assert v.count("<table") == 1 and "cdn.plot.ly" in v
print("tax calc ok")
