import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import blog_engine as be, media_engine as me
sent, photos, edits = [], [], []
def send(text, with_approve_button=False, parse_mode=None, buttons=None, reply_to=None):
    sent.append({"text":text,"buttons":buttons,"reply_to":reply_to}); return 1000+len(sent)
be._telegram_send_message=send
be._telegram_send_photo=lambda path=None, photo_url=None, caption="", reply_to=None: photos.append((caption, reply_to)) or True
be._telegram_edit_text=lambda mid, text: edits.append((mid, text)) or True
be._telegram_answer_callback=lambda *a, **k: None
be.get_gemini_response=lambda *a,**k: '{"scene": "harbor at dusk"}'
be._telegram_download_file=lambda fid, dest: open(dest,"wb").write(fid.encode()) and dest
me.make_title_card=lambda *a, **k: open("card.png","wb").write(b"c") and "card.png"
me.shrink_for_web=lambda src, max_side=1200: open("small.jpg","wb").write(b"s") and "small.jpg"
ups=iter(range(1,100)); be._upload_media=lambda p,m: (next(ups), f"https://ondo99.com/{os.path.basename(p)}")
featured={}; be.wp_set_featured_image=lambda pid, mid: featured.update({pid: mid}) or True
store={55:'<h3>5. 영향</h3><p>a</p><div id="ondo-slot-1" class="ondo-slot"></div>\n<h3>6. 앞으로</h3><p>b</p><div id="ondo-slot-2" class="ondo-slot"></div>\n<h3>FAQ</h3>'}
be.wp_get_post_content=lambda pid: store.get(pid)
be.wp_update_post_content=lambda pid, c: store.update({pid: c}) or True
cb=lambda iid, act: {"callback_query":{"id":"c","data":f"img:{iid}:{act}","message":{"message_id":9999}}}

# 발행 → 요청
me.send_image_prompt(55,"출생아 글","society","https://ondo99.com/a",slots=[{"slot":1,"heading":"5. 영향","text":"t"},{"slot":2,"heading":"6. 앞으로","text":"t"}])
# 답장 없이 그림 2장
me.handle_image_reply({"message":{"message_id":501,"photo":[{"file_id":"IMG_A"}]}})
me.handle_image_reply({"message":{"message_id":502,"photo":[{"file_id":"IMG_B"}]}})
qa, qb = sent[-2], sent[-1]
assert qa["reply_to"]==501 and qb["reply_to"]==502 and "어디에 넣을까요" in qa["text"]
labels=[b[0][0] for b in qa["buttons"]]; print("버튼:", [r[0][0] for r in qa["buttons"]], "+", qa["buttons"][-1])
assert labels[0]=="썸네일" and labels[1].startswith("본문 그림 1 ('5. 영향'") and labels[2].startswith("본문 그림 2")
# 그림 A → 본문 그림 1
me.handle_image_reply(cb(501,"s1"))
assert "small.jpg" in store[55] and 'id="ondo-slot-1" class="ondo-illust"' in store[55] and 'id="ondo-slot-2" class="ondo-slot"' in store[55]
assert photos[-1][1]==501 and "본문 그림 1을 넣었어요 ('5. 영향' 단락 뒤)" in photos[-1][0] and "✅ 본문 그림 1에 넣었어요" in edits[-1][1]
# 그림 B → 썸네일
me.handle_image_reply(cb(502,"t")); assert featured[55] and photos[-1][1]==502 and "썸네일을 바꿨어요" in photos[-1][0]
# 같은 버튼 또 누름 → 오래된 버튼
me.handle_image_reply(cb(502,"t")); assert "이미 처리했거나" in edits[-1][1]
# 새 그림 → 버튼에 ✅ 표시
me.handle_image_reply({"message":{"message_id":503,"photo":[{"file_id":"IMG_C"}]}})
lab=[r[0][0] for r in sent[-1]["buttons"]]; assert "✅" in lab[0] and "✅" in lab[1] and "✅" not in lab[2], lab
me.handle_image_reply(cb(503,"x")); assert "취소했어요" in edits[-1][1]
# 설명 '본문 그림 2' → 바로
n=len(sent); me.handle_image_reply({"message":{"message_id":504,"photo":[{"file_id":"IMG_D"}],"caption":"본문 그림 2"}})
assert 'id="ondo-slot-2" class="ondo-illust"' in store[55] and len(sent)==n and photos[-1][1]==504
# 프롬프트에 답장 → 바로 (썸네일 프롬프트)
reqs=json.load(open("pending_images.json")); thumb_mid=[k for k,v in reqs.items() if v["kind"]=="thumb"][-1]
me.handle_image_reply({"message":{"message_id":505,"photo":[{"file_id":"IMG_E"}],"reply_to_message":{"message_id":int(thumb_mid)}}})
assert photos[-1][1]==505 and "썸네일" in photos[-1][0]
# 다른 글 고르기
me.send_image_prompt(66,"두번째 글","energy","https://ondo99.com/b",slots=[])
me.handle_image_reply({"message":{"message_id":506,"photo":[{"file_id":"IMG_F"}]}})
assert "두번째 글" in sent[-1]["text"]           # 최신 글 기준
me.handle_image_reply(cb(506,"o")); listing=sent[-1]; assert any("출생아 글" in r[0][0] for r in listing["buttons"])
me.handle_image_reply(cb(506,"p55")); assert "출생아 글" in sent[-1]["text"] and sent[-1]["reply_to"]==506
me.handle_image_reply(cb(506,"t")); assert photos[-1][1]==506
# 기다리는 글이 하나도 없을 때
os.remove("pending_images.json"); me.handle_image_reply({"message":{"message_id":507,"photo":[{"file_id":"IMG_G"}]}})
assert "기다리는 글이 없어요" in sent[-1]["text"]
assert me.handle_image_reply({"message":{"text":"메모: x"}}) is False
print("buttons ok")
