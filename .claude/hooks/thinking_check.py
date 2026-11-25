"""제안·판단이 담긴 답에 토론 요약이 없으면 멈추고 다시 쓰게 함(2026-11-25 사용자 '규칙을 계속 까먹는다').
왜: '모든 결정·제안·판단은 사슬·토론을 거친다'는 글 규칙이 재발함(L21 '왜 생각 안 하고 말해?', 11-25 '규칙 왜 무시해?').
글로 적은 규칙은 재발하고 장치로 막은 규칙(영어 답 - korean_reply.py)은 재발 0 → 같은 방식으로.
막는 조건: 한글 300자 이상 + 제안·판단 낱말 + 토론 흔적(반대·토론·찬반·확인한 것·확인 없음) 없음. 짧은 진행 알림·사실 답은 통과.
형식만 채우는 것까지 막지는 못함 - 그래서 '실제로 안 했으면 지금 하라'고 되돌린다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from korean_reply import last_text  # noqa: E402

PROPOSE = re.compile(r"추천|제안|결론|최선|하는 게 (?:좋|맞)|어떨까|판단|하는 것이 좋|권합니다")
DEBATE = re.compile(r"반대|토론|찬반|확인한 것|확인 없음|실제로 확인")


def needs_debate(text):
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    return len(re.findall(r"[가-힣]", t)) >= 300 and bool(PROPOSE.search(t)) and not DEBATE.search(t)


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return 0
    if inp.get("stop_hook_active"):
        return 0
    try:
        text = last_text(inp.get("transcript_path") or "")
    except Exception:
        return 0
    if text and needs_debate(text):
        print(json.dumps({"decision": "block", "reason": (
            "제안·판단이 담긴 답인데 토론 요약이 없습니다(CLAUDE.md '결정할 때'). 사슬(DECISIONS 찾기·목표로 다시 쓰기·전제 의심·실제 확인·운영자라면 최선?)과 "
            "찬반 토론을 실제로 거쳤는지 보고, 안 했다면 지금 하세요. 답에는 찬성 핵심·반대 핵심(무엇을 확인했고 결과)·결론을 짧게 붙여 다시 쓰세요. "
            "확인할 게 없는 취향 문제면 '확인 없음'이라고 적습니다.")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
