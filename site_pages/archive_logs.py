"""긴 기록 나눠 두기(2026-11-24, 사용자 질문 '옛 원문을 계속 두면 또 감당 안 되게 많아지지 않나').

  python site_pages/archive_logs.py [보존일수=14]
CHANGELOG.txt·lab/THINKING.txt에서 보존일수보다 오래된 항목(날짜로 시작하는 머리 줄 ~ 다음 머리 줄)을
archive/<파일이름>-<YYYY-MM>.txt 로 옮긴다(지우지 않음, 달별 파일 맨 위에 붙임). 머리 줄 앞의 안내(적는 법)는 그대로.
날짜 없는 덩어리(옛 PROJECT_STATUS 원문 등)는 바로 앞 항목에 딸려 간다.
기록을 통째로 Read하면 토큰을 크게 씀(11-24: CHANGELOG 42만 자) - 본 파일은 최근 것만, 옛것은 grep -r archive 로 찾는다.
"""
import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("CHANGELOG.txt", os.path.join("lab", "THINKING.txt"))
HEAD = re.compile(r"^\[?(20\d\d-\d\d-\d\d)")


def split(lines):
    """(안내 줄들, [(날짜, 줄들), ...]) - 첫 날짜 머리 줄 앞은 안내."""
    first = next((i for i, l in enumerate(lines) if HEAD.match(l)), len(lines))
    entries, cur = [], None
    for l in lines[first:]:
        m = HEAD.match(l)
        if m:
            cur = (m.group(1), [l])
            entries.append(cur)
        else:
            cur[1].append(l)
    return lines[:first], entries


def run(rel, keep_days, today=None):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return 0
    lines = open(path, encoding="utf-8").read().split("\n")
    head, entries = split(lines)
    cut = ((today or dt.date.today()) - dt.timedelta(days=keep_days)).isoformat()
    keep = [e for e in entries if e[0] >= cut]
    old = [e for e in entries if e[0] < cut]
    if not old:
        return 0
    by_month = {}
    for d, ls in old:
        by_month.setdefault(d[:7], []).extend(ls)
    os.makedirs(os.path.join(ROOT, "archive"), exist_ok=True)
    base = os.path.splitext(os.path.basename(rel))[0]
    for month, ls in by_month.items():
        ap = os.path.join(ROOT, "archive", f"{base}-{month}.txt")
        prev = open(ap, encoding="utf-8").read() if os.path.exists(ap) else ""
        open(ap, "w", encoding="utf-8").write("\n".join(ls).rstrip("\n") + "\n" + (("\n" + prev) if prev else ""))
    out = head + [l for _d, ls in keep for l in ls]
    out.append(f"\n(이보다 옛 기록: archive/{base}-YYYY-MM.txt - grep -r 로 찾기)")
    body = "\n".join(out)
    body = re.sub(r"(\n\(이보다 옛 기록: [^\n]*\))+", "", body.rstrip("\n")) + out[-1] + "\n"
    open(path, "w", encoding="utf-8").write(body)
    moved = sum(len(ls) for _d, ls in old)
    print(f"{rel}: {moved}줄을 archive/{base}-*.txt로 옮김(남은 {len(body.splitlines())}줄)")
    return moved


TAGS = {      # 색인 태그: 낱말이 항목에 있으면 붙임(11-24 사용자 '날짜·태그·번호로 찾게')
    "규칙": r"CLAUDE\.md|규칙|원칙", "결정": r"사용자 결정|DECISIONS|사용자 확인", "검증": r"검증|recheck",
    "고침": r"patch|고침", "공개": r"공개|예약|schedule", "글쓰기": r"작가|프롬프트|rules\.txt|뼈대|지시문",
    "디자인": r"디자인|표지|theme|마스코트|글꼴", "자료": r"자료|데이터|API|yfinance", "번역": r"영어판|번역",
    "워크플로": r"publish\.yml|워크플로|깃허브", "검색": r"검색|서치콘솔|SEO|사이트맵|색인|IndexNow",
    "실수": r"\bL\d+|실수|재발", "애드센스": r"애드센스|AdSense", "점수": r"점수|통과|검토",
}


def build_index():
    """archive/INDEX.txt: 항목마다 '번호 | 날짜 | 태그 | 글번호 | 파일:줄-줄 | 머리 줄'. 찾을 땐 이 목록을 grep하고 그 줄 범위만 읽는다."""
    adir = os.path.join(ROOT, "archive")
    rows = []
    for fn in sorted(os.listdir(adir)) if os.path.isdir(adir) else []:
        if not fn.endswith(".txt") or fn == "INDEX.txt":
            continue
        prefix = "C" if fn.startswith("CHANGELOG") else "T" if fn.startswith("THINKING") else fn[:1].upper()
        lines = open(os.path.join(adir, fn), encoding="utf-8").read().split("\n")
        starts = [i for i, l in enumerate(lines) if HEAD.match(l)]
        seen = {}
        for k, st in enumerate(starts):
            en = (starts[k + 1] if k + 1 < len(starts) else len(lines)) - 1
            d = HEAD.match(lines[st]).group(1)
            seen[d] = seen.get(d, 0) + 1
            subs = [i for i in range(st + 1, en + 1) if lines[i].startswith("■") or lines[i].startswith("--- ")]
            blocks = [(st, en, "")] if not subs else \
                [(st, subs[0] - 1, "")] * (subs[0] - st > 1) + [(b, (subs[j + 1] - 1 if j + 1 < len(subs) else en), chr(97 + j % 26)) for j, b in enumerate(subs)]
            for bs, be, sub in blocks:
                body = "\n".join(lines[bs:be + 1])
                tags = [t for t, pat in TAGS.items() if re.search(pat, body)]
                if "옛 PROJECT_STATUS" in body:
                    tags.append("옛상태문서")
                posts = sorted(set(re.findall(r"(?:\?p=|글 |patch:|recheck:)(\d{3,4})\b", body)) | set(re.findall(r"\b([5-9]\d\d)(?=[·편 ,)])", body)))[:8]
                what = next((l.strip()[:60] for l in lines[bs:be + 1] if "무엇:" in l), "")
                title = (lines[st][:40] + " " + (lines[bs][:50] if sub else "")).strip() + (" / " + what if what else "")
                rows.append(f"{prefix}-{d}-{seen[d]:02d}{sub} | {d} | {','.join(tags)} | {','.join(posts) or '-'} | "
                            f"archive/{fn}:{bs + 1}-{be + 1} | {title}")
    head = ["# 보관함 색인 - 저장만 하는 archive/의 목록(자동 생성: site_pages/archive_logs.py). 처음부터 읽지 말고 이 목록을 grep →",
            "# 그 항목의 '파일:줄-줄'만 Read(offset·limit). 칸: 번호 | 날짜 | 태그 | 글번호 | 위치 | 머리 줄", ""]
    os.makedirs(adir, exist_ok=True)
    open(os.path.join(adir, "INDEX.txt"), "w", encoding="utf-8").write("\n".join(head + rows) + "\n")
    print(f"archive/INDEX.txt: {len(rows)}항목")
    return rows


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    for f in FILES:
        run(f, days)
    build_index()
