"""포스팅 지부장 지침서의 '원문 규칙' 칸을 코드로 다시 만든다(2026-11-25 사용자 '빠짐없이, 변형없이 전달됐는지 확인').
손으로 요약하면 빠지고 바뀐다(첫 판: 작가 규칙 29줄 중 출처 원칙·의미 없는 숫자 등을 빼고, 기업 글 규칙 4개를 빠뜨림)
→ 작가·검토가 실제로 받는 규칙을 원본에서 그대로 뽑아 lab/roles/posting/BRIEF.md의 AUTO 칸에 넣는다.

  python site_pages/posting_brief.py        AUTO 칸 다시 쓰기
  python site_pages/posting_brief.py check  원본과 다르면 끝 코드 1(tests/test_posting_brief.py가 씀)
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEF = os.path.join(ROOT, "lab", "roles", "posting", "BRIEF.md")
START, END = "<!-- AUTO:START (site_pages/posting_brief.py가 만듦 - 손으로 고치지 않음) -->", "<!-- AUTO:END -->"
P = os.path.join(ROOT, "ondo", "writing", "prompts")

# (제목, 파일, 무엇을) - 작가에게 붙는 규칙(코드 속 문자열)
CODE_RULES = [
    ("ETF 설명 글·기업 글 공통 규칙 (explainer_engine.py)", "explainer_engine.py"),
    ("기업 소개 글 규칙 (ondo/company.py)", os.path.join("ondo", "company.py")),
    ("ETF 분석·비교 글 규칙 (ondo/writing/analysis.py)", os.path.join("ondo", "writing", "analysis.py")),
    ("다른 분야 규칙 - 지금은 ETF·투자만 공개 (topic_engine.py)", "topic_engine.py"),
]
# 운영 기록에서 포스팅에 닿는 줄 - 줄 머리로 찾아 원문 그대로(바뀌면 check가 잡음)
DOC_LINES = [
    ("PROJECT_STATUS.txt", ["- 애드센스 '가치 없는 콘텐츠'", "- [L1·", "- [L12·", "- [L13·", "- [L11·", "- [L4·", "- [L14·",
                            "- [L15·", "- [L16·", "- [L17·", "- [L18·", "- [L3·"]),
    ("lab/DECISIONS.txt", ["- 11-20 텔레그램 요청 없이", "- 11-20 기업 글엔", "- 11-21 이미 공개된 글과", "- 11-21 나라별 시장 글",
                           "- 11-25 사용자 '그렇게 하자': ETF 주제도", "- 11-11(11-22·11-24 다시 확인)"]),
    ("CLAUDE.md", ["- 사용자는 금융 전문가가 아니다.", "- 상록 글은 요청 없이도", "- **먼저 묻는 것:**"]),
]
# 작가 단계 지침 안의 규칙 덩어리(설계·고침) - 시작 줄부터 끝 줄 앞까지 원문 그대로
BLOCKS = [
    ("plan.txt", "글 설계 규칙 - 섹션 수·순서·분량·제목 약속", "아래 [사실 자료]만으로", "- 관점:"),
    ("patch.txt", "부분 고침 원칙 - 고침 초안을 쓸 때 그대로 지킴", "[고칠 때 원칙]", "{{rules}}"),
    ("rewrite.txt", "고쳐쓰기 원칙 - 되풀이를 지울 때 남길 것", "[고칠 때 원칙]", "{{rules}}"),
]
REVIEWS = ["review_common.txt", "review_fact.txt", "review_reader.txt", "review_policy.txt", "review_value.txt"]


def _rule_strings(path):
    """파이썬 파일 안의 '- [태그] …' 규칙 문자열(이어 붙은 문자열은 하나로), 나온 순서대로. f-문자열은 뺌."""
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "- [" in node.value:
            for part in ("\n" + node.value).split("\n- [")[1:]:
                line = "- [" + part.strip()
                if "{" not in line.split("]")[0]:
                    out.append((node.lineno, line))
    seen, uniq = set(), []
    for ln, line in sorted(out):
        if line not in seen:
            seen.add(line)
            uniq.append(line)
    return uniq


def build():
    rules = [l for l in open(os.path.join(P, "rules.txt"), encoding="utf-8").read().split("\n") if l.strip().startswith("- ")]
    out = [START, "", "## 7. 원문 규칙 - 작가·검토가 실제로 받는 규칙 그대로 (요약 없음)",
           "점검표 A·B는 이 원문을 빠짐없이 확인하는 순서일 뿐이다. 보고서는 아래 번호(R·C·D)와 W 덩어리마다 ✅/❌/해당 없음 + 근거.", "",
           f"### R. 공통 작가 규칙 (ondo/writing/prompts/rules.txt, {len(rules)}항목)"]
    out += [f"R{i}. {l[2:].strip()}" for i, l in enumerate(rules, 1)]
    k = 0
    for title, path in CODE_RULES:
        rs = _rule_strings(path)
        if not rs:
            continue
        out += ["", f"### C. {title}"]
        for r in rs:
            k += 1
            out.append(f"C{k}. {r[2:].strip()}")
    for fn, title, a, b in BLOCKS:
        lines = open(os.path.join(P, fn), encoding="utf-8").read().split("\n")
        i = next(n for n, l in enumerate(lines) if l.startswith(a))
        j = next(n for n, l in enumerate(lines) if n > i and l.startswith(b))
        out += ["", f"### W. {title} ({fn})", "```", "\n".join(lines[i:j]).strip(), "```"]
    out += ["", "### D. 운영 기록에서 온 포스팅 원칙·결정 (원문 그대로)"]
    j = 0
    for fn, heads in DOC_LINES:
        lines = open(os.path.join(ROOT, fn), encoding="utf-8").read().split("\n")
        for h in heads:
            hit = [l for l in lines if l.startswith(h)]
            if len(hit) != 1:
                raise SystemExit(f"{fn}: '{h}'로 시작하는 줄이 {len(hit)}개 - DOC_LINES를 고칠 것")
            j += 1
            out.append(f"D{j}. ({fn}) {hit[0][2:].strip()}")
    for fn in REVIEWS:
        body = open(os.path.join(P, fn), encoding="utf-8").read().strip()
        out += ["", f"### V. 검토 기준 원문 ({fn}) - 다시 검증에서 이 기준으로 지적이 나온다", "```", body, "```"]
    out += ["", END]
    return "\n".join(out)


def current():
    s = open(BRIEF, encoding="utf-8").read()
    if START in s and END in s:
        return s[s.index(START):s.index(END) + len(END)]
    return None


def write():
    s = open(BRIEF, encoding="utf-8").read()
    new = build()
    s = (s[:s.index(START)] + new + s[s.index(END) + len(END):]) if START in s else (s.rstrip("\n") + "\n\n" + new + "\n")
    open(BRIEF, "w", encoding="utf-8").write(s)
    print("BRIEF AUTO 칸 갱신:", new.count("\nR"), "R ·", new.count("\nC"), "C")


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        ok = current() == build()
        print("지침서 원문 규칙:", "원본과 같음" if ok else "원본과 다름 - python site_pages/posting_brief.py 로 갱신")
        sys.exit(0 if ok else 1)
    write()
