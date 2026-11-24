"""긴 기록 나눠 두기(2026-11-24, 사용자 질문 '옛 원문을 계속 두면 또 감당 안 되게 많아지지 않나').

  python site_pages/archive_logs.py [보존일수=14]
CHANGELOG.txt·lab/THINKING.txt에서 보존일수보다 오래된 항목(날짜로 시작하는 머리 줄 ~ 다음 머리 줄)을
lab/archive/<파일이름>-<YYYY-MM>.txt 로 옮긴다(지우지 않음, 달별 파일 맨 위에 붙임). 머리 줄 앞의 안내(적는 법)는 그대로.
날짜 없는 덩어리(옛 PROJECT_STATUS 원문 등)는 바로 앞 항목에 딸려 간다.
기록을 통째로 Read하면 토큰을 크게 씀(11-24: CHANGELOG 42만 자) - 본 파일은 최근 것만, 옛것은 grep -r lab/archive 로 찾는다.
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
    os.makedirs(os.path.join(ROOT, "lab", "archive"), exist_ok=True)
    base = os.path.splitext(os.path.basename(rel))[0]
    for month, ls in by_month.items():
        ap = os.path.join(ROOT, "lab", "archive", f"{base}-{month}.txt")
        prev = open(ap, encoding="utf-8").read() if os.path.exists(ap) else ""
        open(ap, "w", encoding="utf-8").write("\n".join(ls).rstrip("\n") + "\n" + (("\n" + prev) if prev else ""))
    out = head + [l for _d, ls in keep for l in ls]
    out.append(f"\n(이보다 옛 기록: lab/archive/{base}-YYYY-MM.txt - grep -r 로 찾기)")
    body = "\n".join(out)
    body = re.sub(r"(\n\(이보다 옛 기록: [^\n]*\))+", "", body.rstrip("\n")) + out[-1] + "\n"
    open(path, "w", encoding="utf-8").write(body)
    moved = sum(len(ls) for _d, ls in old)
    print(f"{rel}: {moved}줄을 lab/archive/{base}-*.txt로 옮김(남은 {len(body.splitlines())}줄)")
    return moved


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    for f in FILES:
        run(f, days)
