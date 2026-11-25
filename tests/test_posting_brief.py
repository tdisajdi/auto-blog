"""포스팅 지부장 지침서가 원본 규칙과 같은지(11-25 사용자 '빠짐없이, 변형없이'). 어긋나면: python site_pages/posting_brief.py"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "site_pages"))
import posting_brief as pb  # noqa: E402


def test_brief_matches_sources():
    assert pb.current() == pb.build(), "지침서 원문 칸이 원본 규칙과 다름 - python site_pages/posting_brief.py"


def test_every_writer_rule_verbatim():
    b = open(pb.BRIEF, encoding="utf-8").read()
    rules = [l[2:].strip() for l in open(os.path.join(pb.P, "rules.txt"), encoding="utf-8").read().split("\n") if l.startswith("- ")]
    assert rules and all(r in b for r in rules)


def test_manual_refs_exist():
    """0~6번이 가리키는 R·C·D 번호가 원문 칸에 실제로 있는지(목록이 바뀌어 번호가 밀리면 잡음)."""
    for path, _f in pb.ROLES:
        _refs_ok(open(path, encoding="utf-8").read())


def _refs_ok(b):
    head, auto = b[:b.index(pb.START)], b[b.index(pb.START):]
    for kind in "RCD":
        have = {int(n) for n in re.findall(rf"^{kind}(\d+)\. ", auto, re.M)}
        for a, z in re.findall(rf"{kind}(\d+)(?:~{kind}?(\d+))?", head):
            for n in range(int(a), int(z or a) + 1):
                assert n in have, f"{kind}{n} 없음"
