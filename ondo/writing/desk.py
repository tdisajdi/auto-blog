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

from ondo.checks import lint, numbers
from ondo.config import kst_now
from ondo.writing import llm

PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_REWRITES = 2
MAX_TODO = 5          # 고쳐쓰기 한 번에 주는 지적 수
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
            "sections": clean, "faq": faq or ["자주 묻는 질문 3개를 자료로 답할 수 있는 것으로 고르세요"]}


DEFAULT_PLAN = {
    "title": "", "key_message": "", "slug": "",
    "intro": {"goal": "독자의 질문과 오늘 다룰 범위를 소개", "facts": []},
    "sections": [
        {"heading": "무슨 일이 있었나", "goal": "자료에 있는 사실을 정리", "facts": [], "table": False, "chars": 1100},
        {"heading": "숫자로 보기", "goal": "자료의 숫자를 표로 정리하고 뜻을 설명", "facts": [], "table": True, "chars": 1100},
        {"heading": "아직 모르는 것", "goal": "확인되지 않은 점과 주의할 점", "facts": [], "table": False, "chars": 1000},
    ],
    "faq": ["자료로 답할 수 있는 질문 3개를 고르세요"],
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
    lines.append("정리: 핵심 메시지를 2~3문단으로 마무리")
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
    units.append(("마무리", "<h3>자주 묻는 질문</h3>(질문은 <h4>🔸 질문</h4>, 답 2~3문장) 질문: "
                            + " / ".join(plan["faq"]) + "\n그다음 <h3>정리</h3> + 300~500자 정리"
                            " (+ 맞는 내부 링크가 있으면 그 문단)\n맨 마지막 줄: 태그: 태그1 태그2 태그3 태그4 태그5",
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
                     step=f"쓰기({name})", log=log, tier="strong", start_key=i)   # 섹션마다 다른 키에서 시작
        if not r.text:
            log.step("쓰기 실패", part=name, reason="모든 모델·키가 한도 초과" if r.limited else "답이 없음")
            return None
        pieces.append(_clean_html(r.text))
    draft = "\n".join(pieces)
    r = llm.call(prompt("unify", draft=draft), step="이음새 다듬기", log=log, tier="strong",
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
    return re.sub(r"[\s\W_]+", "", str(t))


def _quote_found(quote, text_norm):
    """AI가 인용한 문장이 실제 본문에 있는지(앞 15글자 기준). 없는 문장을 지적하면 버린다."""
    q = _norm(quote)
    return not q or q[:15] in text_norm


def review(html, facts_text, category_label, log, round_no, must=None):
    """반환: (점수, 문제 목록[{severity, quote, problem, fix, by}]). 담당 전원이 실패하면 (None, [])."""
    text = lint.text_of(re.sub(r"<!--.*?-->", "", html, flags=re.S))[:60000]
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


def _issue_text(f):
    q = f" '{f['quote'][:60]}'" if f.get("quote") else ""
    return f"[{f['severity']}·{f['by']}]{q} → {f['problem']}" + (f" / 고칠 방법: {f['fix']}" if f.get("fix") else "")


def write_article(*, kind_label, title_seed, facts_text, rules, category_label, log, memo="", recent_posts=None,
                  drawer=None, avoid_visuals=(), must_answer=None):
    """반환: {"html", "plan", "score", "issues", "clean"} 또는 None(실패 - 이유는 log에 있음).
    clean=True는 "검토 통과"(점수 기준 이상 + 치명·중요 문제 없음 + 교열 지적 없음). 아니면 임시글로."""
    log.data["facts"] = facts_text[:30000]     # 글쓰기에 넘긴 자료 원문(빠진 사실이 자료 탓인지 작가 탓인지 가리려고)
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
            log.data["result"]["reason"] = "섹션별 쓰기도 실패(모든 키·모델 한도 초과 또는 오류)"
            return None

    min_q = float(os.environ.get("PUBLISH_MIN_QUALITY", "0.7"))
    best = None
    for round_no in range(1, MAX_REWRITES + 2):
        html, lint_issues, fixes = lint.fix_and_check(html)
        nums = numbers.unverified(lint.text_of(html), facts_text)
        score, found = review(html, facts_text, category_label, log, round_no, must=must_answer)
        serious = [f for f in found if f["severity"] in ("치명", "중요")]
        hard_lint = lint.blocking(lint_issues)
        passed = score is not None and score >= min_q and not serious and not hard_lint
        log.data.setdefault("drafts", {})[str(round_no)] = html      # 판마다 원문 보관(사람이 읽고 평가할 수 있게)
        log.step(f"편집장 검토 {round_no}", score=score, passed=passed,
                 issues=[_issue_text(f) for f in found], lint=lint_issues, numbers=nums, fixes=fixes,
                 chars=len(lint.text_of(html)))
        # 통과한 판 > 교열 지적 없는 판 > 점수 순. (2026-10-31: 1.0점 초안에 N/A·분량 문제가 남았는데 발행됨)
        rank = (passed, not hard_lint, -len(serious), score or 0)
        if best is None or rank > best["_rank"]:
            best = {"html": html, "plan": plan, "score": score, "clean": passed, "_rank": rank, "round": round_no,
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
        r = llm.call(prompt("rewrite", issues="\n".join(f"- {t}" for t in todo), draft=html, **ctx["common"]),
                     step=f"고쳐쓰기 {round_no}", log=log, tier="strong", start_key=round_no * 2)
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
    return best
