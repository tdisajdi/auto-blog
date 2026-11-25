"""사용자 말의 주제(표·그래프·캐릭터·카드·표지·목차·색·글 끝·옆 칸…)에 맞는 design/DESIGN_NOTES.txt 칸을 통째로 띄운다.
11-25 사용자 '규칙을 계속 까먹는다': 안 읽어서가 아니라 만들 때 못 떠올림 + 날짜순 메모에 묻힘 → 메모를 주제별 칸으로 묶고,
말마다 그 칸만 짧게 띄운다(너무 많이 띄우면 소음 - 첫 판은 '디자인' 한 낱말에 목차 25줄을 띄웠음).
나눠 적은 사본을 따로 두지 않는다 - 원본 칸에서 그때그때 뽑는다."""
import json
import os
import re
import sys

TOPICS = [   # (말 속 낱말, 칸 머리에 든 말)
    (r"그래프|차트|chart|plotly|막대|(?<![가-힣])표(?![지시현준면])|테이블|table", "표·그래프"),
    (r"캐릭터|마스코트|부엉이", "캐릭터"),
    (r"카드|핀터레스트|쓰레드|스레드|threads|pinterest|sns|공유 미리보기|트위터", "SNS"),
    (r"표지|썸네일|명화|대표 이미지", "표지"),
    (r"목차", "목차"),
    (r"글꼴|폰트|색깔|색상|(?<![가-힣])색(?:을|이|은|도|감|이랑|이나|만|부터)?(?![가-힣])", "색·글꼴"),
    (r"글 ?끝|마지막 부분|출처|각주|공유하기|저자", "글 끝"),
    (r"옆 ?칸|오른쪽|사이드|계기판|계산기", "옆 칸"),
    (r"본문|형광펜|강조|소제목|온도계", "글 화면"),
    (r"디자인|모양|시안|이쁘|예쁘|귀엽|아기자기|픽셀|도트|분위기", "콘셉트"),
]


def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except Exception:
        return
    if "task-notification" in prompt or prompt.lstrip().startswith("<system"):
        return
    heads = [h for p, h in TOPICS if re.search(p, prompt, re.I)]
    if not heads:
        return
    path = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), "design", "DESIGN_NOTES.txt")
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return
    starts = [i for i, l in enumerate(lines) if l.startswith("[")] + [len(lines)]
    out = []
    for a, b in zip(starts, starts[1:]):
        if lines[a].startswith("[순서") or any(h in lines[a] for h in heads):
            out += [l for l in lines[a:b] if l.strip()]
    print(f"[디자인 규칙 자동 알림 - 주제: {', '.join(heads)} / design/DESIGN_NOTES.txt에서]")
    print("\n".join(out[:70]))


main()
