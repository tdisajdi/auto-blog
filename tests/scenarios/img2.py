import os, sys, json, io, contextlib
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import etf_auto as ea, media_engine as me, blog_engine as be
sent=[]
ea._telegram_send_message=be._telegram_send_message=lambda t,*a,**k: sent.append(t) or 900
ea._load_telegram_offset=lambda:0; saved={}
ea._save_telegram_offset=lambda x: saved.update(off=x)
ea._telegram_update_is_authorized=lambda u: True
handled=[]
me.handle_image_reply=lambda u: bool((u.get("message") or {}).get("photo")) and (handled.append(u) or True)
# no pending recs, no updates -> just checks telegram and stops
ea._telegram_get_updates=lambda off: []
buf=io.StringIO()
with contextlib.redirect_stdout(buf): ea.run_check_approval()
assert "썸네일 그림이 왔는지만" in buf.getvalue() and "새로운 텔레그램 응답이 없습니다" in buf.getvalue()
# pending image only + photo update
json.dump({"1":{"post_id":1,"title":"t","category":"etf","url":"u","created_at":"2026-10-30T00:00:00"}},open("pending_images.json","w"))
ea._telegram_get_updates=lambda off:[{"update_id":5,"message":{"photo":[{"file_id":"x"}]}},{"update_id":6,"message":{"text":"메모: 아무"}}]
with contextlib.redirect_stdout(io.StringIO()): ea.run_check_approval()
assert len(handled)==1 and saved["off"]==7
print("check flow ok")
