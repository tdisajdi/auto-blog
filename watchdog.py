"""감시: 외부 알람(cron-job.org)이 멈췄는지 확인한다(2026-11-02).

cron-job.org가 10분마다 깃허브 수동 실행(tick)을 부르는데, 그쪽 계정·토큰 문제로 멈추면 아무도 모른다.
깃허브 자체 예약 실행(10분 점검의 예비)이 돌 때 이 파일이 "마지막 수동 실행(tick)이 언제였는지"를 깃허브 실행 기록에서
읽고, 1시간 넘게 없으면 텔레그램으로 알린다(6시간에 한 번). 기록을 읽기만 하고 아무것도 바꾸지 않는다.
사용: python watchdog.py   (깃허브 예약 실행 안에서만 의미 있음)
"""
import os
from datetime import datetime, timedelta, timezone

import requests

from blog_engine import _kst_now, _load_json_file, _save_json_file, _telegram_send_message

ALERTS_FILE = "failure_alerts.json"
LABEL = "외부 알람 멈춤 감시"
STALE_MINUTES = 60
QUIET_HOURS = 6


def last_dispatch_time():
    repo = os.environ.get("GITHUB_REPOSITORY", "tdisajdi/auto-blog")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/publish.yml/runs",
                     params={"event": "workflow_dispatch", "per_page": 1}, headers=headers, timeout=20)
    runs = r.json().get("workflow_runs", []) if r.ok else None
    if runs is None:
        print(f"ℹ️ 실행 기록을 못 읽음({r.status_code}) - 이번엔 건너뜀")
        return None
    if not runs:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))


def main():
    last = last_dispatch_time()
    if last is None:
        return
    gap = datetime.now(timezone.utc) - last
    print(f"🩺 마지막 외부 알람 실행: {gap.total_seconds() / 60:.0f}분 전")
    if gap < timedelta(minutes=STALE_MINUTES):
        return
    now = _kst_now()
    state = _load_json_file(ALERTS_FILE, {}) or {}
    prev = state.get(LABEL)
    if prev and now - datetime.fromisoformat(prev) < timedelta(hours=QUIET_HOURS):
        return
    hours = gap.total_seconds() / 3600
    sent = _telegram_send_message(
        f"⏰ 외부 알람(cron-job.org)이 {hours:.1f}시간째 깃허브를 안 부르고 있어요.\n"
        "그동안은 깃허브 자체 예약으로만 돌아서 승인 확인이 늦어질 수 있어요.\n"
        "cron-job.org에 들어가서 'ondo 10분 점검'이 켜져 있는지, 최근 실행이 실패(401/403)인지 확인해 주세요.\n"
        "401/403이면 깃허브 토큰(ondo-cron)이 만료·삭제된 거라 새로 만들어 넣어야 해요.")
    if sent:
        state[LABEL] = now.isoformat()
        _save_json_file(ALERTS_FILE, state)


if __name__ == "__main__":
    main()
