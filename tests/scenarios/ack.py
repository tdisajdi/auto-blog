import os, sys, json, io, contextlib
from datetime import datetime
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import etf_auto as ea
sent, edits, answers = [], [], []
ea._telegram_send_message=lambda t,*a,**k: sent.append((t,k.get("reply_to"))) or 1
ea._telegram_edit_text=lambda mid,t: edits.append((mid,t)) or True
ea._telegram_answer_callback=lambda cid,t="": answers.append(cid)
ea._load_telegram_offset=lambda:0; ea._save_telegram_offset=lambda x:None
ea._telegram_update_is_authorized=lambda u: True
ea._save_pending({"ticker":"SPY","label":"단일 분석 - SPY","reason":"r","article_type":"단일 분석","message_id":555,"sent_at":datetime.now().isoformat(),"created_at":datetime.now().isoformat()})
json.dump({"category":"energy","title_seed":"브렌트유 글","message_id":777,"sent_at":datetime.now().isoformat(),"created_at":datetime.now().isoformat(),"topic_key":"energy:BZ=F","reason":"r"},open("pending_topic.json","w"))
ea._telegram_get_updates=lambda off:[{"update_id":1,"callback_query":{"id":"A","data":"approve_topic","message":{"message_id":777}}},
                                     {"update_id":2,"callback_query":{"id":"B","data":"approve","message":{"message_id":555}}}]
buf=io.StringIO()
with contextlib.redirect_stdout(buf): ea.run_check_approval()
out=buf.getvalue(); assert "APPROVED_TOPIC:energy" in out and "APPROVED_TICKER:SPY" in out
assert answers==["A","B"]
assert any(m==777 and "✅ 승인됨" in t for m,t in edits) and any(m==555 and "✅ 승인됨" in t for m,t in edits)
assert any("승인 확인! 두 번째 글" in t and r==777 for t,r in sent) and any("승인 확인! '단일 분석 - SPY'" in t and r==555 for t,r in sent)
# 이미 처리된 추천 버튼을 또 누르면
edits.clear()
ea._telegram_get_updates=lambda off:[{"update_id":3,"callback_query":{"id":"C","data":"approve","message":{"message_id":555}}}]
with contextlib.redirect_stdout(io.StringIO()): ea.run_check_approval()
assert edits and "이미 처리했거나" in edits[-1][1]
# 어제 추천(다른 메시지)의 approve_topic 버튼 → 오늘 추천은 승인 안 됨
json.dump({"category":"energy","title_seed":"브렌트유 글","message_id":777,"sent_at":datetime.now().isoformat(),"created_at":datetime.now().isoformat(),"topic_key":"energy:BZ=F","reason":"r"},open("pending_topic.json","w"))
edits.clear()
ea._telegram_get_updates=lambda off:[{"update_id":4,"callback_query":{"id":"D","data":"approve_topic","message":{"message_id":111}}}]
buf=io.StringIO()
with contextlib.redirect_stdout(buf): ea.run_check_approval()
assert "APPROVED_TOPIC" not in buf.getvalue() and os.path.exists("pending_topic.json") and edits[-1][0]==111
print("ack ok")
