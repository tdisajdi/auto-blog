"""사용자 말에 디자인 낱말(표·그래프·캐릭터·카드·표지·목차·글꼴·색·화면…)이 있으면
design/DESIGN_NOTES.txt에서 그 낱말이 든 [머리] 덩어리만 뽑아 Claude 눈앞에 띄운다(11-25 사용자 '규칙을 계속 까먹는다').
왜: 규칙을 안 읽어서가 아니라 만들 때 떠올리지 못함 + 메모가 날짜순이라 '움직이는 그래프 유지'가 엉뚱한 칸(89줄)에 묻혀 있었다.
나눠 적은 사본을 따로 두지 않는다(두 벌이면 어긋남) - 원본에서 그때그때 뽑는다."""
import json, os, re, sys

TOPICS = {
    "그래프": r"그래프|차트|chart|plotly|막대|선 그래프",
    "표": r"표(?![지시현준])|table|열 |칸",
    "캐릭터": r"캐릭터|마스코트|부엉이|mascot",
    "SNS 카드": r"카드|핀터레스트|쓰레드|threads|pinterest|\bx\b|sns|og",
    "표지": r"표지|썸네일|명화|cover",
    "목차": r"목차|contents|toc",
    "글꼴·색": r"글꼴|폰트|font|색깔|색상|색 ",
    "글 화면": r"화면|디자인|모양|레이아웃|사이드|옆 칸|글 끝|각주|출처 상자|모바일|pc",
}

def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except Exception:
        return
    hit = [t for t, p in TOPICS.items() if re.search(p, prompt, re.I)]
    if not hit:
        return
    path = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), "design", "DESIGN_NOTES.txt")
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return
    starts = [i for i, l in enumerate(lines) if l.startswith("[")] + [len(lines)]
    pat = "|".join(TOPICS[t] for t in hit)
    out = []
    for a, b in zip(starts, starts[1:]):
        block = [l for l in lines[a:b] if re.search(pat, l, re.I)]
        if block:
            out.append(f"{lines[a][:70]} (DESIGN_NOTES {a + 1}줄~)")
            out += ["  " + l.strip()[:220] for l in block[:8]]
    print(f"[디자인 규칙 자동 알림 - 이번 말의 주제: {', '.join(hit)}]")
    print("순서: 사슬·토론 → 시안(PC+휴대폰) → 사용자 확인 → 적용. 모양 변경은 확인 없이 공개하지 않는다(theme_push 확인표).")
    print("\n".join(out[:60]))

main()
