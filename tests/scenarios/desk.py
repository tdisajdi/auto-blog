"""편집국 시험: 키 이름표, 모델 전환, 한 번에 쓰기 / 섹션별 나눠 쓰기, 교열, 숫자 대조, 고쳐쓰기, 편집 기록부."""
import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
os.environ["GEMINI_API_KEY"] = "aa@gmail.com:KEY1,KEY2,메인:KEY3,KEY4"
os.environ["WRITER_MODEL_PRIORITY"] = "strong-a"
os.environ["GEMINI_MODEL_PRIORITY"] = "fast-a"
import blog_engine as be
from ondo import keys
from ondo.writing import llm, desk
from ondo.checks import lint, numbers, editlog
llm.PAUSE_AFTER_OK = 0
sent = []
be._telegram_send_message = lambda text, *a, **k: sent.append(text) or 1

# 1) 키 이름표
assert [(n, l) for n, l, _ in keys.parse(os.environ["GEMINI_API_KEY"])] == [(1, "aa@gmail.com"), (2, ""), (3, "메인"), (4, "")]
assert keys.name_of("KEY3") == "키 3번 (메인)" and keys.name_of("KEY2") == "키 2번"
assert be.GEMINI_API_KEYS == ["KEY1", "KEY2", "KEY3", "KEY4"], be.GEMINI_API_KEYS
print("keys ok")


class R:
    def __init__(self, code=200, text="", finish="STOP", body=None):
        self.status_code, self._t, self._f = code, text, finish
        self.text = body if body is not None else json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]})

    def json(self):
        return json.loads(self.text)


def model_of(url):
    return url.split("/models/")[1].split(":")[0]


# 2) 좋은 모델 429 → 넉넉한 모델로, 403 키는 빼고 이름표로 알림, 키 값은 메시지에 없음
seen = []
def post(url, payload, key):
    seen.append((model_of(url), key))
    if key == "KEY1":
        return R(403, body='{"error": "free tier not available"}')
    if model_of(url) == "strong-a":
        return R(429, body='{"error": "quota per minute"}')
    return R(200, "안녕")
llm._post = post
log = editlog.EditLog("guide", "t1", "시험")
r = llm.call("p", step="시험", log=log, tier="strong")
assert r.text == "안녕" and r.model == "fast-a", r
assert any("aa@gmail.com" in m and "새 프로젝트" in m for m in sent), sent
assert not any("KEY1" in m for m in sent)
assert "KEY1" in llm._excluded and ("strong-a", "KEY1") in seen
assert [c["status"] for c in log.data["calls"]][:4] == ["403", "429", "429", "429"], log.data["calls"]
assert any(s["step"] == "모델 전환" for s in log.data["steps"])
assert all("KEY" not in json.dumps(c) for c in log.data["calls"])          # 기록부에는 번호만
n_alert = len(sent); llm.call("p", step="시험", tier="strong"); assert len(sent) == n_alert   # 같은 키 알림은 12시간에 한 번
print("llm fallback ok")

# 3) 교열·숫자 대조
h, issues, fixes = lint.fix_and_check("<h1>t</h1><h3>Part 2: 숫자</h3><p>**굵게** 수익률은 N/A입니다. 외신 보도에 따르면 그렇습니다.</p>"
                                      "<p>같은 문단이 두 번 나오는 경우를 시험합니다 정말로요.</p><p>같은 문단이 두 번 나오는 경우를 시험합니다 정말로요.</p><img src=x>")
assert "<h3>숫자</h3>" in h and "<strong>굵게</strong>" in h and "<img" not in h and h.count("같은 문단") == 1
assert any("N/A" in i for i in issues) and any("외신 보도" in i for i in issues) and any("너무 얇음" in i for i in issues)
assert any("태그 줄" in i for i in issues)
facts = "[사실 자료]\n- 보수 0.03%, 0.20%\n- 순자산 1,234,567,890달러\n- 배당 3.456%\n- 2024년 출생아 238,300명"
body = "보수는 0.03%와 0.20%로 0.17%p 차이입니다. 배당은 3.46%, 순자산은 약 12억 달러. 출생아 238,300명. 수익률 27.5%. 2025년 10개."
assert numbers.unverified(body, facts) == ["27.5%"], numbers.unverified(body, facts)
_, iss2, _ = lint.fix_and_check("<h1>t</h1><p>양도세는 250만 원 공제 후 22%입니다. 250만 원 공제, 22%. 250만 원과 22%. 다시 250만 원.</p>"
                                "<p>국내 주식형 ETF의 매매차익은 비과세 혜택이 적용됩니다.</p><p>단, 국내 주식형 ETF의 매매차익은 비과세 혜택입니다.</p>"
                                "<table><tr><td>보수</td><td>확인 필요</td></tr></table>")
assert any("'250만원'를 4번" in i for i in iss2), iss2
assert any("비슷한 문장 반복" in i for i in iss2) and any("표에 빈칸" in i for i in iss2), iss2
print("checks ok")

# 4) 한 번에 쓰기 + 고쳐쓰기 1번
PLAN = {"title": "시험 제목", "key_message": "핵심", "slug": "test-slug",
        "intro": {"goal": "질문", "facts": ["보수 0.03%"]},
        "sections": [{"heading": f"Part {i}: 섹션{i}", "goal": "g", "facts": [f"사실{i}"], "table": True, "chars": 1000} for i in range(1, 4)],
        "faq": ["q1", "q2", "q3"]}

import random
SYL = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허고노도로모보소오조초코토포호구누두루무부수우주추"
def _sent(rng):
    return "".join(rng.choice(SYL) for _ in range(rng.randint(28, 40))) + "다."
def long_html(tag="", n=80):
    rng = random.Random(len(tag) * 1000 + n)
    paras = "".join(f"<p>{tag}{_sent(rng)} {_sent(rng)}</p>" for i in range(n))
    return f"<h1>시험 제목</h1><!-- 메타 -->{paras}<h3>섹션1</h3><p>내용</p><h3>정리</h3><p><strong>한 줄 정리:</strong> 시험 글의 핵심을 한 문장으로 짚는다.</p>\n태그: 가 나 다 라 마"

calls = {"review": 0, "rewrite": 0, "section": 0, "unify": 0}
VALUE_ANSWER = {"best_improvement": "청약 정책을 넣으세요", **{k: {"yes": True, "quote": ""} for k in ["answers_title", "unique_info", "decision_rule", "plain_words", "numbers_explained"]}}
def post_desk(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "독자 가치 담당" in p:
        return R(200, json.dumps(VALUE_ANSWER))
    if "기획 회의" in p:
        assert "제목이 던진 질문" in p and "스스로 확인할 기준" in p, "모든 글 공통 필수 질문이 기획에 들어감"
        return R(200, json.dumps(PLAN))
    if "심각도 기준" in p:
        assert "글의 사실 검증 담당입니다" not in p or "제목이 던진 질문" in p, "사실 검증 담당이 공통 필수 질문 누락을 확인"
        calls["review"] += 1
        if calls["review"] <= 3 and "독자 편집 담당" in p:
            return R(200, json.dumps({"issues": [{"severity": "중요", "quote": "", "problem": "섹션1이 얇음", "fix": "자료로 보탤 것"}]}))
        if calls["review"] <= 3 and "사실 검증 담당" in p:   # 본문에 없는 문장을 인용 → 버려져야 함
            return R(200, json.dumps({"issues": [{"severity": "치명", "quote": "이런 문장은 본문 어디에도 없습니다 정말로", "problem": "틀림"}]}))
        return R(200, json.dumps({"issues": []}))
    if "지적된 문제만 고치고" in p:
        calls["rewrite"] += 1
        assert "섹션1이 얇음" in p
        assert "[독자 가치]" not in p, "참고용 독자 가치 제안은 고쳐쓰기에 넣지 않음(자료에 없는 내용이 들어감)"
        return R(200, long_html("고친 "))
    if "글 전체를 한 번에" in p:
        return R(200, long_html())
    raise AssertionError(p[:80])
llm._post = post_desk
log = editlog.EditLog("guide", "single", "시험")
res = desk.write_article(kind_label="기초 가이드", title_seed="시험", facts_text=facts, rules="", category_label="ETF", log=log)
assert res and res["score"] == 1.0 and res["clean"] and calls == {"review": 9, "rewrite": 1, "section": 0, "unify": 0}, (res and res["score"], calls)
first = next(s for s in log.data["steps"] if s["step"] == "편집장 검토 1")
assert first["score"] == 0.88 and not first["passed"], first          # 중요 1개(-0.12), 지어낸 인용 치명은 버림
assert any(s["step"] == "검토 1 정리" for s in log.data["steps"])
assert log.data["mode"] == "single" and "고친 " in res["html"]
assert [s["heading"] for s in res["plan"]["sections"]] == ["섹션1", "섹션2", "섹션3"]
assert sum(s["table"] for s in res["plan"]["sections"]) == 1
path = log.finish(status="publish", score=res["score"])
assert os.path.exists(path) and "한 번에 쓰기" in log.summary_line() and "고쳐쓰기 1번" in log.summary_line()
print("single ok")

# 5) 한 번에 쓰기가 잘림 → 섹션별 나눠 쓰기(섹션마다 다른 키) → 이음새 다듬기
calls.update(review=99); starts = []
def post_sections(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "글 전체를 한 번에" in p:
        return R(200, "<h1>잘린 글", finish="MAX_TOKENS")
    if "한 부분만 씁니다" in p:
        calls["section"] += 1; starts.append(key)
        assert "글 전체 설계도" in p and "지금까지 쓴 글" in p
        if calls["section"] > 1:
            assert f"부분{calls['section'] - 1} " in p, "앞 섹션 글이 같이 가야 함"
        return R(200, long_html(f"부분{calls['section']} ", 18).replace("<h1>시험 제목</h1>", "<h1>시험 제목</h1>" if calls["section"] == 1 else ""))
    if "나눠 쓴 것을 이어 붙였습니다" in p:
        calls["unify"] += 1
        return R(200, p.split("--- 글 시작 ---")[1].split("--- 글 끝 ---")[0])
    return post_desk(url, payload, key)
llm._post = post_sections
log = editlog.EditLog("society", "sections", "시험")
res = desk.write_article(kind_label="사회", title_seed="시험", facts_text=facts, rules="", category_label="사회", log=log)
assert res and log.data["mode"] == "sections" and calls["section"] == 5 and calls["unify"] == 1, (calls, log.data["mode"])
assert len(set(starts)) >= 3, starts                       # 키를 나눠 썼다
assert any("잘림" in s.get("reason", "") for s in log.data["steps"] if s["step"] == "쓰기 방식")
log.finish(status="draft", score=res["score"])
print("sections ok")

# 6) 전부 막히면 None + 이유 기록
llm._post = lambda url, payload, key: R(429, body="quota")
log = editlog.EditLog("trend", "fail", "시험")
assert desk.write_article(kind_label="k", title_seed="s", facts_text="f", rules="", category_label="c", log=log) is None
assert "한도" in log.data["result"]["reason"], log.data["result"]
log.finish(status="failed")
print("fail ok")

# 7) 주간 요약
lines = editlog.weekly_summary()
text = "\n".join(lines)
assert "편집 기록 (" in text and "섹션별 나눠 쓰기" in text and "편집장 점수" in text and "막힌 호출" in text, text
print(text)
print("weekly ok")

# 8) 좋은 모델만 429 → 한 번에 쓰기는 약한 모델로 내려가지 않고 섹션별로(섹션마다 좋은 모델 → 막히면 넉넉한 모델)
calls.update(review=99, section=0, unify=0)
def post_limit(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "글 전체를 한 번에" in p:
        assert model_of(url) == "strong-a", "한 번에 쓰기는 좋은 모델만"
        return R(429, body="quota")
    return post_sections(url, payload, key)
llm._post = post_limit
log = editlog.EditLog("energy", "limit", "시험")
res = desk.write_article(kind_label="k", title_seed="s", facts_text=facts, rules="", category_label="c", log=log)
assert res and log.data["mode"] == "sections" and calls["section"] == 5
assert any("429" in s.get("reason", "") for s in log.data["steps"] if s["step"] == "쓰기 방식")
print("limit -> sections ok")

# 9) 점수는 높아도 교열 지적이 남은 판보다, 고쳐서 깨끗해진 판을 고른다(실제 사고 재현)
calls.update(review=0, rewrite=0)
def post_pick(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "심각도 기준" in p:
        calls["review"] += 1
        return R(200, json.dumps({"issues": []}))
    if "지적된 문제만 고치고" in p:
        calls["rewrite"] += 1
        return R(200, long_html("고친 "))
    if "글 전체를 한 번에" in p:
        return R(200, long_html("", 40).replace("내용", "수익률 N/A"))
    return post_desk(url, payload, key)
llm._post = post_pick
log = editlog.EditLog("guide", "pick", "시험")
res = desk.write_article(kind_label="k", title_seed="s", facts_text=facts, rules="", category_label="c", log=log)
assert res["clean"] and "고친 " in res["html"] and calls["rewrite"] == 1, (res["score"], res["clean"], calls)
print("pick clean ok")

# 10) 사실 판단은 사실 검증 담당만: 정책 담당의 "사실 오류" 치명 지적은 사소로 낮춘다(실제 사고 재현).
#     같은 숫자 반복은 참고만(발행을 막지 않음)
body10 = long_html("", 60).replace("</h1>", "</h1><p>손익 통산은 되지 않습니다. 2,000만원 2,000만원 2,000만원 2,000만원 2,000만원.</p>", 1)
def post_guard(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "독자 가치 담당" in p:
        return R(200, json.dumps(VALUE_ANSWER))
    if "심각도 기준" in p and "정책·신뢰 담당" in p:
        return R(200, json.dumps({"issues": [{"severity": "치명", "quote": "손익 통산은 되지 않습니다", "problem": "손익 통산이 가능하므로 사실 오류"}]}))
    if "심각도 기준" in p:
        return R(200, json.dumps({"issues": []}))
    raise AssertionError("고쳐쓰기로 가면 안 됨: " + p[:40])
llm._post = post_guard
log = editlog.EditLog("guide", "guard", "시험")
score, found = desk.review(body10, facts, "c", log, 1)
assert found[0]["severity"] == "사소" and score == 0.97, (score, found)
_, li, _ = lint.fix_and_check(body10)
assert li and not lint.blocking(li), li
print("role guard ok")

# 11) 글자까지 같은 문장이 도입과 FAQ에 반복되면 코드가 하나만 남긴다(FAQ 답은 비우지 않음 - 실제 사례)
A = "해외(미국 등) 상장 ETF는 ISA·연금저축·IRP 계좌로 직접 살 수 없습니다."
B = "이 계좌들의 세제 혜택을 쓰려면 같은 지수를 추종하는 국내 상장 ETF를 사야 합니다."
html11 = (f"<h1>t</h1><p>두 상품은 같은 지수를 따라도 세금 차이가 큽니다. {A} {B} 본인 상황에 맞춘 계산이 필요합니다.</p>"
          f"<h3>자주 묻는 질문</h3><h4>🔸 직접 살 수 있나요?</h4><p>{A} {B}</p>")
h11, iss11, fx11 = lint.fix_and_check(html11)
assert h11.count(A) == 1 and h11.count(B) == 1 and f"<p>{A} {B}</p>" in h11, h11
assert not any("같은 문장 반복" in i for i in iss11) and any("반복 문장 삭제" in f for f in fx11), (iss11, fx11)
print("dup sentence fix ok")

# 12) 독자 가치: '예'라도 본문에 없는 인용이면 '아니오'. 참고용이라 통과 여부는 바꾸지 않음(VALUE_BLOCKING 없을 때)
body12 = long_html("", 50)
real = desk.lint.text_of(body12)[40:90]
ans = {k: {"yes": True, "quote": real if k in ("answers_title", "unique_info") else "본문에 없는 문장입니다 아무렇게나"}
       for k in ["answers_title", "unique_info", "decision_rule", "plain_words", "numbers_explained"]}
ans["best_improvement"] = "계산 예시를 하나 더"
llm._post = lambda url, payload, key: R(200, json.dumps(ans))
v, marks, tip = desk.value_review(body12, "제목", "c", editlog.EditLog("g", "v", "s"), 1)
assert v == 0.4 and marks["answers_title"] and not marks["plain_words"] and tip, (v, marks)
print("value review ok")

# 2026-11-05: 필수 답(정리의 숫자)은 반복 지적 예외 - 독자 편집·고쳐쓰기 규칙이 서로 부딪히지 않게
assert "'사소'로만" in desk.prompt("review_reader", category_label="c", facts="", must="")
assert "직접 답" in open("ondo/writing/prompts/rewrite.txt", encoding="utf-8").read()
print("must vs repetition ok")

# 2026-11-05: 통과한 글에 남은 짧은 오타는 검토가 집어 준 대로 코드가 고친다(본문에 정확히 한 번 나올 때만)
h, _fx = desk.apply_typo_fixes("<p>지시장을 지지했다. 시장은</p>", [
    {"severity": "사소", "fix": "'지시장을'을 '시장을'로 수정합니다."},
    {"severity": "사소", "fix": "'시장'을 '증시'로"},            # 두 번 나오는 말은 안 바꿈
    {"severity": "중요", "fix": "'지지'를 '방어'로"}])            # 사소만
assert h == "<p>시장을 지지했다. 시장은</p>", h
print("typo autofix ok")

# 2026-11-06: 용어집 - 자료에 나오는 어려운 말만, 우리 계산식과 같은 뜻으로
from ondo.writing import glossary
picked = dict(glossary.pick("VOO 최대 낙폭(5년) -24.52%, 일드갭 -3.84%, 배당수익률 1.05%"))
assert list(picked) == ["최대 낙폭(MDD)", "일드갭"] and "배당수익률 − 미국 10년물 국채 금리" in picked["일드갭"], picked
assert glossary.block("숫자 없음 그냥 글") == ""
seen_plan = []
_old_post = llm._post
def post_gl(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "기획 회의" in p:
        seen_plan.append(p)
    return post_desk(url, payload, key)
llm._post = post_gl
calls.update({"review": 10})
desk.write_article(kind_label="ETF 분석", title_seed="시험", facts_text=facts + "\n- 최대 낙폭(5년) -24.52%", rules="",
                   category_label="ETF", log=editlog.EditLog("analysis", "single", "용어"))
assert seen_plan and "[용어 풀이" in seen_plan[0] and "최대 낙폭(MDD)" in seen_plan[0], "용어 풀이가 자료와 함께 기획에 들어감"
llm._post = _old_post
print("glossary ok")

h2, fx2 = desk.apply_typo_fixes("<p>20세 이상 장기 국채</p>", [{"severity": "치명", "fix": "'20세 이상'을 '20년 이상'으로 수정해야 합니다."}],
                                severities=("치명", "중요", "사소"))
assert h2 == "<p>20년 이상 장기 국채</p>" and len(fx2) == 1
print("typo autofix all severities ok")
# 계산표가 들어가는 글([표 금지])은 작가 표를 지운다
seen_html = []
_old2 = llm._post
def post_tb(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "글 전체를 한 번에" in p:
        return R(200, long_html().replace("<h3>섹션1</h3>", "<h3>섹션1</h3><table><tr><td>1</td></tr></table>"))
    return post_desk(url, payload, key)
llm._post = post_tb
r_tb = desk.write_article(kind_label="이슈 해설", title_seed="시험", facts_text=facts, rules="- [표 금지] 시스템이 표를 넣음\n",
                          category_label="ETF", log=editlog.EditLog("issue", "single", "표"))
assert r_tb and "<table" not in r_tb["html"], "작가가 만든 표는 지워짐"
llm._post = _old2
print("table ban ok")
# 2026-11-07: 검토 담당이 링크를 볼 수 있게 [링크] 표시
assert desk.review_text('<p><a href="https://x" target="_blank">TradingKey</a>에 따르면 <strong>3%</strong></p>') == "TradingKey[링크]에 따르면 3%"
print("review link marker ok")
tn = desk._norm(desk.review_text('<p><a href="https://x">TradingKey</a>에 따르면 VOO 자산이 늘었다</p>'))
assert desk._quote_found("TradingKey에 따르면 VOO 자산이 늘었다", tn) and desk._quote_found("TradingKey[링크]에 따르면 VOO", tn)
print("quote match with link marker ok")

assert "조건과 숫자로 쓴 판단 기준은 권유가 아니라" in desk.prompt("review_policy", category_label="c", facts="", must="")
print("policy allows conditional criteria ok")
# 2026-11-08: 독자 편집이 '정리 섹션 반복'을 '중요'로 지적하면 코드가 '사소'로(11-07 규칙 강제)
assert desk._SUMMARY_REPEAT.search("환율 예시 설명이 뒤의 '정리' 섹션에서 거의 동일하게 반복됩니다.")
assert desk._SUMMARY_REPEAT.search("앞서 다룬 수치를 결론부에서 그대로 되풀이")
assert not desk._SUMMARY_REPEAT.search("계좌 선택 섹션에서 GLD 수치가 중복으로 되풀이되고 있습니다.")
# 11-08 개정: 지난 기록에서 틀렸던 사례들
assert desk._summary_repeat("본문의 가상 계산 예시와 마지막 '정리' 섹션의 구체적 금액(10년 뒤 약 16만 원, 20년 뒤 약 53만 원) 사이에 설명 방식이 중복되어 있습니다.")
assert not desk._summary_repeat("표에 이미 정리된 수치를 본문에서 그대로 풀어 다시 읽어주어 내용이 중복됩니다.")
assert not desk._summary_repeat("정리 섹션을 제외하고 본문에서 1,000만 원 원금과 5% 수익률 가정 계산 내용이 여러 번 반복됩니다.")
assert not desk._summary_repeat("마지막 '정리' 섹션과 중복되지는 않으나 본문 내 다른 수치 설명들과 어우러져 반복되었습니다.")
assert not desk._summary_repeat("서론과 결론에서 청년층 주거 지원 정책을 거의 동일한 내용으로 반복하고 있습니다.")
print("summary repeat downgrade ok")

# 2026-11-09: 부분 고침 - 지적이 모두 본문 문장을 가리키면 그 문장만 고쳐 받아 바꿔 넣는다
h = ("<h1>t</h1><p>보수는 <strong>0.03%</strong>로 낮은 편이며 최근 10년 중 가장 낮은 수준입니다. 다른 문장은 그대로 둡니다 정말로요.</p>"
     "<p>배당은 3.456%입니다. 이 문장은 지적과 상관없는 설명 문장입니다.</p>")
f_q = [{"severity": "치명", "quote": "최근 10년 중 가장 낮은 수준", "problem": "자료에 없는 기간", "by": "사실 검증"}]
assert desk.patchable(f_q, [], [], h)
assert not desk.patchable(f_q, ["한 줄 정리 없음"], [], h)                       # 교열 막힘은 전체 고쳐쓰기
assert not desk.patchable(f_q + [{"severity": "중요", "quote": "", "problem": "[누락] 판단 기준", "by": "x"}], [], [], h)
assert not desk.patchable([{"severity": "사소", "quote": "x", "problem": "p", "by": "x"}], [], [], h)
new, n, dropped = desk.apply_patches(h, [
    {"find": "보수는 0.03%로 낮은 편이며 최근 10년 중 가장 낮은 수준입니다.", "replace": "보수는 0.03%로 낮은 편입니다."},  # 굵게 태그가 끼어도 찾음
    {"find": "배당은 3.456%입니다.", "replace": "배당은 27.5%입니다."},                                                 # 자료에 없는 숫자 → 버림
    {"find": "없는 문장을 찾으라고 한 경우입니다.", "replace": "x"}], facts)
assert n == 1 and "최근 10년" not in new and "보수는 0.03%로 낮은 편입니다." in new and "배당은 3.456%" in new, (n, new)
assert any("자료에 없는 숫자" in d for d in dropped) and any("못 찾음" in d for d in dropped), dropped
assert "다른 문장은 그대로 둡니다" in new
# 흐름: 첫 판 인용 지적 → 부분 고침(전체 고쳐쓰기 안 부름) → 다음 판 통과
body_p = long_html("", 60).replace("</h1>", "</h1><p>이 상품은 최근 10년 중 가장 낮은 보수를 받는다고 알려져 있습니다.</p>", 1)
calls_p = {"patch": 0, "rewrite": 0, "review": 0}
def post_patch(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "독자 가치 담당" in p:
        return R(200, json.dumps(VALUE_ANSWER))
    if "기획 회의" in p:
        return R(200, json.dumps(PLAN))
    if "심각도 기준" in p:
        calls_p["review"] += 1
        if "사실 검증 담당" in p and "최근 10년 중" in p:
            return R(200, json.dumps({"issues": [{"severity": "치명", "quote": "최근 10년 중 가장 낮은 보수", "problem": "자료에 없는 기간"}]}))
        return R(200, json.dumps({"issues": []}))
    if "지적된 문장만 고쳐서" in p:
        calls_p["patch"] += 1
        return R(200, json.dumps({"edits": [{"find": "이 상품은 최근 10년 중 가장 낮은 보수를 받는다고 알려져 있습니다.", "replace": ""}]}))
    if "지적된 문제만 고치고" in p:
        calls_p["rewrite"] += 1
        return R(200, long_html("고친 "))
    if "글 전체를 한 번에" in p:
        return R(200, body_p)
    raise AssertionError(p[:80])
llm._post = post_patch
log = editlog.EditLog("guide", "patch", "시험")
res = desk.write_article(kind_label="k", title_seed="s", facts_text=facts, rules="", category_label="c", log=log)
assert res["clean"] and calls_p["patch"] == 1 and calls_p["rewrite"] == 0 and "최근 10년" not in res["html"], (calls_p, res["score"])
assert any(s["step"] == "부분 고침" and s["applied"] == 1 for s in log.data["steps"])
print("patch mode ok")

# 2026-11-09: 통과 직전 확인 채점 - 첫 채점이 놓친 치명을 확인 채점이 잡으면 통과 취소 → 다음 판에서 고침
calls_c = {"review": 0, "rewrite": 0}
body_c = long_html("", 60).replace("</h1>", "</h1><p>이 상품은 지난 10년 중 가장 낮은 보수를 받는 상품으로 알려져 있습니다.</p>", 1)
def post_confirm(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "독자 가치 담당" in p:
        return R(200, json.dumps(VALUE_ANSWER))
    if "기획 회의" in p:
        return R(200, json.dumps(PLAN))
    if "심각도 기준" in p:
        calls_c["review"] += 1
        # 사실 검증의 두 번째 채점(확인)에서만 잡힘 - 첫 채점은 놓침
        if "사실 검증 담당" in p and "지난 10년 중" in p and calls_c["review"] > 3:
            return R(200, json.dumps({"issues": [{"severity": "치명", "quote": "지난 10년 중 가장 낮은 보수", "problem": "자료에 없는 기간"}]}))
        return R(200, json.dumps({"issues": []}))
    if "지적된 문장만 고쳐서" in p:
        return R(200, json.dumps({"edits": [{"find": "이 상품은 지난 10년 중 가장 낮은 보수를 받는 상품으로 알려져 있습니다.", "replace": ""}]}))
    if "지적된 문제만 고치고" in p:
        calls_c["rewrite"] += 1
        return R(200, long_html("고친 "))
    if "글 전체를 한 번에" in p:
        return R(200, body_c)
    raise AssertionError(p[:80])
llm._post = post_confirm
log = editlog.EditLog("guide", "confirm", "시험")
res = desk.write_article(kind_label="k", title_seed="s", facts_text=facts, rules="", category_label="c", log=log)
conf = [s for s in log.data["steps"] if s["step"] == "통과 확인 검토"]
first = next(s for s in log.data["steps"] if s["step"] == "편집장 검토 1")
assert conf and conf[0]["new_serious"] and not first["passed"], (conf, first.get("passed"))
assert res["clean"] and "지난 10년" not in res["html"], res["score"]
print("confirm review ok")

# 2026-11-09: 부분 고침이 바로 앞 문장을 되풀이하면 그 고침은 지움(VOO 연달아 시험 사고 재현)
h_dup = ("<p>VOO 배당금은 지급 시 미국 현지에서 15%의 세금이 원천징수된 후 계좌로 입금됩니다. "
         "한국 배당소득세율 14%보다 미국 세율이 높아 추가로 떼는 세금은 없다고 단정하는 문장입니다.</p><p>직접 살 수 없습니다 정말로 그렇습니다.</p>")
nd, n_ok, dr = desk.apply_patches(h_dup, [{"find": "한국 배당소득세율 14%보다 미국 세율이 높아 추가로 떼는 세금은 없다고 단정하는 문장입니다.",
    "replace": "미국 현지에서 15% 세금이 원천징수되며, 배당소득을 포함한 한 해 금융소득이 2,000만 원을 넘으면 금융소득종합과세 대상에 포함됩니다."}],
    facts + "\n- 15% 원천징수\n- 2,000만 원")
assert n_ok == 1 and "단정하는" not in nd and nd.count("원천징수") == 1 and any("옆 문장과 겹쳐" in x for x in dr), (nd, dr)
print("patch neighbor dup ok")
