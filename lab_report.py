"""연구 노트 도구(2026-11-08): 편집 기록부(logs/) 전체를 읽어 '무엇 때문에 떨어지는지'를 종류별로 센다.

사용자 요청 - "스스로 오류를 찾고 최선의 방향으로 나아가는" 연구개발 방식. 지적이 나오면 고치는 데서 그치지 않고,
쌓인 시험 기록에서 가장 자주 막히는 원인을 숫자로 골라 그것부터 고치기 위한 도구다(예전에 74판을 손으로 셌던 것을 자동으로).

실행: python lab_report.py [시작날짜 YYYY-MM-DD]   → 화면에 보고서. 저장소의 파일은 바꾸지 않는다.
"""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

# 지적 문장 → 원인 종류(위에서부터 처음 맞는 것). 새 원인이 '기타'로 많이 쌓이면 여기에 추가한다.
CAUSES = [
    ("필수 답 누락", r"\[누락\]|누락\]|질문에 답하지|답이 없"),
    ("반복: 표를 문장으로 다시 읽음", r"(반복|되풀이|중복|나열|그대로).*(표|그래프|시각)|(표|그래프|시각).*(반복|되풀이|중복|나열|그대로)"),
    ("반복", r"반복|되풀이|중복|같은 (내용|숫자|설명)"),
    ("자료에 없음·지어냄", r"자료에 없|지어내|확인되지 않|근거 없|출처를 밝히지|사실 자료와 다"),
    ("숫자·계산 오류", r"계산|수치가 (틀|다르)|숫자가 (틀|다르)|기간이 다른"),
    ("과장·권유", r"과장|권유|단정|추천|적합|유리|압도적"),
    ("링크·출처", r"링크|출처"),
    ("문체·어색함", r"번역투|어색|기계적|어미|문장이 (길|다소)"),
    ("일반론·얇음", r"일반론|뻔한|얇|구체적이지|분량"),
    ("구조·제목", r"제목|섹션|순서|흐름"),
]
LINT_CAUSES = [
    ("교열: 한 줄 정리 없음", r"한 줄 정리 없음"),
    ("교열: 비슷한·같은 문장", r"비슷한 문장|같은 문장"),
    ("교열: 금지 표현", r"금지 표현"),
    ("교열: 너무 얇음", r"너무 얇음"),
    ("교열: 숫자 나열", r"숫자 줄글 나열"),
    ("교열: 영어·깨진 단어", r"영어 문구|깨진 단어"),
    ("교열: 출처 표현", r"확인할 수 없는 출처"),
    ("교열: 표", r"표가 \d+개|표에 빈칸"),
]


def classify(text, table=CAUSES):
    for name, pat in table:
        if re.search(pat, text):
            return name
    return "기타"


def _severity(issue):
    m = re.match(r"\[(치명|중요|사소)·([^\]]+)\]", issue)
    return (m.group(1), m.group(2)) if m else (None, None)


def load(since=None, root="logs"):
    out = []
    for f in sorted(glob.glob(os.path.join(root, "*", "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = os.path.basename(os.path.dirname(f)) + "-" + os.path.basename(f)[:2]
        if since and day < since:
            continue
        rounds = [s for s in d.get("steps", []) if str(s.get("step", "")).startswith("편집장 검토")]
        if not rounds:
            continue
        out.append({"file": f, "day": day, "type": d.get("article_type") or "?", "topic": d.get("topic_id") or "",
                    "rounds": rounds, "result": d.get("result") or {}})
    return out


def report(arts):
    lines = []
    if not arts:
        return "기록 없음"
    blocking, minor, lint_block, value_miss = Counter(), Counter(), Counter(), Counter()
    by_role = Counter()
    per_type = defaultdict(lambda: {"n": 0, "pass": 0, "first": 0, "rounds": 0})
    examples = defaultdict(list)
    n_rounds = 0
    for a in arts:
        t = per_type[a["type"]]
        t["n"] += 1
        passed_at = next((i + 1 for i, r in enumerate(a["rounds"]) if r.get("passed")), None)
        if passed_at:
            t["pass"] += 1
            t["rounds"] += passed_at
            t["first"] += passed_at == 1
        for r in a["rounds"]:
            n_rounds += 1
            for iss in r.get("issues") or []:
                sev, role = _severity(iss)
                cause = classify(iss)
                if sev in ("치명", "중요"):
                    blocking[cause] += 1
                    by_role[role] += 1
                    if len(examples[cause]) < 2:
                        examples[cause].append(iss[:110])
                elif sev == "사소":
                    minor[cause] += 1
            for li in r.get("lint") or []:
                if not li.startswith("[참고]"):
                    lint_block[classify(li, LINT_CAUSES)] += 1
            for v in r.get("value_missing") or []:
                value_miss[v] += 1
    days = sorted({a["day"] for a in arts})
    lines.append(f"[범위] 글 {len(arts)}편, 검토 {n_rounds}판, {days[0]} ~ {days[-1]}")
    lines.append("\n[글 종류별] 통과 / 첫 판 통과 / 통과까지 평균 판 수")
    for k, t in sorted(per_type.items(), key=lambda kv: -kv[1]["n"]):
        avg = f"{t['rounds'] / t['pass']:.1f}" if t["pass"] else "-"
        lines.append(f"- {k}: {t['pass']}/{t['n']} 통과, 첫 판 통과 {t['first']}, 평균 {avg}판")
    lines.append("\n[통과를 막은 지적(치명·중요) - 원인별, 많은 순]  ← 여기 1~2위부터 고친다")
    total = sum(blocking.values()) or 1
    for c, n in blocking.most_common():
        lines.append(f"- {c}: {n}번 ({n / total * 100:.0f}%)")
        for ex in examples[c]:
            lines.append(f"    예) {ex}")
    lines.append("\n[막은 검토 담당] " + ", ".join(f"{k} {v}" for k, v in by_role.most_common()))
    if lint_block:
        lines.append("\n[통과를 막은 교열 지적] " + ", ".join(f"{k} {v}" for k, v in lint_block.most_common()))
    if value_miss:
        lines.append("\n[독자 가치에서 빠진 것] " + ", ".join(f"{k} {v}" for k, v in value_miss.most_common()))
    if minor:
        lines.append("\n[사소 지적 원인] " + ", ".join(f"{k} {v}" for k, v in minor.most_common(6)))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(load(sys.argv[1] if len(sys.argv) > 1 else None)))
