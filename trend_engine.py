"""
공용 검색 트렌드 모듈 (어느 카테고리에서든 키워드만 넘기면 쓸 수 있게 만듦).

- get_interest(keywords, geo, timeframe): 키워드별 구글 검색 관심도 요약
  {"키워드": {"latest": 최근값, "avg": 기간 평균, "momentum_pct": 최근 7개 평균이 기간 평균보다 몇 % 높은지}}
- get_trending_searches(geo): 지금 급상승 중인 검색어 목록

구글 트렌드는 공식 API가 아직 일반 공개되지 않아(2025.7 알파, 신청제), 아래 순서로 시도한다.
  1) trendspy (무료, 키 불필요, 개발 유지 중)
  2) pytrends (무료, 키 불필요, 2025.4 개발 중단 - 예비용)
  3) SerpApi (SERPAPI_KEY가 .env에 있을 때만, 월 무료 한도 있음)
모두 실패하면 빈 결과를 돌려준다. 이 모듈은 "있으면 참고하는 신호"라서, 실패해도
글 고르기·발행은 멈추면 안 된다. 같은 요청은 CACHE_TTL_HOURS 동안 다시 보내지 않는다.
구글 계정 로그인은 필요 없고, 절대 넣지 않는다.

점검: python etf_auto.py --check-trends (깃허브 Actions 수동 실행의 check_trends)
"""
import json
import os
import time
from datetime import datetime

import requests

CACHE_FILE = "trend_cache.json"
CACHE_TTL_HOURS = 20
REQUEST_GAP_SECONDS = 4
MAX_KEYWORDS_PER_REQUEST = 5   # 구글 트렌드 한 번 비교 최대 개수
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()


def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_get(key):
    entry = _load_cache().get(key)
    if not entry:
        return None
    try:
        age_h = (datetime.now() - datetime.fromisoformat(entry["at"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError):
        return None
    return entry.get("value") if age_h < CACHE_TTL_HOURS else None


def _cache_set(key, value):
    cache = _load_cache()
    cache[key] = {"at": datetime.now().isoformat(), "value": value}
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:
        pass


def _summarize(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    recent = vals[-7:]
    recent_avg = sum(recent) / len(recent)
    return {"latest": round(vals[-1], 1), "avg": round(avg, 1),
            "momentum_pct": round((recent_avg / avg - 1) * 100, 1) if avg > 0 else 0.0}


# ---------------- 관심도 제공자 ----------------

def _df_to_series(df, keywords):
    out = {}
    for kw in keywords:
        if df is not None and kw in getattr(df, "columns", []):
            out[kw] = [None if v != v else v for v in df[kw].tolist()]  # NaN 제거
    return out


def _interest_trendspy(keywords, geo, timeframe):
    from trendspy import Trends
    return _df_to_series(Trends().interest_over_time(keywords, timeframe=timeframe, geo=geo), keywords)


def _interest_pytrends(keywords, geo, timeframe):
    from pytrends.request import TrendReq
    py = TrendReq(hl="ko-KR", tz=540, timeout=(10, 25))
    py.build_payload(keywords, timeframe=timeframe, geo=geo)
    return _df_to_series(py.interest_over_time(), keywords)


def _interest_serpapi(keywords, geo, timeframe):
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY 없음")
    r = requests.get("https://serpapi.com/search.json", timeout=30, params={
        "engine": "google_trends", "q": ",".join(keywords), "geo": geo, "date": timeframe,
        "data_type": "TIMESERIES", "api_key": SERPAPI_KEY})
    r.raise_for_status()
    out = {kw: [] for kw in keywords}
    for point in (r.json().get("interest_over_time") or {}).get("timeline_data", []):
        for v in point.get("values", []):
            if v.get("query") in out:
                out[v["query"]].append(v.get("extracted_value"))
    return {k: v for k, v in out.items() if v}


_INTEREST_PROVIDERS = [("trendspy", _interest_trendspy), ("pytrends", _interest_pytrends), ("serpapi", _interest_serpapi)]


def get_interest(keywords, geo="KR", timeframe="today 3-m"):
    """키워드별 검색 관심도 요약. 실패한 키워드는 결과에서 빠진다(빈 dict일 수 있음).
    키워드 묶음마다 구글이 0~100으로 따로 맞추므로, 서로 다른 묶음끼리 latest/avg를
    비교하지 말고 각 키워드의 momentum_pct(자기 평균 대비 최근 변화)를 쓰는 게 안전하다."""
    keywords = [k for k in dict.fromkeys(str(k).strip() for k in keywords) if k]
    result = {}
    for i in range(0, len(keywords), MAX_KEYWORDS_PER_REQUEST):
        chunk = keywords[i:i + MAX_KEYWORDS_PER_REQUEST]
        key = f"interest|{geo}|{timeframe}|{'|'.join(chunk)}"
        cached = _cache_get(key)
        if cached is not None:
            result.update(cached)
            continue
        summary = {}
        for name, fn in _INTEREST_PROVIDERS:
            try:
                series = fn(chunk, geo, timeframe)
                summary = {kw: s for kw, s in ((kw, _summarize(v)) for kw, v in series.items()) if s}
                if summary:
                    print(f"📈 검색 관심도 조회 성공({name}): {', '.join(summary)}")
                    break
            except Exception as e:
                print(f"ℹ️ 검색 관심도 {name} 실패: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(REQUEST_GAP_SECONDS)
        if summary:
            _cache_set(key, summary)
        result.update(summary)
        time.sleep(REQUEST_GAP_SECONDS)
    return result


# ---------------- 급상승 검색어 제공자 ----------------

def _trending_trendspy_rss(geo):
    from trendspy import Trends
    return [getattr(t, "keyword", None) or str(t) for t in Trends().trending_now_by_rss(geo=geo)]


def _trending_trendspy(geo):
    from trendspy import Trends
    return [getattr(t, "keyword", None) or str(t) for t in Trends().trending_now(geo=geo, language="ko")]


def _trending_serpapi(geo):
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY 없음")
    r = requests.get("https://serpapi.com/search.json", timeout=30, params={
        "engine": "google_trends_trending_now", "geo": geo, "api_key": SERPAPI_KEY})
    r.raise_for_status()
    return [t.get("query") for t in r.json().get("trending_searches", []) if t.get("query")]


_TRENDING_PROVIDERS = [("trendspy-rss", _trending_trendspy_rss), ("trendspy", _trending_trendspy), ("serpapi", _trending_serpapi)]


def get_trending_searches(geo="KR"):
    key = f"trending|{geo}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    for name, fn in _TRENDING_PROVIDERS:
        try:
            items = [x for x in fn(geo) if x]
            if items:
                print(f"🔥 급상승 검색어 조회 성공({name}): {len(items)}개")
                _cache_set(key, items)
                return items
        except Exception as e:
            print(f"ℹ️ 급상승 검색어 {name} 실패: {type(e).__name__}: {str(e)[:120]}")
        time.sleep(REQUEST_GAP_SECONDS)
    return []


def check():
    """각 제공자가 실제로 데이터를 주는지 점검한다(캐시 무시)."""
    sample = ["S&P500", "나스닥", "환율"]
    for name, fn in _INTEREST_PROVIDERS:
        try:
            series = fn(sample, "KR", "today 3-m")
            print(f"✅ 관심도 {name}: " + ", ".join(f"{k}={_summarize(v)}" for k, v in series.items()) if series
                  else f"❌ 관심도 {name}: 빈 결과")
        except Exception as e:
            print(f"❌ 관심도 {name}: {type(e).__name__}: {str(e)[:150]}")
        time.sleep(REQUEST_GAP_SECONDS)
    for name, fn in _TRENDING_PROVIDERS:
        try:
            items = fn("KR")
            print(f"✅ 급상승 {name}: {len(items)}개 - {items[:8]}" if items else f"❌ 급상승 {name}: 빈 결과")
        except Exception as e:
            print(f"❌ 급상승 {name}: {type(e).__name__}: {str(e)[:150]}")
        time.sleep(REQUEST_GAP_SECONDS)
