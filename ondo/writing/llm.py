"""편집국 전용 Gemini 호출기.

- 등급(tier): "strong"(글쓰기·고쳐쓰기용 좋은 모델, 막히면 넉넉한 모델로 내려감) /
  "strong_only"(좋은 모델만 - 한 번에 쓰기용) / "fast"(기획·검토용 넉넉한 모델).
  모델을 내려갈 때는 그 사실과 이유를 편집 기록부에 남긴다.
- 키는 순서대로 돌리되 start_key로 시작 키를 바꿀 수 있다(섹션별로 쓸 때 키를 나눠 쓰기 위해).
- 403·잘못된 키는 이번 실행 동안 빼고, 텔레그램으로 어느 키인지 알린다(ondo/keys.py).
- 결과: Result(text, model, key_no, limited, truncated). text가 None이면 실패.
  limited=True는 "횟수 한도 때문에 실패", truncated=True는 "답이 길이 한도에서 잘림".

모델 순서는 .env로 바꿀 수 있다: WRITER_MODEL_PRIORITY(좋은 모델), GEMINI_MODEL_PRIORITY(넉넉한 모델).
"""
import os
import time
from dataclasses import dataclass

import requests

from ondo import keys

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_STRONG = ["gemini-3.6-flash", "gemini-3.5-flash"]
DEFAULT_FAST = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
TIMEOUT = 240
PAUSE_AFTER_OK = 3            # 같은 키를 연달아 두드리지 않도록 잠깐 쉼

_excluded = set()             # 이번 실행 동안 뺀 키(403·잘못된 키)
_dead_models = set()          # 이번 실행 동안 없는 모델(404)


@dataclass
class Result:
    text: object = None
    model: str = ""
    key_no: int = 0
    limited: bool = False
    truncated: bool = False


def _env_list(name):
    return [m.strip() for m in os.environ.get(name, "").split(",") if m.strip()]


def models_for(tier):
    strong = _env_list("WRITER_MODEL_PRIORITY") or DEFAULT_STRONG
    fast = _env_list("GEMINI_MODEL_PRIORITY") or DEFAULT_FAST + DEFAULT_STRONG
    if tier == "strong_only":          # 한 번에 쓰기: 좋은 모델만. 막히면 섹션별 나눠 쓰기로 넘어간다
        order = strong
    elif tier == "strong":
        order = strong + [m for m in fast if m not in strong]
    else:
        order = fast
    return [m for m in order if m not in _dead_models]


def _post(url, payload, key):
    """실제 인터넷 호출(시험에서는 이 함수를 가짜로 바꿔 끼운다)."""
    return requests.post(url, json=payload, headers={"x-goog-api-key": key}, timeout=TIMEOUT)


def _text_of(data):
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text, cand.get("finishReason", "")


def call(prompt, *, step, log=None, tier="fast", json_out=False, thinking=0, start_key=0,
         max_tokens=65536, models=None):
    """프롬프트 하나를 보낸다. 모델 순서대로, 모델마다 키를 돌려가며 시도."""
    all_keys = [(no, k) for no, _label, k in keys.gemini_keys()]
    if not all_keys:
        print("🛑 GEMINI_API_KEY가 비어 있어요")
        return Result()
    models = models or models_for(tier)
    first_model = models[0] if models else ""
    saw_limit = saw_truncated = False

    for model in models:
        if model in _dead_models:
            continue
        cfg = {"maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": thinking}}
        if json_out:
            cfg["responseMimeType"] = "application/json"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        n = len(all_keys)
        order = [all_keys[(start_key + i) % n] for i in range(n)]
        for key_no, key in order:
            if key in _excluded:
                continue
            t0 = time.time()
            status, reason, text, finish = "error", "", None, ""
            try:
                r = _post(API.format(model=model), payload, key)
                if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
                    cfg.pop("thinkingConfig")      # 이 모델은 생각 설정을 안 받음 → 빼고 같은 키로 한 번 더
                    r = _post(API.format(model=model), payload, key)
                if r.status_code == 200:
                    text, finish = _text_of(r.json())
                    status = "ok" if text.strip() else "empty"
                    if finish == "MAX_TOKENS":
                        status, reason = "truncated", "답이 길이 한도에서 잘림"
                else:
                    status, reason = str(r.status_code), r.text[:160].replace("\n", " ")
            except requests.exceptions.Timeout:
                status, reason = "timeout", f"{TIMEOUT}초 안에 답이 없음"
            except Exception as e:
                status, reason = "error", f"{type(e).__name__}: {str(e)[:120]}"
            sec = time.time() - t0
            if log:
                log.call(step, model, key_no, status, reason, sec, len(text or ""))

            if status == "ok":
                if model != first_model and log:
                    log.step("모델 전환", from_model=first_model, to_model=model,
                             reason="앞 모델이 막힘(위 호출 기록 참고)", for_step=step)
                try:
                    from blog_engine import _record_api_call
                    _record_api_call(model)
                except Exception:
                    pass
                time.sleep(PAUSE_AFTER_OK)
                return Result(text, model, key_no)
            print(f"⚠️ [{step}] {model} 키{key_no}: {status} {reason[:80]}")
            if status == "429":
                saw_limit = True
                continue                           # 다음 키(다른 계정)로
            if status == "truncated":
                saw_truncated = True
                break                              # 같은 모델은 또 잘림 → 다음 모델로
            problem = keys.classify_error(int(status) if status.isdigit() else 0, reason)
            if problem:
                _excluded.add(key)
                keys.alert_key_problem(key, problem, reason)
                continue
            if status == "404":
                _dead_models.add(model)
                break
            if status == "400":
                break                              # 요청 형식을 이 모델이 안 받음 → 다음 모델
            # 5xx·timeout·빈 답 → 다음 키
    return Result(limited=saw_limit, truncated=saw_truncated)


def parse_json(text):
    """```json 울타리나 앞뒤 잡글이 있어도 JSON을 꺼낸다. 실패하면 None."""
    import json
    import re
    if not text:
        return None
    t = re.sub(r"```[a-zA-Z]*\n?|```", "", text).strip()
    for a, b in (("{", "}"), ("[", "]")):
        i, j = t.find(a), t.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    return None
