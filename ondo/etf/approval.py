"""텔레그램 추천·승인: 추천 보내기, 승인/메모 답장 처리, 대상 ETF 점검.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.selection import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
# ============================================================
# 텔레그램 알림 / 승인 체크
# ============================================================

PENDING_RECOMMENDATION_FILE = "pending_recommendation.json"
TELEGRAM_OFFSET_FILE = "telegram_offset.json"
REMINDER_MAX_DAYS = int(os.environ.get("REMINDER_MAX_DAYS", "3"))  # C안: 이 날짜까지 리마인드, 넘으면 새로 발굴


# ============================================================
# [신규] 홍보팀 - 발행 완료 시 Threads에 카드형 요약 자동 게시
# ============================================================



# 카드 이미지 크기. 1080x1350은 인스타/스레드에서 가장 무난하게 쓰이는
# 4:5 세로 비율 - 스레드 피드에서 화면을 많이 차지해 눈에 잘 띈다.


















# ============================================================
# [신규] 검색엔진 알림 - IndexNow 프로토콜
#
# 구글은 2023년에 자체 핑 엔드포인트를 없앴고 IndexNow도 지원하지 않는다
# (사이트맵으로만 발견됨 - 이미 워드프레스가 자동 생성해주므로 별도 조치 불필요).
# 대신 Bing/Yandex/네이버/Seznam/Yep은 공통으로 IndexNow 프로토콜을 지원해서,
# 한 번의 요청으로 이 검색엔진들에 동시에 "새 글 생겼다"고 알릴 수 있다.
# 완전 무료, API 키 발급 절차도 없다 - 키를 우리가 직접 만들고, 그 키가
# 진짜 이 사이트 소유자가 보낸 요청인지 확인할 수 있게 공개 URL에 올려두기만
# 하면 된다.
# ============================================================




















def _load_pending():
    return _load_json_file(PENDING_RECOMMENDATION_FILE, None)


def _save_pending(data):
    _save_json_file(PENDING_RECOMMENDATION_FILE, data)


def _record_pending_message(msg_id):
    """방금 보낸 ETF 추천 메시지 번호를 저장한다(답장 메모가 어느 추천 것인지 구분할 때 사용)."""
    pending = _load_pending()
    if pending and msg_id:
        pending["message_id"] = msg_id if msg_id is not True else None
        if msg_id is not True:
            pending["message_ids"] = (pending.get("message_ids") or []) + [msg_id]   # 첫 추천 + 리마인드 전부
        pending["sent_at"] = datetime.now().isoformat()
        _save_pending(pending)


def _is_current_message(rec, message_id):
    """눌린 버튼의 메시지가 이 추천을 보낸 메시지(첫 추천 또는 리마인드)인지. 기록이 없으면 그냥 인정."""
    known = set(rec.get("message_ids") or []) | ({rec.get("message_id")} - {None, True})
    return not known or message_id in known


def _mark_recommendation_approved(message_id, label):
    """승인한 추천 메시지의 버튼을 없애고 '승인됨'으로 바꿔서, 된 건지 한눈에 보이고 두 번 누르지 않게 한다."""
    if not message_id or message_id is True:
        return
    from blog_engine import _kst_now
    _telegram_edit_text(message_id, f"📌 {label}\n\n✅ 승인됨 ({_kst_now():%m/%d %H:%M}) - 글쓰기를 시작했어요.")


def _clear_pending():
    if os.path.exists(PENDING_RECOMMENDATION_FILE):
        os.remove(PENDING_RECOMMENDATION_FILE)


def _load_telegram_offset():
    data = _load_json_file(TELEGRAM_OFFSET_FILE, {"offset": None})
    return data.get("offset")


def _save_telegram_offset(offset):
    _save_json_file(TELEGRAM_OFFSET_FILE, {"offset": offset})


REPLY_HELP_TEXT = (
    "• 승인: [✅ 승인] 버튼 (누르면 10분 안에 '승인 확인' 답장이 와요)\n"
    "• 다른 종목으로: 티커를 답장 (예: SPY 또는 SPY,360750)\n"
    "• 운영자 메모(선택): '메모: 내용'으로 답장하면 글에 그대로 들어가요"
)


def run_discover_and_notify():
    """
    [매일 예약 실행되는 진입점] 1번(발굴) -> 2번(토론)까지만 진행하고,
    3번(기획) 이전에 멈춰서 텔레그램으로 알림만 보낸다.

    - 대기 중인 추천(pending)이 없으면: 새로 발굴+토론해서 알림
    - 대기 중인 추천이 있고 REMINDER_MAX_DAYS 안이면: 새로 발굴/토론 안 하고
      (=토큰 낭비 없이) 같은 후보로 리마인드만 다시 보냄
    - 대기 중인 추천이 REMINDER_MAX_DAYS를 넘겼으면: 그 추천은 폐기하고
      처음부터 새로 발굴+토론
    """
    pending = _load_pending()

    if pending:
        created_at = datetime.fromisoformat(pending["created_at"])
        age_days = (datetime.now() - created_at).days
        if age_days < REMINDER_MAX_DAYS:
            pending["reminder_count"] = pending.get("reminder_count", 0) + 1
            pending["last_reminded_at"] = datetime.now().isoformat()
            _save_pending(pending)
            _record_pending_message(_telegram_send_message(
                f"⏰ 아직 승인 안 하신 추천이 있어요 ({age_days}일째)\n\n"
                f"글 종류: {pending.get('article_type', '단일 분석')}\n"
                f"주제: {pending.get('label') or _topic_label(pending['ticker'])}\n"
                f"이유: {pending['reason']}\n\n"
                f"{REPLY_HELP_TEXT}\n"
                f"(이 알림은 {REMINDER_MAX_DAYS}일까지 반복되고, 넘기면 새로 추천해드려요)",
                with_approve_button=True,
            ))
            print(f"ℹ️ 기존 추천({pending['ticker']})이 아직 {REMINDER_MAX_DAYS}일 안이라 리마인드만 보냈습니다.")
            return
        else:
            print(f"ℹ️ 기존 추천({pending['ticker']})이 {REMINDER_MAX_DAYS}일을 넘겨서 폐기하고 새로 발굴합니다.")
            _clear_pending()

    explainer = _choose_explainer_topic(get_macro_data())
    if explainer:
        topic, article_type, why = explainer
        _save_pending({
            "ticker": topic,
            "label": _topic_label(topic),
            "article_type": article_type,
            "reason": why,
            "candidates": [],
            "created_at": datetime.now().isoformat(),
            "reminder_count": 0,
        })
        _record_pending_message(_telegram_send_message(
            f"📌 오늘의 추천 주제\n\n글 종류: {article_type}\n주제: {_topic_label(topic)}\n이유: {why}\n\n"
            f"{REPLY_HELP_TEXT}\n({REMINDER_MAX_DAYS}일간 리마인드되고, 그 안에 응답 없으면 자동으로 새로 추천해드려요)",
            with_approve_button=True,
        ))
        print(f"✅ 새 추천을 알림으로 보냈습니다: {topic} ({article_type})")
        return

    candidates = discover_candidates()
    if not candidates:
        # 발굴에서 아무 후보도 못 찾았을 때(전부 쿨다운에 걸림) - 재포스팅으로 폴백
        fallback = pick_next_topic()
        _save_pending({
            "ticker": fallback["ticker"],
            "article_type": "단일 분석",
            "reason": f"재포스팅 폴백: {fallback['reason']}",
            "candidates": [],
            "created_at": datetime.now().isoformat(),
            "reminder_count": 0,
        })
        _record_pending_message(_telegram_send_message(
            f"ℹ️ 오늘은 새로 다룰 만한 신호가 있는 종목이 없어서, 재포스팅(업데이트) 후보를 추천드려요.\n\n"
            f"주제: {_topic_label(fallback['ticker'])}\n"
            f"사유: {fallback['reason']}\n\n"
            f"{REPLY_HELP_TEXT}",
            with_approve_button=True,
        ))
        return

    decision = debate_and_select(candidates)
    topic, article_type = decision["ticker"], "단일 분석"
    comparison_share = _recent_comparison_share()
    if comparison_share < COMPARISON_TARGET_SHARE:
        partners = _find_comparison_partner(topic)
        if partners:
            topic, article_type = ",".join([topic] + partners), "비교"
            print(f"ℹ️ 최근 비교 글 비율 {comparison_share:.0%} → 오늘은 비교 글: {topic}")

    _save_pending({
        "ticker": topic,
        "label": _topic_label(topic),
        "article_type": article_type,
        "reason": decision["reason"],
        "candidates": [{"ticker": c["ticker"], "signal_score": c["signal_score"]} for c in candidates],
        "created_at": datetime.now().isoformat(),
        "reminder_count": 0,
    })

    candidate_summary = ", ".join(f"{c['ticker']}({c['signal_score']}점)" for c in candidates)
    _record_pending_message(_telegram_send_message(
        f"📌 오늘의 추천 주제\n\n"
        f"글 종류: {article_type}\n"
        f"주제: {_topic_label(topic)}\n"
        f"이유: {decision['reason']}\n\n"
        f"검토한 후보군: {candidate_summary}\n\n"
        f"{REPLY_HELP_TEXT}\n"
        f"({REMINDER_MAX_DAYS}일간 리마인드되고, 그 안에 응답 없으면 자동으로 새로 추천해드려요)",
        with_approve_button=True,
    ))
    print(f"✅ 새 추천을 알림으로 보냈습니다: {topic} ({article_type})")


MAX_OPERATOR_MEMO_CHARS = 300


def _parse_topic_reply(text):
    """텔레그램 답장이 종목 지정인지 판단한다. 맞으면 (정규화된 "A,B" 문자열, 강제 여부),
    아니면 None. "OK"처럼 짧은 영어 답장을 종목으로 착각하지 않도록 목록에 없는
    영문 티커는 2~5자이면서 흔한 답장 단어가 아닐 때만 인정한다."""
    t = (text or "").strip().upper()
    force = t.startswith("강제")
    if force:
        t = t[2:].strip()
    tokens = [x.strip() for x in t.split(",") if x.strip()]
    if not tokens or len(tokens) > 3:
        return None
    out = []
    for tok in tokens:
        if re.fullmatch(r"\d{6}(\.KS)?", tok):
            out.append(_normalize_ticker(tok[:6]))
        elif tok in ETF_UNIVERSE:
            out.append(tok)
        elif re.fullmatch(r"[A-Z]{2,5}", tok) and tok not in _TICKER_REPLY_STOPWORDS:
            out.append(tok)
        else:
            return None
    return ",".join(out), force


def _parse_memo_reply(text):
    m = re.match(r"^\s*(메모|memo)\s*[:：]?\s*(.+)$", text or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    memo = m.group(2).strip()
    return memo[:MAX_OPERATOR_MEMO_CHARS] if memo else None


def _recently_written_groups(topic, within_days=COOLDOWN_HARD_FLOOR_DAYS):
    """topic의 종목 중 within_days 안에 같은 지수 묶음 글이 있는 것을 (그룹, 일수)로 돌려준다."""
    now = datetime.now()
    last_by_group = _last_written_dates_by_group()
    hits = []
    for t in topic.split(","):
        g = _etf_group(t)
        dt = last_by_group.get(g)
        if dt and (now - dt).days < within_days:
            hits.append((g, (now - dt).days))
    return hits


def run_check_universe():
    """ETF_UNIVERSE의 각 티커가 야후 파이낸스에서 가격/이름을 받아오는지 점검한다.
    국내 ETF 코드가 맞는 상품인지도 이름으로 확인할 수 있다."""
    failed = []
    load_dynamic_kr_etfs()
    print("[자동 발굴 국내 ETF - 거래대금 상위, 레버리지·인버스 제외]")
    for t, meta in _DYNAMIC_UNIVERSE.items():
        print(f"   {t:10} {meta['theme']:8} {meta['group']:16} {meta['name']}")
    print("\n[고정 목록 데이터 점검]")
    for t, meta in ETF_UNIVERSE.items():
        name, rows = "", 0
        try:
            tk = yf.Ticker(t)
            rows = len(tk.history(period="1mo"))
            try:
                name = (tk.info or {}).get("shortName") or (tk.info or {}).get("longName") or ""
            except Exception:
                name = "(이름 조회 실패)"
        except Exception as e:
            name = f"(오류: {type(e).__name__})"
        mark = "✅" if rows else "❌"
        print(f"{mark} {t:10} {meta['theme']:8} {meta['group']:12} 가격 {rows:3}일  {name}")
        if not rows:
            failed.append(t)
    print(f"\n점검 결과: {len(ETF_UNIVERSE) - len(failed)}/{len(ETF_UNIVERSE)}개 정상"
          + (f", 실패: {', '.join(failed)}" if failed else ""))


PENDING_TOPIC_FILE = "pending_topic.json"            # 두 번째 글(ETF 외 분야) 추천 - topic_engine.py


def _memo_target(update, pending, pending2):
    """메모가 어느 추천 것인지: 그 추천 메시지에 답장했으면 그 추천, 아니면 가장 최근에 보낸 추천."""
    reply_id = (((update.get("message") or {}).get("reply_to_message")) or {}).get("message_id")
    if pending2 and reply_id and reply_id == pending2.get("message_id"):
        return "topic"
    if pending and reply_id and reply_id == pending.get("message_id"):
        return "etf"
    if pending and pending2:
        return "topic" if (pending2.get("sent_at") or "") > (pending.get("sent_at") or "") else "etf"
    return "topic" if pending2 else "etf"


def run_check_approval():
    """
    [자주 실행되는(예: 10분마다) 진입점] 텔레그램 응답을 확인해서:
    - ETF 추천의 [✅ 승인] → APPROVED_TICKER:{주제}
    - 두 번째 글(ETF 외 분야) 추천의 [✅ 승인] → APPROVED_TOPIC:{분야}
    - 종목 답장(예: "SPY" 또는 "SPY,360750") → ETF 추천을 그 종목으로 바꿔서 진행
      (단, 7일 안에 같은 지수 글이 있으면 거절. "강제 SPY"면 그래도 진행)
    - "메모: 내용" → 운영자 메모로 저장. 추천 메시지에 답장으로 보내면 그 추천에,
      그냥 보내면 가장 최근 추천에 붙는다. 글에 그대로 실린다.
    - 운영자 채팅방이 아닌 곳에서 온 메시지는 모두 무시
    GitHub Actions가 위 두 줄을 grep해서 각각의 글쓰기를 실행한다.
    """
    pending = _load_pending()
    pending2 = _load_json_file(PENDING_TOPIC_FILE, None)
    import media_engine
    if not pending and not pending2:
        # 추천이 없어도 텔레그램은 확인한다 - 썸네일 그림(설명에 글 주소를 붙이면 아무 글이나)이 올 수 있음
        print("ℹ️ 대기 중인 추천은 없습니다. 썸네일 그림이 왔는지만 확인합니다.")

    offset = _load_telegram_offset()
    updates = _telegram_get_updates(offset)
    if not updates:
        print("ℹ️ 새로운 텔레그램 응답이 없습니다.")
        return

    confirmed_topic, override, topic2_ok = None, False, False
    max_update_id = offset or 0
    changed, changed2 = False, False

    for update in updates:
        max_update_id = max(max_update_id, update.get("update_id", 0))
        if not _telegram_update_is_authorized(update):
            print("⚠️ 운영자 채팅방이 아닌 곳에서 온 텔레그램 메시지를 무시했습니다.")
            continue

        # 썸네일 그림 답장(ComfyUI로 만든 이미지) → 그 글의 대표 이미지 교체
        if media_engine.handle_image_reply(update):
            continue

        callback = update.get("callback_query")
        if callback:
            # 누른 사람 화면의 '로딩 중' 표시 끄기 (10분 뒤라 만료됐을 수 있음 - 실패해도 무시)
            _telegram_answer_callback(callback.get("id"), "승인 받았어요")
            # 버튼 신호만으로는 어느 추천 것인지 몰라서, 눌린 메시지가 지금 기다리는 추천(또는 그 리마인드)인지 확인한다.
            # 안 그러면 어제 지나간 추천의 버튼을 눌러도 오늘 추천이 승인돼 버린다.
            cb_mid = (callback.get("message") or {}).get("message_id")
            if callback.get("data") == "approve" and pending and _is_current_message(pending, cb_mid):
                confirmed_topic, override = pending["ticker"], False
            elif callback.get("data") == "approve_topic" and pending2 and _is_current_message(pending2, cb_mid):
                topic2_ok = True
            elif callback.get("data") in ("approve", "approve_topic"):
                # 이미 처리했거나 시간이 지나 사라진 추천의 버튼
                _telegram_edit_text((callback.get("message") or {}).get("message_id"),
                                    "이 추천은 이미 처리했거나 기간이 지났어요. 새 추천을 기다려주세요.")
            continue

        text = ((update.get("message") or {}).get("text") or "").strip()
        if not text:
            continue

        memo = _parse_memo_reply(text)
        if memo:
            if not pending and not pending2:
                # 썸네일만 기다리는 중이라 메모를 붙일 추천이 없다
                _telegram_send_message("📝 메모를 받았는데 지금 승인을 기다리는 추천이 없어서 저장하지 못했어요.")
                continue
            if _memo_target(update, pending, pending2) == "topic":
                pending2["memo"], changed2 = memo, True
                where = "두 번째 글"
            else:
                pending["memo"], changed = memo, True
                where = "ETF 글"
            _telegram_send_message(f"📝 운영자 메모를 저장했어요({where}). 이 글에 그대로 실립니다:\n\"{memo}\"")
            continue

        parsed = _parse_topic_reply(text) if pending else None
        if not parsed:
            continue
        topic, force = parsed
        recent = _recently_written_groups(topic)
        if recent and not force:
            detail = ", ".join(f"{g}({d}일 전)" for g, d in recent)
            _telegram_send_message(
                f"⛔ {topic.replace('.KS', '')}: 최근 {COOLDOWN_HARD_FLOOR_DAYS}일 안에 같은 지수 글이 있어 진행하지 않았어요 → {detail}\n"
                f"같은 내용이 반복되면 애드센스 심사에 불리해요. 그래도 진행하려면 '강제 {topic.replace('.KS', '')}'로 답장해주세요."
            )
            continue
        confirmed_topic, override = topic, True

    _save_telegram_offset(max_update_id + 1)
    if changed and not confirmed_topic:
        _save_pending(pending)
    if changed2 and not topic2_ok:
        _save_json_file(PENDING_TOPIC_FILE, pending2)

    if topic2_ok:
        print(f"APPROVED_TOPIC:{pending2['category']}")
        _save_json_file(CONFIRMED_TOPIC2_FILE, pending2)
        os.remove(PENDING_TOPIC_FILE)
        memo_note = "\n📝 운영자 메모도 함께 실려요." if pending2.get("memo") else ""
        _mark_recommendation_approved(pending2.get("message_id"), f"두 번째 글 - {pending2['title_seed']}")
        _telegram_send_message(f"✅ 승인 확인! 두 번째 글 '{pending2['title_seed']}' 글쓰기를 시작해요.\n"
                               f"보통 15~30분 뒤에 '발행 완료' 메시지와 글 링크가 와요.{memo_note}",
                               reply_to=pending2.get("message_id"))

    if not confirmed_topic:
        if not topic2_ok:
            print("ℹ️ 응답은 있었지만 승인/종목 지정으로 해석되지 않았습니다. 계속 대기합니다.")
        return

    print(f"✅ 확정된 주제: {confirmed_topic}")
    print(f"APPROVED_TICKER:{confirmed_topic}")
    # 3번(기획) 단계와 글쓰기가 선정 사유·글 종류·운영자 메모를 이어받을 수 있게 남겨둔다.
    # run_automation()이 읽어서 쓰고 지운다.
    _save_json_file("confirmed_topic_context.json", {
        "ticker": confirmed_topic,
        "reason": "사용자가 추천 대신 직접 지정한 주제" if override else pending.get("reason", ""),
        "article_type": ("비교" if "," in confirmed_topic else "단일 분석") if override else pending.get("article_type", "단일 분석"),
        "memo": pending.get("memo", ""),
    })
    _clear_pending()
    memo_note = "\n📝 운영자 메모도 함께 실려요." if pending.get("memo") else ""
    label = pending.get('label') if confirmed_topic == pending.get('ticker') else None
    shown = label or _topic_label(confirmed_topic)
    _mark_recommendation_approved(pending.get("message_id"), f"ETF - {shown}")
    _telegram_send_message(f"✅ 승인 확인! '{shown}' 글쓰기를 시작해요.\n"
                           f"보통 15~30분 뒤에 '발행 완료' 메시지와 글 링크가 와요.{memo_note}",
                           reply_to=pending.get("message_id"))

__all__ = [k for k in dir() if not k.startswith('__')]
