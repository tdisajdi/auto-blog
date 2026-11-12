"""교열부 2: 숫자 대조. 본문에 나온 숫자가 [사실 자료]에 있는지 코드가 확인한다.

- 대상: 소수점 숫자, %·%p, 원·달러·명·배럴 등 단위가 붙은 숫자, 네 자리 이상 숫자
- 넘어가는 것: 연도·오늘 날짜, 1~12 같은 작은 정수(순서·개수), 자료 숫자를 반올림한 값
- 자료에 없는 숫자는 "확인 필요"로 고쳐쓰기 때 AI에게 전달한다(지어낸 숫자 방지).
  두 자료 숫자의 차이·합처럼 계산해서 나온 숫자는 맞는 것으로 본다.
"""
import re

from ondo.config import kst_now

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%p|%|퍼센트|원|달러|명|배럴|가구|건|개국|배|조|억|만)?")


# '824만 4,308가구', '1억 2,000만 원'처럼 억·만 단위로 나눠 쓴 한 숫자(11-12 인구사회: '4,308가구'를 따로 읽어 '자료에 없는 숫자'로
# 잘못 경고 - 고쳐쓰기 때 AI에게 '확인 필요'로 넘어가 맞는 숫자를 건드릴 수 있음). 끝 조각 뒤가 년·월·일·%면 다른 숫자로 본다.
_PART = r"\d{1,3}(?:,\d{3})+|\d{1,4}"
_COMPOUND = re.compile(rf"(?<![\w.])(?:({_PART})\s*억\s*)?(?:({_PART})\s*만\s*)?(?:({_PART})(\s*천)?(?![\d,]|\s*(?:년|월|일|%|\.\d|만|억)))?"
                       r"\s*(원|달러|명|배럴|가구|건|개국)?")


def _compounds(text):
    """억·만으로 나눠 쓴 숫자 → [(시작, 끝, 원문, 값, 단위)]. 억·만 중 하나 이상과 끝 조각이 함께 있을 때만."""
    out = []
    for m in _COMPOUND.finditer(text or ""):
        eok, man, rest, thou, unit = m.groups()
        if sum(1 for x in (eok, man, rest) if x) < 2:
            continue                                     # 조각이 하나면 보통 숫자(아래 _NUM이 읽음)
        n = lambda x: int(x.replace(",", "")) if x else 0
        if n(rest) * (1000 if thou else 1) >= 10000 or (eok and man and n(man) >= 10000):
            continue
        out.append((m.start(), m.end(), m.group(0).strip(), float(n(eok) * 10 ** 8 + n(man) * 10 ** 4 + n(rest) * (1000 if thou else 1)), unit or ""))
    return out


def _numbers(text):
    out = []
    spans = []
    for st, en, raw, v, unit in _compounds(text):
        out.append((raw, v, 0, unit))
        spans.append((st, en))
    for m in _NUM.finditer(text or ""):
        if any(st <= m.start() < en for st, en in spans):
            continue
        whole, frac, unit = m.group(1), m.group(2), m.group(3) or ""
        try:
            v = float(whole.replace(",", "") + (f".{frac}" if frac else ""))
        except ValueError:
            continue
        out.append((m.group(0).strip(), v, len(frac or ""), unit))
    return out


def _matches(v, decimals, facts, pair_sums):
    for f in facts:
        if abs(f - v) < 1e-9 or round(f, decimals) == v or abs(f) >= 1 and abs(round(f) - v) < 1e-9:
            return True
        if v >= 1e5 and abs(f) >= 100 and _rounded_eq(abs(f) * 1e3, v):   # 천 단위 자료(원유 재고 409,760천 배럴 → 4억 976만 배럴)
            return True
        for scale in (100, 1e3, 1e4, 1e6, 1e8, 1e12):     # 단위 환산(예: 12,000,000 → 1,200만)
            if abs(f / scale - v) < 1e-9 or round(f / scale, decimals) == v:
                return True
    if v >= 1e5 and any(abs(s) >= 100 and _rounded_eq(abs(s) * 1e3, v) for s in pair_sums):
        return True                                      # 천 단위 자료끼리의 차이(재고 변화 865천 → 86만 5천 배럴)
    return any(round(s, decimals) == v for s in pair_sums)


def _rounded_eq(target, v):
    """v의 끝자리 0 개수만큼 target을 반올림해 같으면 참(4억 2,413만 배럴 = 424,134천 배럴을 만 단위로 줄임)."""
    iv = int(v)
    if iv != v:
        return False
    z = 0
    while iv and iv % 10 == 0 and z < 8:
        iv //= 10
        z += 1
    return round(target, -z) == v if z else abs(target - v) < 1e-6


def unverified(body_text, facts_text, limit=8):
    """자료에 없는 본문 숫자 목록(중복 제거, 최대 limit개)."""
    facts = [v for _, v, _, _ in _numbers(facts_text)]
    small = [f for f in facts if abs(f) < 1e7][:300]
    pair_sums = {abs(a - b) for a in small for b in small} | {a + b for a in small[:80] for b in small[:80]}
    today = kst_now()
    skip = {today.year, today.year - 1, today.month, today.day}
    out = []
    for raw, v, decimals, unit in _numbers(body_text):
        is_year = decimals == 0 and not unit and 1990 <= v <= today.year + 10
        if is_year or v in skip and not unit or (decimals == 0 and not unit and v <= 12):
            continue
        if decimals == 0 and not unit and v < 1000:
            continue                                     # 단위 없는 작은 정수는 개수·순서일 때가 많다
        if _matches(v, decimals, facts, pair_sums):
            continue
        if raw not in out:
            out.append(raw)
        if len(out) >= limit:
            break
    return out
