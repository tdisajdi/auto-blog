"""사용자가 말을 걸 때마다 공개 예약의 최근 실패·미리 대조 어긋남을 Claude 눈앞에 띄운다(2026-11-25).
왜: 823 영어판 예약이 04:20에 실패했는데 Claude는 3시간 뒤에야 알았다(텔레그램 알림은 사용자에게만 감).
깃허브 main의 lab/publish_schedule.json을 받아(로컬 사본은 낡았을 수 있음) 48시간 안의 실패와 '어긋남'만 보인다. 없으면 조용히."""
import datetime as dt
import json
import os
import subprocess
import sys


def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except Exception:
        prompt = ""
    if "task-notification" in prompt:
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=root, timeout=8, capture_output=True)
        raw = subprocess.run(["git", "show", "origin/main:lab/publish_schedule.json"], cwd=root, timeout=5,
                             capture_output=True, text=True).stdout
        items = json.loads(raw).get("items") or []
    except Exception:
        return
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for it in items:
        f = it.get("failed")
        if f and now - dt.datetime.fromisoformat(f.replace("Z", "+00:00")) < dt.timedelta(hours=48):
            out.append(f"- {it['id']} {it['kind']} 실패 {f}: {it.get('result', '')}")
        elif it.get("pre") == "어긋남" and not it.get("done"):
            out.append(f"- {it['id']} {it['kind']} 미리 대조 어긋남({it.get('pre_at')}), 예정 {it['at']}")
    if out:
        print("[공개 예약 문제 - 먼저 원인 확인·고친 뒤 사용자 말에 답할 때 함께 알림]")
        print("\n".join(out))


main()
