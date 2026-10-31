import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import topic_engine as te, media_engine as me
calls={}
me.make_chart=lambda spec, out_path=None: calls.setdefault("chart_spec", spec) and "/tmp/x.png"
me.make_title_card=lambda t,c,out_path=None: calls.update(card=(t,c)) or "/tmp/c.png"
up=iter([(11,"https://ondo99.com/chart.png"),(22,"https://ondo99.com/card.png")])
me.upload_png=lambda p: next(up)
me.unsplash_photo=lambda q, used=None: calls.update(q=q) or {"url":"https://images.unsplash.com/p","author":"A","author_url":"u","unsplash_url":"v","alt":"x"}
te._ask_json=lambda *a,**k: {"query_en":"emergency food supplies","alt_ko":"비상식량 사진"}
te.plan_outline=lambda *a: {"outline":[{"part":i,"heading":f"h{i}","focus":"f"} for i in range(1,6)]}
te._write_parts=lambda *a: {"_slug":"x"}
te._assemble=lambda parts: ("제목","<p>intro</p><h3>A</h3><p>a</p><h3>B</h3><p>b</p><h3>C</h3><table></table><h3>D</h3><p>d</p>",["t"])
te._check_duplicate=lambda *a: False
te._llm_quality_check=lambda *a, **k: {"quality_score":0.9,"issues":[]}
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
assert b.index("ondo-photo")<b.index("<h3>A") and b.index("ondo-chart")>b.index("<h3>B")
assert "</table><figure" not in b.replace("\n","")
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
assert s=="publish" and calls["featured"] is None and "ondo-chart" not in calls["body"]
print("fallback ok")
