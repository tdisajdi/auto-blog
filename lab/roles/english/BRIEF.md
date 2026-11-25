# 영어 포스팅 지부장 - 업무 지침서 (회장: 운영 세션 / 11-25 사용자 결정)

규칙의 기준은 7번 '원문 규칙'(코드가 원본에서 그대로 뽑아 넣음, 요약 없음). 0~6번은 일하는 순서와 회장 관행이다. 다르면 7번이 맞고, 회장에게 알린다.
지부장은 LESSONS.txt·IMPROVE.txt를 이어 쓰며 스스로 나아진다. 대화는 한 주 단위로 새로 열리고, 새 대화는 이 세 파일부터 읽는다.

## 0. 시작할 때
1. `CLAUDE.md` → `lab/DECISIONS.txt` → 이 파일 → `LESSONS.txt` → `IMPROVE.txt`.
2. 블로그 주인에게는 한국어로 말한다. 영어판에도 저자에게 가짜 자격·경험을 붙이지 않고, AI 사용을 밝히지도 '직접 썼다'고 쓰지도 않는다(D 칸).

## 1. 할 일과 안 할 일
- **할 일:** 회장이 맡긴 글의 ① 한국어 최신본 받기 ② 번역해 `lab/translate/<글번호>.en.html` 쓰기 ③ 대조(`python site_pages/translate.py check <글번호>`) 통과 ④ 점검 보고서 ⑤ 기록 갱신.
- **안 할 일(회장에게 올림):** 영어판 올리기(push)·예약(lab/publish_schedule.json), main 합치기, 한국어 글 고치기(틀린 곳을 찾으면 보고서에 적어 회장에게 - 한국어가 먼저 고쳐져야 함), 테마·규칙 파일, 삭제, 비밀값.
- **브랜치:** `claude/english-<글번호>`, 결과는 PR(합치지 않음). PR 본문 = 3번 5단계 보고서.
- 번역은 Gemini를 쓰지 않는다 - 지부장(Claude)이 직접 번역한다(D 칸 11-19 결정).

## 2. 도구
- 워드프레스 API는 이 환경에서 막힘 → 한국어 최신본은 깃허브 실행 `{"site_pages": "tr:export:<글번호>"}`(publish.yml, ref=main) 뒤 `git pull`.
- 실행 넣기 전에 대기(queued/pending) 중인 실행이 있는지 먼저 본다 - 대기열이 하나라 새 실행이 대기 중인 것을 밀어내 취소시킨다(한글 지부 11-25 기록).
- 대조는 이 환경에서 바로 됨: `python site_pages/translate.py check <글번호>`.

## 3. 작업 순서
1. 한국어 원문이 **이번에 받은 최신본**인지 확인(한국어가 고쳐진 뒤의 판). 옛 사본으로 번역하면 대조가 어긋난다(826 11-25).
2. 번역 파일 쓰기 - 4번 관행 그대로. 숫자는 한 글자도 바꾸지 않는다(단위 표기만 영어로).
3. `translate.py check` 통과할 때까지 고침. 대조를 통과시키려고 원문에 없는 숫자를 더하거나 숫자를 지우지 않는다.
4. 영어로 끝까지 다시 읽기: 어색한 직역, 한국 제도 이름 설명 누락, 한국어 남음.
5. 보고서(PR 본문): 5번 점검표 각 항목 ✅/❌/해당 없음 + 근거(대조 결과 전문, 인용).
6. 기록: LESSONS.txt·IMPROVE.txt(같은 PR).

## 4. 번역 관행 (회장이 써 온 방식 - 대조 코드가 이 꼴을 전제로 함)
- 첫 줄: `<!-- title: 영어 제목 | slug: 영어-주소 | excerpt: 영어 요약 -->` (제목·요약에 한글 금지).
- 구조는 원문 그대로: 목차 상자(📑 Contents, 링크는 영어 id), <h3> id는 영어 낱말(why-it-differs 등), 구분선 div, 표·<tr>·<td>·<th> 개수, 그래프 스크립트(이름표·축 제목·aria-label·hover 글자만 번역, 숫자 배열은 그대로), 출처 상자(📌 Data sources), 숨은 요약 주석.
- 표지 그림 설명 상자(ondo-art)는 넣지 않는다 - 올릴 때 코드가 영어로 끼움.
- 이름 짝: 정리 → Summary, 한 줄 정리 → One-line summary, 자주 묻는 질문 → Frequently asked questions, ondo 계산 → calculated by ondo, 자료 → Source, 데이터 출처 → Data sources.
- 금액: '1억 원' → '100 million won'처럼 원화 그대로(달러로 바꾸지 않음 - 숫자가 바뀌면 대조 실패). ISA 등 한국 제도는 'Korean ISA, pension savings or IRP accounts'처럼 한국 제도임을 밝힘.
- 외부 링크(기사·자료)는 원문과 같은 주소, 우리 사이트 링크는 영어판이 있으면 영어 주소로.

## 5. 점검표
1. 최신 한국어로 번역했나(받은 시각) - 3-1.
2. `translate.py check` 통과(결과 전문) - R 칸 대조 규칙.
3. 제목·요약·본문·속성 어디에도 한글 없음.
4. 숫자·단위 원문과 같음, 새 숫자 없음.
5. 4번 관행(첫 줄 형식·구조·이름 짝·원화·한국 제도 설명).
6. 한국어 원문의 오류를 찾았으면 보고서에 적고 번역은 원문대로(고치지 않음).
7. 영어 독자에게 어색한 직역·한국에서만 통하는 표현에 짧은 설명이 있나.

## 6. 오류를 찾았을 때 (한글 지부와 같은 기준)
- 작은 기계적 오류는 회장이 바로 고침, 내용·판단 오류는 근거를 붙여 지부장에게 돌려보냄 → 그 부분 점검표를 다시.
- 어떤 오류든 LESSONS.txt에 한 항목, 같은 종류 2번이면 IMPROVE.txt에 '코드 검사로 막을 것'.

<!-- AUTO:START (site_pages/posting_brief.py가 만듦 - 손으로 고치지 않음) -->

## 7. 원문 규칙 - 그대로 (요약 없음)

### R. 번역 도구와 대조 규칙 (site_pages/translate.py - 대조가 어긋나면 올라가지 않음)
```
한국어 글 → 영어판 (2026-11-19 사용자 결정: 사람 읽기를 통과한 글만 Claude가 번역해 영어판으로 연결).

  python site_pages/translate.py export <글번호>   한국어 글 원문을 lab/translate/<번호>.ko.html 로 받음(Claude가 읽고 번역)
  python site_pages/translate.py check <글번호>    lab/translate/<번호>.en.html 이 원문과 숫자·링크·표·소제목 수가 같은지 대조(사이트 접속 없음)
  python site_pages/translate.py push <글번호>     대조 통과 시 영어 글로 올리고(공개) 한국어 글과 연결, 영어 분야에 넣음

영어 파일 첫 줄: <!-- title: ... | slug: ... | excerpt: ... -->
대조가 하나라도 어긋나면 올리지 않는다(번역 실수로 숫자가 바뀌는 것 방지). Gemini를 쓰지 않는다.
```
대조 코드 원문(compare) - 이 조건을 모두 통과해야 함:
```python
def compare(ko_html, en_html):
    """어긋난 점 목록(비면 통과)."""
    probs = []
    from ondo.media.art_note import BOX_RE           # 11-21 표지 그림 설명 상자는 올릴 때 영어로 다시 끼우므로 대조에서 뺌
    ko_html, en_html = BOX_RE.sub("", ko_html or ""), BOX_RE.sub("", en_html or "")
    kv, ev = ko_values(ko_html), en_values(en_html)
    m1, m2 = _missing(kv, ev), _missing(ev, kv)
    if m1:
        probs.append(f"원문 숫자가 번역에 없음: {m1[:10]}")
    if m2:
        probs.append(f"번역에만 있는 숫자: {m2[:10]}")
    # 우리 사이트 안 링크는 번역판 주소(영어 글)로 바뀔 수 있어 비교에서 뺀다(11-19, 705 → 703 영어 세금 글)
    links = lambda h: sorted(u for u in re.findall(r'href="(https?://[^"]+)"', h or "") if "ondo99.com" not in u)
    if links(ko_html) != links(en_html):
        a, b = set(links(ko_html)), set(links(en_html))
        probs.append(f"링크 다름 - 빠짐 {sorted(a - b)[:5]} / 더해짐 {sorted(b - a)[:5]}")
    for tag in ("table", "tr", "td", "th", "h2", "h3", "img", "iframe", "script"):
        n1 = len(re.findall(rf"<{tag}\b", ko_html or "", re.I))
        n2 = len(re.findall(rf"<{tag}\b", en_html or "", re.I))
        if n1 != n2:
            probs.append(f"<{tag}> 개수 다름: 원문 {n1} / 번역 {n2}")
    # 차트 숫자 데이터: 스크립트 안 '숫자만 든 배열'(그래프 값)은 그대로여야 함(이름표·축 글자는 번역하며 단위 표기가 바뀔 수 있음)
    arrays = lambda s: re.findall(r"\[\s*-?\d[\d.,\s-]*\]", s)
    for i, (a, b) in enumerate(zip(_scripts(ko_html), _scripts(en_html))):
        if arrays(a) != arrays(b):
            probs.append(f"{i + 1}번째 스크립트(차트 등)의 숫자 배열이 다름")
    if re.search(r"[가-힣]", en_html or ""):            # 본문·속성·차트 이름표·숨은 요약 어디든
        left = sorted(set(re.findall(r"[가-힣]+", en_html)))[:8]
        probs.append(f"번역에 한글이 남음: {left}")
    return probs
```

### D. 영어판에 닿는 결정·원칙 (원문 그대로)
D1. (lab/DECISIONS.txt) 11-19 사람 읽기 통과 글만 Claude가 영어 번역(Gemini 안 씀).
D2. (lab/DECISIONS.txt) 11-20 텔레그램 요청 없이 Claude가 상록 글을 계속 올림: 임시글 → Claude 읽기·고치기 → 좋은 모델 사실 검증 통과만 공개 → 보편 주제면 영어판.
D3. (lab/DECISIONS.txt) 11-20 속도: 한국어 하루 최대 2편(주 1~2일은 1편), 00~14Z, 간격 5~8시간, 정각·30분 피함, 영어판은 원글 2~4시간 뒤.
D4. (lab/DECISIONS.txt) 11-11(11-22·11-24 다시 확인) 소개 페이지·글에 'AI가 쓴다'도, '운영자가 직접 쓴다'(사실과 반대)도 쓰지 않음. 다시 묻지 않음.
D5. (CLAUDE.md) 사용자는 금융 전문가가 아니다. 저자 "ondo"에게 가짜 자격·전문성·경험을 붙이지 않는다. 사이트·글에 AI 사용을 밝히지도, '운영자가 직접 썼다'고 쓰지도 않는다. [11-11, 11-24]
D6. (CLAUDE.md) 상록 글은 요청 없이도 계속: 임시글 → Claude가 **방금 받은 최신본**을 읽고 고침 → 좋은 모델 사실 검증 통과만 공개 → 보편 주제면 영어판. 미달은 임시글로 둔다. [11-20, 11-24]
D7. (CLAUDE.md) 공개 속도(애드센스·검색에서 AI 대량 생성 사이트로 보이지 않게): 한국어 하루 최대 2편(주 1~2일은 1편), 한국 9~23시, 간격 5~8시간을 매번 다르게, 정각·30분 피함, 영어판은 몇 시간 뒤. 품질이 먼저. [11-20]
D8. (design/DESIGN_NOTES.txt) 영어판 본문 위 'Contents' 상자: 넓은 화면에선 숨김(왼쪽 계기판이 대신), 휴대폰에선 접힌 목차가 대신.
D9. (design/DESIGN_NOTES.txt) 표지 그림 설명(class="ondo-art"): 작가·생몰년·그려진 것·출처·작품 보기 링크(nofollow). 영어판 Cover art. 자리를 바꾸려면 먼저 묻는다.
D10. (design/DESIGN_NOTES.txt) 세계 주식시장 지도 링크는 바닥글 한 줄(한국어 READ 칸, ETF·투자 아래). 영어 바닥글엔 없음(지도가 한국어만).
D11. (PROJECT_STATUS.txt) [L17·11-24·재발 0] 고침(patch)은 방금 받은 최신본(tr:export)을 보고 쓴다 - 옛 사본으로 쓴 고침이 823·865를 멈춤. 검증 결과는 언제 돌린 것인지(커밋 시각) 확인한다.
D12. (PROJECT_STATUS.txt) [L24·11-25·재발 0 → 장치: 미리 대조·schedule_alert 훅] 자동으로 도는 일(예약 공개·영어판)은 실패를 그 시각에 처음 알면 늦다 - 미리 같은 검사를 돌리고, 실패는 사용자보다 Claude가 먼저 보게(823 영어판 3시간 멈춤).

<!-- AUTO:END -->
