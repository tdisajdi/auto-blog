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
    return f"<h1>시험 제목</h1><!-- 메타 -->{paras}<h3>섹션1</h3><p>내용</p>\n태그: 가 나 다 라 마"

calls = {"review": 0, "rewrite": 0, "section": 0, "unify": 0}
def post_desk(url, payload, key):
    p = payload["contents"][0]["parts"][0]["text"]
    if "기획 회의" in p:
        return R(200, json.dumps(PLAN))
    if "심각도 기준" in p:
        calls["review"] += 1
        if calls["review"] <= 3 and "독자 편집 담당" in p:
            return R(200, json.dumps({"issues": [{"severity": "중요", "quote": "", "problem": "섹션1이 얇음", "fix": "자료로 보탤 것"}]}))
        if calls["review"] <= 3 and "사실 검증 담당" in p:   # 본문에 없는 문장을 인용 → 버려져야 함
            return R(200, json.dumps({"issues": [{"severity": "치명", "quote": "이런 문장은 본문 어디에도 없습니다 정말로", "problem": "틀림"}]}))
        return R(200, json.dumps({"issues": []}))
    if "지적된 문제만 고치고" in p:
        calls["rewrite"] += 1
        assert "섹션1이 얇음" in p
        return R(200, long_html("고친 "))
    if "글 전체를 한 번에" in p:
        return R(200, long_html())
    raise AssertionError(p[:80])
llm._post = post_desk
log = editlog.EditLog("guide", "single", "시험")
res = desk.write_article(kind_label="기초 가이드", title_seed="시험", facts_text=facts, rules="", category_label="ETF", log=log)
assert res and res["score"] == 1.0 and res["clean"] and calls == {"review": 6, "rewrite": 1, "section": 0, "unify": 0}, (res and res["score"], calls)
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
