"""2026-11-08: 측정 도구(lab_bench.py) - 기록 다시 돌리기·성적표·시험지가 가짜 기록으로 맞게 재는지."""
import os, sys, json, types
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import lab_bench as lb

os.makedirs("logs/2026-11", exist_ok=True)
ONE = "<p><strong>한 줄 정리:</strong> 하루 3배 상품은 오르내림이 반복되면 같은 자리로 돌아와도 손실이 남습니다.</p>"


def body(head, extra=""):
    paras = "".join(f"<p>{'설명 문장입니다. ' * 6}수익률은 {i + 1}.25% 였습니다.</p>" for i in range(5))
    return (f"<h1>제목</h1><p>첫 문장은 글마다 다르게 {head} 시작합니다. 이어지는 문장입니다.</p>"
            f"<h3>{head}의 원리</h3>{paras}{extra}<h3>계좌와 세금 관련 유의사항</h3><p>{'세금 설명입니다. ' * 8}</p>"
            f"<h3>정리</h3><p>{'정리 문장입니다. ' * 6}</p>{ONE}")


def log(name, typ, topic, drafts, passed, facts, started):
    steps = [{"step": f"편집장 검토 {k}", "passed": passed and k == str(len(drafts)), "score": 1.0, "value": 0.8}
             for k in drafts]
    json.dump({"article_type": typ, "topic_id": topic, "started_at": started, "facts": facts, "steps": steps,
               "drafts": drafts, "result": {"score": 1.0 if passed else 0.6}},
              open(f"logs/2026-11/{name}.json", "w", encoding="utf-8"), ensure_ascii=False)


calc = "[계산 예시 - 코드가 계산한 값]\n- 하루 +10%·-9.09% 뒤 3배 상품 -5.45%, 1억 원 기준\n[최근 뉴스]\n- 뉴스 3.33%"
log("07-guide-a", "guide", "a", {"1": body("레버리지", "<p>3배 상품은 -5.45%가 됩니다. 이렇게 손실이 남는 이유를 설명하는 문장입니다.</p>")},
    True, calc, "2026-11-07T10:00:00")
log("07-guide-b", "guide", "b", {"1": body("총보수")}, True, calc.replace("-5.45%", "-7.77%"), "2026-11-07T11:00:00")
log("07-guide-c", "guide", "c", {"1": body("배당"), "2": body("배당")}, True, "[최근 뉴스]\n- 1억 원", "2026-11-07T12:00:00")
log("07-guide-c-2", "guide", "c", {"1": body("배당")}, True, "[최근 뉴스]\n- x", "2026-11-07T13:00:00")
log("07-energy-x", "energy", "x", {"1": "<h1>t</h1><p>짧음</p>"}, False, "", "2026-11-07T14:00:00")

arts = lb.load_logs()
assert [a["topic"] for a in arts] == ["a", "b", "c", "c", "x"], [a["file"] for a in arts]
assert lb.final_round(arts[2]) == "2"

# 고유 숫자: a는 계산값(-5.45%)을 본문에 씀, b는 안 씀(-7.77%가 본문에 없음), 공통 가정값(1억 원)은 세지 않음
consts = lb.common_constants(arts, min_topics=2)
assert lb.unique_numbers(arts[0]["drafts"]["1"], arts[0]["facts"], consts) == ["-5.45%"] or \
    lb.unique_numbers(arts[0]["drafts"]["1"], arts[0]["facts"], consts) == ["5.45%"], lb.unique_numbers(arts[0]["drafts"]["1"], arts[0]["facts"], consts)
assert lb.unique_numbers(arts[1]["drafts"]["1"], arts[1]["facts"], consts) == []
out = lb.scorecard(arts)
assert "① 글 종류 시험: 1/9" in out and "energy" not in out.split("②")[1].split("③")[0], out
assert "③ 연달아 통과" in out and "1개 주제: c" in out, out
assert "없는 글 2개" in out and "guide:b" in out and "guide:c" in out, out
assert "'계좌와 세금 관련 유의사항' 3편" in out, out          # 틀 반복(같은 소제목) 잡힘
assert "자주 묻는" not in out.split("⑧")[1].split("\n")[1]
print("scorecard ok")

# 다시 돌리기: 옛 교열('한 줄 정리' 규칙이 없던 때)과 비교하면 지금 교열은 한 줄 정리 없는 떨어진 초안만 새로 잡는다
def _old_fix(h):
    h2, iss, fx = lb.lint.fix_and_check(h)
    return h2, [i for i in iss if "한 줄 정리" not in i], fx
old = types.SimpleNamespace(fix_and_check=_old_fix, blocking=lb.lint.blocking)
rep = lb.replay(arts, old=old)
assert "통과했던 최종 초안을 새로 막은 것: 0개" in rep and "떨어졌던 판에서 새로 잡은 것: 1개" in rep and "새로 막는 것: 한 줄 정리 없음 1" in rep, rep
print("replay ok")

# 시험지: 변형이 결함을 넣고, 잡았는지 판정이 맞는지
html = arts[0]["drafts"]["1"]
for name, fn in lb.MUTATIONS.items():
    new, marker = fn(html, "")
    assert new and new != html, name
    if marker:
        assert marker[:15] in lb.lint.text_of(new), name
w, mk = lb.mut_wrong_number(html, "")
assert mk and "1.25%" not in mk, mk
assert lb.mut_no_summary("<p>x</p>", "") == (None, None)
item = {"kind": "mutation", "mutation": "judgement", "marker": "지금이 비중을 늘리기에 가장 좋은 시기라고 볼 수 있습니다."}
assert lb.caught(item, [], [{"severity": "중요", "quote": "지금이 비중을 늘리기에 가장 좋은 시기", "problem": "권유"}])
assert not lb.caught(item, [], [{"severity": "사소", "quote": "지금이 비중을 늘리기에 가장 좋은 시기", "problem": "권유"}])
assert not lb.caught(item, [], [{"severity": "중요", "quote": "전혀 다른 문장을 가리킨 지적입니다", "problem": "x"}])
assert lb.caught({"kind": "good"}, ["[참고] x"], [{"severity": "중요", "quote": "q", "problem": "p"}])
assert not lb.caught({"kind": "good"}, ["한 줄 정리 없음"], [])            # 교열은 replay가 따로 잰다
assert lb.caught({"kind": "real", "expect": "유리"}, [], [{"severity": "치명", "quote": "q", "problem": "근거 없이 유리하다고 단정"}])

os.makedirs("lab", exist_ok=True)
exam = {"version": 1, "mutations": ["judgement", "fake_fact", "wrong_number"], "mutations_per_base": 2,
        "bases": [{"id": "g-a", "file": arts[0]["file"], "round": 1},
                  {"id": "g-b", "file": arts[1]["file"], "round": 1, "hidden": True}],
        "real": [{"id": "r-c", "file": arts[2]["file"], "round": 2, "expect": "세금"}]}
json.dump(exam, open("lab/exam.json", "w", encoding="utf-8"), ensure_ascii=False)
assert lb.check_exam(lb.load_exam()) == []
assert lb.check_exam(dict(exam, mutations=["없는변형"])) == ["변형 '없는변형' 없음"]
items = lb.plan_exam(exam)
assert [i["kind"] for i in items] == ["good", "mutation", "mutation", "good", "mutation", "mutation", "real"], items


def fake_review(h, facts, cat):      # 넣은 문장 중 일부만 잡는 가짜 검토 담당
    t = lb.lint.text_of(h)
    out = []
    for s in sum(lb.VARIANTS.values(), []):
        if s in t and ("좋은" in s or "정답" in s or "시기" in s):
            out.append({"severity": "중요", "quote": s[:30], "problem": "권유"})
    return out


res = lb.run_exam(exam, fake_review)
assert len(res) == 7 and all(r["kind"] != "good" or not r["hit"] for r in res), res
s = lb.summarize(res, 1)
assert "공개 문제: 결함 잡음" in s and "숨긴 문제" in s and "judgement" in s and "실제 실패 0/1" in s, s
print("exam ok")
