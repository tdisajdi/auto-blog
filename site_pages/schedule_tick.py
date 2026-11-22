"""공개 예약을 깃허브 10분 점검(tick)에서 처리(2026-11-22, 백로그 97).

  python site_pages/schedule_tick.py          lab/publish_schedule.json을 읽어 지금 할 일 1개만 함
왜: 지금까지 공개 예약은 Claude 세션 알림으로 돌았는데, 세션이 다른 일로 바쁘면 늦음(771이 9분 늦음).
    깃허브 tick은 세션과 상관없이 10분마다 돈다.
파일 형식:
  {"mode": "dry" | "live",
   "items": [{"id": 887, "kind": "ko", "at": "2026-12-02T03:19:00Z"},
             {"id": 887, "kind": "en", "at": "2026-12-02T06:07:00Z"}]}
  처리하면 항목에 "done"(시각)·"result"(한 줄)를 적는다. 실패한 영어판은 "failed"를 적고 다시 시도하지 않는다(사람이 확인).
지키는 것(11-20 사용자 요청 속도 규칙):
  - 한 번에 1개만. 한국어 공개는 00:00~14:00Z(한국 9~23시), 12~13Z는 피함, 앞 한국어 공개와 5시간 이상, 하루(UTC) 최대 2편.
  - 정각·30분(분이 0·1·30·31)이면 다음 tick으로 미룸.
  - 이미 공개된 글(세션 알림이 먼저 올렸거나 손으로 올린 경우)은 공개 시각만 받아 'done'으로 적음 - 두 번 올리지 않음.
  - 'dry'면 무엇을 할지 출력만 함(이미 공개된 글의 'done' 적기만 함). 하루 dry-run 뒤 'live'로 바꿈.
  - 영어판: 한국어가 공개된 뒤에만, 원문을 새로 받아(export) 대조(check) 통과할 때만 올림(push).
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PATH = os.path.join(ROOT, "lab", "publish_schedule.json")
GAP_H = 5
DAY_MAX = 2


def _t(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _z(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ko_window(now):
    """한국어 공개 가능한 때인가: (가능, 이유)."""
    if not (0 <= now.hour < 14):
        return False, "공개 시간 밖(00~14Z만)"
    if now.hour in (12, 13):
        return False, "12~13Z는 피함"
    if now.minute in (0, 1, 30, 31):
        return False, "정각·30분 피함 - 다음 tick"
    return True, ""


def pick(items, now):
    """지금 할 항목 하나와 미룬 이유들. 한국어 규칙(창·간격·하루 2편)은 여기서 판단."""
    done_ko = sorted(_t(i["done"]) for i in items if i.get("kind") == "ko" and i.get("done"))
    notes = []
    for it in sorted(items, key=lambda i: i["at"]):
        if it.get("done") or it.get("failed") or _t(it["at"]) > now:
            continue
        if it.get("kind") == "en":
            if _t(it["at"]).hour == 12 or now.hour in (12, 13) or now.minute in (0, 1, 30, 31):
                notes.append(f"{it['id']} 영어판: 12~13Z·정각·30분 피함")
                continue
            return it, notes
        ok, why = ko_window(now)
        if not ok:
            notes.append(f"{it['id']}: {why}")
            continue
        if done_ko and now - done_ko[-1] < dt.timedelta(hours=GAP_H):
            notes.append(f"{it['id']}: 앞 공개({_z(done_ko[-1])})와 {GAP_H}시간 안 됨")
            continue
        if sum(1 for d in done_ko if d.date() == now.date()) >= DAY_MAX:
            notes.append(f"{it['id']}: 오늘 이미 {DAY_MAX}편")
            continue
        return it, notes
    return None, notes


def _wp_status(pid):
    """(상태, 공개 시각 UTC 문자열)."""
    import requests
    import blog_engine as be
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}",
                     headers={"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}, params={"fields": "status,date"}, timeout=30)
    j = r.json() if r.ok else {}
    d = j.get("date")
    return j.get("status"), (_z(_t(d)) if d else None)


def _alert(text):
    try:
        import blog_engine as be
        be._telegram_send_message(text)
    except Exception as e:
        print("알림 실패:", type(e).__name__)


def sync_done(items, status=_wp_status):
    """세션 알림·손으로 먼저 공개된 한국어 글은 공개 시각만 적음(간격 계산이 맞게, 두 번 올리지 않게)."""
    changed = False
    for it in items:
        if it.get("kind") == "ko" and not it.get("done") and not it.get("failed"):
            try:
                st, when = status(it["id"])
            except Exception as e:
                print(f"{it['id']} 상태 확인 실패:", type(e).__name__)
                continue
            if st == "publish" and when:
                it["done"], it["result"] = when, "이미 공개돼 있음(세션·손 공개)"
                changed = True
                print(f"{it['id']}: 이미 공개 {when} - 기록만")
    return changed


def run(data, now, status=_wp_status, publish=None, english=None):
    """한 번 처리. (바뀌었나, 출력 줄). publish/english는 시험에서 바꿔 끼움."""
    items = data.get("items") or []
    changed = sync_done(items, status)
    it, notes = pick(items, now)
    for n in notes:
        print("미룸:", n)
    if not it:
        print("지금 할 공개 없음")
        return changed
    live = data.get("mode") == "live"
    label = f"{it['id']} {'한국어 공개' if it['kind'] == 'ko' else '영어판'} (예정 {it['at']})"
    if not live:
        print("[dry] 할 일:", label)
        return changed
    if it["kind"] == "ko":
        from site_pages import publish_passed
        rc = (publish or publish_passed.main)(it["id"])
        st, when = status(it["id"])
        if rc == 0 and st == "publish":
            it["done"], it["result"] = when or _z(now), "공개"
        else:
            it["failed"], it["result"] = _z(now), f"공개 안 됨(rc {rc}, 상태 {st})"
            _alert(f"⚠️ 예약 공개 실패: {label} - 로그 확인")
    else:
        rc = (english or _english)(it["id"])
        if rc == 0:
            it["done"], it["result"] = _z(now), "영어판 올림"
        elif rc == 2:
            print("영어판: 한국어 원문이 아직 공개 전 - 다음 tick")
            return changed
        else:
            it["failed"], it["result"] = _z(now), f"영어판 실패(rc {rc})"
            _alert(f"⚠️ 예약 영어판 실패: {label} - 번역 대조·로그 확인")
    print("처리:", label, "→", it["result"])
    return True


def _english(pid):
    """0 올림 / 2 한국어 공개 전(다음에) / 1 실패. 원문 새로 받기 → 대조 → 올리기."""
    from site_pages import translate
    if not os.path.exists(os.path.join(translate.DIR, f"{pid}.en.html")):
        print("영어 파일 없음(번역 먼저)")
        return 1
    if translate.export(str(pid)):
        return 1
    meta = json.load(open(os.path.join(translate.DIR, f"{pid}.ko.json"), encoding="utf-8"))
    if meta.get("status") != "publish":
        return 2
    return translate.push(int(pid))


def main():
    if not os.path.exists(PATH):
        print("예약 파일 없음")
        return 0
    data = json.load(open(PATH, encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    if run(data, now):
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
