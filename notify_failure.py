"""작업이 중간에 멈추면 텔레그램으로 알린다 (깃허브 작업의 마지막 단계에서 실패했을 때만 실행).

예전엔 글쓰기가 실패해도 아무 연락이 없어서, 실행 기록을 직접 열어봐야 알 수 있었다(2026-10-31).
10분마다 도는 점검이 같은 이유로 계속 실패하면 알림이 쏟아지므로, 같은 작업은 3시간에 한 번만 알린다.
사용: python notify_failure.py "작업 이름"
"""
import os
import sys
from datetime import datetime, timedelta

from blog_engine import _kst_now, _load_json_file, _save_json_file, _telegram_send_message

ALERTS_FILE = "failure_alerts.json"
QUIET_HOURS = 3


def main():
    label = (sys.argv[1] if len(sys.argv) > 1 else "자동 작업").strip()
    now = _kst_now()
    state = _load_json_file(ALERTS_FILE, {}) or {}
    last = state.get(label)
    if last and now - datetime.fromisoformat(last) < timedelta(hours=QUIET_HOURS):
        print(f"ℹ️ '{label}' 실패 알림은 {QUIET_HOURS}시간 안에 이미 보냈습니다.")
        return
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    sent = _telegram_send_message(
        f"⚠️ '{label}' 작업이 중간에 멈췄어요 ({now:%m/%d %H:%M}).\n"
        "다음 점검 때 다시 시도해요. 계속 반복되면 Claude에게 이 메시지를 보여주세요.\n"
        + (f"실행 기록: {run_url}" if run_url else ""))
    if sent:
        state[label] = now.isoformat()
        _save_json_file(ALERTS_FILE, state)


if __name__ == "__main__":
    main()
