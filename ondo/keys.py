"""API 키 이름표.

GEMINI_API_KEY에 키를 쉼표로 여러 개 넣는다. 키 앞에 "이름표:"를 붙이면 문제가 생겼을 때
텔레그램에 그 이름표로 알려준다(어느 계정 키를 다시 받아야 하는지 바로 알 수 있게).

    GEMINI_API_KEY=aa@gmail.com:AIza...,메인:AIza...,AIza...

- 이름표는 아무 글자나 된다(이메일, 별명). 이름표 없는 키는 "키 N번"으로 부른다.
- 저장소가 공개라서 logs/ 기록에는 이름표 대신 번호만 남긴다. 이름표는 텔레그램(개인 채팅)에만.
- 키 값 자체는 어디에도 출력하지 않는다.
"""
import json
import os
import time

KEY_ALERT_FILE = "key_alerts.json"
KEY_ALERT_HOURS = 12      # 같은 키, 같은 문제는 12시간에 한 번만 알림


def parse(raw):
    """'이름표:키,키,...' → [(번호, 이름표, 키)]. 키에는 ':'가 없으므로 마지막 ':' 앞이 이름표."""
    out = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        label, _, key = item.rpartition(":")
        key, label = key.strip(), label.strip()
        if key:
            out.append((len(out) + 1, label, key))
    return out


def gemini_keys():
    return parse(os.environ.get("GEMINI_API_KEY", ""))


def number_of(key):
    for no, _label, k in gemini_keys():
        if k == key:
            return no
    return 0


def name_of(key):
    """텔레그램용 이름: '키 3번 (aa@gmail.com)' / 이름표가 없으면 '키 3번'."""
    for no, label, k in gemini_keys():
        if k == key:
            return f"키 {no}번 ({label})" if label else f"키 {no}번"
    return "알 수 없는 키"


# 문제 종류별 "사용자가 할 일"
ADVICE = {
    "forbidden": "이 키는 거부당하고 있어요(403). 그 계정에서 AI Studio 키를 새로 발급받아 바꿔주세요.",
    "free_tier": "이 키의 프로젝트는 무료 등급을 못 쓴다고 해요(403). 그 계정에서 새 프로젝트로 키를 다시 받아주세요.",
    "invalid": "키 값이 잘못됐다고 해요(400 API key not valid). 복사가 덜 됐는지 확인하거나 새로 발급해주세요.",
}


def alert_key_problem(key, kind, detail="", department="글쓰기"):
    """키 문제를 텔레그램으로 알린다(12시간에 한 번). 키 값은 절대 보내지 않는다."""
    no = number_of(key)
    state = {}
    try:
        with open(KEY_ALERT_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    tag = f"{no}:{kind}"
    if time.time() - state.get(tag, 0) < KEY_ALERT_HOURS * 3600:
        return False
    state[tag] = time.time()
    try:
        with open(KEY_ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass
    msg = (f"🔑 [{department}] Gemini {name_of(key)} 문제\n"
           f"{ADVICE.get(kind, '이 키로 계속 실패하고 있어요.')}\n"
           + (f"응답: {detail[:150]}\n" if detail else "")
           + "다른 키로 자동 전환해서 작업은 계속해요.")
    try:
        from blog_engine import _telegram_send_message
        _telegram_send_message(msg)
    except Exception as e:  # 알림 실패가 글쓰기를 멈추면 안 된다
        print(f"ℹ️ 키 문제 알림 실패: {type(e).__name__}")
    return True


def classify_error(status, text):
    """HTTP 응답 → 키 문제 종류(없으면 None)."""
    t = (text or "").lower()
    if status == 403:
        return "free_tier" if "free tier" in t else "forbidden"
    if status == 400 and "api key not valid" in t:
        return "invalid"
    return None
