"""측정 도구(2026-11-08): 글을 새로 쓰지 않고 '지금 규칙이 나아졌는지'를 숫자로 잰다.

사용자 요청 - "더 체계적으로". 한 편 재시험 결과(점수가 0.88↔1.0으로 흔들림)만 보고 고친 효과를 판단하지 않기 위한 도구.
저장소의 파일은 바꾸지 않는다(시험지 실행 결과만 logs/lab/에 남김).

  python lab_bench.py replay [--vs main]   지난 기록의 모든 초안에 지금 교열을 다시 돌림(--vs: 옛 교열과 비교). 돈·한도 0.
  python lab_bench.py score                완료 기준 성적표(①②③⑤⑥⑧ + 자료 대조). 돈·한도 0.
  python lab_bench.py exam --check         시험지(lab/exam.json) 점검
  python lab_bench.py exam --run           시험지를 실제 검토 담당에게 풀림(AI 호출 - 깃허브 실행 lab_exam으로)
  python lab_bench.py exam --report        지금까지 푼 시험지 결과 모아 보기
  python lab_bench.py compete [--fetch]    경쟁 글 비교(lab/compete.json의 검색 상위 글과 구조 비교. --fetch는 깃허브 lab_compete로)

시험지 원칙(사용자와 정함 2026-11-08): 한 번 만든 자로만 재면 글이 자에 맞춰질 뿐이다 → 시험지도 계속 고친다. 단
  ① 새로 찾은 실패만 더한다(빼지 않음) ② 판이 바뀌면 version을 올리고 결과는 판끼리만 비교한다
  ③ hidden 문제는 규칙을 고칠 때 보지 않고 확인할 때만 쓴다.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

from ondo.checks import lint, numbers

EXAM_FILE = os.path.join("lab", "exam.json")
READS_FILE = os.path.join("lab", "reads.json")
RESULT_DIR = os.path.join("logs", "lab")
REQUIRED_TYPES = ["analysis", "comparison", "guide", "issue", "energy", "society", "trend", "tech", "bio"]


# ───────────────────────── 기록 읽기 ─────────────────────────
def load_logs(root="logs", since=None):
    out = []
    for f in glob.glob(os.path.join(root, "*", "*.json")):
        if os.path.basename(os.path.dirname(f)) == "lab":
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        drafts = d.get("drafts") or {}
        if not drafts:
            continue
        day = os.path.basename(os.path.dirname(f)) + "-" + os.path.basename(f)[:2]
        if since and day < since:
            continue
        rounds = {str(s["step"]).split()[-1]: s for s in d.get("steps", [])
                  if str(s.get("step", "")).startswith("편집장 검토")}
        out.append({"file": f, "day": day, "started": d.get("started_at") or day, "type": d.get("article_type") or "?",
                    "topic": d.get("topic_id") or "", "category": d.get("category") or "", "drafts": drafts,
                    "rounds": rounds, "facts": d.get("facts") or "", "result": d.get("result") or {}})
    out.sort(key=lambda a: (a["started"], a["file"]))
    return out


def passed(a):
    return any(s.get("passed") for s in a["rounds"].values())


def final_round(a):
    """발행(임시글)에 쓰인 판: 통과한 판이 있으면 그 판, 없으면 마지막 판."""
    keys = sorted(a["drafts"], key=int)
    ok = [k for k in keys if (a["rounds"].get(k) or {}).get("passed")]
    return ok[-1] if ok else keys[-1]


def body_text(html):
    return lint.text_of(re.sub(r"<!--.*?-->", "", html or "", flags=re.S))


# ───────────────────────── ① 기록 다시 돌리기 ─────────────────────────
def load_lint(ref):
    """git의 다른 시점(ref) 교열 코드를 따로 불러온다(지금 코드와 나란히 비교하려고)."""
    src = subprocess.check_output(["git", "show", f"{ref}:ondo/checks/lint.py"], text=True)
    spec = importlib.util.spec_from_loader("lint_" + re.sub(r"\W", "_", ref), loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(src, f"{ref}:lint.py", "exec"), mod.__dict__)
    return mod


def lint_blocks(mod, html):
    _h, issues, _fixes = mod.fix_and_check(html)
    return mod.blocking(issues)


def _kind(issue):
    return re.sub(r"\s*[-(:'\"].*$", "", re.sub(r"^\[[^\]]*\]\s*", "", issue))[:24] or issue[:24]


def replay(arts, new=lint, old=None):
    lines = []
    finals = [(a, final_round(a)) for a in arts if passed(a)]
    rounds = [(a, k) for a in arts for k in a["drafts"]]
    lines.append(f"[범위] 기록 {len(arts)}편, 초안 {len(rounds)}개, 통과한 글의 최종 초안 {len(finals)}개")
    bad = Counter(_kind(i) for a, k in finals for i in lint_blocks(new, a["drafts"][k]))
    lines.append(f"\n[통과한 최종 초안이 지금 교열에 걸리는 이유] " + (", ".join(f"{k} {v}" for k, v in bad.most_common(8)) or "없음")
                 + "\n  (대부분 그 초안 뒤에 생긴 규칙이다. 규칙을 바꾼 효과는 --vs로 옛 교열과 같은 초안끼리 비교해서 본다)")
    kinds = Counter(_kind(i) for a, k in rounds for i in lint_blocks(new, a["drafts"][k]))
    lines.append("\n[모든 초안에서 지금 교열이 막는 이유] " + (", ".join(f"{k} {v}" for k, v in kinds.most_common(10)) or "없음"))
    if old is not None:
        gained, lost = Counter(), Counter()
        hurt, caught = [], 0
        final_set = {(a["file"], k) for a, k in finals}
        for a, k in rounds:
            o = {_kind(i) for i in lint_blocks(old, a["drafts"][k])}
            n = {_kind(i) for i in lint_blocks(new, a["drafts"][k])}
            for x in n - o:
                gained[x] += 1
            for x in o - n:
                lost[x] += 1
            if n - o:
                if (a["file"], k) in final_set:
                    hurt.append(f"{os.path.basename(a['file'])} {k}판: {', '.join(sorted(n - o))}")
                elif not (a["rounds"].get(k) or {}).get("passed"):
                    caught += 1
        lines.append("\n[옛 교열과 비교]")
        lines.append("- 새로 막는 것: " + (", ".join(f"{k} {v}" for k, v in gained.most_common()) or "없음"))
        lines.append("- 더는 안 막는 것: " + (", ".join(f"{k} {v}" for k, v in lost.most_common()) or "없음"))
        lines.append(f"- 떨어졌던 판에서 새로 잡은 것: {caught}개 / 통과했던 최종 초안을 새로 막은 것: {len(hurt)}개")
        lines.extend(f"    {h}" for h in hurt[:10])
    return "\n".join(lines)


# ───────────────────────── ② 완료 기준 성적표 ─────────────────────────
# '(코드 계산)' 표시가 없어도 코드가 계산해 넣는 판단 숫자 줄(에너지 1년 범위 위치·평균 대비, 통계 기준선 넘은 해 등).
# 2026-11-08: 이 줄을 못 알아봐서 성적표가 에너지·인구사회 글을 '고유 숫자 0개'로 잘못 셌음.
CODE_HINT = re.compile(r"코드 계산|범위\(최저=0%|평균 [\d.,]+ 대비|처음 넘은 해|구성비|가장 컸던 때")


def _code_values(facts):
    """[사실 자료] 중 코드가 계산한 줄의 숫자(값, 소수 자리)."""
    vals, in_code = set(), False
    for line in (facts or "").splitlines():
        if line.startswith("["):
            in_code = "코드" in line
            continue
        for m in re.finditer(r"(\d+)% 지점", line):          # 1년 범위 중 위치(작은 정수지만 코드가 계산한 판단 숫자)
            vals.add((float(m.group(1)), 0))
        if in_code or CODE_HINT.search(line):
            for _raw, v, dec, unit in numbers._numbers(line):
                if dec == 0 and (abs(v) < 100 if unit else (v < 1000 or 1990 <= v <= 2100)):
                    continue                     # 3배·10%·1억 같은 작은 정수는 가정값일 때가 많다
                vals.add((v, dec))
    return vals


def common_constants(arts, min_topics=3):
    """여러 주제의 계산 줄에 똑같이 나오는 숫자 = 가정값·세율(1억 원, 15.4% 등). 고유 숫자로 치지 않는다."""
    seen = defaultdict(set)
    for a in arts:
        for v in _code_values(a["facts"]):
            seen[v].add(a["topic"])
    return {v for v, t in seen.items() if len(t) >= min_topics}


def unique_numbers(html, facts, constants=()):
    """본문에 쓰인, 코드가 계산한 이 글만의 숫자."""
    code = [v for v in _code_values(facts) if v not in constants]
    found = []
    for raw, v, dec, _unit in numbers._numbers(body_text(html)):
        for f, _fd in code:
            if abs(f - v) < 1e-9 or (dec >= 1 and round(f, dec) == v):
                if raw not in found:
                    found.append(raw)
                break
    return found


def _headings(html):
    hs = [lint.text_of(h) for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html or "", flags=re.S)]
    return [re.sub(r"[\d.,%]+", "", h).strip() for h in hs if h.strip()]


_STOP = {"ETF", "비교", "차이", "특징", "기준", "확인", "실제", "데이터", "원리", "구조", "관련", "본", "뜻", "기초", "핵심"}


def _tokens(h):
    ws = re.findall(r"[가-힣A-Za-z]{2,}", h)
    ws = [re.sub(r"(으로|에서|와|과|의|및|을|를|이|가|은|는|에|로|하기)$", "", w) for w in ws]
    return {w for w in ws if len(w) >= 2 and w not in _STOP}


def _hsim(a, b):
    """소제목 둘이 같은 틀인가: 핵심 낱말 2개 이상이 같거나(예: '계좌와 세금 관련 유의사항'↔'계좌 활용과 세금 기준') 글자가 많이 겹침."""
    return len(_tokens(a) & _tokens(b)) >= 2 or _sim(a, b) >= 0.5


def _sim(a, b):
    ga, gb = lint._grams(a), lint._grams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def _first_sentence(html):
    m = re.search(r"<p[^>]*>(.*?)</p>", re.sub(r"<!--.*?-->", "", html or "", flags=re.S), flags=re.S)
    t = lint.text_of(m.group(1)) if m else ""
    return re.split(r"(?<=[.!?])\s", t)[0][:120]


INTENDED_HEADINGS = re.compile(r"자주 묻는 질문|정리|마무리")   # 일부러 모든 글에 두는 소제목(내용은 글마다 다름)


def template_report(reps, th=0.5):
    """같은 종류 글끼리 같은 소제목·첫 문장(붕어빵 틀). 반 넘는 글에 나오는 소제목을 찾는다."""
    out = []
    by_type = defaultdict(list)
    for a in reps:
        by_type[a["type"]].append(a)
    for typ, arts in sorted(by_type.items()):
        if len(arts) < 3:
            continue
        hs = [(a, _headings(a["drafts"][final_round(a)])) for a in arts]
        shared = []
        for i, (a, mine) in enumerate(hs):
            for h in mine:
                if INTENDED_HEADINGS.search(h):
                    continue
                n = 1 + sum(any(_hsim(h, x) for x in other) for j, (_b, other) in enumerate(hs) if j != i)
                if n * 2 > len(arts) and not any(_hsim(h, s) for s, _ in shared):
                    shared.append((h, n))
        firsts = [_first_sentence(a["drafts"][final_round(a)]) for a in arts]
        close = sum(1 for i in range(len(firsts)) for j in range(i + 1, len(firsts)) if _sim(firsts[i], firsts[j]) >= th)
        out.append((typ, len(arts), shared, close))
    return out


def representatives(arts):
    """주제마다 지금 남아 있는 대표 글(통과한 마지막 기록, 없으면 마지막 기록)."""
    by_topic = defaultdict(list)
    for a in arts:
        by_topic[(a["type"], a["topic"])].append(a)
    reps = []
    for _k, lst in by_topic.items():
        ok = [a for a in lst if passed(a)]
        reps.append((ok or lst)[-1])
    return reps, by_topic


def _reads():
    try:
        return json.load(open(READS_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 0, "reads": []}


def scorecard(arts):
    lines = []
    reps, by_topic = representatives(arts)
    consts = common_constants(arts)
    lines.append(f"[범위] 주제 {len(reps)}개(대표 글 기준), 기록 {len(arts)}편")
    tested = {a["type"] for a in reps if passed(a)}
    miss = [t for t in REQUIRED_TYPES if t not in tested]
    lines.append(f"\n① 글 종류 시험: {len(REQUIRED_TYPES) - len(miss)}/{len(REQUIRED_TYPES)}" + (f" - 아직: {', '.join(miss)}" if miss else " ✔"))
    lines.append("\n② 종류별 대표 글(통과한 것) 최저 점수 / 최저 독자 가치  (기준 0.9 / 0.8)")
    per = defaultdict(list)
    for a in reps:
        if passed(a):
            st = a["rounds"].get(final_round(a)) or {}
            per[a["type"]].append((a["result"].get("score", st.get("score")), st.get("value"), a))
    for t in REQUIRED_TYPES:
        if t not in per:
            continue
        s = min((x[0] for x in per[t] if x[0] is not None), default=None)
        v = min((x[1] for x in per[t] if x[1] is not None), default=None)
        ok = s is not None and s >= 0.9 and (v is None or v >= 0.8)
        lows = [os.path.basename(x[2]["file"]) for x in per[t] if (x[0] or 0) < 0.9 or (x[1] is not None and x[1] < 0.8)]
        lines.append(f"- {t}: {s} / {v} {'✔' if ok else '✘ ' + ', '.join(lows[:3])}")
    lines.append("\n③ 연달아 통과(같은 주제 마지막 두 번이 모두 통과)")
    twice = [k[1] for k, lst in by_topic.items() if len(lst) >= 2 and all(passed(a) for a in lst[-2:])]
    lines.append(f"- {len(twice)}개 주제: {', '.join(twice[:8]) or '없음'}")
    rd = _reads()
    read_types = {r.get("type") for r in rd.get("reads", [])}
    lines.append(f"\n⑤ 사람 눈 읽기(채점표 {rd.get('version', 0)}판): 읽은 종류 {len(read_types & set(REQUIRED_TYPES))}개"
                 + (f" - 아직: {', '.join(t for t in REQUIRED_TYPES if t in tested and t not in read_types)}" if tested - read_types else ""))
    lines.append("\n⑥ 고유한 숫자(코드가 계산한, 이 글에만 있는 숫자가 본문에 1개 이상)")
    no_unique = []
    for a in sorted(reps, key=lambda x: x["type"]):
        if not passed(a):
            continue
        u = unique_numbers(a["drafts"][final_round(a)], a["facts"], consts)
        if not u:
            no_unique.append(f"{a['type']}:{a['topic'][:30]}")
    lines.append(f"- 없는 글 {len(no_unique)}개" + (": " + ", ".join(no_unique) if no_unique else " ✔"))
    lines.append("\n⑦ 자료 대조(자동 일부): 본문 숫자 중 자료에서 못 찾은 것")
    for a in reps:
        if passed(a):
            nums = numbers.unverified(body_text(a["drafts"][final_round(a)]), a["facts"])
            if nums:
                lines.append(f"- {a['type']}:{a['topic'][:30]} → {', '.join(nums[:5])}")
    lines.append("  (교차 확인 자체 - 같은 숫자를 다른 방법으로 다시 계산 - 은 시나리오 시험의 자료 점검으로)")
    lines.append("\n⑧ 틀 반복(같은 종류 글의 반 넘게 나오는 소제목 / 첫 문장이 비슷한 쌍. '자주 묻는 질문'·정리는 일부러 둔 것이라 뺌)")
    for typ, n, shared, close in template_report([a for a in reps if passed(a)]):
        lines.append(f"- {typ}({n}편): " + (", ".join(f"'{h}' {c}편" for h, c in shared[:4]) or "공통 소제목 없음")
                     + f" / 첫 문장 비슷한 쌍 {close}")
    one = sum(1 for a in reps if passed(a) and lint.ONE_LINE.search(a["drafts"][final_round(a)]))
    lines.append(f"\n[참고] 한 줄 정리 있는 대표 글: {one}/{sum(1 for a in reps if passed(a))}")
    return "\n".join(lines)


# ───────────────────────── ③ 검토 담당 시험지 ─────────────────────────
# 변형 문제: 좋은 초안에 알려진 결함을 하나 넣는다 → 정답(무엇을 잡아야 하는지)이 확실하다.
def _paras(html):
    return [m for m in re.finditer(r"<p>(?!<strong>한 줄 정리)(.*?)</p>", html, flags=re.S)
            if len(lint.text_of(m.group(1))) >= 40]


def _insert_before_summary(html, para):
    m = re.search(r"<h[23][^>]*>[^<]*(정리|마무리|결론)[^<]*</h[23]>", html)
    pos = m.start() if m else len(html)
    return html[:pos] + para + "\n" + html[pos:]


def mut_wrong_number(html, facts):
    for m in _paras(html):
        n = re.search(r"(?<![\d.])(\d+\.\d+)(?=\s*%)", m.group(1))
        if n:
            dec = len(n.group(1).split(".")[1])
            wrong = f"{float(n.group(1)) * 1.37 + 0.7:.{dec}f}"
            para = m.group(1)[:n.start()] + wrong + m.group(1)[n.end():]
            sent = next((s for s in re.split(r"(?<=[.!?])\s", lint.text_of(para)) if wrong in s), wrong)
            return html[:m.start(1)] + para + html[m.end(1):], sent
    return None, None


# 같은 문장만 넣으면 그 문장만 잡도록 규칙이 맞춰질 수 있어 표현을 여러 개 두고 글마다 돌려 쓴다.
VARIANTS = {
    "judgement": ["결론적으로 이 상품이 다른 선택지보다 훨씬 유리하므로 지금 바로 사 두는 것이 가장 좋은 선택입니다.",
                  "이런 흐름이라면 지금이 비중을 늘리기에 가장 좋은 시기라고 볼 수 있습니다.",
                  "장기 투자자라면 고민할 필요 없이 이쪽을 고르는 것이 정답입니다."],
    "invented_source": ["한 대형 증권사 관계자는 내년에도 이런 흐름이 이어질 가능성이 높다고 내다봤습니다.",
                        "시장 전문가들 사이에서는 이 흐름이 당분간 이어질 것이라는 의견이 우세합니다.",
                        "업계에서는 이번 변화를 구조적인 전환점으로 보는 시각이 많습니다."],
    "fake_fact": ["이 상품은 지난해 국내 개인투자자 순매수 1위를 차지하며 가장 많은 자금이 몰린 것으로 집계됐습니다.",
                  "같은 기간 관련 상품의 거래대금은 전년보다 두 배 넘게 늘어난 것으로 나타났습니다.",
                  "이 분야는 최근 3년 연속으로 정부 지원 예산이 늘어난 대표적인 영역이기도 합니다."],
}


def _variant(kind, html):
    v = VARIANTS[kind]
    return v[sum(map(ord, html[:200])) % len(v)]


def mut_judgement(html, facts):
    s = _variant("judgement", html)
    return _insert_before_summary(html, f"<p>{s}</p>"), s


def mut_invented_source(html, facts):
    s = _variant("invented_source", html)
    return _insert_before_summary(html, f"<p>{s}</p>"), s


def mut_fake_fact(html, facts):
    s = _variant("fake_fact", html)
    return _insert_before_summary(html, f"<p>{s}</p>"), s


def mut_repeat_para(html, facts):
    ps = _paras(html)
    if len(ps) < 4:
        return None, None
    m = max(ps[:len(ps) // 2], key=lambda x: len(x.group(1)))
    copy = f"<p>{m.group(1)}</p>"
    return _insert_before_summary(html, copy), lint.text_of(m.group(1))[:80]


def mut_no_summary(html, facts):
    new = lint.ONE_LINE.sub("", html, count=1)
    return (new, "") if new != html else (None, None)


MUTATIONS = {"wrong_number": mut_wrong_number, "judgement": mut_judgement, "invented_source": mut_invented_source,
             "fake_fact": mut_fake_fact, "repeat_para": mut_repeat_para, "no_summary": mut_no_summary}


def load_exam(path=EXAM_FILE):
    return json.load(open(path, encoding="utf-8"))


def _art(path):
    d = json.load(open(path, encoding="utf-8"))
    return d


def check_exam(exam):
    probs = []
    for it in exam.get("bases", []) + exam.get("real", []):
        if not os.path.exists(it["file"]):
            probs.append(f"{it['id']}: 파일 없음 {it['file']}")
            continue
        if str(it["round"]) not in (_art(it["file"]).get("drafts") or {}):
            probs.append(f"{it['id']}: {it['round']}판 초안 없음")
    for m in exam.get("mutations", []):
        if m not in MUTATIONS:
            probs.append(f"변형 '{m}' 없음")
    return probs


def plan_exam(exam, limit=None):
    """풀 문제 목록: 좋은 초안 그대로(헛지적 재기) + 변형(잡는지 재기) + 실제 실패 초안."""
    items = []
    muts = exam.get("mutations", [])
    per = exam.get("mutations_per_base", 2)
    for i, b in enumerate(exam.get("bases", [])):
        d = _art(b["file"])
        html, facts = d["drafts"][str(b["round"])], d.get("facts") or ""
        cat = d.get("category") or d.get("article_type") or ""
        items.append({"id": b["id"], "kind": "good", "hidden": b.get("hidden", False), "html": html, "facts": facts,
                      "category": cat, "marker": None, "mutation": None})
        for j in range(per):
            name = muts[(i * per + j) % len(muts)] if muts else None
            if not name:
                continue
            new, marker = MUTATIONS[name](html, facts)
            if new is None:
                continue
            items.append({"id": f"{b['id']}+{name}", "kind": "mutation", "hidden": b.get("hidden", False), "html": new,
                          "facts": facts, "category": cat, "marker": marker, "mutation": name, "base": b["id"]})
    for r in exam.get("real", []):
        d = _art(r["file"])
        items.append({"id": r["id"], "kind": "real", "hidden": r.get("hidden", False),
                      "html": d["drafts"][str(r["round"])], "facts": d.get("facts") or "",
                      "category": d.get("category") or d.get("article_type") or "", "marker": None,
                      "expect": r.get("expect", ""), "mutation": None})
    return items[:limit] if limit else items


def caught(item, lint_issues, review_issues, base_lint=()):
    """막는 지적(교열 막음 / 검토 치명·중요) 가운데 넣은 결함을 가리키는 것이 있나."""
    hard = [i for i in lint.blocking(lint_issues) if _kind(i) not in {_kind(b) for b in base_lint}]
    serious = [f for f in review_issues if f.get("severity") in ("치명", "중요")]
    if item["kind"] == "good":
        return bool(serious)          # 좋은 글에 치명·중요 지적 = '헛지적'(교열은 기계 규칙이라 replay로 따로 잰다)
    if item["kind"] == "real":
        pat = item.get("expect") or "."
        return any(re.search(pat, f"{f.get('quote', '')} {f.get('problem', '')}") for f in serious) or \
            any(re.search(pat, i) for i in hard)
    if item["mutation"] == "no_summary":
        return any("한 줄 정리 없음" in i for i in hard)
    mk = item["marker"] or ""
    for f in serious:
        q = f.get("quote", "")
        if q and mk and (_sim(q, mk) >= 0.3 or q[:20] in mk or mk[:20] in q):
            return True
    return any(mk[:15] in i for i in hard) if mk else False


def run_exam(exam, review_fn, limit=None):
    """review_fn(html, facts, category) → 검토 지적 목록. 결과를 모아 돌려준다."""
    items = plan_exam(exam, limit)
    base_lint = {}
    res = []
    for it in items:
        h, li, _fx = lint.fix_and_check(it["html"])
        if it["kind"] == "good":
            base_lint[it["id"]] = lint.blocking(li)
        found = review_fn(h, it["facts"], it["category"]) or []
        hit = caught(it, li, found, base_lint.get(it.get("base"), ()))
        res.append({"id": it["id"], "kind": it["kind"], "mutation": it.get("mutation"), "hidden": it["hidden"],
                    "hit": hit, "issues": [f"[{f.get('severity')}·{f.get('by', '')}] {f.get('quote', '')[:50]} → "
                                           f"{f.get('problem', '')[:80]}" for f in found][:8],
                    "lint": lint.blocking(li)[:4]})
    return res


def summarize(res, version):
    lines = [f"[시험지 {version}판] 문제 {len(res)}개"]
    for hidden in (False, True):
        part = [r for r in res if r["hidden"] == hidden]
        if not part:
            continue
        good = [r for r in part if r["kind"] == "good"]
        muts = [r for r in part if r["kind"] != "good"]
        tag = "숨긴 문제" if hidden else "공개 문제"
        lines.append(f"- {tag}: 결함 잡음 {sum(r['hit'] for r in muts)}/{len(muts)}, "
                     f"좋은 초안을 막음(헛지적) {sum(r['hit'] for r in good)}/{len(good)}")
    by = defaultdict(list)
    for r in res:
        if r["kind"] != "good":
            by[r["mutation"] or "실제 실패"].append(r["hit"])
    lines.append("- 결함 종류별 잡은 비율: " + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by.items())))
    return "\n".join(lines)


def exam_main(args):
    exam = load_exam()
    if args.check:
        probs = check_exam(exam)
        print("시험지 문제 없음" if not probs else "\n".join(probs))
        items = plan_exam(exam)
        print(f"{exam.get('version')}판: 문제 {len(items)}개 "
              f"(좋은 초안 {sum(i['kind'] == 'good' for i in items)}, 변형 {sum(i['kind'] == 'mutation' for i in items)}, "
              f"실제 실패 {sum(i['kind'] == 'real' for i in items)})")
        return 1 if probs else 0
    if args.report:
        runs = sorted(glob.glob(os.path.join(RESULT_DIR, "exam-*.json")))
        by_v = defaultdict(list)
        for f in runs:
            d = json.load(open(f, encoding="utf-8"))
            by_v[d["version"]].append((os.path.basename(f), d["results"]))
        for v, lst in sorted(by_v.items()):
            for name, res in lst:
                print(name + "\n" + summarize(res, v))
        return 0
    from ondo.checks.editlog import EditLog
    from ondo.writing import desk
    log = EditLog("lab", "exam", "시험지")

    def review_fn(html, facts, category):
        _score, found = desk.review(html, facts, category, log, 1)
        return found
    res = run_exam(exam, review_fn, args.limit)
    from ondo.config import kst_now
    os.makedirs(RESULT_DIR, exist_ok=True)
    path = os.path.join(RESULT_DIR, f"exam-{kst_now():%Y%m%d-%H%M}.json")
    json.dump({"version": exam.get("version"), "results": res}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(summarize(res, exam.get("version")))
    print("저장:", path)
    return 0


# ───────────────────────── ④ 경쟁 글 비교 ─────────────────────────
# 사용자 제안(2026-11-08): 실제 독자·구글 평가는 공개 뒤 오래 걸리므로, 같은 질문으로 검색하면 위에 나오는 글과 지금 비교한다.
# 본문은 저장하지 않고 구조만 잰다(분량·소제목·표·그림·숫자 수·FAQ·날짜·저자 표시). 우리가 배울 수 있는 것만 본다 -
# 도메인 나이·링크 수 같은 '글 밖' 요인은 비교하지 않는다.
COMPETE_FILE = os.path.join("lab", "compete.json")
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}


def page_features(html, site_chrome=True):
    """글 구조 측정. site_chrome=False면 우리 초안(사이트 머리·날짜·저자는 워드프레스가 붙임)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    raw = str(soup)[:300000]
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        t.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ")).strip()
    heads = [re.sub(r"\s+", " ", h.get_text(" ")).strip()[:60] for h in main.find_all(["h2", "h3"])]
    heads = [h for h in heads if h]
    nums = [n for n in numbers._numbers(text) if n[2] or n[3]]
    return {"chars": len(text), "n_headings": len(heads), "headings": heads[:30],
            "tables": len(main.find_all("table")), "images": len(main.find_all("img")), "numbers": len(nums),
            "faq": bool(re.search(r"자주 묻는|FAQ|Q&A|질문과 답", text)),
            "date": None if not site_chrome else bool(re.search(
                r"(작성|게시|수정|업데이트|발행|입력)\s*(일|일시)?\s*[:：]?\s*20\d\d|20\d\d[.\-/]\s?\d{1,2}[.\-/]\s?\d{1,2}", text[:4000] + raw[:40000])),
            "author": None if not site_chrome else bool(re.search(r"글쓴이|작성자|기자|에디터|필자|rel=\"author\"|\"author\"", raw)),
            "words": sorted(_tokens(" ".join(heads)))[:60], "_text": text}


def fetch_compete(conf, get=None):
    import requests
    get = get or (lambda u: requests.get(u, headers=_UA, timeout=(8, 20)))
    out = {"version": conf.get("version"), "topics": []}
    for t in conf.get("topics", []):
        pages = []
        for u in t.get("urls", []):
            try:
                r = get(u)
                if not r.ok:
                    pages.append({"url": u, "ok": False, "status": r.status_code})
                    continue
                r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else r.apparent_encoding
                f = page_features(r.text)
                f.pop("_text", None)
                pages.append({"url": u, "ok": f["chars"] >= 500, "status": r.status_code, "features": f})
            except Exception as e:
                pages.append({"url": u, "ok": False, "status": type(e).__name__})
        out["topics"].append({"id": t["id"], "query": t.get("query", ""), "pages": pages})
    return out


# 사이트 틀(관련 글 목록·태그·댓글)의 소제목은 글 내용이 아니므로 뺀다(2026-11-08 첫 측정: '관련글·TAG·더보기'가 빠진 말로 잡힘)
_CHROME = re.compile(r"관련\s?글|함께 보면|같은 주제|TAG|태그|댓글|더보기|메일로 받아|저장 상태|구독|공유|이전 글|다음 글|추천 글|인기 글|가이드$")


def _clean_features(f):
    f = dict(f)
    heads = []
    for h in f.get("headings") or []:
        if _CHROME.search(h):
            break                        # 보통 글 끝의 '관련 글' 뒤로는 전부 사이트 틀
        heads.append(h)
    f["n_headings"] = len(heads) if f.get("headings") is not None else f.get("n_headings", 0)
    f["words"] = sorted(_tokens(" ".join(heads)))
    return f


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def compete_report(conf, result):
    lines = [f"[경쟁 글 비교 {result.get('version')}판] 같은 질문으로 검색했을 때 위에 나오는 글과 구조 비교(본문 저장 안 함)"]
    by_id = {t["id"]: t for t in result.get("topics", [])}
    for t in conf.get("topics", []):
        r = by_id.get(t["id"])
        if not r:
            continue
        good = [_clean_features(p["features"]) for p in r["pages"] if p.get("ok")]
        lines.append(f"\n■ {t['id']} - '{t.get('query', '')}' (읽은 경쟁 글 {len(good)}/{len(r['pages'])})")
        if not good:
            continue
        try:
            d = json.load(open(t["ours"], encoding="utf-8"))
            a = {"drafts": d["drafts"], "rounds": {str(s["step"]).split()[-1]: s for s in d.get("steps", [])
                                                  if str(s.get("step", "")).startswith("편집장 검토")}}
            ours = page_features(d["drafts"][final_round(a)], site_chrome=False)
        except (OSError, ValueError, KeyError):
            lines.append("  (우리 글 기록 없음)")
            continue
        lines.append("  (우리 글의 표·그림은 0으로 나오지만 계산표·차트는 발행할 때 시스템이 따로 넣음 - 본문 글자만 비교)")
        for key, name in (("chars", "분량(글자)"), ("n_headings", "소제목 수"), ("tables", "표"), ("images", "그림"), ("numbers", "숫자 수")):
            lines.append(f"  - {name}: 우리 {ours[key]} / 경쟁 중간값 {_median([g[key] for g in good])} (최대 {max(g[key] for g in good)})")
        lines.append(f"  - FAQ 있는 경쟁 글 {sum(g['faq'] for g in good)}/{len(good)} (우리 {'있음' if ours['faq'] else '없음'})"
                     f", 날짜 표시 {sum(bool(g['date']) for g in good)}/{len(good)}, 저자 표시 {sum(bool(g['author']) for g in good)}/{len(good)}")
        cnt = Counter(w for g in good for w in set(g.get("words") or []))
        body = ours["_text"]
        gaps = [w for w, n in cnt.most_common() if n >= 2 and w not in body]
        lines.append("  - 경쟁 글 2곳 이상의 소제목에 나오는데 우리 글엔 없는 말: " + (", ".join(gaps[:12]) or "없음"))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--vs")
    r.add_argument("--since")
    s = sub.add_parser("score")
    s.add_argument("--since")
    e = sub.add_parser("exam")
    e.add_argument("--check", action="store_true")
    e.add_argument("--run", action="store_true")
    e.add_argument("--report", action="store_true")
    e.add_argument("--limit", type=int)
    c = sub.add_parser("compete")
    c.add_argument("--fetch", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "replay":
        print(replay(load_logs(since=a.since), lint, load_lint(a.vs) if a.vs else None))
    elif a.cmd == "score":
        print(scorecard(load_logs(since=a.since)))
    elif a.cmd == "compete":
        conf = json.load(open(COMPETE_FILE, encoding="utf-8"))
        if a.fetch:
            res = fetch_compete(conf)
            from ondo.config import kst_now
            os.makedirs(RESULT_DIR, exist_ok=True)
            path = os.path.join(RESULT_DIR, f"compete-{kst_now():%Y%m%d-%H%M}.json")
            json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("저장:", path)
        else:
            runs = sorted(glob.glob(os.path.join(RESULT_DIR, "compete-*.json")))
            if not runs:
                print("경쟁 글 측정 결과 없음 - 깃허브 실행 lab_compete로 먼저 모으세요")
                return 1
            res = json.load(open(runs[-1], encoding="utf-8"))
        print(compete_report(conf, res))
    else:
        return exam_main(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
