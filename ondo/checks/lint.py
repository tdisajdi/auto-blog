"""교열부 1: 코드로 잡을 수 있는 실수는 AI에게 맡기지 않고 코드가 바로 고치거나 지적한다.

fix_and_check(html) → (고친 html, 남은 문제 목록, 고친 것 목록)
- 고치는 것: 제목의 "Part 3:" 번호, 마크다운 흔적(**굵게**, ## 제목, ``` 울타리), AI가 넣은 <img>,
  똑같은 문장이 두 번 나온 것
- 지적만 하는 것(고쳐쓰기 때 AI에게 전달): N/A 언급, 확인할 수 없는 출처, 표 2개 이상, 분량 부족,
  제목(<h1>)·태그 줄 없음
"""
import re

MIN_CHARS = 4500          # 글자 수(태그 뺀 본문). 첫 실제 글이 약 5,700자로 짧다는 평가를 받았다
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
        issues.append(f"분량 부족: 본문 {body_chars}자 (최소 {MIN_CHARS}자) - 사실 자료로 설명을 더 채울 것")
    if not re.search(r"<h1[^>]*>.*?</h1>", h, flags=re.S):
        issues.append("제목(<h1>) 없음")
    if not re.search(r"태그:\s*\S", h):
        issues.append("마지막 태그 줄(태그: ...) 없음")
    dup = [s for s in _sentences(text) if text.count(s) > 1]
    if dup:
        issues.append(f"같은 문장 반복: '{dup[0][:30]}…'")
    return h, issues, fixes
