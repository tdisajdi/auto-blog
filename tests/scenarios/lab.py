"""2026-11-08: 연구 노트 도구(lab_report.py) - 가짜 기록부로 원인 분류·종류별 통과 집계가 맞는지."""
import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import lab_report as lr
os.makedirs("logs/2026-11", exist_ok=True)
def _log(name, typ, rounds):
    steps = [{"step": f"편집장 검토 {i + 1}", "passed": p, "issues": iss, "lint": li, "value_missing": vm}
             for i, (p, iss, li, vm) in enumerate(rounds)]
    json.dump({"article_type": typ, "steps": steps, "result": {}}, open(f"logs/2026-11/{name}.json", "w", encoding="utf-8"))
_log("07-guide-a", "guide", [(False, ["[중요·독자 편집] '숫자' → 표에 있는 수치를 문장으로 그대로 나열", "[사소·독자 편집] 'x' → 어미 반복"],
                             ["한 줄 정리 없음 - …", "[참고] 꾸밈말"], ["제목 질문에 답함"]),
                            (True, [], [], [])])
_log("07-issue-b", "issue", [(True, ["[치명·사실 검증] 'y' → 자료에 없는 기관 이름을 지어내어"], [], [])])
arts = lr.load("2026-11-01")
assert len(arts) == 2
out = lr.report(arts)
assert "guide: 1/1 통과, 첫 판 통과 0, 평균 2.0판" in out and "issue: 1/1 통과, 첫 판 통과 1" in out, out
assert "반복: 표를 문장으로 다시 읽음: 1번" in out and "자료에 없음·지어냄: 1번" in out, out
assert "교열: 한 줄 정리 없음 1" in out and "꾸밈말" not in out.split("[통과를 막은 교열 지적]")[1].split("\n")[0], out
assert lr.classify("정리 섹션에서 같은 숫자를 되풀이") == "반복" and lr.classify("무관한 말") == "기타"
print("lab report ok")
