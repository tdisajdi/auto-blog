"""기준을 통과했는데 임시글로 남은 글을 공개로(2026-11-19 - 다시 쓰기 경로가 상태를 안 바꾸던 문제의 뒷정리).
  python site_pages/publish_passed.py <글번호>
안전장치: logs/ 안에 그 글(?p=번호)의 기록이 있고 마지막 '편집장 검토'가 통과(passed)이며,
그 판의 사실 검증(본·확인)을 좋은 모델이 했을 때만 공개한다(11-19)."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def passed_log(pid, slug=None):
    """그 글의 기록 중 가장 늦게 시작한 것(started_at) - 깃허브에선 파일 시각이 모두 같아 시각 정렬은 못 씀."""
    best = None
    for f in glob.glob(os.path.join(ROOT, "logs", "*", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        res = d.get("result") or {}
        if not isinstance(res, dict):
            continue
        url = str(res.get("url", ""))
        if (f"?p={pid}" not in url and str(pid) != str(res.get("post_id", ""))
                and not (slug and url.rstrip("/").endswith("/" + slug))):   # 공개 글은 주소가 slug로 남음(11-19)
            continue
        if best is None or str(d.get("started_at", "")) > str(best[1].get("started_at", "")):
            best = (f, d)
    if not best:
        return None, False, None
    reviews = [s for s in best[1].get("steps", []) if str(s.get("step", "")).startswith("편집장 검토")]
    ok = bool(reviews and reviews[-1].get("passed"))
    if ok and not strong_fact(best[1], reviews[-1]["step"].split()[-1]):
        print("주의: 통과 기록이지만 사실 검증(본·확인)을 좋은 모델이 하지 않음 - 통과로 치지 않음(11-19 규칙)")
        ok = False
    return best[0], ok, reviews[-1].get("score") if reviews else None


def strong_fact(d, round_no):
    """그 판의 본 검토(N)와 확인 검토(N+10) 사실 검증이 모두 좋은 모델로 끝났나(11-19: 가벼운 모델 통과 막기)."""
    from ondo.writing import llm
    strong = set(llm.models_for("strong_only"))
    calls = [c for c in d.get("calls") or [] if isinstance(c, dict) and c.get("status") == "ok"]
    for r in (str(round_no), str(int(round_no) + 10)):
        done = [c for c in calls if str(c.get("step", "")).startswith(f"검토 {r}(사실 검증)")]
        if not done or done[-1].get("model") not in strong:
            return False
    return True


def main(pid):
    import requests
    import blog_engine as be
    f, ok, score = passed_log(pid)
    if not ok:
        print(f"공개 안 함: 통과 기록 없음({f}, 점수 {score})")
        return 1
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}"
    r = requests.post(base, headers=h, data={"status": "publish"}, timeout=30)
    j = r.json() if r.ok else {}
    print(f"공개: {r.status_code} {j.get('status')} {j.get('URL')} (근거 {os.path.basename(f)}, 점수 {score})")
    return 0 if j.get("status") == "publish" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 and sys.argv[1].isdigit() else (print(__doc__) or 1))
