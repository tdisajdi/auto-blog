"""글끼리 비교 점검 실행(2026-11-24): 공개 한국어 글(공개 API) + 예약 임시글(lab/translate/*.ko.html).

  python site_pages/cross_check.py          문제 목록 출력(바꾸는 것 없음)
"""
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ondo.checks import crosspost  # noqa: E402


def published():
    u = "https://ondo99.com/wp-json/wp/v2/posts?per_page=50&lang=ko&_fields=id,title,content"
    try:
        ps = json.load(urllib.request.urlopen(u, timeout=30))
    except Exception as e:
        print("공개 글 못 받음:", type(e).__name__)
        return []
    return [(p["id"], p["title"]["rendered"], p["content"]["rendered"]) for p in ps
            if re.search(r"[가-힣]", p["title"]["rendered"])]


def drafts(ids=None):
    sched = json.load(open(os.path.join(ROOT, "lab", "publish_schedule.json"), encoding="utf-8"))
    want = ids or {i["id"] for i in sched.get("items", [])} | set(sched.get("held", {}).get("ids", []))
    out = []
    for f in glob.glob(os.path.join(ROOT, "lab", "translate", "*.ko.html")):
        pid = int(os.path.basename(f).split(".")[0])
        if pid in want:
            out.append((pid, "", open(f, encoding="utf-8").read()))
    return out


def main():
    pub = published()
    have = {p[0] for p in pub}
    posts = pub + [d for d in drafts() if d[0] not in have]
    probs = crosspost.check(posts)
    print(f"글 {len(posts)}편(공개 {len(pub)}) - 문제 {len(probs)}개")
    for kind, ids, what in probs:
        print(f"- [{kind}] {','.join(map(str, ids))}: {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
