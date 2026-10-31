"""교열부 2: 숫자 대조. 본문에 나온 숫자가 [사실 자료]에 있는지 코드가 확인한다.

- 대상: 소수점 숫자, %·%p, 원·달러·명·배럴 등 단위가 붙은 숫자, 네 자리 이상 숫자
- 넘어가는 것: 연도·오늘 날짜, 1~12 같은 작은 정수(순서·개수), 자료 숫자를 반올림한 값
- 자료에 없는 숫자는 "확인 필요"로 고쳐쓰기 때 AI에게 전달한다(지어낸 숫자 방지).
  두 자료 숫자의 차이·합처럼 계산해서 나온 숫자는 맞는 것으로 본다.
"""
import re

from ondo.config import kst_now

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%p|%|퍼센트|원|달러|명|배럴|가구|건|개국|배|조|억|만)?")


def _numbers(text):
    out = []
    for m in _NUM.finditer(text or ""):
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
        for scale in (100, 1e3, 1e4, 1e6, 1e8, 1e12):     # 단위 환산(예: 12,000,000 → 1,200만)
            if abs(f / scale - v) < 1e-9 or round(f / scale, decimals) == v:
                return True
    return any(round(s, decimals) == v for s in pair_sums)


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
