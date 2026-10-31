"""교열부 1: 코드로 잡을 수 있는 실수는 AI에게 맡기지 않고 코드가 바로 고치거나 지적한다.

fix_and_check(html) → (고친 html, 남은 문제 목록, 고친 것 목록)
- 고치는 것: 제목의 "Part 3:" 번호, 마크다운 흔적(**굵게**, ## 제목, ``` 울타리), AI가 넣은 <img>,
  똑같은 문장이 두 번 나온 것
- 지적만 하는 것(고쳐쓰기 때 AI에게 전달): N/A 언급, 표 빈칸('확인 필요' 등), 확인할 수 없는 출처,
  표 2개 이상, 너무 얇은 글, 비슷한 문장 반복, 같은 숫자를 너무 여러 번 씀, 제목(<h1>)·태그 줄 없음
- 분량은 "최소 몇 자"로 몰아붙이지 않는다. 2026-10-31 첫 글에서 4,500자 기준을 채우려고 같은 말을
  되풀이해 글이 오히려 나빠졌다. 정말 얇을 때(2,500자 미만)만 지적한다.
"""
import re

MIN_CHARS = 2500          # 이보다 짧으면 '얇은 글'. 분량을 채우라고 몰면 반복이 생겨서 낮게 둔다
VAGUE_SOURCES = ["외신 보도", "외신에 따르면", "전문가들은", "업계에 따르면", "관계자에 따르면", "알려졌다"]


def text_of(html):
    t = re.sub(r"<!--.*?-->", " ", html or "", flags=re.S)
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", text) if len(s.strip()) >= 25]


def fix_and_check(html):
    fixes, issues = [], []
    h = html or ""

    new = re.sub(r"```[a-zA-Z]*\n?|```", "", h)
    if new != h:
        fixes.append("코드 울타리(```) 제거")
        h = new
    new = re.sub(r"(<h[1-4][^>]*>\s*(?:🔸\s*)?)part\s*\d+\s*[:.\-)]?\s*", r"\1", h, flags=re.I)
    if new != h:
        fixes.append("제목의 Part 번호 제거")
        h = new
    new = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
    new = re.sub(r"(?m)^\s*#{2,4}\s+(.+)$", r"<h3>\1</h3>", new)
    if new != h:
        fixes.append("마크다운 표기를 HTML로 변환")
        h = new
    new = re.sub(r"<img[^>]*>", "", h)
    if new != h:
        fixes.append("AI가 넣은 <img> 제거(그림은 시스템이 넣음)")
        h = new

    # 똑같은 문단(<p>)이 두 번 나오면 뒤엣것 삭제
    seen = set()

    def _dedupe(m):
        key = text_of(m.group(0))
        if len(key) >= 25 and key in seen:
            fixes.append(f"중복 문단 삭제: {key[:30]}…")
            return ""
        seen.add(key)
        return m.group(0)
    h = re.sub(r"<p[^>]*>.*?</p>", _dedupe, h, flags=re.S)

    text = text_of(h)
    if re.search(r"(?<![A-Za-z])N/A(?![A-Za-z])|해당 없음으로 (기재|표시)", text):
        issues.append("N/A 언급: 자료에 값이 없는 항목은 아예 쓰지 말 것")
    for v in VAGUE_SOURCES:
        if v in text:
            issues.append(f"확인할 수 없는 출처 표현: '{v}' - 링크 있는 기사로 바꾸거나 삭제")
    n_tables = len(re.findall(r"<table", h, flags=re.I))
    if n_tables > 1:
        issues.append(f"표가 {n_tables}개: 표는 1개만, 나머지는 문장으로")
    body_chars = len(text_of(re.sub(r"<h1[^>]*>.*?</h1>", "", h, flags=re.S)))
    if body_chars < MIN_CHARS:
        issues.append(f"너무 얇음: 본문 {body_chars}자 - 같은 말을 늘리지 말고, 자료에 있는데 안 쓴 사실로 설명을 보탤 것")
    if not re.search(r"<h1[^>]*>.*?</h1>", h, flags=re.S):
        issues.append("제목(<h1>) 없음")
    if not re.search(r"태그:\s*\S", h):
        issues.append("마지막 태그 줄(태그: ...) 없음")
    dup = [s for s in _sentences(text) if text.count(s) > 1]
    if dup:
        issues.append(f"같은 문장 반복: '{dup[0][:30]}…'")
    pairs = similar_sentences(text)
    if pairs:
        tag = "" if len(pairs) >= 2 else SOFT
        issues.append(f"{tag}비슷한 문장 반복 {len(pairs)}쌍 - 한 번만 남기고 지울 것. 예: '{pairs[0][0][:40]}…' / '{pairs[0][1][:40]}…'")
    # 같은 숫자가 서로 다른 사실일 수 있다(2,000만 원 = ISA 납입 한도이자 금융소득종합과세 기준) → 참고만
    for raw, n in repeated_numbers(text):
        issues.append(f"{SOFT}같은 숫자 '{raw}'를 {n}번 씀 - 같은 사실을 되풀이한 것이면 줄일 것(다른 사실이면 그대로 둠)")
    cells = [c for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", h, flags=re.S) if text_of(c) in EMPTY_CELLS]
    if cells:
        issues.append(f"표에 빈칸 표시('{text_of(cells[0])}') {len(cells)}곳 - 값이 없는 줄·칸은 표에서 빼거나 표 구성을 바꿀 것")
    return h, issues, fixes


SOFT = "[참고] "     # 이 표시가 붙은 지적은 고쳐쓰기에 전달만 하고 발행을 막지는 않는다


def blocking(issues):
    return [i for i in issues if not i.startswith(SOFT)]


EMPTY_CELLS = {"확인 필요", "제공 안 됨", "정보 없음", "N/A", "-", "–", "없음(자료 없음)", "자료 없음", "미제공"}


def _grams(s, n=3):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def similar_sentences(text, threshold=0.55, limit=5):
    """뜻이 거의 같은 문장 쌍(글자 3개 묶음이 55% 이상 겹침). 반복으로 분량을 채운 흔적을 잡는다."""
    sents = _sentences(text)
    grams = [_grams(s) for s in sents]
    out = []
    for i in range(len(sents)):
        for j in range(i + 1, len(sents)):
            a, b = grams[i], grams[j]
            if a and b and len(a & b) / len(a | b) >= threshold:
                out.append((sents[i], sents[j]))
                if len(out) >= limit:
                    return out
    return out


def repeated_numbers(text, max_times=3):
    """단위가 붙은 같은 숫자(예: 22%, 250만 원)가 max_times번 넘게 나오면 [(숫자, 횟수)]."""
    from collections import Counter
    found = re.findall(r"\d[\d,]*(?:\.\d+)?\s*(?:%p|%|만\s?원|억\s?원|원|달러)", text)
    counts = Counter(re.sub(r"\s+", "", f) for f in found)
    return [(k, v) for k, v in counts.most_common() if v > max_times][:3]
