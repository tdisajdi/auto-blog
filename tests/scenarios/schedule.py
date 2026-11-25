"""공개 예약 tick(백로그 97): 시간 창·5시간 간격·하루 2편·정각 피함·이미 공개 기록·dry·영어판 순서."""
import os, sys
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import datetime as dt
from site_pages import schedule_tick as st

T = lambda s: dt.datetime.fromisoformat(s + "+00:00")
items = [{"id": 1, "kind": "ko", "at": "2026-12-01T03:13:00Z"},
         {"id": 2, "kind": "ko", "at": "2026-12-01T09:47:00Z"},
         {"id": 1, "kind": "en", "at": "2026-12-01T06:07:00Z"},
         {"id": 3, "kind": "ko", "at": "2026-12-01T13:10:00Z"}]
it, _ = st.pick(items, T("2026-12-01T03:12:00")); assert it is None            # 아직 이름
it, _ = st.pick(items, T("2026-12-01T03:20:00")); assert (it["id"], it["kind"]) == (1, "ko")
_, n = st.pick(items, T("2026-12-01T03:30:00")); assert any("30분" in x for x in n), n
_, n = st.pick(items, T("2026-12-01T15:20:00")); assert any("시간 밖" in x for x in n[:1]), n
items[0]["done"] = "2026-12-01T03:20:00Z"
it, n = st.pick(items, T("2026-12-01T06:10:00")); assert (it["id"], it["kind"]) == (1, "en"), (it, n)
items[2]["done"] = "2026-12-01T06:10:00Z"
it, n = st.pick(items, T("2026-12-01T07:50:00")); assert it is None                # 2는 아직 이름
it, n = st.pick(items, T("2026-12-01T09:50:00")); assert it["id"] == 2
items[0]["done"] = "2026-12-01T07:00:00Z"                                          # 간격 5시간 미만이면 미룸
it, n = st.pick(items, T("2026-12-01T09:50:00")); assert it is None and any("5시간" in x for x in n), n
items[0]["done"] = "2026-12-01T03:20:00Z"; items[1]["done"] = "2026-12-01T09:50:00Z"
items.append({"id": 4, "kind": "ko", "at": "2026-12-01T03:00:00Z", "done": "2026-12-01T00:15:00Z"})
it, n = st.pick(items, T("2026-12-02T00:10:00")); assert it["id"] == 3              # 다음 날로 넘어간 3은 날 바뀌면 공개
it, n = st.pick(items, T("2026-12-01T13:20:00")); assert it is None                # 12~13Z
# 이미 공개된 글 기록 + dry는 공개 안 함
data = {"mode": "dry", "items": [{"id": 9, "kind": "ko", "at": "2026-12-01T03:13:00Z"},
                                 {"id": 8, "kind": "ko", "at": "2026-12-01T03:15:00Z"}]}
calls = []
stat = lambda pid: ("publish", "2026-12-01T03:14:00Z") if pid == 9 else ("draft", None)
ch = st.run(data, T("2026-12-01T03:20:00"), status=stat, publish=lambda pid: calls.append(pid) or 0)
assert ch and data["items"][0]["done"] == "2026-12-01T03:14:00Z" and calls == [] and not data["items"][1].get("done")
# live: 8은 앞 공개(9, 03:14)와 5시간 안 돼 미룸 → 08:20엔 공개
data["mode"] = "live"
st.run(data, T("2026-12-01T03:40:00"), status=stat, publish=lambda pid: calls.append(pid) or 0); assert calls == []
pub = {}
stat2 = lambda pid: ("publish", "2026-12-01T09:14:00Z") if pid == 9 or pub.get(pid) else ("draft", None)
st.run(data, T("2026-12-01T09:20:00"), status=stat2, publish=lambda pid: pub.__setitem__(pid, 1) or 0)
assert data["items"][1]["done"] and data["items"][1]["result"] == "공개", data
# 공개 실패는 failed로 남고 다시 시도 안 함
st._alert = lambda t: None
d2 = {"mode": "live", "items": [{"id": 7, "kind": "ko", "at": "2026-12-01T03:13:00Z"}]}
st.run(d2, T("2026-12-01T03:20:00"), status=lambda pid: ("draft", None), publish=lambda pid: 1)
assert d2["items"][0].get("failed") and st.pick(d2["items"], T("2026-12-01T09:20:00"))[0] is None
# 영어판: 한국어 공개 전이면 다음에(2), 실패(1)는 failed
d3 = {"mode": "live", "items": [{"id": 5, "kind": "en", "at": "2026-12-01T06:07:00Z"}]}
st.run(d3, T("2026-12-01T06:10:00"), status=stat, english=lambda pid: 2); assert not d3["items"][0].get("done") and not d3["items"][0].get("failed")
st.run(d3, T("2026-12-01T06:20:00"), status=stat, english=lambda pid: 0); assert d3["items"][0]["done"]
# 11-25: 영어판은 예정 6시간 안에 미리 대조, 어긋나면 한 번만 알림, 3시간 뒤 다시 대조
al = []; st._alert = lambda t: al.append(t)
d4 = {"mode": "live", "items": [{"id": 6, "kind": "en", "at": "2026-12-01T12:47:00Z"}]}
st.run(d4, T("2026-12-01T05:00:00"), status=stat, precheck=lambda pid: 1); assert "pre" not in d4["items"][0]   # 7시간 전 - 아직
st.run(d4, T("2026-12-01T07:00:00"), status=stat, precheck=lambda pid: 1); assert d4["items"][0]["pre"] == "어긋남" and len(al) == 1
st.run(d4, T("2026-12-01T08:00:00"), status=stat, precheck=lambda pid: 1); assert len(al) == 1                  # 3시간 안엔 다시 안 함
st.run(d4, T("2026-12-01T10:10:00"), status=stat, precheck=lambda pid: 1); assert len(al) == 1                  # 같은 문제 - 알림 한 번
st.run(d4, T("2026-12-01T13:20:00") - dt.timedelta(hours=3), status=stat, precheck=lambda pid: 0)
print("schedule ok")
