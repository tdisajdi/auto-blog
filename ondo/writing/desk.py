"""편집국: 기획 회의 → 쓰기 → 교열(코드) → 편집장 검토 → 고쳐쓰기(최대 2번).

write_article(...)이 글 한 편의 HTML을 만든다. 발행은 하지 않는다(topic_engine.produce_article이 함).

쓰기 방식
- 기본은 "한 번에 쓰기": 좋은 모델 한 번 호출로 글 전체를 쓴다(앞뒤 흐름이 이어지고 반복이 적다).
- 좋은 모델이 한도(429)에 막히거나 답이 길이 한도에서 잘리면 "섹션별 나눠 쓰기"로 자동 전환:
  섹션마다 다른 키로 쓰되, 매번 설계도 전체 + 그 섹션에 배정된 사실 + 앞까지 쓴 글을 같이 준다.
  다 쓰면 한 번 더 불러 이음새를 다듬는다. 전환 이유는 편집 기록부에 남는다.
- 모든 호출의 모델·키 번호·실패 이유는 편집 기록부(ondo/checks/editlog.py)에 남는다.
"""
import os
import random
import re
from pathlib import Path

from ondo.writing import glossary
from ondo.checks import lint, numbers
from ondo.config import kst_now
from ondo.writing import llm

PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_REWRITES = 2
MAX_TODO = 5          # 고쳐쓰기 한 번에 주는 지적 수
# 글을 쓰고 고치는 단계는 좋은 모델만(2026-11-02). 예전엔 좋은 모델이 한도에 걸리면 섹션 쓰기·고쳐쓰기가 조용히
# 약한 모델로 내려갔다. 비공개로 다듬는 지금은 약한 글보다 "오늘은 건너뛰기"가 낫다. ALLOW_WEAK_WRITER=1이면 예전처럼.
WRITE_TIER = "strong" if os.environ.get("ALLOW_WEAK_WRITER") == "1" else "strong_only"
ANGLES = [
    "독자가 가장 먼저 궁금해할 질문 하나에서 출발해, 자료의 사실로 답을 쌓아가는 구성",
    "흔한 오해나 단편적인 반응을 먼저 짚고, 자료로 더 정확한 그림을 보여주는 구성",
]


def prompt(name, **values):
    text = (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v or ""))
    return text


def _today():
    return f"{kst_now():%Y년 %m월 %d일}"


# ------------------------------------------------------------
# 기획 회의
# ------------------------------------------------------------

def _clean_heading(h):
    return re.sub(r"^\s*(part\s*\d+|\d+\s*부|\d+[.)])\s*[:.\-)]?\s*", "", str(h), flags=re.I).strip() or str(h)


def _valid_plan(p):
    if not isinstance(p, dict):
        return None
    secs = p.get("sections")
    if not isinstance(secs, list) or not 3 <= len(secs) <= 5:
        return None
    clean = []
    for s in secs:
        if not isinstance(s, dict) or not s.get("heading") or not s.get("goal"):
            return None
        facts = s.get("facts") if isinstance(s.get("facts"), list) else []
        try:
            chars = max(600, min(1600, int(s.get("chars") or 1000)))
        except (TypeError, ValueError):
            chars = 1000
        clean.append({"heading": _clean_heading(s["heading"]), "goal": str(s["goal"]),
                      "facts": [str(f) for f in facts][:10], "table": bool(s.get("table")), "chars": chars})
    if sum(s["table"] for s in clean) > 1:          # 표는 1개만 - 첫 번째 것만 남긴다
        first = next(i for i, s in enumerate(clean) if s["table"])
        for i, s in enumerate(clean):
            s["table"] = i == first
    intro = p.get("intro") if isinstance(p.get("intro"), dict) else {}
    faq = [str(q) for q in (p.get("faq") or []) if q][:4]
    return {"title": str(p.get("title") or ""), "key_message": str(p.get("key_message") or ""),
            "slug": str(p.get("slug") or ""),
            "intro": {"goal": str(intro.get("goal") or "독자의 질문과 이 글의 범위"),
                      "facts": [str(f) for f in (intro.get("facts") or [])][:6]},
            "sections": clean, "faq": faq or ["자료로 답할 수 있는 질문 2~3개를 고르세요"]}


DEFAULT_PLAN = {
    "title": "", "key_message": "", "slug": "",
    "intro": {"goal": "독자의 질문과 그 답(숫자 한두 개)을 먼저, 이어서 오늘 다룰 범위", "facts": []},
    "sections": [
        {"heading": "무슨 일이 있었나", "goal": "자료에 있는 사실을 정리", "facts": [], "table": False, "chars": 1100},
        {"heading": "숫자로 보기", "goal": "자료의 숫자를 표로 정리하고 뜻을 설명", "facts": [], "table": True, "chars": 1100},
        {"heading": "아직 모르는 것", "goal": "확인되지 않은 점과 주의할 점", "facts": [], "table": False, "chars": 1000},
    ],
    "faq": ["자료로 답할 수 있는 질문 2~3개를 고르세요"],
}


# ------------------------------------------------------------
# 시각 자료 서랍: 코드가 만든 그래프·표 목록에서 기획이 글마다 2~3개를 골라 섹션 뒤에 배치한다(2026-10-31 사용자 결정)
# drawer = [{"id", "name", "desc", "fits"}]  (실제 HTML은 발행 쪽이 가지고 있다)
# ------------------------------------------------------------
MAX_VISUALS = 3


def drawer_text(drawer):
    if not drawer:
        return ""
    return ("[시각 자료 서랍 - 코드가 정확한 숫자로 만든 그래프·표입니다. 이 글의 방향에 꼭 맞는 것만 2~3개 골라,"
            " 어느 섹션 뒤에 둘지 visuals에 적으세요. 서로 비슷한 것을 같이 고르지 마세요]\n"
            + "\n".join(f"- {d['id']}: {d['name']} - {d['desc']} (어울리는 글: {d['fits']})" for d in drawer) + "\n")


def choose_visuals(raw, drawer, n_sections, avoid=()):
    """기획이 고른 시각 자료를 검사한다: 서랍에 있는 것만, 최대 3개, 중복 없이, 섹션 번호는 1~n.
    고른 게 없으면 서랍 앞쪽 2개. 최근 글과 똑같은 조합이면 하나를 다른 것으로 바꾼다(매번 같은 구성 방지)."""
    ids = [d["id"] for d in drawer or []]
    picks, used = [], set()
    for v in raw if isinstance(raw, list) else []:
        if not isinstance(v, dict) or v.get("id") not in ids or v["id"] in used:
            continue
        try:
            after = max(1, min(n_sections, int(v.get("after_section") or 1)))
        except (TypeError, ValueError):
            after = 1
        picks.append({"id": v["id"], "after_section": after})
        used.add(v["id"])
        if len(picks) >= MAX_VISUALS:
            break
    if not picks and ids:
        picks = [{"id": i, "after_section": min(n_sections, k + 1)} for k, i in enumerate(ids[:2])]
    combo = frozenset(p["id"] for p in picks)
    if picks and combo in {frozenset(a) for a in avoid}:
        spare = [i for i in ids if i not in combo]
        if spare:
            picks[-1] = {"id": spare[0], "after_section": picks[-1]["after_section"]}
    return picks


def _must_plan(must):
    if not must:
        return ""
    return ("[이 글이 꼭 답해야 할 질문 - 섹션에 나눠 담으세요(순서·제목·관점은 자유)]\n"
            + "\n".join(f"- {q}" for q in must) + "\n")


def _must_review(must):
    if not must:
        return ""
    return ("- 아래 질문 중 본문이 답하지 않은 것이 있으면 '중요'로 지적하세요(quote는 빈 문자열, problem에 '[누락] 질문'):\n"
            + "\n".join(f"  · {q}" for q in must) + "\n")


def make_plan(kind_label, title_seed, facts_text, memo, log, drawer=None, avoid=(), must=None):
    angles = random.sample(ANGLES, len(ANGLES))
    for attempt, angle in enumerate(angles):
        r = llm.call(prompt("plan", kind_label=kind_label, title_seed=title_seed, today=_today(), angle=angle,
                            facts=facts_text, memo=f"[운영자 메모 - 이 관점을 반영하세요] {memo}" if memo else "",
                            drawer=drawer_text(drawer), must=_must_plan(must)),
                     step="기획", log=log, tier="fast", json_out=True, thinking=8192, start_key=attempt * 3)
        raw = llm.parse_json(r.text)
        plan = _valid_plan(raw)
        if plan:
            plan["visuals"] = choose_visuals(raw.get("visuals"), drawer, len(plan["sections"]), avoid) if drawer else []
            log.step("기획", title=plan["title"], sections=[s["heading"] for s in plan["sections"]],
                     visuals=[f"{v['id']}→섹션{v['after_section']}" for v in plan["visuals"]],
                     model=r.model, angle=angle[:30])
            return plan
        log.step("기획 실패", attempt=attempt + 1,
                 reason="답이 없음(한도·오류)" if r.text is None else "설계도 형식이 맞지 않음")
    plan = dict(DEFAULT_PLAN)
    plan["visuals"] = choose_visuals([], drawer, len(plan["sections"]), avoid) if drawer else []
    log.step("기획", sections=[s["heading"] for s in plan["sections"]], reason="기본 설계도 사용")
    return plan


def plan_text(plan):
    lines = []
    if plan.get("title"):
        lines.append(f"제목(안): {plan['title']}")
    if plan.get("key_message"):
        lines.append(f"핵심 메시지: {plan['key_message']}")
    lines.append(f"도입: {plan['intro']['goal']}" + "".join(f"\n   - {f}" for f in plan["intro"]["facts"]))
    names = {d["id"]: d for d in plan.get("_drawer") or []}
    for i, s in enumerate(plan["sections"], 1):
        lines.append(f"섹션 {i}. <h3>{s['heading']}</h3> (약 {s['chars']}자{', 표 1개 포함' if s['table'] else ', 표 없음'})"
                     f" - {s['goal']}" + "".join(f"\n   - 배정된 사실: {f}" for f in s["facts"]))
        for v in plan.get("visuals") or []:
            if v["after_section"] == i and v["id"] in names:
                d = names[v["id"]]
                lines.append(f"   ↳ 이 섹션 끝에 [{d['name']}]이(가) 들어갑니다(시스템이 넣음): {d['desc']}. "
                             "섹션 마지막 문단에서 이 자료를 어떻게 읽으면 되는지 한두 문장으로 이어주세요. 표로 다시 만들지 마세요.")
    lines.append("자주 묻는 질문: " + " / ".join(plan["faq"]))
    lines.append("정리: 핵심 메시지를 2~3문단으로 마무리 + 마지막 문단 '<p><strong>한 줄 정리:</strong> …</p>' 한 문장")
    return "\n".join(lines)


# ------------------------------------------------------------
# 쓰기
# ------------------------------------------------------------

def _clean_html(text):
    t = re.sub(r"```[a-zA-Z]*\n?|```", "", text or "").strip()
    i = t.find("<")
    return t[i:] if i > 0 else t


def _write_single(ctx, log):
    r = llm.call(prompt("write", plan=plan_text(ctx["plan"]), **ctx["common"]),
                 step="쓰기(한 번에)", log=log, tier="strong_only")
    return r


def _section_units(plan):
    units = [("도입", "도입: 맨 위에 <h1>제목</h1>, 다음 줄에 <!-- 120~160자 메타 설명 -->, 그다음 도입 문단"
                      f"(400~600자, 대제목 없이). 다룰 것: {plan['intro']['goal']}",
              "<h1>로 시작하세요.")]
    for i, s in enumerate(plan["sections"], 1):
        units.append((f"섹션 {i}", f"섹션 {i}. <h3>{s['heading']}</h3> - {s['goal']} (약 {s['chars']}자"
                                   f"{', 표 1개 포함' if s['table'] else ', 표 만들지 말 것'})\n배정된 사실:\n"
                                   + "\n".join(f"- {f}" for f in s["facts"]),
                      f"<h3>{s['heading']}</h3>로 시작하세요."))
    units.append(("마무리", "<h3>자주 묻는 질문</h3>(질문은 <h4>🔸 질문</h4>, 답 2~3문장, 본문 숫자 다시 나열 금지 - "
                            "용어 뜻·자주 하는 오해·자료의 한계처럼 본문에서 안 다룬 것) 질문: "
                            + " / ".join(plan["faq"]) + "\n그다음 <h3>정리</h3> + 300~500자 정리 + 마지막 문단 <p><strong>한 줄 정리:</strong> 글 전체의 핵심 한 문장</p>"
                            " (+ 맞는 내부 링크가 있으면 그 뒤 문단)\n맨 마지막 줄: 태그: 태그1 태그2 태그3 태그4 태그5",
                  "<h3>자주 묻는 질문</h3>으로 시작하고 '태그:' 줄로 끝내세요."))
    return units


def _write_sections(ctx, log):
    pieces = []
    for i, (name, target, fmt) in enumerate(_section_units(ctx["plan"])):
        common = dict(ctx["common"])
        if name != "마무리":
            common["link_rule"] = ""
        r = llm.call(prompt("section", plan=plan_text(ctx["plan"]), previous="\n".join(pieces) or "(아직 없음 - 첫 부분입니다)",
                            target=target, target_format=fmt, **common),
                     step=f"쓰기({name})", log=log, tier=WRITE_TIER, start_key=i)   # 섹션마다 다른 키에서 시작
        if not r.text:
            log.step("쓰기 실패", part=name, reason="좋은 모델이 모든 키에서 한도 초과" if r.limited else "답이 없음")
            return None
        pieces.append(_clean_html(r.text))
    draft = "\n".join(pieces)
    r = llm.call(prompt("unify", draft=draft), step="이음새 다듬기", log=log, tier=WRITE_TIER,
                 start_key=len(pieces))
    unified = _clean_html(r.text) if r.text else ""
    if unified and len(lint.text_of(unified)) >= 0.85 * len(lint.text_of(draft)):
        return unified
    log.step("이음새 다듬기 건너뜀", reason="답이 없음" if not unified else "다듬은 글이 너무 짧아져서 원래 글 사용")
    return draft


# ------------------------------------------------------------
# 검토와 고쳐쓰기
# ------------------------------------------------------------

# 검토 담당 3명: 같은 질문을 3번 하는 대신 보는 것이 다른 사람을 둔다(서로 다른 문제를 찾게).
# 점수는 AI가 매기지 않고, 문제의 심각도 개수로 코드가 계산한다(AI 점수가 너무 후했다 - 2026-10-31).
REVIEWERS = [
    ("사실 검증", "review_fact", "strong"),
    ("독자 편집", "review_reader", "fast"),
    ("정책·신뢰", "review_policy", "fast"),
]
SEVERITY_WEIGHT = {"치명": 0.35, "중요": 0.12, "사소": 0.03}
POLICY_WORDS = re.compile(r"권유|보장|확정|단정|과장|전문가|경험|출처|매수|매도|의료|치료")


def _norm(t):
    # [링크] 표시는 비교에서 뺀다(검토 담당이 인용할 때 빼든 넣든 같은 문장으로 보게)
    return re.sub(r"[\s\W_]+", "", str(t).replace("[링크]", ""))


def _quote_found(quote, text_norm):
    """AI가 인용한 문장이 실제 본문에 있는지(앞 15글자 기준). 없는 문장을 지적하면 버린다."""
    q = _norm(quote)
    return not q or q[:15] in text_norm


# 정리 섹션 반복 판정(11-08 개정): 섹션을 가리키는 말만('정리된·정리하여' 같은 동사는 아님), 부정문·도입부 언급은 제외.
# 지난 기록의 독자 편집 '중요' 지적에 돌려 확인 - 옛 판정은 "표에 이미 정리된 수치를…"(진짜 반복)과 "'정리' 섹션과 중복되지는
# 않으나…"까지 낮추고, 정작 "'정리' 섹션의 구체적 금액(…) 사이에 중복"(총보수 글, 40자 넘게 떨어짐)은 못 잡았다.
_SUMMARY_SEC = r"(?:['‘\"]?정리['’\"]?\s*(?:섹션|부분|문단|단락)|결론(?:부|에서|에|과|부분)|마무리)"
# 11-10: '[^.]'가 '7.5% 하락'의 소수점에서 끊겨 숫자가 든 지적을 못 잡음(환율 고정 시험) → 숫자 사이 점은 건너뜀
_NODOT = r"(?:[^.]|\.(?=\d))"
_SUMMARY_REPEAT = re.compile(rf"{_SUMMARY_SEC}{_NODOT}{{0,90}}(?:반복|되풀이|중복)|(?:반복|되풀이|중복){_NODOT}{{0,90}}{_SUMMARY_SEC}")
_SUMMARY_NOT = re.compile(r"제외|밖의|밖에서|중복되지는? 않|반복되지는? 않|아니라|서론|도입|서두|첫 문단")


_INTRO_REPEAT = re.compile(rf"(?:도입|서두|첫 문단){_NODOT}{{0,90}}(?:반복|되풀이|중복)|(?:반복|되풀이|중복){_NODOT}{{0,90}}(?:도입|서두|첫 문단)")


def _summary_repeat(problem):
    """독자 편집의 '중요' 되풀이 지적 가운데 필수 요소를 겨냥한 것(→ '사소'로 낮춤):
    정리 섹션 반복(11-07 규칙) + 11-09 밤부터 도입부 첫 문단의 답 숫자가 본문에서 다시 나오는 것(답은 도입부에서 먼저 - 독자 30초 기준)."""
    p = str(problem)
    return (bool(_SUMMARY_REPEAT.search(p)) and not _SUMMARY_NOT.search(p)) or bool(_INTRO_REPEAT.search(p))


def review_text(html):
    """검토 담당에게 보여 줄 글자. 링크가 걸린 말 뒤에 [링크]를 붙인다(2026-11-07: 태그를 빼고 보여 줬더니 링크가 있는데도
    '매체명에 링크 없음'을 매번 '중요'로 지적 - VOO 글이 이 잘못된 지적으로 세 번 떨어짐)."""
    h = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    h = re.sub(r"<a\b[^>]*\bhref=[^>]*>(.*?)</a>", r"\1[링크]", h, flags=re.S | re.I)
    return lint.text_of(h)[:60000]


def review(html, facts_text, category_label, log, round_no, must=None):
    """반환: (점수, 문제 목록[{severity, quote, problem, fix, by}]). 담당 전원이 실패하면 (None, [])."""
    text = review_text(html)
    text_norm = _norm(text)
    common = prompt("review_common", today=_today(), text=text)
    found, answered, dropped = [], 0, 0
    for i, (role, name, tier) in enumerate(REVIEWERS):
        r = llm.call(prompt(name, category_label=category_label, facts=facts_text, must=_must_review(must)) + common,
                     step=f"검토 {round_no}({role})", log=log, tier=tier, json_out=True, thinking=8192,
                     start_key=4 + round_no * 3 + i)
        data = llm.parse_json(r.text)
        if not isinstance(data, dict):
            continue
        answered += 1
        for it in data.get("issues") or []:
            if not isinstance(it, dict) or not it.get("problem"):
                continue
            sev = it.get("severity") if it.get("severity") in SEVERITY_WEIGHT else "사소"
            # 사실 판단은 사실 검증 담당만(자료를 보고 대조함). 2026-10-31: 정책 담당(약한 모델)이 자료와 반대로
            # "손익 통산이 된다"고 치명 지적 → 고쳐쓰기가 따라서 맞던 글이 틀려졌다.
            if role != "사실 검증" and sev == "치명" and not POLICY_WORDS.search(str(it.get("problem", ""))):
                sev = "사소"
            # 11-07에 정한 규칙(정리 섹션의 숫자 재언급은 최대 '사소')을 빠른 모델이 무시하고 '중요'로 지적함(11-08 환율 글) → 코드가 지킴.
            # 정리 밖 본문끼리의 반복은 그대로 '중요'.
            if role == "독자 편집" and sev == "중요" and _summary_repeat(it.get("problem", "")):
                sev = "사소"
            if not _quote_found(it.get("quote", ""), text_norm):
                dropped += 1
                continue
            found.append({"severity": sev, "quote": str(it.get("quote", ""))[:120], "problem": str(it["problem"])[:200],
                          "fix": str(it.get("fix", ""))[:200], "by": role})
    if not answered:
        return None, []
    score = max(0.0, 1.0 - sum(SEVERITY_WEIGHT[f["severity"]] for f in found))
    if dropped:
        log.step(f"검토 {round_no} 정리", dropped=dropped, reason="본문에 없는 문장을 인용한 지적은 버림")
    if answered < len(REVIEWERS):
        log.step(f"검토 {round_no} 일부 실패", answered=answered, total=len(REVIEWERS))
    return round(score, 2), found


# 독자 가치 담당(2026-10-31 추가): 감점 점수는 "문제가 적은가"만 본다. "독자에게 쓸모 있는가"는 따로 본다.
# 느낌 점수 대신 질문 5개 예/아니오 + 근거 인용(본문에 없으면 아니오). 처음에는 참고용(발행 조건 아님) -
# 실제 글로 기준이 너무 후하거나 짠지 맞춰본 뒤 통과 조건에 넣는다. VALUE_BLOCKING으로 켤 수 있다.
VALUE_KEYS = [("answers_title", "제목 질문에 답함"), ("unique_info", "이 글만의 정보"),
              ("decision_rule", "판단 기준 제시"), ("plain_words", "용어 풀이"), ("numbers_explained", "숫자 해석")]
VALUE_MIN = 0.6


def value_review(html, title, category_label, log, round_no, facts_text=""):
    """반환: (가치 점수 0~1 또는 None, {key: bool}, 개선 한 가지).
    참고용이라 고쳐쓰기에는 넘기지 않는다(2026-11-03: 자료를 모르는 담당이 "청약·주거 정책을 넣으라"고 제안 →
    고쳐쓰기가 자료에 없는 내용을 지어냄). 자료도 같이 보여줘서, 개선 제안은 자료 안에서만 하게 한다."""
    text = lint.text_of(re.sub(r"<!--.*?-->", "", html, flags=re.S))[:60000]
    r = llm.call(prompt("review_value", category_label=category_label, title=title, text=text, facts=facts_text),
                 step=f"검토 {round_no}(독자 가치)", log=log, tier="fast", json_out=True, thinking=8192,
                 start_key=2 + round_no * 3)
    data = llm.parse_json(r.text)
    if not isinstance(data, dict):
        return None, {}, ""
    norm = _norm(text)
    marks = {}
    for key, _name in VALUE_KEYS:
        it = data.get(key) if isinstance(data.get(key), dict) else {}
        q = it.get("quote", "")
        marks[key] = bool(it.get("yes")) and bool(_norm(q)) and _quote_found(q, norm)
    return round(sum(marks.values()) / len(VALUE_KEYS), 2), marks, str(data.get("best_improvement") or "")[:200]


def _issue_text(f):
    q = f" '{f['quote'][:60]}'" if f.get("quote") else ""
    return f"[{f['severity']}·{f['by']}]{q} → {f['problem']}" + (f" / 고칠 방법: {f['fix']}" if f.get("fix") else "")


# 모든 글이 꼭 답할 질문(2026-11-05): 시험한 글 13편 중 독자 가치 검토에서 '제목 질문에 답함'이 12번, '판단 기준 제시'가
# 9번 빠졌다. 종목 분석 글처럼 기획이 이 질문을 섹션에 담고, 검토가 빠졌는지 확인하게 한다.
COMMON_MUST = [
    # 11-09: '정리에서 한 번만 - 도입부엔 쓰지 말 것'이었는데, 검색해 들어온 독자는 30초 안에 답을 찾아야 한다(점검표 하②) - 이 규칙 때문에
    # 환율·에너지 글이 '도입부에 답을 미리 씀'으로 떨어졌다 → 답은 도입부에서 먼저, 정리에서는 같은 문장을 되풀이하지 않기로
    # 11-10: 뒤에 붙였던 '정리에서 같은 숫자로 되풀이하지 말 것'이 사실 검증에게도 넘어가(must는 기획·검토가 봄), 1판엔 '기준에 숫자 넣어라',
    # 3판엔 '기준의 숫자가 도입 답 되풀이'로 정반대 '중요'를 냄(환율 고정 시험). 되풀이는 작가 규칙(rules 23줄)·독자 편집이 보므로 여기선 뺌.
    "제목이 던진 질문(또는 약속)에 대한 답을, 자료의 숫자를 넣어 도입부 첫 문단에서 한두 문장으로 먼저 말하기(검색해 들어온 독자가 바로 답을 보게)",
    "독자가 같은 종류의 숫자·뉴스를 다시 볼 때 스스로 확인할 기준 2~3개를 자료의 숫자와 함께 제시하기(매수·매도 권유가 아닌 '무엇을 보면 되는지')",
]


_TYPO_FIX = re.compile(r"['‘“\"]([^'’”\"]{1,15})['’”\"]\s*[을를]\s*['‘“\"]([^'’”\"]{1,15})['’”\"]\s*(?:으)?로")


def apply_typo_fixes(html, found, log=None, severities=("사소",)):
    """검토가 "'지시장을'을 '시장을'로"처럼 짧은 단어 바꾸기를 콕 집어 준 지적은 코드가 바로 고친다(2026-11-05).
    AI를 다시 부르지 않고, 본문에 정확히 한 번 나오는 짧은 말만 바꾼다. 반환: (고친 html, 고친 지적 목록)
    2026-11-06: '20세 이상'→'20년 이상' 같은 오타가 '치명'으로 지적돼 1.0점짜리 글이 떨어짐 → 검토 직후에는 모든 심각도에 적용."""
    done, fixed = [], []
    for f in found or []:
        if f.get("severity") not in severities:
            continue
        m = _TYPO_FIX.search(f.get("fix") or "")
        if not m:
            continue
        old, new = m.group(1), m.group(2)
        if old == new or html.count(old) != 1 or "<" in old + new or ">" in old + new:
            continue
        html = html.replace(old, new, 1)
        done.append(f"{old}→{new}")
        fixed.append(f)
    if done and log:
        log.step("오타 자동 고침", fixes=done)
    return html, fixed


# 부분 고침(2026-11-09): 지난 기록에서 '치명·중요' 지적의 77%가 고칠 문장을 콕 집었는데, 그때도 글 전체를 다시 써서
# 고쳐쓰기 90번 중 29번은 점수가 떨어졌다(멀쩡한 곳에 '최근 10년'·'약 3년' 같은 사실을 새로 지어냄).
# → 지적이 모두 본문 문장을 가리키면 그 문장만 고쳐 받아 코드가 바꿔 넣는다. 빠진 내용·교열 막힘이 있으면 예전처럼 전체 고쳐쓰기.
MAX_PATCH = 6


def patchable(found, hard_lint, nums, html):
    serious = [f for f in found if f["severity"] in ("치명", "중요")]
    if not serious or hard_lint or nums:
        return False
    text_norm = _norm(review_text(html))
    return all(f.get("quote") and len(_norm(f["quote"])) >= 8 and _quote_found(f["quote"], text_norm)
               and not str(f.get("problem", "")).lstrip().startswith("[누락]") for f in serious)


def _sentence_pattern(sentence):
    """본문 글자 사이에 인라인 태그(<strong>, <a …>)·공백 차이가 있어도 찾게 한다."""
    chars = [c for c in lint.text_of(sentence).strip() if not c.isspace()]
    return re.compile(r"(?:<[^>]+>|\s)*".join(re.escape(c) for c in chars)) if len(chars) >= 8 else None


_NUM = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?\s*(?:%p|%|만|억|조|원|달러|배)?")


def _restates_section(html, m, new):
    """고친 문장(new)의 숫자가 2개 이상이고, 모두 같은 섹션의 나머지 글에 이미 있으면 True(되풀이)."""
    nums = {re.sub(r"[\s,+]", "", x) for x in _NUM.findall(lint.text_of(new)) if re.search(r"\d", x)}
    nums = {x for x in nums if not re.fullmatch(r"(19|20)\d\d", x)}       # 연도는 빼고 센다
    # 11-10 VOO 5: '1년'의 1까지 숫자로 세어 숫자 1개짜리 고침을 2개로 봄 → 단위·소수점·쉼표 없는 한 자리~두 자리 맨 숫자는 뺌
    nums = {x for x in nums if not re.fullmatch(r"\d{1,2}", x)}
    if len(nums) < 2:
        return False
    starts = [h.start() for h in re.finditer(r"<h[1-4]\b", html, flags=re.I)]
    a = max([x for x in starts if x <= m.start()], default=0)
    b = min([x for x in starts if x >= m.end()], default=len(html))
    rest = lint.text_of(html[a:m.start()] + " " + html[m.end():b])
    have = {re.sub(r"[\s,+]", "", x) for x in _NUM.findall(rest)}
    return nums <= have


def apply_patches(html, edits, facts_text, log=None):
    """edits: [{find, replace}]. 본문에 정확히 한 번 나오는 문장만, 새 확인 안 된 숫자를 들이지 않는 것만 바꾼다.
    반환: (고친 html, 적용 수, 버린 이유 목록)"""
    applied, dropped = 0, []
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        find, new = str(e.get("find") or "").strip(), str(e.get("replace") or "").strip()
        pat = _sentence_pattern(find)
        if not pat:
            dropped.append("찾을 문장이 너무 짧음")
            continue
        hits = list(pat.finditer(html))
        if len(hits) != 1:
            dropped.append(f"본문에서 {'못 찾음' if not hits else '여러 번 나옴'}: {find[:30]}")
            continue
        old_nums = set(numbers.unverified(find, facts_text, limit=20))
        added = [n for n in numbers.unverified(new, facts_text, limit=20) if n not in old_nums]
        if added:
            dropped.append(f"자료에 없는 숫자를 새로 넣음({', '.join(added)}): {find[:30]}")
            continue
        if len(new) > 2 * len(lint.text_of(find)) + 80 or "<h" in new.lower():
            dropped.append(f"고친 문장이 너무 길거나 소제목을 넣음: {find[:30]}")
            continue
        m = hits[0]
        # 소제목(<h1>~<h4>) 안의 글은 고치지 않는다(2026-11-09 VOO: FAQ 질문 소제목을 지워 '질문 없이 답만' 지적)
        before = html[:m.start()]
        if re.search(r"<h[1-4][^>]*>(?:(?!</h[1-4]>).)*$", before, flags=re.S | re.I):
            dropped.append(f"소제목은 고치지 않음: {find[:30]}")
            continue
        # 고친 문장이 바로 앞뒤 문장과 거의 같으면 이미 있는 내용 → 지운다(2026-11-09 VOO 연달아 시험: 고친 문장이 앞 문장
        # '미국에서 15% 원천징수'를 되풀이해 다음 판에서 '중요' 반복 지적)
        if new:
            near = lint._sentences(lint.text_of(html[max(0, m.start() - 400):m.start()]))[-2:] + \
                lint._sentences(lint.text_of(html[m.end():m.end() + 400]))[:2]
            gn = lint._grams(new)
            # 옆 문장 내용이 고친 문장 안에 얼마나 들어 있나(포함 비율). 실제 사례 0.39, 상관없는 문장 0.09~0.14 → 0.35
            if any(gn and len(gn & lint._grams(x)) / len(lint._grams(x)) >= 0.35 for x in near if lint._grams(x)):
                dropped.append(f"고친 문장이 바로 옆 문장과 겹쳐 지움: {new[:30]}")
                new = ""
            # 11-10 배당성장 가이드: 고친 문장 '5년 연평균 +9.1%인 SCHD는 매입가 대비 4.97%'가 세 문장 앞의 두 숫자를 되풀이 →
            # 다음 판 독자 편집 '중요'. 고친 문장의 숫자가 모두 같은 섹션(앞뒤 소제목 사이)의 다른 곳에 이미 있으면 되풀이로 보고 지운다.
            elif _restates_section(html, m, new):
                dropped.append(f"고친 문장의 숫자가 같은 섹션에 이미 모두 있어 지움: {new[:30]}")
                new = ""
        html = html[:m.start()] + new + html[m.end():]
        applied += 1
    html = re.sub(r"<p>\s*</p>", "", html)
    if log:
        log.step("부분 고침", applied=applied, dropped=dropped[:6])
    return html, applied, dropped


def write_article(*, kind_label, title_seed, facts_text, rules, category_label, log, memo="", recent_posts=None,
                  drawer=None, avoid_visuals=(), must_answer=None, visual_texts=()):
    """반환: {"html", "plan", "score", "issues", "clean"} 또는 None(실패 - 이유는 log에 있음).
    clean=True는 "검토 통과"(점수 기준 이상 + 치명·중요 문제 없음 + 교열 지적 없음). 아니면 임시글로."""
    # 자료에 나오는 어려운 말의 뜻(코드가 정한 그대로)을 자료 끝에 붙인다 - 작가·사실 검증 모두 같은 뜻을 본다(2026-11-06)
    gl = glossary.block(facts_text)
    if gl and "[용어 풀이" not in facts_text:
        facts_text = facts_text + "\n" + gl
    log.data["facts"] = facts_text[:30000]     # 글쓰기에 넘긴 자료 원문(빠진 사실이 자료 탓인지 작가 탓인지 가리려고)
    must_answer = list(must_answer or []) + [q for q in COMMON_MUST if q not in (must_answer or [])]
    plan = make_plan(kind_label, title_seed, facts_text, memo, log, drawer=drawer, avoid=avoid_visuals, must=must_answer)
    plan["_drawer"] = drawer or []
    posts = recent_posts or []
    link_rule = ("[내부 링크] 아래 글 중 이 글과 주제가 직접 이어지는 것이 있을 때만 1개를 골라, 정리 문단 끝에 "
                 "별도 문장으로 `<p>👉 함께 보면 좋은 글: <a href=\"주소\">제목</a></p>` 형식으로 넣으세요. "
                 "문장 중간에 다른 글 제목을 끼워 넣지 마세요. 맞는 글이 없으면 생략하세요.\n"
                 + "\n".join(f"- {p['title']} ({p.get('link', '')})" for p in posts[:15])) if posts else ""
    ctx = {"plan": plan, "common": {
        "kind_label": kind_label, "title_seed": title_seed, "today": _today(),
        "rules": prompt("rules"), "category_rules": rules, "facts": facts_text, "link_rule": link_rule}}

    r = _write_single(ctx, log)
    html = _clean_html(r.text) if r.text else ""
    if html and len(lint.text_of(html)) >= 1500:
        log.set_mode("single", f"모델 {r.model}")
    else:
        why = ("좋은 모델이 모든 키에서 한도 초과(429)" if r.limited else
               "답이 길이 한도에서 잘림" if r.truncated else
               "답이 너무 짧음" if html else "답이 없음")
        log.set_mode("sections", f"한 번에 쓰기 실패: {why}")
        html = _write_sections(ctx, log)
        if not html:
            fail = next((st for st in reversed(log.data["steps"]) if st["step"] == "쓰기 실패"), {})
            limited = "한도" in str(fail.get("reason", "")) or r.limited
            log.data["result"]["reason"] = ("좋은 모델(글쓰기용)이 모든 키에서 오늘 한도를 다 씀 - 한국 시간 오후 5시쯤(서머타임 기간 4시) "
                                            "한도가 풀린 뒤 다시 시도해 주세요" if limited
                                            else f"섹션별 쓰기 실패({fail.get('part', '?')}: {fail.get('reason', '답이 없음')})")
            return None

    min_q = float(os.environ.get("PUBLISH_MIN_QUALITY", "0.7"))
    best = None
    for round_no in range(1, MAX_REWRITES + 2):
        dropped_table = "[표 금지]" in (rules or "") and "<table" in html
        if dropped_table:
            html = re.sub(r"<table.*?</table>", "", html, flags=re.S | re.I)
        html, lint_issues, fixes = lint.fix_and_check(html)
        html = lint.link_sources(html, facts_text, fixes)
        if dropped_table:
            fixes.append("계산표가 들어가는 글이라 작가가 만든 표 삭제")
        picked = {v["id"] for v in plan.get("visuals") or []}
        # 코드가 넣는 시각 자료(서랍에서 고른 것 + 가이드·이슈의 계산표)를 베낀 표는 지운다(2026-11-03 환율 글: 계산표를 손으로
        # 다시 만들었고, 고쳐쓰기가 반복을 지우면서 표 대신 숫자 해석 문장을 지워 제목 질문에 답을 못 하게 됨)
        html = lint.drop_copied_tables(html, [d.get("text", "") for d in drawer or [] if d["id"] in picked]
                                       + list(visual_texts or ()), fixes)
        nums = numbers.unverified(lint.text_of(html), facts_text)
        score, found = review(html, facts_text, category_label, log, round_no, must=must_answer)
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S)
        value, marks, improve = value_review(html, lint.text_of(title_m.group(1)) if title_m else title_seed,
                                             category_label, log, round_no, facts_text)
        # 콕 집어 준 짧은 단어 바꾸기는 바로 고치고 그 감점은 돌려준다(고쳐쓰기 한 번을 아낌)
        html, fixed = apply_typo_fixes(html, found, log, severities=("치명", "중요", "사소"))
        if fixed:
            found = [f for f in found if f not in fixed]
            if score is not None:
                score = round(max(0.0, 1.0 - sum(SEVERITY_WEIGHT[f["severity"]] for f in found)), 2)
        serious = [f for f in found if f["severity"] in ("치명", "중요")]
        hard_lint = lint.blocking(lint_issues)
        passed = score is not None and score >= min_q and not serious and not hard_lint
        if os.environ.get("VALUE_BLOCKING") == "1" and value is not None and value < VALUE_MIN:
            passed = False
        # 통과 직전 확인 채점(2026-11-09): 같은 글을 3번 채점해 보니 치명·중요 지적 7개 중 4개가 매번 나오지 않았다(lab_bench noise).
        # 한 번 채점으로 '운 좋게 통과'하는 글을 막으려고, 통과로 나온 판만 한 번 더 채점해 새 치명·중요가 나오면 통과를 취소한다.
        # 비교한 방법: 매번 두 번 채점해 합치기(비용 2배·괜한 지적도 늘어남) / 좋은 모델로(사실 검증은 이미 좋은 모델) → 통과 판만 확인.
        if passed and os.environ.get("CONFIRM_REVIEW", "1") != "0":
            score2, found2 = review(html, facts_text, category_label, log, round_no + 10, must=must_answer)
            if score2 is not None:
                known = {_norm(f.get("quote") or f.get("problem", ""))[:15] for f in found}
                extra = [f for f in found2 if f["severity"] in ("치명", "중요")
                         and _norm(f.get("quote") or f.get("problem", ""))[:15] not in known]
                log.step("통과 확인 검토", score=score2, new_serious=[_issue_text(f) for f in extra])
                if extra:
                    found = found + extra
                    serious = serious + extra
                    score = round(max(0.0, 1.0 - sum(SEVERITY_WEIGHT[f["severity"]] for f in found)), 2)
                    passed = False
        log.data.setdefault("drafts", {})[str(round_no)] = html      # 판마다 원문 보관(사람이 읽고 평가할 수 있게)
        missing = [name for key, name in VALUE_KEYS if marks and not marks.get(key)]
        log.step(f"편집장 검토 {round_no}", score=score, passed=passed, value=value, value_missing=missing,
                 value_tip=improve, issues=[_issue_text(f) for f in found], lint=lint_issues, numbers=nums,
                 fixes=fixes, chars=len(lint.text_of(html)))
        # 통과한 판 > 교열 지적 없는 판 > 치명(지어낸 사실) 없는 판 > 점수 순. (2026-10-31: 1.0점 초안에 N/A·분량 문제가 남았는데 발행됨)
        # 2026-11-09: 지적 '개수'를 점수보다 앞에 두었더니 중요 1개(0.88점) 판 대신 치명 1개(0.38점) 판을 남겼다(?p=308)
        rank = (passed, not hard_lint, -sum(f["severity"] == "치명" for f in found), score or 0, -len(serious), value or 0)
        if best is None or rank > best["_rank"]:
            best = {"html": html, "plan": plan, "score": score, "clean": passed, "_rank": rank, "round": round_no,
                    "value": value, "value_missing": missing, "_found": found,
                    "issues": [_issue_text(f) for f in serious] + lint_issues
                              + [_issue_text(f) for f in found if f not in serious]}
        if passed or round_no > MAX_REWRITES:
            break
        order = {"치명": 0, "중요": 1, "사소": 2}
        # 한 번에 가장 중요한 5개만(2026-10-31: 8개를 한꺼번에 줬더니 엉뚱한 곳까지 건드리고 숫자가 빠졌다)
        ranked = sorted(found, key=lambda f: order[f["severity"]])
        todo = ([_issue_text(f) for f in ranked if f["severity"] != "사소"] + hard_lint
                + (["자료에서 확인되지 않는 숫자: " + ", ".join(nums) + " → 자료에 있는 값으로 바꾸거나 빼세요. "
                    "자료의 두 숫자로 계산한 값이면 무엇으로 계산했는지 문장에 밝히세요."] if nums else [])
                + [_issue_text(f) for f in ranked if f["severity"] == "사소"]
                + [i for i in lint_issues if i not in hard_lint])[:MAX_TODO]
        if not todo:
            break                                     # 고칠 방향이 없다(검토 실패 등)
        if os.environ.get("PATCH_MODE", "1") != "0" and patchable(found, hard_lint, nums, html):
            items = [_issue_text(f) for f in ranked if f.get("quote")][:MAX_PATCH]
            r = llm.call(prompt("patch", issues="\n".join(f"- {t}" for t in items), draft=html, max_edits=MAX_PATCH,
                                **ctx["common"]),
                         step=f"부분 고침 {round_no}", log=log, tier=WRITE_TIER, json_out=True, start_key=round_no * 2)
            data = llm.parse_json(r.text) if r.text else None
            edits = data.get("edits") if isinstance(data, dict) else data if isinstance(data, list) else None
            patched, n_ok, _dropped = apply_patches(html, edits, facts_text, log)
            if n_ok:
                html = patched
                continue                              # 고친 문장만 바뀐 글로 다음 판 검토
            # 하나도 못 바꿨으면 아래 전체 고쳐쓰기로
        r = llm.call(prompt("rewrite", issues="\n".join(f"- {t}" for t in todo), draft=html, **ctx["common"]),
                     step=f"고쳐쓰기 {round_no}", log=log, tier=WRITE_TIER, start_key=round_no * 2)
        new = _clean_html(r.text) if r.text else ""
        if not new:
            log.step(f"고쳐쓰기 {round_no} 실패", reason="모든 키·모델 한도 초과" if r.limited else "답이 없음")
            break
        # 반복을 지우면 짧아지는 게 정상이라, 절반 넘게 사라졌을 때만 이상한 답으로 본다
        if len(lint.text_of(new)) < 0.5 * len(lint.text_of(html)):
            log.step(f"고쳐쓰기 {round_no} 버림", reason="고친 글이 원래의 절반도 안 됨")
            break
        log.step(f"고쳐쓰기 {round_no}", model=r.model, todo=len(todo))
        html = new
    if best:
        best["html"] = apply_typo_fixes(best["html"], best.pop("_found", []), log)[0]
    return best
