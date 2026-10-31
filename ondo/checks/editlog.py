"""편집 기록부: 글 한 편마다 무슨 일이 있었는지 전부 남긴다.

logs/2026-11/01-guide-overseas-vs-domestic-tax.json 처럼 저장된다.
- 단계마다(기획, 쓰기, 점검, 검토, 고쳐쓰기) 쓴 모델·키 번호·걸린 시간
- 모델을 바꾼 이유(예: 3.6-flash 429 → 다음 모델), 쓰기 방식을 바꾼 이유(한 번에 → 섹션별)
- 편집장 점수, 지적 사항, 코드가 고친 것, 실패 이유
저장소가 공개라서 키는 번호만 남긴다(이름표·키 값은 절대 기록하지 않음).

weekly_summary()는 주간 상태 점검 리포트에 붙는 요약을 만든다.
"""
import glob
import json
import os
import re
import time
from collections import Counter
from datetime import timedelta

from ondo.config import kst_now

LOG_DIR = "logs"


def _slug(text):
    return re.sub(r"[^0-9a-z가-힣]+", "-", str(text).lower()).strip("-")[:50] or "article"


class EditLog:
    def __init__(self, article_type, topic_id, title_seed, category=""):
        now = kst_now()
        self.started = time.time()
        self.data = {
            "article_type": article_type, "topic_id": topic_id, "title_seed": title_seed,
            "category": category, "started_at": now.isoformat(timespec="seconds"),
            "mode": None, "calls": [], "steps": [], "result": {},
        }
        self.path = os.path.join(LOG_DIR, now.strftime("%Y-%m"),
                                 f"{now:%d}-{_slug(article_type)}-{_slug(topic_id)}.json")
        if os.path.exists(self.path):   # 같은 날 같은 주제를 다시 쓰면 덮어쓰지 않고 번호를 붙인다
            base, n = self.path[:-5], 2
            while os.path.exists(f"{base}-{n}.json"):
                n += 1
            self.path = f"{base}-{n}.json"

    def call(self, step, model, key_no, status, reason="", seconds=0.0, chars=0):
        """AI 호출 한 번(성공이든 실패든)."""
        self.data["calls"].append({"step": step, "model": model, "key": key_no, "status": status,
                                   "reason": reason, "sec": round(seconds, 1), "chars": chars})

    def step(self, name, **info):
        """단계 하나의 결과(점수, 지적, 고친 것, 방식 전환 이유 등)."""
        info = {k: v for k, v in info.items() if v not in (None, "", [], {})}
        self.data["steps"].append({"step": name, "at": kst_now().strftime("%H:%M:%S"), **info})
        print(f"📒 [{name}] " + ", ".join(f"{k}={str(v)[:80]}" for k, v in info.items()))

    def set_mode(self, mode, reason=""):
        self.data["mode"] = mode
        self.step("쓰기 방식", mode=mode, reason=reason)

    def finish(self, **result):
        self.data["result"].update({k: v for k, v in result.items() if v is not None})
        self.data["minutes"] = round((time.time() - self.started) / 60, 1)
        return self.save()

    def models_used(self):
        """성공한 호출의 모델 이름(순서 유지, 중복 제거)."""
        seen = []
        for c in self.data["calls"]:
            if c["status"] == "ok" and c["model"] not in seen:
                seen.append(c["model"])
        return seen

    def summary_line(self):
        """텔레그램 한 줄 요약: 쓰기 방식·모델·고쳐쓰기 횟수·실패 호출 수."""
        mode = {"single": "한 번에 쓰기", "sections": "섹션별 나눠 쓰기"}.get(self.data["mode"], "-")
        rewrites = sum(1 for s in self.data["steps"] if re.fullmatch(r"고쳐쓰기 \d+", s["step"]))
        fails = sum(1 for c in self.data["calls"] if c["status"] != "ok")
        return (f"글쓰기: {mode} / 모델: {', '.join(self.models_used()) or '-'} / 고쳐쓰기 {rewrites}번"
                + (f" / 실패한 호출 {fails}번(자동 전환됨)" if fails else ""))

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            print(f"📒 편집 기록 저장: {self.path}")
        except OSError as e:
            print(f"⚠️ 편집 기록 저장 실패: {e}")
        return self.path


def _recent_logs(days):
    since = kst_now() - timedelta(days=days)
    out = []
    for p in glob.glob(os.path.join(LOG_DIR, "*", "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("started_at", "") >= since.isoformat(timespec="seconds"):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def weekly_summary(days=7):
    """주간 리포트용 요약 줄 목록. 기록이 없으면 빈 목록."""
    logs = _recent_logs(days)
    if not logs:
        return []
    lines = ["", f"📒 편집 기록 ({len(logs)}편)"]
    status = Counter(d.get("result", {}).get("status", "?") for d in logs)
    lines.append("  결과: " + ", ".join(f"{ {'publish': '발행', 'draft': '임시글', 'failed': '실패'}.get(k, k)} {v}편"
                                       for k, v in status.items()))
    modes = Counter(d.get("mode") or "-" for d in logs)
    if modes.get("sections"):
        lines.append(f"  섹션별 나눠 쓰기로 바뀐 글: {modes['sections']}편 (좋은 모델이 막혀서)")
    first, final = [], []
    for d in logs:
        scores = [s["score"] for s in d.get("steps", []) if s["step"].startswith("편집장") and "score" in s]
        if scores:
            first.append(scores[0])
            final.append(d.get("result", {}).get("score", scores[-1]) or scores[-1])
    if first:
        lines.append(f"  편집장 점수: 처음 평균 {sum(first) / len(first):.2f} → 최종 평균 {sum(final) / len(final):.2f}")
    calls = [c for d in logs for c in d.get("calls", [])]
    ok = Counter(c["model"] for c in calls if c["status"] == "ok")
    if ok:
        lines.append("  쓴 모델: " + ", ".join(f"{m} {n}회" for m, n in ok.most_common()))
    bad = Counter((c["model"], c["status"]) for c in calls if c["status"] != "ok")
    if bad:
        lines.append("  막힌 호출: " + ", ".join(f"{m} {s} {n}회" for (m, s), n in bad.most_common(4)))
    bad_keys = Counter(c["key"] for c in calls if c["status"] in ("403", "invalid_key"))
    if bad_keys:
        lines.append("  ⚠️ 거부된 키 번호: " + ", ".join(f"{k}번({n}회)" for k, n in bad_keys.most_common()))
    issues = Counter()
    for d in logs:
        for s in d.get("steps", []):
            for i in s.get("lint", []) + s.get("issues", []):
                issues[re.sub(r"[:：(].*", "", str(i)).strip()[:30]] += 1
    if issues:
        lines.append("  자주 나온 지적: " + " / ".join(f"{k}({n})" for k, n in issues.most_common(4)))
    fails = [d.get("result", {}).get("reason", "") for d in logs if d.get("result", {}).get("status") == "failed"]
    if any(fails):
        lines.append("  실패 이유: " + " / ".join(f for f in fails if f)[:200])
    return lines
