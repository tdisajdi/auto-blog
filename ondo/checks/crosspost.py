"""글끼리 비교 점검(2026-11-24, 원칙 L11 - '한 편씩만 봐서 못 잡은 것' 두 번째 재발 → 코드로).

외부 검토가 공개 글 6편을 나란히 읽고 찾은 것을 우리 검수(한 편씩·숫자 위주)는 못 잡았다:
  ① 같은 문단이 여러 글에 되풀이(계좌 제한 문단 5/6편)  ② 정리의 '첫째·둘째·셋째' 틀 6/6편
  ③ 다른 글 이름만 있고 링크 없음  ④ 시점을 타는 말('국회 심의 중')  ⑤ 같은 숫자가 글마다 다름(SCHD 낙폭)
check(posts) → 문제 목록. posts = [(id, title, html), ...]. 막지 않고 알려 줌(사람 읽기·patch에서 고침).
"""
import html as _html
import re
from collections import defaultdict

SHINGLE = 8            # 낱말 8개 연속이 같으면 '같은 문장 조각'
REPEAT_POSTS = 3       # 3편 이상에 같은 조각이면 되풀이
TIME_WORDS = r"국회|개편안|발의|심의\s*중|추진\s*중|검토\s*중|시행\s*예정|도입\s*예정|논의\s*중|입법\s*예고"
REF_PAT = re.compile(r"([가-힣A-Za-z0-9·\s]{2,24}?(가이드|글|페이지))\s*(을|를|에서|에)?\s*(참고|확인|자세히|정리|다룹|다뤘|보면)")
METRIC = re.compile(r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])[^.。\n]{0,40}?(최대\s*낙폭|MDD)[^.。\n]{0,30}?(-?\d{1,2}(?:\.\d{1,2})?)\s*%")
PERIOD = re.compile(r"(\d{1,2})\s*년")
NOT_TICKER = {"ETF", "MDD", "ISA", "IRP", "CSI", "MSCI", "FAQ", "USD", "KRW", "CAGR", "AUM"}


def _text(h):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).strip()


def _body(h):
    """사이트 공통 부품(출처 상자·면책·표지 설명·함께 볼 글·그래프 코드·표·목차)은 원래 같은 꼴이라 뺌."""
    h = h or ""
    h = re.sub(r"<(script|style|table|figure)\b.*?</\1>", " ", h, flags=re.S)
    h = re.split(r"📌\s*데이터 출처|<h[23][^>]*>\s*(📚\s*)?(출처|참고 자료|Sources)", h)[0]
    h = re.sub(r"<p[^>]*>[^<]*(👉\s*함께 보면 좋은 글|🖼)[\s\S]*?</p>", " ", h)
    h = re.sub(r"<div[^>]*(toc|disclaimer|o-cover)[^>]*>.*?</div>", " ", h, flags=re.S)
    h = re.sub(r"이 글은 공개 데이터를 정리한[^<]*", " ", h)
    h = re.sub(r"\((MDD|최대 낙폭)?[,:]?\s*가장 높았던 값에서[^)]*\)", " ", h)   # 용어 풀이 괄호는 일부러 같게 둠
    return h


def repeated_chunks(posts):
    seen = defaultdict(set)
    for pid, _t, h in posts:
        words = re.sub(r"[\d.,%]+", "#", _text(_body(h))).split()
        for i in range(len(words) - SHINGLE + 1):
            seen[" ".join(words[i:i + SHINGLE])].add(pid)
    hits = {k: v for k, v in seen.items() if len(v) >= REPEAT_POSTS}
    # 이어진 조각은 하나로: 같은 글 묶음별 가장 앞 조각만
    out, groups = [], set()
    for k, v in sorted(hits.items(), key=lambda x: -len(x[1])):
        key = tuple(sorted(v))
        if key in groups:
            continue
        groups.add(key)
        out.append(("되풀이 문단", key, k))
    return out


def summary_pattern(pid, h):
    parts = re.split(r"<h3[^>]*>\s*(?:<[^>]+>\s*)*정리\s*(?:<[^>]+>\s*)*</h3>", _body(h))
    tail = _text(parts[-1]) if len(parts) > 1 else ""
    return [("정리 첫째·둘째·셋째 틀", (pid,), tail[:60])] if all(w in tail for w in ("첫째", "둘째", "셋째")) else []


def unlinked_refs(pid, h):
    no_links = re.sub(r"<a\b[^>]*>.*?</a>", " ", _body(h), flags=re.S)
    return [("링크 없는 글 언급", (pid,), m.group(0).strip()[:50]) for m in REF_PAT.finditer(_text(no_links))
            if not re.search(r"(이|그|이번|아래|위)\s*(글|페이지)", m.group(1))]


def time_words(pid, h):
    sents = re.split(r"(?<=[.。?!])\s", _text(_body(h)))
    return [("시점 타는 말", (pid,), s_[:80]) for s_ in sents if re.search(TIME_WORDS, s_)]   # 한 문장에 한 번


def metric_conflicts(posts):
    vals = defaultdict(dict)
    for pid, _t, h in posts:
        for sent in re.split(r"(?<=[.。])\s", _text(_body(h))):
            for m in METRIC.finditer(sent):
                if m.group(1) in NOT_TICKER:
                    continue
                p = PERIOD.search(sent)
                vals[(m.group(1), p.group(1) if p else "?")][pid] = abs(float(m.group(3)))
    out = []
    for (tk, per), d in vals.items():
        if len(d) >= 2 and max(d.values()) - min(d.values()) > 0.5:
            out.append(("같은 숫자가 글마다 다름", tuple(sorted(d)), f"{tk} {per}년 낙폭 " + ", ".join(f"{k}:{v}%" for k, v in d.items())))
    return out


def check(posts):
    probs = repeated_chunks(posts) + metric_conflicts(posts)
    for pid, _t, h in posts:
        probs += summary_pattern(pid, h) + unlinked_refs(pid, h) + time_words(pid, h)
    return probs
