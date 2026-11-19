"""기준을 통과했는데 임시글로 남은 글을 공개로(2026-11-19 - 다시 쓰기 경로가 상태를 안 바꾸던 문제의 뒷정리).
  python site_pages/publish_passed.py <글번호>
안전장치: logs/ 안에 그 글(?p=번호)의 기록이 있고 마지막 '편집장 검토'가 통과(passed)일 때만 공개한다."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def passed_log(pid):
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
        if f"?p={pid}" not in str(res.get("url", "")) and str(pid) != str(res.get("post_id", "")):
            continue
        if best is None or str(d.get("started_at", "")) > str(best[1].get("started_at", "")):
            best = (f, d)
    if not best:
        return None, False, None
    reviews = [s for s in best[1].get("steps", []) if str(s.get("step", "")).startswith("편집장 검토")]
    return best[0], bool(reviews and reviews[-1].get("passed")), reviews[-1].get("score") if reviews else None


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
