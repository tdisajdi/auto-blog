import os, sys, json
from datetime import datetime, timedelta
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
os.environ["NONINTERACTIVE"]="1"
import topic_engine as te, blog_engine as be
sent=[]
def fake_send(text, with_approve_button=False, **k):
    sent.append((text, with_approve_button)); return 1000+len(sent)
te._telegram_send_message = fake_send

def cand(cat, score, key):
    return {"category":cat,"topic_key":key,"title_seed":f"{cat} 주제 {key}","facts_text":"사실들","news":[{"title":"n","link":"http://x"}],"score":score,"reason":"이유","source_note":"출처"}

# 1) choose_topic: weak everywhere -> None; one strong -> picked; failing adapter skipped
te.ADAPTERS = {"trend":lambda:[cand("trend",0.1,"a")], "tech":lambda:(_ for _ in ()).throw(RuntimeError("x")),
               "bio":lambda:[], "energy":lambda:[cand("energy",0.05,"b")], "society":lambda:[]}
import random; random.seed(1)
# no history -> full staleness bonus 0.8; 0.1+0.8+<=0.3 could pass 1.0; use history to remove bonus
now=datetime.now().isoformat()
for c in ["trend","energy"]:
    json.dump({"articles":[{"timestamp":now,"topic_data":{"_meta":{"topic_key":"zzz"}}}]}, open(f"{c}_article_state.json","w"))
assert te.choose_topic() is None, "weak should skip"
te.ADAPTERS["bio"]=lambda:[cand("bio",2.0,"fda1")]
best=te.choose_topic(); assert best["category"]=="bio", best
# repeat block: same key recently written in bio
json.dump({"articles":[{"timestamp":now,"topic_data":{"_meta":{"topic_key":"fda1"}}}]}, open("bio_article_state.json","w"))
assert te.choose_topic() is None, "repeat should be blocked"
os.remove("bio_article_state.json")
print("choose_topic ok")

# 2) run_discover_and_notify writes pending with message_id + button
te.run_discover_and_notify()
p=json.load(open("pending_topic.json")); assert p["category"]=="bio" and p["message_id"]==1001 and sent[-1][1]=="approve_topic"
# reminder path
te.run_discover_and_notify(); p=json.load(open("pending_topic.json")); assert "아직" in sent[-1][0] and p["message_id"]==1002
print("discover ok")

# 3) two-slot approval
import etf_auto as ea
ea._telegram_send_message = fake_send
ea._save_pending({"ticker":"SPY","reason":"r","article_type":"단일 분석","message_id":555,"sent_at":(datetime.now()-timedelta(hours=5)).isoformat(),"created_at":datetime.now().isoformat()})
ea._load_telegram_offset=lambda:0; ea._save_telegram_offset=lambda x:None
ea._telegram_update_is_authorized=lambda u: u.get("ok",True)
ups=[{"update_id":1,"message":{"text":"메모: 바이오 메모","reply_to_message":{"message_id":1002}}},
     {"update_id":2,"message":{"text":"메모: ETF 메모","reply_to_message":{"message_id":555}}},
     {"update_id":3,"ok":False,"callback_query":{"data":"approve"}},
     {"update_id":4,"callback_query":{"data":"approve_topic","message":{"message_id":1002}}}]
ea._telegram_get_updates=lambda off: ups
import io, contextlib
buf=io.StringIO()
with contextlib.redirect_stdout(buf): ea.run_check_approval()
out=buf.getvalue(); print(out)
assert "APPROVED_TOPIC:bio" in out and "APPROVED_TICKER" not in out
c=json.load(open("confirmed_topic2_context.json")); assert c["memo"]=="바이오 메모"
assert not os.path.exists("pending_topic.json")
assert ea._load_pending()["memo"]=="ETF 메모"
print("approval ok")

# 4) run_confirmed -> produce_article with mocks
calls={}
te.get_wordpress_recent_posts=lambda *a, **k: []
te.write_article=lambda **k: {"html":"<h1>바이오 제목</h1><p>intro</p><h3>h</h3><p>x</p><p>태그: 태그</p>",
    "plan":{"slug":"bio test","title":"t"},"score":0.65,"issues":["근거 부족"]}
te._check_duplicate=lambda *a: False
def fake_pub(title, body, tags=None, status="publish", slug=None, category_slug=None, featured_image=None):
    calls.update(title=title, body=body, status=status, slug=slug); return True, "https://ondo99.com/?p=1"
te.publish_to_wordpress=fake_pub
te._register_article=lambda *a, **k: calls.update(reg=k)
te.run_confirmed()
assert calls["status"]=="draft" and "바이오 메모" in calls["body"] and "의료진" in calls["body"] and calls["slug"]=="bio-test", calls
assert calls["reg"]["extra_data"]["_meta"]["topic_key"]=="fda1"
assert "임시글" in sent[-1][0]
assert not os.path.exists("confirmed_topic2_context.json")
print("run_confirmed ok")

# 5) 다시 쓰기: REPLACE_URL이면 새로 올리지 않고 그 글을 바꾼다, 지적 남은 판(clean=False)은 임시글
upd = {}
te.wp_find_post_by_url = lambda u: (242, "옛 제목", "etf")
te.wp_update_post = lambda pid, **f: upd.update(pid=pid, **f) or True
te.publish_to_wordpress = lambda *a, **k: (_ for _ in ()).throw(AssertionError("새 글을 올리면 안 됨"))
te.write_article = lambda **k: {"html": "<h1>새 제목</h1><p>본문</p>\n태그: a b", "plan": {"slug": "s"}, "score": 0.9,
                                "issues": [], "clean": True}
os.environ["REPLACE_URL"] = "https://ondo99.com/2026/10/31/x/"
st, t, u = te.produce_article(kind_label="기초 가이드", title_seed="s", facts_text="f", rules="", category_label="ETF",
                              article_type="guide", topic_id="g")
assert st == "publish" and upd["pid"] == 242 and upd["title"] == "새 제목" and u == os.environ["REPLACE_URL"], (st, upd)
upd.clear()
te.write_article = lambda **k: {"html": "<h1>새 제목</h1><p>본문</p>", "plan": {}, "score": 0.95, "issues": ["분량 부족"], "clean": False}
st, _, _ = te.produce_article(kind_label="k", title_seed="s", facts_text="f", rules="", category_label="ETF",
                              article_type="guide", topic_id="g")
assert st == "failed" and "pid" not in upd and "원래 글은 그대로" in sent[-1][0], (st, upd)
del os.environ["REPLACE_URL"]
print("replace ok")
