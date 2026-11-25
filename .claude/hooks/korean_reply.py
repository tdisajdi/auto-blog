"""사용자에게 한 마지막 답이 영어면 멈추고 한국어로 다시 쓰게 함(2026-11-25).
왜: '항상 한국어로 답한다' 규칙을 11-24·11-25 두 번 어김(압축 뒤 맥락이 바뀐 직후) - 같은 실수 2번이면 말 대신 장치로(CLAUDE.md 배우고 넓히기).
Stop 훅: 표준 입력 JSON의 transcript_path에서 마지막 assistant 글(text)을 읽고, 코드·주소를 뺀 글자 중 한글 비율이 30% 미만이면 block.
"""
import json
import re
import sys


def last_text(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") or {}
        if m.get("role") == "user" and any(isinstance(c, dict) and c.get("type") == "text" for c in (m.get("content") or [])
                                           if isinstance(m.get("content"), list)) or (m.get("role") == "user" and isinstance(m.get("content"), str)):
            return ""          # 마지막 사용자 말 뒤에 글 답이 없음
        if m.get("role") == "assistant":
            texts = [c.get("text", "") for c in (m.get("content") or []) if isinstance(c, dict) and c.get("type") == "text"]
            if any(t.strip() for t in texts):
                return "\n".join(texts)
    return ""


def is_english(text):
    t = re.sub(r"```.*?```|`[^`]*`|https?://\S+|\S+\.(py|json|txt|md|yml|html)\b", " ", text, flags=re.S)
    han = len(re.findall(r"[가-힣]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    return lat > 80 and han / max(1, han + lat) < 0.3


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return 0
    if inp.get("stop_hook_active"):
        return 0
    path = inp.get("transcript_path") or ""
    try:
        text = last_text(path)
    except Exception:
        return 0
    if text and is_english(text):
        print(json.dumps({"decision": "block", "reason": "마지막 답이 영어로 쓰였습니다. 사용자에게는 항상 한국어로 답합니다(CLAUDE.md 첫 규칙). 같은 내용을 한국어로 다시 쓰세요."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
