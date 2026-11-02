"""감시: 외부 알람이 1시간 넘게 안 부르면 알림(6시간에 한 번), 최근에 불렀으면 조용히."""
import os, sys
from datetime import datetime, timedelta, timezone
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import watchdog as wd
sent = []
wd._telegram_send_message = lambda text, *a, **k: sent.append(text) or 1


class R:
    ok, status_code = True, 200

    def __init__(self, minutes_ago):
        t = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._j = {"workflow_runs": [{"created_at": t}]}

    def json(self):
        return self._j


wd.requests.get = lambda *a, **k: R(15)
wd.main()
assert not sent, sent
wd.requests.get = lambda *a, **k: R(130)
wd.main()
assert len(sent) == 1 and "cron-job.org" in sent[0] and "2.2시간" in sent[0], sent
wd.main()
assert len(sent) == 1, "6시간 안에 같은 알림은 한 번만"
print("watchdog ok")
