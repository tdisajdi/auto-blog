import sys
import time
import requests
from datetime import datetime
import re
import random
import pandas as pd
import os
import json
import urllib.parse
import yfinance as yf
import FinanceDataReader as fdr  # <-- 이거 한 줄 추가
from io import StringIO
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from dotenv import load_dotenv

# 계정 정보/API 키는 코드에 직접 넣지 않고 .env 파일에서 불러옵니다.
# 같은 폴더에 .env 파일을 만들고 아래 형식으로 채워주세요:
#   TISTORY_ID=your_email@example.com
#   TISTORY_PW=your_password
#   BLOG_NAME=https://yourblog.tistory.com
#   GEMINI_API_KEY=your_api_key
# .env 파일은 절대 깃허브 등 외부에 올리지 마세요 (.gitignore에 추가 권장).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# [중요] blog_engine.py는 모듈 import 시점에 BLOG_CATEGORY 환경변수를 읽어
# article_state.json 등 카테고리별 상태 파일 이름을 정한다(예: etf_article_state.json).
# 워크플로우에서 이미 BLOG_CATEGORY=etf를 설정해주지만, 로컬에서 직접 실행할
# 때도 같은 이름을 쓰도록 여기서도 기본값을 정해둔다(이미 설정돼 있으면 안 건드림).
os.environ.setdefault("BLOG_CATEGORY", "etf")

from blog_engine import (
    WP_SITE_URL, GEMINI_API_KEYS, API_USAGE_LOG_FILE, _load_json_file, _save_json_file, _load_cache,
    _get_cached_record, _set_cached_record, get_gemini_response, _check_publish_interval,
    _clean_stale_sessions, _telegram_send_message, _telegram_get_updates, _telegram_update_is_authorized,
    _telegram_answer_callback, _telegram_edit_text, _load_state, _discover_due, _mark_discovered,
)

TISTORY_ID = os.environ.get("TISTORY_ID")
TISTORY_PW = os.environ.get("TISTORY_PW")
BLOG_NAME = os.environ.get("BLOG_NAME")

# [신규] 발행 플랫폼 선택. .env에 PLATFORM=tistory 또는 PLATFORM=wordpress로 지정.
# 지정 안 하면 기존과 동일하게 티스토리로 동작(하위 호환).
PLATFORM = os.environ.get("PLATFORM", "tistory").strip().lower()

# [신규] 차트 렌더링 방식 선택. .env에 CHART_MODE=script 또는 CHART_MODE=image로 지정.
CHART_MODE = os.environ.get("CHART_MODE", "script").strip().lower()

# [수정] PLATFORM 값에 따라 필요한 환경변수가 다르므로 분기해서 검증한다.
if PLATFORM == "wordpress":
    _missing = [name for name, val in [
        ("WP_SITE_URL", WP_SITE_URL),
    ] if not val]
else:
    _missing = [name for name, val in [
        ("TISTORY_ID", TISTORY_ID), ("TISTORY_PW", TISTORY_PW), ("BLOG_NAME", BLOG_NAME),
    ] if not val]
if not GEMINI_API_KEYS:
    _missing.append("GEMINI_API_KEY")
if _missing:
    raise SystemExit(
        f"❌ .env 파일에 다음 값이 없습니다: {', '.join(_missing)}\n"
        f"   같은 폴더에 .env 파일을 만들고 해당 값을 채워주세요.\n"
        f"   GEMINI_API_KEY는 쉼표로 여러 개 넣을 수 있습니다: GEMINI_API_KEY=키1,키2\n"
        f"   현재 PLATFORM={PLATFORM} 기준으로 필요한 값입니다. (PLATFORM=tistory 또는 wordpress)"
    )


INVESTING_ETF_SLUGS = {
    "QQQ": "powershares-qqqq",
    "SPY": "spdr-s-p-500",
    "IVV": "ishares-core-s-p-500",
    "VOO": "vanguard-s-p-500",
    "VTI": "vanguard-total-stock-mkt",
    "IWM": "ishares-russell-2000",
    "EFA": "ishares-msci-eafe-index",
    "EEM": "ishares-msci-emg-markets",
    "GLD": "spdr-gold-shares",
    "SLV": "ishares-silver-trust",
    "TQQQ": "proshares-trust-ultrapro-qqq",
    "QQQM": "qqqm",
}
INVESTING_BASE = "https://kr.investing.com/etfs"
INVESTING_SEARCH = "https://kr.investing.com/search/?q="

# 매일 후보를 고르는 ETF 목록.
# - theme: 주제. 최근 글에 같은 주제가 몰리면 그 주제는 후보에서 뺀다(주제 쏠림 방지).
# - group: 같은 지수/자산 묶음. 재사용 금지 기간을 묶음 단위로 적용해서,
#   SPY 글 직후에 VOO나 TIGER 미국S&P500 글이 나오는 "사실상 같은 글"을 막는다.
# 데이터가 안 받아지는 티커는 발굴 단계에서 자동으로 건너뛴다. 목록 점검은
# `python etf_auto.py --check-universe` (깃허브 Actions 수동 실행의 check_universe).
ETF_UNIVERSE = {
    "SPY": {"theme": "미국 대표지수", "group": "S&P500"},
    "VOO": {"theme": "미국 대표지수", "group": "S&P500"},
    "IVV": {"theme": "미국 대표지수", "group": "S&P500"},
    "QQQ": {"theme": "미국 대표지수", "group": "나스닥100"},
    "QQQM": {"theme": "미국 대표지수", "group": "나스닥100"},
    "VTI": {"theme": "미국 대표지수", "group": "미국 전체시장"},
    "DIA": {"theme": "미국 대표지수", "group": "다우30"},
    "IWM": {"theme": "미국 대표지수", "group": "러셀2000"},
    "SCHD": {"theme": "배당", "group": "미국 배당다우존스"},
    "VYM": {"theme": "배당", "group": "미국 고배당"},
    "DGRO": {"theme": "배당", "group": "미국 배당성장"},
    "JEPI": {"theme": "커버드콜", "group": "JEPI"},
    "JEPQ": {"theme": "커버드콜", "group": "JEPQ"},
    "QYLD": {"theme": "커버드콜", "group": "QYLD"},
    "XYLD": {"theme": "커버드콜", "group": "XYLD"},
    "TLT": {"theme": "채권", "group": "미국 장기국채"},
    "IEF": {"theme": "채권", "group": "미국 중기국채"},
    "SHY": {"theme": "채권", "group": "미국 단기국채"},
    "BND": {"theme": "채권", "group": "미국 종합채권"},
    "LQD": {"theme": "채권", "group": "미국 회사채"},
    "HYG": {"theme": "채권", "group": "미국 하이일드"},
    "XLK": {"theme": "섹터", "group": "기술"},
    "XLF": {"theme": "섹터", "group": "금융"},
    "XLE": {"theme": "섹터", "group": "에너지"},
    "XLV": {"theme": "섹터", "group": "헬스케어"},
    "SMH": {"theme": "섹터", "group": "반도체"},
    "GLD": {"theme": "원자재", "group": "금"},
    "SLV": {"theme": "원자재", "group": "은"},
    "DBC": {"theme": "원자재", "group": "원자재 종합"},
    "EFA": {"theme": "해외 주식", "group": "선진국"},
    "EEM": {"theme": "해외 주식", "group": "신흥국"},
    "VWO": {"theme": "해외 주식", "group": "신흥국"},
    "EWJ": {"theme": "해외 주식", "group": "일본"},
    "INDA": {"theme": "해외 주식", "group": "인도"},
    "TQQQ": {"theme": "레버리지", "group": "나스닥100 3배"},
    # 국내 상장: 같은 지수의 미국 ETF와 group을 공유한다.
    "069500.KS": {"theme": "국내 주식", "group": "코스피200", "name": "KODEX 200"},
    "360750.KS": {"theme": "미국 대표지수", "group": "S&P500", "name": "TIGER 미국S&P500"},
    "133690.KS": {"theme": "미국 대표지수", "group": "나스닥100", "name": "TIGER 미국나스닥100"},
    "458730.KS": {"theme": "배당", "group": "미국 배당다우존스", "name": "TIGER 미국배당다우존스"},
    "132030.KS": {"theme": "원자재", "group": "금", "name": "KODEX 골드선물(H)"},
    "148070.KS": {"theme": "채권", "group": "한국 국고채10년", "name": "KIWOOM 국고채10년"},
}

RECENT_THEME_WINDOW = 7          # 최근 이 편수 안에서
MAX_SAME_THEME_IN_WINDOW = 2     # 같은 주제가 이만큼 있으면 그 주제는 후보에서 제외
RECENT_TYPE_WINDOW = 6           # 글 종류 비율을 볼 최근 편수
COMPARISON_TARGET_SHARE = 0.34   # 최근 글 중 비교 글 비율이 이보다 낮으면 비교 글을 만든다
_TICKER_REPLY_STOPWORDS = {"OK", "YES", "NO", "GO", "HI", "THX", "TY"}
EXPLAINER_TYPE_WINDOW = 10                               # 글 종류 비율을 볼 최근 편수
EXPLAINER_TARGET_SHARE = {"guide": 0.2, "issue": 0.15}   # 이 비율보다 적으면 가이드/이슈 글을 추천
EXPLAINER_MIN_HISTORY = 3                                # 기록이 이보다 적으면 ETF 글부터


# 국내 ETF 자동 발굴: 네이버 금융 ETF 목록에서 거래대금 상위 종목을 그날의 후보에 더한다.
# 이름으로 주제/지수 묶음을 정해서, 같은 지수의 다른 운용사 상품(예: TIGER·KODEX·ACE
# S&P500)끼리 비교 글을 만들 수 있게 한다. 레버리지·인버스는 금융 글 위험이 커서 제외.
KR_DYNAMIC_TOP_N = 40
_KR_EXCLUDE_PATTERN = r"레버리지|인버스|2X|곱버스|합성.*인버스"
_KR_UNDERLYING_RULES = [
    # (이름 패턴, 묶음, 주제) - 위에서부터 먼저 맞는 것을 쓴다
    (r"S&P\s?500|에스앤피500", "S&P500", "미국 대표지수"),
    (r"나스닥\s?100|NASDAQ\s?100", "나스닥100", "미국 대표지수"),
    (r"배당다우존스", "미국 배당다우존스", "배당"),
    (r"다우존스\s?30|다우30", "다우30", "미국 대표지수"),
    (r"테크\s?TOP\s?10|빅테크|매그니피센트|M7", "미국 빅테크", "섹터"),
    (r"반도체", "반도체", "섹터"),
    (r"2차전지|이차전지", "2차전지", "섹터"),
    (r"골드|금현물|금선물", "금", "원자재"),
    (r"은선물|실버", "은", "원자재"),
    (r"CD.{0,3}금리|KOFR|SOFR|머니마켓|MMF|단기금리|초단기", "파킹형(초단기금리)", "채권"),
    (r"미국채\s?30년|미국\s?30년|30년국채", "미국 장기국채", "채권"),
    (r"미국채\s?10년|미국\s?10년", "미국 중기국채", "채권"),
    (r"국고채\s?10년", "한국 국고채10년", "채권"),
    (r"국고채\s?30년", "한국 국고채30년", "채권"),
    (r"코스닥\s?150", "코스닥150", "국내 주식"),
    (r"(^|\s)200(TR)?$|코스피\s?200|KOSPI\s?200", "코스피200", "국내 주식"),
]
_KR_CATEGORY_THEME = {"1": "국내 주식", "2": "섹터", "4": "해외 주식", "5": "원자재", "6": "채권"}
_DYNAMIC_UNIVERSE = {}


def _classify_kr_etf(name, category=None):
    """국내 ETF 이름(과 네이버 분류)으로 (주제, 묶음)을 정한다. 제외 대상이면 None."""
    name = str(name or "")
    if str(category) == "3" or re.search(_KR_EXCLUDE_PATTERN, name, flags=re.IGNORECASE):
        return None
    underlying = next(((g, th) for pat, g, th in _KR_UNDERLYING_RULES
                       if re.search(pat, name, flags=re.IGNORECASE)), None)
    if re.search(r"커버드콜|프리미엄|타겟위클리|위클리|옵션", name):
        return "커버드콜", f"커버드콜:{underlying[0] if underlying else name}"
    if underlying:
        return underlying[1], underlying[0]
    if re.search(r"배당", name):
        return "배당", name
    return _KR_CATEGORY_THEME.get(str(category), "기타"), name


_KR_ETF_NAMES = {}


NAVER_KR_INFO_URL = "https://m.stock.naver.com/api/stock/{code}/integration"


def _naver_kr_pairs(data):
    """네이버 모바일 종목 데이터(JSON)에서 {'key': 이름, 'value': 값} 묶음을 모두 모아 {이름: 값}으로."""
    out = {}

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("key"), str) and "value" in x:
                out.setdefault(x["key"], str(x["value"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return out


def _naver_kr_info(code):
    """국내 ETF 펀드보수·기초지수 등(2026-11-08). 깃허브 서버에선 네이버 금융 화면에 '보수'가 안 나와(요소 없음) 국내 운용사
    비교 글의 핵심인 보수가 비었다 → check_sources 진단으로 열리는 것을 확인한 모바일 데이터 주소에서 읽는다. 실패하면 {}."""
    try:
        r = requests.get(NAVER_KR_INFO_URL.format(code=str(code).replace(".KS", "")), timeout=(8, 20),
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        return _naver_kr_pairs(r.json()) if r.status_code == 200 else {}
    except Exception as e:
        print(f"   ⚠️ 네이버 모바일 종목 자료 실패: {type(e).__name__}")
        return {}


def _kr_etf_name(code):
    """국내 ETF 코드 → 이름(KRX ETF 목록). 실패하면 None."""
    if not _KR_ETF_NAMES:
        try:
            df = fdr.StockListing('ETF/KR')
            _KR_ETF_NAMES.update({str(r.get('Symbol', '')).zfill(6): str(r.get('Name', '')) for _, r in df.iterrows()})
        except Exception as e:
            print(f"ℹ️ 국내 ETF 이름 목록 못 받음: {type(e).__name__}")
            return None
    return _KR_ETF_NAMES.get(str(code).replace('.KS', '').zfill(6)) or None


def load_dynamic_kr_etfs(top_n=KR_DYNAMIC_TOP_N):
    """거래대금 상위 국내 ETF를 불러와 _DYNAMIC_UNIVERSE에 채운다. 실패해도 고정 목록만으로 진행."""
    if _DYNAMIC_UNIVERSE:
        return _DYNAMIC_UNIVERSE
    try:
        df = fdr.StockListing('ETF/KR')
        if 'Amount' in df.columns:
            df = df.sort_values('Amount', ascending=False)
        added = 0
        for _, row in df.iterrows():
            if added >= top_n:
                break
            code = f"{str(row.get('Symbol', '')).zfill(6)}.KS"
            meta = _classify_kr_etf(row.get('Name'), row.get('Category'))
            if not meta or code in ETF_UNIVERSE:
                continue
            _DYNAMIC_UNIVERSE[code] = {"theme": meta[0], "group": meta[1], "name": str(row.get('Name'))}
            added += 1
        print(f"✅ 거래대금 상위 국내 ETF {len(_DYNAMIC_UNIVERSE)}개를 후보에 추가했습니다.")
    except Exception as e:
        print(f"⚠️ 국내 ETF 목록 조회 실패(고정 목록만으로 진행): {type(e).__name__}: {e}")
    return _DYNAMIC_UNIVERSE


def _universe():
    merged = dict(_DYNAMIC_UNIVERSE)
    merged.update(ETF_UNIVERSE)
    return merged


def _normalize_ticker(raw):
    t = str(raw).strip().upper()
    if re.fullmatch(r"\d{6}", t):
        t += ".KS"
    return t


def _etf_meta(ticker, name=None):
    """티커의 주제/묶음/이름. 목록에 없는 국내 ETF는 이름이 있으면 이름으로 분류한다
    (예전에 자동 발굴로 썼던 종목도 발행 기록에 저장된 이름으로 다시 분류됨)."""
    t = _normalize_ticker(ticker)
    meta = _universe().get(t)
    if meta:
        return meta
    if name and t.endswith(".KS"):
        cls = _classify_kr_etf(name)
        if cls:
            return {"theme": cls[0], "group": cls[1], "name": name}
    return {"theme": "기타", "group": t, "name": name or t}


def _etf_theme(ticker, name=None):
    return _etf_meta(ticker, name)["theme"]


def _etf_group(ticker, name=None):
    return _etf_meta(ticker, name)["group"]


def _etf_display_name(ticker):
    t = _normalize_ticker(ticker)
    name = _universe().get(t, {}).get("name")
    return name or t.replace(".KS", "")


def _article_ticker_names(article):
    data = article.get('etf_data') or article.get('topic_data') or {}
    return {_normalize_ticker(k): (v or {}).get('name') for k, v in data.items()
            if not str(k).startswith('_') and isinstance(v, dict)}


def _article_tickers(article):
    """저장된 글 기록에서 그 글이 다룬 티커 목록을 꺼낸다. 발행 때 함께 저장된
    데이터(etf_data/topic_data)의 키를 우선 쓰고, 없으면 제목에서 티커를 찾는다.
    제목 검색은 앞뒤가 영숫자가 아닐 때만 인정해 QQQM 글을 QQQ로 착각하지 않는다."""
    data = article.get('etf_data') or article.get('topic_data') or {}
    keys = [_normalize_ticker(k) for k in data if not str(k).startswith('_')]
    if keys:
        return keys
    title = article.get('title', '')
    found = []
    for t in _universe():
        code = t.replace('.KS', '')
        if re.search(rf'(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])', title):
            found.append(t)
    return found
NEWS_CACHE_TTL = 60 * 60  # 1시간 캐시

def get_tistory_rss_links(blog_url):
    print("🔗 블로그 기존 글 목록(RSS) 수집 중...")
    # 티스토리 블로그마다(스킨/설정에 따라) RSS 경로가 /rss 또는 /feed로 다를 수
    # 있는 것으로 확인됨. 하나가 실패하면 조용히 포기하지 않고 다른 경로도 순서대로 시도한다.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    base = blog_url.rstrip('/')
    candidate_paths = ["/rss", "/feed"]

    for path in candidate_paths:
        feed_url = f"{base}{path}"
        try:
            response = requests.get(feed_url, timeout=10, headers=headers)

            if response.status_code != 200:
                # 이전에는 200이 아니면 아무 로그 없이 조용히 빈 리스트를 반환해서,
                # RSS 수집이 왜 실패했는지 전혀 알 수 없었음(403/404/리다이렉트
                # 등도 전부 "기존 글 목록이 없습니다"로만 보였음).
                print(f"⚠️ RSS 수집 실패: HTTP {response.status_code} (URL: {feed_url})")
                continue

            root = ET.fromstring(response.content)
            items = []
            for item in root.findall('./channel/item'):
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else ''
                if title and link:
                    items.append({"title": title, "url": link})

            if not items:
                print(f"⚠️ RSS 응답은 성공했지만 글 항목이 0개입니다 (URL: {feed_url}). 다른 경로를 시도합니다.")
                continue

            print(f"✅ RSS 수집 성공 (URL: {feed_url})")
            return items[:50]
        except requests.exceptions.RequestException as e:
            print(f"⚠️ RSS 요청 실패 ({feed_url}): {type(e).__name__}: {e}")
        except ET.ParseError as e:
            print(f"⚠️ RSS 응답 파싱 실패 ({feed_url}, XML 형식이 아닐 수 있음): {type(e).__name__}: {e}")

    print("⚠️ /rss, /feed 경로 모두 실패했습니다. BLOG_NAME(.env) 값이 정확한지, 블로그에 발행된 글이 실제로 있는지 확인해보세요.")
    return []


def _calculate_dividend_growth_rate(dividends):
    """TTM 방식으로 배당 성장률 산정: 최근 1년 vs 이전 1년 비교"""
    try:
        if dividends is None or dividends.empty:
            return None

        divs = dividends.copy()
        divs.index = pd.to_datetime(divs.index, errors='coerce')
        divs = divs.dropna()
        if divs.empty:
            return None

        now = pd.Timestamp.now(tz=divs.index.tz) if hasattr(divs.index, 'tz') else pd.Timestamp.now()
        if now.tz is None and divs.index.tz is not None:
            now = now.tz_localize(divs.index.tz)

        end_of_current = now
        start_of_current = end_of_current - pd.DateOffset(years=1)
        start_of_previous = start_of_current - pd.DateOffset(years=1)

        ttm_current = divs[(divs.index > start_of_current) & (divs.index <= end_of_current)].sum()
        ttm_previous = divs[(divs.index > start_of_previous) & (divs.index <= start_of_current)].sum()

        if ttm_previous <= 0 or pd.isna(ttm_previous):
            return None

        return (ttm_current / ttm_previous - 1) * 100
    except (ValueError, TypeError):
        return None


















MACRO_CACHE_TTL = 3600
TICKER_CACHE_TTL = 1800
































def _get_recent_news_for_query(query, max_results=3):
    cache = _load_cache()
    cache_key = f"news:{query}"
    cached_news = _get_cached_record(cache, cache_key, NEWS_CACHE_TTL)
    if cached_news:
        return cached_news

    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    encoded_query = urllib.parse.quote_plus(query + " ETF")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

    try:
        response = requests.get(rss_url, headers={'User-Agent': user_agent}, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall('.//item')[:max_results]:
            title = item.findtext('title', default='').strip()
            link = item.findtext('link', default='').strip()
            source = item.findtext('source', default='Google News').strip()
            pub_date = item.findtext('pubDate', default='').strip()
            items.append({
                'title': title,
                'url': link,
                'source': source,
                'pubDate': pub_date,
            })
        if items:
            _set_cached_record(cache, cache_key, items)
            return items
    except (requests.exceptions.RequestException, ET.ParseError, OSError, ValueError) as e:
        print(f"⚠️ 뉴스 수집 실패 ({query}): {type(e).__name__}: {e}")

    return []


def _get_recent_news_for_etfs(etf_data_cache, macro_data):
    queries = []
    for ticker, data in etf_data_cache.items():
        if data.get('name'):
            queries.append(data['name'])
        if data.get('index'):
            queries.append(data['index'])
        queries.append(ticker)
    if macro_data.get('usd_krw'):
        queries.append('원/달러 환율')
    if macro_data.get('us_10y'):
        queries.append('미국 10년물 금리')

    unique_queries = []
    for q in queries:
        if q and q not in unique_queries:
            unique_queries.append(q)

    news_items = []
    for query in unique_queries:
        for item in _get_recent_news_for_query(query, max_results=2):
            if len(news_items) >= 6:
                break
            news_items.append(item)
        if len(news_items) >= 6:
            break

    return news_items















































def _add_scenario_analysis(etf_data_cache, title_tickers):
    """실제 연평균성장률(CAGR) 반영 투자 시나리오 분석.
    [중요] 이전에는 d.get('cagr', 0.08)로 기본값 8%를 썼는데, 애초에
    etf_data_cache에 'cagr' 키 자체가 채워지지 않아 사실상 모든 ETF가
    실제 데이터와 무관하게 항상 8%로 시뮬레이션되고 있었음(get_etf_real_data가
    실제로 계산한 5년 총수익률이 다른 변수에만 저장되고 여기로 연결이 안 됨).
    이제 get_etf_real_data가 실제 CAGR을 계산해 넘겨주므로, 그 값이 없을 때만
    (계산 실패 등) 시뮬레이션 자체를 생략하고 그 이유를 명시한다 - 근거 없는
    숫자를 지어내 마치 실제 데이터인 것처럼 보이게 하지 않기 위함."""
    html = '<h3 style="margin-top:30px;">💡 투자 시나리오별 수익/손실 분석</h3>'
    for ticker, d in etf_data_cache.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        yield_pct = float(d.get('yield', '0').replace('%', '').split()[0]) if '%' in d.get('yield', '0') else 0.0

        principal = 10_000_000
        annual_return_estimate = d.get('cagr')

        if annual_return_estimate is None:
            html += f"""
<div style="margin-top:20px;padding:15px;background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;">
<p style="margin:0;font-size:13px;color:#7f8c8d;"><em>※ {ticker_clean}은(는) 과거 가격 데이터가 충분하지 않아 장기 보유 시뮬레이션을 계산할 수 없습니다. 최근 수익률 데이터는 위 표를 참고하세요.</em></p>
</div>
"""
            continue

        final_value_5y = principal * ((1 + annual_return_estimate) ** 5)
        annual_dividend = principal * (yield_pct / 100)
        total_5y_dividend = annual_dividend * 5
        overseas = _is_overseas_listed(d)
        div_tax_rate = TAX_US_DIVIDEND_WITHHOLDING if overseas else TAX_DOMESTIC_DIVIDEND
        div_tax_label = "배당세(미국 원천징수 15%)" if overseas else "배당소득세(15.4%)"
        sale_tax_note = ("매도 차익 세금(연 250만 원 공제 후 22%)은 빠져 있습니다." if overseas
                         else "매도 차익 세금(일반계좌 15.4%, 국내 주식형 ETF는 비과세)은 빠져 있습니다.")
        tax_on_dividend = total_5y_dividend * div_tax_rate
        net_after_tax = (final_value_5y - principal) + (total_5y_dividend - tax_on_dividend)

        # [수정] "5년 후 평가액"이 원금보다 늘었는지 줄었는지와 무관하게 항상
        # 빨강으로 고정되어 있었음. CAGR이 음수(예: IBIT처럼 -18%)면 실제로는
        # 원금보다 줄어드는데도 빨강(국내 관행상 상승/이득 신호)으로 표시되어
        # 오해를 줄 수 있었음. 실제 손익 방향에 따라 동적으로 색을 결정.
        value_color = "#c0392b" if final_value_5y >= principal else "#2166ac"

        html += f"""
<div style="margin-top:20px;padding:15px;background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;">
<p style="margin:0 0 10px 0;font-weight:bold;color:#333;">{ticker_clean} - 실제 데이터 기반 연평균성장률(CAGR {annual_return_estimate*100:.1f}%) 기준: 1,000만원 5년 보유 시뮬레이션</p>
<p style="margin:0 0 10px 0;font-size:12px;color:#888;">※ 이 CAGR은 상장일부터 지금까지 확보된 <strong>전체 기간</strong>을 기준으로 계산한 값으로, 앞서 본 최근 1년 수익률과는 <strong>기준 기간이 다릅니다</strong>. 최근 1년 성과가 나빠도 상장 이후 누적으로는 플러스일 수 있고, 그 반대도 가능합니다.</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:10px;">
<tr style="background:#f5f5f5;">
<th style="border:1px solid #ddd;padding:10px;text-align:left;">항목</th>
<th style="border:1px solid #ddd;padding:10px;text-align:right;">예상 금액</th>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">초기 투자</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;">1,000만원</td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">5년 후 유가증권 평가액</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:{value_color};">약 {int(final_value_5y/10000):,}만원</span></td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">배당금 합계(세전)</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;">{int(total_5y_dividend/10000):,}만원</td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">{div_tax_label}</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:#2166ac;">-{int(tax_on_dividend/10000):,}만원</span></td>
</tr>
<tr style="background:#f0f0f0;font-weight:bold;">
<td style="border:1px solid #ddd;padding:10px;">5년 후 총 순수익</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:{'#c0392b' if net_after_tax >= 0 else '#2166ac'};font-size:14px;">약 {int(net_after_tax/10000):,}만원</span></td>
</tr>
</table>
<p style="margin-top:10px;font-size:11px;color:#7f8c8d;"><em>※ 위 시나리오는 이 ETF의 실제 과거 가격 데이터로 계산한 연평균성장률(CAGR)을 그대로 5년간 유지된다고 가정한 예시이며, 미래 수익을 보장하지 않습니다. 실제 데이터 확보 기간이 5년 미만인 경우, 확보된 기간의 CAGR을 사용했습니다. 세금은 배당에 대한 것만 반영했고, {sale_tax_note}</em></p>
</div>
"""
    return html


def _add_competitive_comparison(etf_data_cache):
    """비교분석 강화"""
    if len(etf_data_cache) < 2:
        return ""
    
    html = '<h3 style="margin-top:30px;">⚖️ 경쟁 상품 비교: 왜 이 분석 대상인가?</h3>'
    html += '<p style="color:#555;line-height:1.6;">동일 지수 추종 상품들 중 선택 근거:</p>'
    html += '<ul style="padding-left:20px;line-height:1.8;color:#333;">'
    
    for ticker, d in etf_data_cache.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        expense = d.get('expense_ratio', 'N/A')
        div_growth = d.get('dividend_growth_rate', 'N/A')
        fx_exposure = d.get('fx_exposure', 'N/A')
        
        html += f'<li><strong>{ticker_clean}</strong>: 보수({expense}), 배당성장({div_growth}), 환노출({fx_exposure})</li>'
    
    html += '</ul>'
    html += """
<p style="margin-top:15px;padding:12px;background:#fffbea;border-left:3px solid #f39c12;color:#7d6608;font-size:12px;">
<strong>💡 핵심 차별고:</strong> 이 분석이 다른 블로그와 다른 이유는 단순 "어느 ETF 좋다"가 아니라, 
<strong>당신의 구체적 상황(연령, 납입기간, 세금계좌) 기반으로 수익률뿐 아니라 세금·환율·변동성까지</strong> 종합 검토한다는 점입니다.
</p>
"""
    
    return html








def _add_risk_scenarios(etf_data_cache, principal=100_000_000):
    """실제 MDD(최대 낙폭) 기반 위험 시나리오 분석"""
    html = '<h3 style="margin-top:30px;">⚠️ 위기 시나리오: 최악의 경우 내 계좌는?</h3>'
    html += '<p style="color:#555;">각 ETF의 과거 실제 최대 낙폭(MDD)을 기준으로, 1억 원 투자 시 감내해야 할 최악의 손실 규모입니다.</p>'

    # [수정] 이전에는 <table width:100%>인데 각 셀에 폭 지정이 없어서, ETF가
    # 1~2개뿐일 때 브라우저가 셀 내용물 크기에 맞춰 열을 비정상적으로 좁게
    # 렌더링하는 문제가 있었음(실제 렌더링 확인 결과 글자가 세로로 눌린 듯 보임).
    # 여러 ETF를 나란히 비교하는 경우가 아니면 표보다 카드형이 더 읽기 편해서,
    # ETF가 3개 미만이면 카드형 레이아웃으로 전환한다.
    risk_results_by_ticker = {}
    ticker_count = len(etf_data_cache)

    if ticker_count < 3:
        # 카드형 레이아웃 (1~2개 ETF일 때)
        cards_html = ""
        for ticker, d in etf_data_cache.items():
            ticker_clean = ticker.replace(".KS", "").replace(".US", "")
            mdd_str = str(d.get('mdd', '0')).replace('%', '').strip()
            try:
                mdd_val = float(mdd_str) / 100.0
            except ValueError:
                mdd_val = 0.0
            if mdd_val > 0:
                mdd_val = -mdd_val
            loss_amount = principal * mdd_val
            remaining = principal + loss_amount

            risk_results_by_ticker[ticker] = {
                "principal": principal,
                "mdd_pct": round(mdd_val * 100, 2),
                "loss_amount": round(loss_amount),
                "remaining": round(remaining),
            }

            if mdd_val == 0:
                cards_html += (
                    f'<div style="padding:16px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px;background:#fafafa;">'
                    f'<p style="margin:0;font-weight:bold;color:#333;">{ticker_clean}</p>'
                    f'<p style="margin:8px 0 0;color:#666;">MDD 데이터 없음</p></div>'
                )
            else:
                cards_html += f"""
<div style="padding:18px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px;background:#fafafa;">
<p style="margin:0 0 10px;font-weight:bold;color:#333;font-size:15px;">{ticker_clean}</p>
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;">
<div><span style="font-size:12px;color:#888;">실제 최대낙폭(MDD)</span><br/><span style="font-size:17px;font-weight:bold;color:#2166ac;">{mdd_val*100:.2f}%</span></div>
<div><span style="font-size:12px;color:#888;">최대 손실 금액</span><br/><span style="font-size:17px;font-weight:bold;color:#c0392b;">{int(loss_amount/10000):,}만원</span></div>
<div><span style="font-size:12px;color:#888;">잔여 자산</span><br/><span style="font-size:17px;font-weight:bold;color:#555;">{int(remaining/10000):,}만원</span></div>
</div>
</div>
"""
        html += f'<div style="margin-top:20px;padding:15px;border:1px solid #ddd;border-left:4px solid #2166ac;border-radius:4px;background:#fff;">{cards_html}'
    else:
        # 표형 레이아웃 (3개 이상 비교할 때 - 열 최소 너비 지정으로 가독성 확보)
        html += """
<div style="margin-top:20px;padding:15px;border:1px solid #ddd;border-left:4px solid #2166ac;border-radius:4px;background:#fafafa;overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<tr style="background:#f5f5f5;">
"""
        for ticker in etf_data_cache.keys():
            ticker_clean = ticker.replace(".KS", "").replace(".US", "")
            html += f'<th style="border:1px solid #ddd;padding:10px;min-width:130px;">{ticker_clean}</th>'
        html += '</tr><tr>'

        for ticker, d in etf_data_cache.items():
            mdd_str = str(d.get('mdd', '0')).replace('%', '').strip()
            try:
                mdd_val = float(mdd_str) / 100.0
            except ValueError:
                mdd_val = 0.0
            if mdd_val > 0:
                mdd_val = -mdd_val
            loss_amount = principal * mdd_val
            remaining = principal + loss_amount

            risk_results_by_ticker[ticker] = {
                "principal": principal,
                "mdd_pct": round(mdd_val * 100, 2),
                "loss_amount": round(loss_amount),
                "remaining": round(remaining),
            }

            html += '<td style="border:1px solid #ddd;padding:10px;text-align:center;min-width:130px;">'
            if mdd_val == 0:
                html += '<span style="color:#666;">MDD 데이터 없음</span>'
            else:
                html += f'<span style="color:#2166ac;font-weight:bold;">실제 MDD: {mdd_val*100:.2f}%</span><br/>'
                html += f'<span style="color:#2166ac;font-weight:bold;">최대 손실: {int(loss_amount/10000):,}만원</span><br/>'
                html += f'<span style="color:#666;font-size:11px;">잔액: {int(remaining/10000):,}만원</span>'
            html += '</td>'
        html += '</tr></table></div>'

    html += """
<p style="font-size:11px;color:#555;margin-top:10px;line-height:1.5;">
<strong>💡 시사점:</strong> 단순한 시장 하락 가정이 아닌, 해당 ETF가 역사적으로 겪었던 <b>실제 가장 깊은 하락폭(MDD)</b>을 적용한 팩트 데이터입니다. 투자 전 반드시 위 표의 최대 손실 금액을 감내할 수 있는지 점검하시기 바랍니다.
</p>
"""
    if ticker_count < 3:
        html += "</div>"
    return html, risk_results_by_ticker




def _normalize_previous_url(raw_url):
    """[신규] 저장된 이전 글 URL의 도메인이 지금 설정된 대표 도메인과 다르면
    (예: 무료 시절 ondo99.wordpress.com으로 저장된 URL을, 유료 전환 후
    ondo99.com으로 정규화) 현재 도메인 기준으로 바꿔준다.
    워드프레스 리디렉션 덕분에 예전 URL도 실제로는 계속 작동하지만, 화면에
    "이전 글 URL"로 노출될 때 예전 도메인 그대로 보이면 일관성이 없어
    보이므로, 항상 최신 도메인 기준으로 통일해 보여준다.
    티스토리는 도메인이 바뀔 일이 없으므로 원본 그대로 반환(하위 호환)."""
    if not raw_url or PLATFORM != "wordpress" or not WP_SITE_URL:
        return raw_url
    try:
        from urllib.parse import urlparse, urlunparse
        parsed_saved = urlparse(raw_url)
        parsed_current = urlparse(WP_SITE_URL)
        if parsed_saved.netloc and parsed_current.netloc and parsed_saved.netloc != parsed_current.netloc:
            normalized = parsed_saved._replace(netloc=parsed_current.netloc, scheme=parsed_current.scheme)
            return urlunparse(normalized)
    except Exception:
        pass  # 정규화 실패해도 원본 URL은 여전히 유효하니 조용히 원본 반환
    return raw_url


def _get_previous_analysis(etf_list, today_str, rss_posts=None):
    """같은 ETF의 이전 글 찾기 (시리즈 추적용).

    [신규] rss_posts(실제 서버에서 조회한 발행 글 목록)가 주어지면, 저장된
    "추정 URL"보다 우선해서 실제 확인된 URL로 교정한다. 반자동 발행(클립보드
    복사 후 수동 붙여넣기) 방식에서는 정확한 발행 URL을 코드가 알 수 없어
    recommended_url 기반 추정치를 저장해왔는데, RSS는 서버가 실제로 확인해준
    데이터라 이걸로 보정하면 훨씬 정확한 URL을 확보할 수 있다."""
    state = _load_state()
    previous_analyses = {}
    rss_posts = rss_posts or []
    
    for ticker in etf_list:
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        previous = None
        version = 1  # 기본 버전
        
        # [수정] 이전에는 리스트를 순서대로 훑다가 같은 티커의 "가장 먼저
        # 발견된"(보통 가장 오래된) 글에서 멈췄음(break). 그 결과 QQQ를 3번째,
        # 4번째 쓸 때도 항상 1번째(v1) 글과만 비교하고, version도 항상
        # "1+1=2"로 잘못 계산되는 버그가 있었음(실제로는 3번째 글인데 v2로
        # 표시됨). 같은 티커의 모든 과거 글을 모아서 그 중 "가장 최근에 쓴
        # 글"과 비교하도록 수정 - 이래야 "지난 분석 대비"라는 서술이 실제로
        # 바로 직전 글을 가리키고, 버전 번호도 정확히 이어진다.
        all_matching = [a for a in state.get('articles', [])
                        if a.get('status') != 'draft'
                        and _normalize_ticker(ticker) in _article_tickers(a)]
        # 같은 날 쓴 글과 비교하면 "지난 분석(오늘 날짜) 대비" 같은 모순 문장이
        # 나온다(7/21에 같은 티커 글이 두 번 발행되며 실제로 발생). 오늘보다 이전
        # 날짜의 글만 비교 대상으로 삼고, 버전 번호는 전체 글 기준으로 이어간다.
        try:
            today_iso = datetime.strptime(today_str, "%Y년 %m월 %d일").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            today_iso = datetime.now().strftime("%Y-%m-%d")
        matching_articles = [a for a in all_matching if str(a.get('timestamp', ''))[:10] < today_iso]
        max_version = max((a.get('version', 1) for a in all_matching), default=0)
        if matching_articles:
            try:
                latest_article = max(matching_articles, key=lambda a: a.get('timestamp', ''))
            except (TypeError, ValueError):
                latest_article = matching_articles[-1]  # 정렬 실패 시 리스트상 마지막 것으로 폴백

            resolved_url = _normalize_previous_url(latest_article.get('url', ''))
            # RSS 실제 데이터에서 제목이 일치하는 글을 찾아 URL을 교정
            # (완전 일치가 아니라도, 저장된 제목이 RSS 제목에 포함되어 있으면
            # 같은 글로 판단 - AI가 태그[ETF 분석 v2] 등을 앞에 붙이는 경우가
            # 있어 완전 일치를 요구하면 놓칠 수 있음)
            saved_title = latest_article.get('title', '')
            for rss_item in rss_posts:
                if saved_title and (saved_title in rss_item.get('title', '') or rss_item.get('title', '') in saved_title):
                    resolved_url = rss_item.get('url', resolved_url)
                    break

            prev_day = str(latest_article.get('timestamp', ''))[:10]
            try:
                prev_day = datetime.strptime(prev_day, "%Y-%m-%d").strftime("%Y년 %m월 %d일")
            except ValueError:
                pass
            previous = {
                'title': latest_article['title'],
                'date': latest_article['timestamp'],
                'date_display': prev_day,
                'url': resolved_url,
                'version': latest_article.get('version', 1),
                # 7월까지의 기록은 'etf_data', 공용 엔진(blog_engine._register_article)으로
                # 바뀐 뒤 저장되는 기록은 'topic_data'에 들어간다. 둘 다 읽어야 시리즈
                # 비교가 두 번째 글 이후에도 끊기지 않는다.
                'etf_data': latest_article.get('etf_data') or latest_article.get('topic_data') or {},
                'content': latest_article.get('content', ''),  # 섹션 구성 비교(차별화 지시)에 사용
            }
        if all_matching:
            version = max_version + 1  # 다음 버전

        previous_analyses[ticker_clean] = {
            'previous': previous,
            'current_version': version,
            'next_update_suggestion': _suggest_next_update_date(today_str) if previous else None
        }
    
    return previous_analyses


def _suggest_next_update_date(current_date_str):
    """다음 업데이트 추천일 계산 (3개월 후)"""
    from datetime import datetime, timedelta
    current = datetime.strptime(current_date_str, "%Y년 %m월 %d일")
    next_update = current + timedelta(days=90)  # 3개월
    return next_update.strftime("%Y년 %m월 %d일")








def _add_sector_deep_analysis(etf_data_cache, macro_data):
    """심화 섹터 분석 (팩트 기반)"""
    html = '<h3 style="margin-top:30px;">🔍 섹터 분석 및 거시경제 전망</h3>'
    primary_etf = list(etf_data_cache.values())[0]
    ticker = primary_etf.get('ticker', list(etf_data_cache.keys())[0]).replace(".KS", "").replace(".US", "")
    real_sector = primary_etf.get('sector', '종합 / 판단 불가')
    real_industry = primary_etf.get('industry', '종합 / 판단 불가')
    
    usd_krw = float(str(macro_data.get('usd_krw', '1300원')).replace('원', '').replace(',', ''))
    us_10y = float(str(macro_data.get('us_10y', '4.0%')).replace('%', ''))
    
    future_outlook = "긍정적" if (usd_krw < 1250 and us_10y < 3.8) else "보수적 접근 필요" if (usd_krw > 1380 or us_10y > 4.5) else "중립적"
    future_color = "#c0392b" if future_outlook == "긍정적" else "#2166ac" if future_outlook == "보수적 접근 필요" else "#ffc107"
    
    html += f'''
<p style="color:#555;">{ticker} ETF의 투자 영역(<strong>{real_sector} / {real_industry}</strong>)과 거시경제 분석입니다.</p>
<div style="margin:20px 0;padding:15px;border:1px solid #e9ecef;border-radius:8px;background:#f8f9fa;">
<h4 style="margin:0 0 10px 0;color:#333;">🌍 거시경제 연계 대응 전략</h4>
<p style="margin:0 0 10px 0;font-size:13px;">현재 환율(<strong>{usd_krw:,.0f}원</strong>)과 금리(<strong>{us_10y:.2f}%</strong>) 기준 전망: <span style="color:{future_color};font-weight:bold;">{future_outlook}</span></p>
<ul style="margin:0;padding-left:20px;font-size:12px;line-height:1.6;">
<li><strong>환율 영향:</strong> 현재 환율은 환노출(UH) 수익률에 직접적 영향을 미칩니다.</li>
<li><strong>금리 영향:</strong> 국채 금리 {us_10y:.2f}% 수준은 주식 시장의 밸류에이션에 영향을 줍니다.</li>
</ul>
</div>
'''

    # 스크래핑한 실제 Top 5 표 삽입 (데이터가 있을 때만 노출)
    top_holdings = primary_etf.get('top_holdings', [])
    if top_holdings:
        html += '<h4 style="margin:25px 0 10px 0; font-size:15px; color:#212529;">📦 상위 5대 보유 종목 (Top 5 Holdings)</h4>'
        html += '<div style="margin:10px 0; overflow-x:auto;">'
        html += '<table style="width:100%; border-collapse:collapse; font-size:13px; text-align:left; border:1px solid #dee2e6;">'
        html += '<tr style="background:#f1f3f5; border-bottom:2px solid #dee2e6;">'
        html += '<th style="padding:10px; border-right:1px solid #dee2e6; text-align:center;">순위</th>'
        html += '<th style="padding:10px; border-right:1px solid #dee2e6;">종목명 (티커)</th>'
        html += '<th style="padding:10px; text-align:right;">비중</th>'
        html += '</tr>'
        
        for i, holding in enumerate(top_holdings[:5], 1):
            symbol = holding.get("symbol", "")
            name = holding.get("name", "")
            weight = holding.get("weight", 0)
            
            html += '<tr style="border-bottom:1px solid #e9ecef;">'
            html += f'<td style="padding:10px; border-right:1px solid #e9ecef; text-align:center; color:#868e96;">{i}</td>'
            html += f'<td style="padding:10px; border-right:1px solid #e9ecef;"><strong>{name}</strong> <span style="color:#666; font-size:11px;">({symbol})</span></td>'
            html += f'<td style="padding:10px; text-align:right; font-weight:bold; color:#1f3c88;">{weight:.2f}%</td>'
            html += '</tr>'
            
        html += '</table></div><br>'
    
    div_stability = primary_etf.get('dividend_stability_desc', '')
    if div_stability: html += f'<div style="margin:15px 0;padding:10px;background:#e8f5e8;border-left:4px solid #28a745;border-radius:4px;"><strong>💰 배당 안정성:</strong> {div_stability}</div>'
    
    ma200_info = primary_etf.get('ma200_info')
    if ma200_info:
        diff_pct = ma200_info.get('diff_pct', 0)
        color = '#c0392b' if diff_pct > 0 else '#2166ac'
        ma200_status = ma200_info.get('status', '')
        html += f'<div style="margin:15px 0;padding:10px;background:#e3f2fd;border-left:4px solid #4A90E2;border-radius:4px;"><strong>📈 기술 분석 (MA200):</strong> {ma200_status} (현재가 MA200 대비 <span style="color:{color};font-weight:bold;">{diff_pct:+.2f}%</span>)</div>'
    
    html += _build_advanced_sections(etf_data_cache)
    return html














def _create_backtest_simulation_chart(ticker, data, wrapper_style, usd_krw_rate=1300.0, investment_amount=10000000):
    """
    [신규] 기존에는 Portfolio Visualizer 외부 사이트를 셀레니움으로 조작해 스크린샷을
    찍으려 했으나, 사이트 UI가 바뀌면서 계속 깨지는 문제가 있었고(엉뚱한 샘플 포트폴리오
    화면이 찍힘), 애초에 본문에 자동 삽입되지도 않는 죽은 기능이었음.

    외부 사이트 의존성을 완전히 없애고, 이미 갖고 있는 가격 데이터(yfinance)로 직접
    "거치식(목돈을 한 번에 투자)" vs "적립식(매달 나눠서 투자, DCA)" 시뮬레이션 곡선을
    그려서 대체함. 월봉/주봉처럼 같은 데이터를 촘촘하게만 보여주는 것보다, 실제로
    결과가 달라지는 두 투자 방식을 비교하는 것이 독자에게 더 실질적인 정보를 줌.
    """
    is_kr = ticker.endswith('.KS')
    raw_code = ticker.replace('.KS', '') if is_kr else ticker
    safe_id = raw_code.replace('.', '_')

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        hist = ticker_obj.history(period="5y")

        if not hist.empty:
            hist['Close'] = pd.to_numeric(hist['Close'], errors='coerce')
            hist = hist.dropna(subset=['Close'])
            if len(hist) > 21:
                hist = hist.iloc[:-21]

        if hist.empty or len(hist) < 30:
            return "", None  # 데이터 부족 시 조용히 생략 (필수 요소가 아니므로 fallback 링크까지는 불필요)

        currency_symbol = "₩" if is_kr else "$"
        close = hist['Close'].copy()
        if not is_kr and usd_krw_rate > 1.0:
            close = close * usd_krw_rate
            currency_symbol = "₩"

        # 월말 종가로 리샘플링 (일별로 하면 데이터 포인트가 너무 많아 무거워짐)
        monthly_close = close.resample('ME').last().dropna()
        if len(monthly_close) < 6:
            return "", None

        dates_str = monthly_close.index.strftime('%Y-%m').tolist()
        prices = monthly_close.tolist()

        # --- 시나리오 1: 거치식 (첫 달에 investment_amount 전액 투자) ---
        shares_lump = investment_amount / prices[0]
        lump_values = [round(shares_lump * p) for p in prices]

        # --- 시나리오 2: 적립식 DCA (전체 기간에 걸쳐 매달 동일 금액 분할 투자) ---
        monthly_invest = investment_amount / len(prices)
        dca_shares = 0.0
        dca_values = []
        for p in prices:
            dca_shares += monthly_invest / p
            dca_values.append(round(dca_shares * p))

        chart_title = data.get("name", ticker)
        full_title = f"{chart_title}" if is_kr else f"{chart_title} ({ticker})"

        chart_id = f"backtest_chart_{safe_id}"
        plotly_script_id = f"backtest_plotly_script_{safe_id}"
        btn_lump_id = f"btn_lump_{safe_id}"
        btn_dca_id = f"btn_dca_{safe_id}"

        chart_data = [
            {
                'type': 'scatter', 'mode': 'lines', 'x': dates_str, 'y': lump_values,
                'name': '거치식 (한 번에 투자)', 'visible': True,
                'line': {'color': '#1f3c88', 'width': 3},
            },
            {
                'type': 'scatter', 'mode': 'lines', 'x': dates_str, 'y': dca_values,
                'name': '적립식 (매달 분할 투자)', 'visible': False,
                'line': {'color': '#e67e22', 'width': 3},
            },
        ]

        amount_str = f"{investment_amount:,.0f}"
        chart_layout = {
            'title': f"{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션",
            'yaxis': {'title': f"평가금액 ({currency_symbol})"},
            'xaxis': {'title': '투자 개월', 'type': 'category', 'nticks': 8, 'tickangle': 0},
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'height': 420,
            'margin': {'t': 60, 'b': 45, 'l': 60, 'r': 20},
        }

        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initPlotly_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'    var btn_lump = document.getElementById("{btn_lump_id}");'
            f'    var btn_dca = document.getElementById("{btn_dca_id}");'
            f'    if(btn_lump) btn_lump.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [true, false]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션"}}); }});'
            f'    if(btn_dca) btn_dca.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [false, true]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 월 {round(investment_amount/len(prices)):,}{currency_symbol} 적립식 시뮬레이션"}}); }});'
            f'  }}'
            f'  if(window.Plotly) initPlotly_{safe_id}();'
            f'  else if(!document.getElementById("{plotly_script_id}")) {{'
            f'    var s = document.createElement("script");'
            f'    s.id = "{plotly_script_id}";'
            f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'    s.onload = initPlotly_{safe_id};'
            f'    document.head.appendChild(s);'
            f'  }} else {{'
            f'    document.getElementById("{plotly_script_id}").addEventListener("load", initPlotly_{safe_id});'
            f'  }}'
            f'}})();'
            f'</script>'
        )

        backtest_aria_label = f"{full_title} 거치식 vs 적립식 투자 시뮬레이션 그래프, {amount_str}{currency_symbol} 기준"

        # [신규] 연령별 포트폴리오 가이드 등 다른 섹션에서 "이 ETF만의 실제 숫자"를
        # 재사용할 수 있도록, 계산 중간값을 버리지 않고 딕셔너리로 함께 반환한다.
        # (CHART_MODE와 무관하게 항상 동일하게 계산됨)
        lump_final = lump_values[-1]
        dca_final = dca_values[-1]
        backtest_result = {
            "ticker": ticker,
            "currency_symbol": currency_symbol,
            "investment_amount": investment_amount,
            "lump_final_value": lump_final,
            "lump_return_pct": round((lump_final - investment_amount) / investment_amount * 100, 2),
            "dca_final_value": dca_final,
            "dca_return_pct": round((dca_final - investment_amount) / investment_amount * 100, 2),
            "months": len(prices),
        }

        if CHART_MODE == "image":
            # [신규] "버튼으로 전환"하는 인터랙션은 이미지로 구현 불가능하므로,
            # 거치식/적립식 각각을 정적 PNG로 렌더링해 <details>(순수 HTML)로
            # 감싸 접어두고 클릭하면 펼쳐보는 방식으로 대체한다.
            lump_layout = dict(chart_layout)
            lump_layout['title'] = f"{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션"
            lump_data = [{**chart_data[0], 'visible': True}]
            lump_img = _plotly_fig_to_img_tag(lump_data, lump_layout, f"{full_title} 거치식 투자 시뮬레이션", width=700, height=420)

            dca_layout = dict(chart_layout)
            dca_layout['title'] = f"{full_title} - 월 {round(investment_amount/len(prices)):,}{currency_symbol} 적립식 시뮬레이션"
            dca_data = [{**chart_data[1], 'visible': True}]
            dca_img = _plotly_fig_to_img_tag(dca_data, dca_layout, f"{full_title} 적립식 투자 시뮬레이션", width=700, height=420)

            if not lump_img and not dca_img:
                return "", backtest_result  # 이미지 실패해도 계산값은 다른 섹션이 쓸 수 있게 반환

            caption = (
                f'<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
                f'※ 최근 5년 실제 가격 데이터를 기반으로, {amount_str}{currency_symbol}을 처음에 한 번에 투자(거치식)했을 때와 '
                f'매달 나누어 투자(적립식)했을 때의 평가금액 변화를 비교한 시뮬레이션입니다. 배당 재투자, 세금, 환율 변동은 반영되지 않았습니다.'
                f'</p>'
            )

            sections_html = ""
            if lump_img:
                sections_html += f'''
<details open style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">💰 거치식(한 번에 투자) 시뮬레이션 보기 (클릭)</summary>
<div style="margin-top:15px;">{lump_img}</div>
</details>
'''
            if dca_img:
                sections_html += f'''
<details style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#e67e22;list-style:none;">💰 적립식(매달 분할 투자) 시뮬레이션 보기 (클릭)</summary>
<div style="margin-top:15px;">{dca_img}</div>
</details>
'''
            safe_wrapper_style_img = wrapper_style + " overflow: visible !important;"
            html_output = f'<div style="{safe_wrapper_style_img}"><h4 style="margin-bottom:10px;">📊 {full_title} 투자 시뮬레이션: 거치식 vs 적립식</h4>{sections_html}{caption}</div>'
            return html_output, backtest_result

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{backtest_aria_label}" style="width:100%;min-height:420px;"></div>'
        button_html = (
            f'<div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; margin-top:5px; margin-bottom:15px;">'
            f'<button id="{btn_lump_id}" type="button" style="padding:8px 14px; border:1px solid #1f3c88; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">거치식</button>'
            f'<button id="{btn_dca_id}" type="button" style="padding:8px 14px; border:1px solid #e67e22; background:#fff; color:#e67e22; cursor:pointer; border-radius:6px; font-weight:bold;">적립식(DCA)</button>'
            f'</div>'
        )
        caption = (
            f'<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
            f'※ 최근 5년 실제 가격 데이터를 기반으로, {amount_str}{currency_symbol}을 처음에 한 번에 투자(거치식)했을 때와 '
            f'매달 나누어 투자(적립식)했을 때의 평가금액 변화를 비교한 시뮬레이션입니다. 배당 재투자, 세금, 환율 변동은 반영되지 않았습니다.'
            f'</p>'
        )

        safe_wrapper_style = wrapper_style + " overflow: visible !important;"
        html_output = f'<div style="{safe_wrapper_style}"><h4 style="margin-bottom:10px;">📊 {full_title} 투자 시뮬레이션: 거치식 vs 적립식</h4>{chart_div}{button_html}{chart_js}{caption}</div>'

        return html_output, backtest_result

    except Exception as e:
        print(f"⚠️ {ticker} 백테스트 시뮬레이션 차트 생성 실패: {type(e).__name__}: {e}")
        return "", None  # 실패해도 본문 전체를 막지 않도록 조용히 생략


def _create_chrome_driver():
    print("🚀 크롬 브라우저를 실행합니다...")
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    # [신규] GitHub Actions 등 디스플레이(화면)가 없는 무인 실행 환경에서는
    # 헤드리스 모드가 아니면 크롬 자체가 실행되지 않는다. NONINTERACTIVE=1일
    # 때 자동으로 헤드리스로 전환하고, 로컬 터미널에서 직접 돌릴 때(사람이
    # 화면으로 로그인/발행 과정을 지켜봐야 하는 경우)는 기존처럼 창이 보이게 유지한다.
    if os.environ.get("NONINTERACTIVE"):
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ 크롬 드라이버 초기화 실패: {type(e).__name__}: {e}")
        print("   확인해보세요: 1) 크롬 브라우저가 설치되어 있는지, 2) 인터넷 연결 상태(드라이버 자동 다운로드 필요), 3) 방화벽/백신이 드라이버 실행을 막고 있지는 않은지.")
        raise SystemExit(1)


def get_macro_data():
    print("🌍 실시간 거시경제 지표(환율, 금리, 공포/탐욕 지수) 조회 중...")
    cache = _load_cache()
    cached_macro = _get_cached_record(cache, 'macro', MACRO_CACHE_TTL)
    if cached_macro:
        print("✅ 매크로 데이터 캐시 사용")
        return cached_macro

    macro_info = {
        "usd_krw": "조회 실패",
        "us_10y": "조회 실패",
        "fear_greed": "조회 실패",
        "tnx_val": 0.0,
        "is_fx_volatile": False,
        "usd_krw_diff_pct": 0.0,
        "usd_krw_direction": ""
    }
    
    try:
        krw = yf.Ticker("KRW=X")
        krw_price = krw.fast_info['last_price']
        macro_info["usd_krw"] = f"{krw_price:,.2f}원"

        hist = krw.history(period="5d")
        if len(hist) >= 2:
            yesterday_close = hist['Close'].iloc[-2]
            if yesterday_close != 0:
                diff_raw = krw_price - yesterday_close
                diff_pct = abs(diff_raw / yesterday_close * 100)
                direction = "상승" if diff_raw > 0 else "하락"
                if diff_pct >= 0.5:
                    macro_info["is_fx_volatile"] = True
                    macro_info["usd_krw_diff_pct"] = round(diff_pct, 2)   # 반올림 없이 글에 '1.214117186666646%'가 들어갔음
                    macro_info["usd_krw_direction"] = direction
    except (KeyError, AttributeError, ValueError) as e:
        print(f"⚠️ 환율 조회 실패: {type(e).__name__}: {e}")
        pass
    
    try:
        tnx = yf.Ticker("^TNX")
        tnx_price = tnx.fast_info['last_price']
        macro_info["us_10y"] = f"{tnx_price:.3f}%"
        macro_info["tnx_val"] = float(tnx_price)
    except (KeyError, AttributeError, ValueError) as e:
        print(f"⚠️ 미국 10년물 금리 조회 실패: {type(e).__name__}: {e}")
        pass
        
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            score = data['fear_and_greed']['score']
            rating = data['fear_and_greed']['rating']
            rating_map = {
                "extreme greed": "극단적 탐욕",
                "greed": "탐욕",
                "neutral": "중립",
                "fear": "공포",
                "extreme fear": "극단적 공포"
            }
            rating_ko = rating_map.get(rating.lower(), rating)
            macro_info["fear_greed"] = f"{int(score)}점 ({rating_ko})"
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
        print(f"⚠️ 공포/탐욕 지수 조회 실패: {type(e).__name__}: {e}")
        
    _set_cached_record(cache, 'macro', macro_info)
    return macro_info


def _get_upcoming_earnings(ticker_obj):
    """(신규 1) 상위 종목 실적 발표일 수집"""
    try:
        calendar = ticker_obj.calendar
        if calendar is not None and not calendar.empty:
            earning_date = calendar.iloc[0].get('Earnings Date')
            if pd.notnull(earning_date):
                if isinstance(earning_date, list):
                    earning_date = earning_date[0]
                if isinstance(earning_date, pd.Timestamp):
                    return earning_date.strftime("%Y년 %m월 %d일")
    except Exception:
        pass
    return None


def _get_aum_trend(ticker_symbol):
    """(신규 2) 야후 파이낸스에서 AUM(순자산) 가져오기"""
    try:
        tick = yf.Ticker(ticker_symbol)
        info = tick.info
        aum = info.get('totalAssets')
        if aum:
            return f"${aum / 1_000_000_000:.2f}B"
    except Exception:
        pass
    return None


def _build_advanced_sections(etf_data_cache):
    """신규 3종 고급 기능 HTML 조립 (데이터 있을 때만 노출)"""
    html = ""
    primary_etf = list(etf_data_cache.values())[0]
    ticker = list(etf_data_cache.keys())[0]

    earnings = primary_etf.get('earnings_info', [])
    yield_gap = primary_etf.get('yield_gap')
    aum = primary_etf.get('aum_str')

    if not (earnings or yield_gap or aum):
        return html

    html += '<h3 style="margin-top:30px; color:#2c3e50;">💡 온도(ondo)의 프리미엄 인사이트</h3>'
    html += '<div style="margin:20px 0; display:flex; flex-direction:column; gap:15px;">'

    if yield_gap:
        try:
            val = float(str(yield_gap).replace('%', '').strip())
        except Exception:
            val = None
        color = "#c0392b" if val is not None and val > 2.0 else "#e67e22" if val is not None and val > 0 else "#2166ac"
        eval_text = "주식 투자 매력도 높음" if val is not None and val > 2.0 else "중립적 접근 필요" if val is not None and val > 0 else "채권 대비 투자 매력 낮음"
        html += f'''
            <div style="padding:15px; background:#f8f9fa; border-left:4px solid {color}; border-radius:4px;">
                <h4 style="margin:0 0 5px 0; color:#333;">⚖️ 일드 갭 (주식 기대수익률 vs 국채 금리)</h4>
                <p style="margin:0; font-size:13px; color:#555;">현재 일드 갭은 <strong style="color:{color};">{yield_gap}</strong> 수준입니다. ({eval_text})</p>
                <p style="margin:5px 0 0 0; font-size:11px; color:#888;">*이 ETF의 배당수익률에서 미국 10년물 국채금리를 뺀 수치로, 배당 관점에서 채권 대비 상대적 매력도를 참고하는 지표입니다(주식 전체의 기대수익률과는 다른 개념입니다).</p>
            </div>
        '''

    if earnings:
        li_html = "".join([f"<li style='margin-bottom:3px;'>{e}</li>" for e in earnings])
        html += f'''
            <div style="padding:15px; background:#fffcf5; border-left:4px solid #f1c40f; border-radius:4px;">
                <h4 style="margin:0 0 5px 0; color:#333;">📅 상위 종목 실적 발표 캘린더</h4>
                <p style="margin:0 0 8px 0; font-size:13px; color:#555;">해당 ETF의 방향성을 결정할 핵심 기업들의 실적 발표일입니다. 단기 변동성에 유의하세요.</p>
                <ul style="margin:0; padding-left:20px; font-size:13px; color:#b7950b; font-weight:bold;">{li_html}</ul>
            </div>
        '''

    if aum:
        html += f'''
            <div style="padding:15px; background:#f0f8ff; border-left:4px solid #3498db; border-radius:4px;">
                <h4 style="margin:0 0 5px 0; color:#333;">💸 스마트머니 동향 (총 운용자산)</h4>
                <p style="margin:0; font-size:13px; color:#555;">현재 {ticker.replace('.US','')}의 총 순자산(AUM) 규모는 <strong>{aum}</strong>입니다. 시장의 거대한 자금이 머무르는 핵심 투자처임을 보여줍니다.</p>
            </div>
        '''

    html += '</div>'
    return html


def _drawdown_detail(close):
    """최대 낙폭이 언제 시작(고점)해서 언제 바닥이었고, 고점 가격을 언제 되찾았는지(못 되찾았으면 None) 코드가 계산한다.
    2026-11-06: '최대 낙폭 -24.52%'만으로는 독자가 판단하기 어렵다 - "떨어지면 회복까지 얼마나 걸렸나"가 장기 보유의 실제 판단 기준.
    가격 기준(배당 제외). 실패하면 None."""
    try:
        c = close.dropna()
        if len(c) < 30:
            return None
        dd = c / c.cummax() - 1.0
        trough = dd.idxmin()
        peak = c.loc[:trough].idxmax()
        peak_px = float(c.loc[peak])
        after = c.loc[trough:]
        rec = after[after >= peak_px]
        recovered = rec.index[0] if len(rec) else None
        day = lambda d: f"{d:%Y-%m-%d}" if hasattr(d, "strftime") else str(d)
        out = {"pct": round(float(dd.min()) * 100, 2), "peak": day(peak), "trough": day(trough),
               "fall_days": int((trough - peak).days) if hasattr(trough - peak, "days") else None,
               "recovered": day(recovered) if recovered is not None else None,
               "recover_days": int((recovered - trough).days) if recovered is not None and hasattr(recovered - trough, "days") else None,
               "now_vs_peak": round((float(c.iloc[-1]) / peak_px - 1) * 100, 2)}
        return out
    except Exception:
        return None


def get_etf_real_data(ticker_symbol, driver, macro_data):
    print(f"🔍 {ticker_symbol} 데이터 및 스크래핑 중... (투트랙 방식 적용)")
    cache = _load_cache()
    cached = _get_cached_record(cache, ticker_symbol, TICKER_CACHE_TTL)
    if cached: 
        print(f"✅ {ticker_symbol} 캐시 사용")
        return cached

    is_kr = ticker_symbol.endswith(".KS") or (len(ticker_symbol) == 6 and ticker_symbol.isdigit())
    raw_code = ticker_symbol.replace(".KS", "").replace(".US", "")
    currency = "KRW" if is_kr else "USD"
    
    # 공통 기본값 초기화
    returns = {"1개월": 0.0, "3개월": 0.0, "6개월": 0.0, "1년": 0.0}
    mdd_val = "정보 없음"
    mdd_detail = None   # 최대 낙폭의 고점·바닥·회복 날짜와 회복에 걸린 기간(2026-11-06)
    simulated_result = "정보 없음"
    cagr = None  # 실제 데이터로 계산 성공한 경우에만 값이 채워짐 (임의 기본값 없음)
    current_price = 0.0
    calculated_yield = "0.00%"
    div_cycle = "정보 없음"
    expense_ratio = "N/A"
    kr_index = None
    kr_info = {}
    calculated_div_growth = None
    top_holdings = []
    earnings_info = []
    aum_str = None
    yield_gap = None
    ma200_info = None  # [신규] 200일 이동평균 대비 현재가 - 실제 계산 성공 시에만 채워짐
    dividend_stability_desc = ""  # [신규] 배당 이력 기반 안정성 설명 - 실제 계산 성공 시에만 채워짐
    short_name = ticker_symbol
    dividends_list = []
    info = {}  # 미국 ETF용 메타 정보 컨테이너

    if is_kr:
        # ==========================================
        # 🇰🇷 Track 1: 한국 ETF (FDR + Naver Selenium)
        # ==========================================
        print("   ▶ 한국 ETF 감지: FDR 및 네이버 스크래핑 엔진 가동")
        
        # 1. 가격 및 수익률 (FinanceDataReader)
        try:
            df = fdr.DataReader(raw_code)
            if not df.empty:
                current_price = float(df['Close'].iloc[-1])
                
                def get_ret(days):
                    if len(df) > days:
                        start_p = float(df['Close'].iloc[-(days+1)])
                        return ((current_price - start_p) / start_p) * 100
                    return 0.0
                    
                returns["1개월"] = get_ret(20)
                returns["3개월"] = get_ret(60)
                returns["6개월"] = get_ret(120)
                returns["1년"] = get_ret(250)
                
                df_5y = df.tail(250 * 5)
                if not df_5y.empty:
                    roll_max = df_5y['Close'].cummax()
                    mdd_val = f"{(df_5y['Close'] / roll_max - 1.0).min() * 100:.2f}%"
                    mdd_detail = _drawdown_detail(df_5y['Close'])
                    
                    if len(df_5y) > 10:
                        start_price_5y = float(df_5y['Close'].iloc[0])
                        total_return_5y = (current_price - start_price_5y) / start_price_5y
                        final_amount = 10000000 * (1 + total_return_5y)
                        simulated_result = f"5년 전 1,000만 원 투자 시 현재 가치 약 {int(final_amount/10000):,}만 원"
                        # 실제 보유 기간(연 단위)을 반영한 CAGR 계산. 상장한 지 얼마 안 된
                        # ETF(예: 2년치 데이터만 있는 경우)에 5년 CAGR을 적용하면 왜곡되므로,
                        # 실제 데이터 기간(years_held)을 반영해 계산한다.
                        years_held = len(df_5y) / 250.0
                        if years_held > 0 and (1 + total_return_5y) > 0:
                            cagr = (1 + total_return_5y) ** (1 / years_held) - 1
                        else:
                            cagr = None
        except Exception as e:
            print(f"   ⚠️ FDR 데이터 오류: {e}")

        # 2-0. 펀드보수·기초지수: 네이버 모바일 데이터(브라우저 없이) - 화면 스크래핑보다 먼저, 화면에서 못 읽어도 남는다
        kr_info = _naver_kr_info(raw_code)
        fee = kr_info.get("펀드보수") or kr_info.get("총보수")
        if fee and re.search(r"\d", fee):
            expense_ratio = fee if fee.endswith("%") else f"{fee}%"
        kr_index = kr_info.get("기초지수") or None
        # 2. 메타 정보 (네이버 금융 스크래핑)
        try:
            driver.get(f"https://finance.naver.com/item/main.naver?code={raw_code}")
            time.sleep(2)
            
            try:
                short_name = driver.find_element(By.XPATH, "//div[@class='wrap_company']/h2/a").text
            except Exception:
                short_name = raw_code
            if not short_name or short_name == raw_code:
                # 네이버 화면을 못 읽으면 이름이 숫자 코드만 남아 환율 영향 판단(_fx_exposure_label)이 빠졌다(2026-10-31)
                short_name = _kr_etf_name(raw_code) or raw_code
            
            # AUM (시가총액으로 대체)
            try:
                market_cap_text = driver.find_element(By.ID, "_market_sum").text
                aum_str = f"약 {market_cap_text}억 원"
            except Exception as e:
                print(f"   ⚠️ AUM 스크래핑 실패: {type(e).__name__}: {e}")
            
            dfs = pd.read_html(StringIO(driver.page_source))
            for df in dfs:
                df_str = df.to_string()
                if ("펀드보수" in df_str or "총보수" in df_str) and expense_ratio == "N/A":
                    for _, row in df.iterrows():
                        r_text = " ".join([str(x) for x in row.values])
                        if "펀드보수" in r_text or "총보수" in r_text:
                            match = re.search(r"(\d+\.\d+)\s*%", r_text)
                            if match: expense_ratio = f"{match.group(1)}%"
                if "분배수익률" in df_str:
                    for _, row in df.iterrows():
                        r_text = " ".join([str(x) for x in row.values])
                        if "분배수익률" in r_text:
                            match = re.search(r"(\d+\.\d+)\s*%", r_text)
                            if match: calculated_yield = f"{match.group(1)}%"
                if '종목명' in df.columns and '비중' in df.columns:
                    for _, row in df.dropna(subset=['종목명', '비중']).head(5).iterrows():
                        try:
                            top_holdings.append({"symbol": "-", "name": str(row['종목명']), "weight": float(str(row['비중']).replace('%', ''))})
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            print(f"   ⚠️ 네이버 스크래핑 실패: {e}")

    else:
        # ==========================================
        # 🇺🇸 Track 2: 미국 ETF (yfinance + Yahoo Selenium)
        # ==========================================
        print("   ▶ 미국 ETF 감지: Yahoo API 및 스크래핑 엔진 가동")
        try:
            ticker = yf.Ticker(raw_code)
            info = ticker.info
            # shortName은 "…S&P 500 ETF T"처럼 잘려서 글에 그대로 나갔다 → 정식 이름 우선
            short_name = info.get('longName') or info.get('shortName') or raw_code
            
            try:
                raw_inc = info.get('fundInceptionDate')
                if raw_inc:
                    inception_date_str = datetime.fromtimestamp(int(raw_inc)).strftime('%Y-%m-%d')
                else:
                    inception_date_str = '정보 없음'
            except Exception as e:
                print(f"   ⚠️ 상장일 정보 파싱 실패: {type(e).__name__}: {e}")
                inception_date_str = '정보 없음'
            
            try:
                current_price = ticker.fast_info['last_price']
            except Exception as e:
                print(f"   ⚠️ 현재가 정보 호출 실패: {type(e).__name__}: {e}")
                current_price = ticker.history(period="1d")['Close'].iloc[-1] if not ticker.history(period="1d").empty else 0.0

            for p_key, p_name in {"1mo": "1개월", "3mo": "3개월", "6mo": "6개월", "1y": "1년"}.items():
                try:
                    h = ticker.history(period=p_key)
                    returns[p_name] = ((current_price - h['Close'].iloc[0]) / h['Close'].iloc[0] * 100) if not h.empty else 0.0
                except Exception as e:
                    print(f"   ⚠️ 수익률(history {p_key}) 계산 실패: {type(e).__name__}: {e}")
            
            try:
                h_mdd = ticker.history(period="5y")
                if not h_mdd.empty:
                    mdd_val = f"{(h_mdd['Close'] / h_mdd['Close'].cummax() - 1.0).min() * 100:.2f}%"
                    mdd_detail = _drawdown_detail(h_mdd['Close'])
                    if len(h_mdd) > 10:
                        total_return_5y = (current_price - h_mdd['Close'].iloc[0]) / h_mdd['Close'].iloc[0]
                        final_amount = 10000000 * (1 + total_return_5y)
                        simulated_result = f"5년 전 1,000만 원 투자 시 현재 가치 약 {int(final_amount/10000):,}만 원"
                        # 실제 보유 기간(연 단위)을 반영한 CAGR 계산. IBIT처럼 상장한 지
                        # 2~3년밖에 안 된 ETF에 5년 CAGR을 그대로 적용하면 왜곡되므로,
                        # 실제로 확보된 데이터 기간(years_held)을 반영해 계산한다.
                        years_held = len(h_mdd) / 250.0
                        if years_held > 0 and (1 + total_return_5y) > 0:
                            cagr = (1 + total_return_5y) ** (1 / years_held) - 1

                    # [신규] MA200(200일 이동평균) 대비 현재가 위치. 이미 받아온
                    # 5년치 데이터(h_mdd)를 재사용해 추가 API 호출 없이 계산.
                    # AI 개입 없이 순수 파이썬 산술로만 처리되므로, 이 값을 잘못
                    # 서술할 위험이 없다(코드가 만든 완성 HTML을 그대로 삽입하는
                    # 구조라 지난번 명언/용어사전과 달리 AI가 재해석할 지점 자체가 없음).
                    if len(h_mdd) >= 200:
                        ma200 = h_mdd['Close'].tail(200).mean()
                        if ma200 > 0:
                            diff_pct = (current_price - ma200) / ma200 * 100
                            status = "MA200 상회 (중장기 상승 추세)" if diff_pct > 0 else "MA200 하회 (중장기 하락/조정 국면)"
                            ma200_info = {"status": status, "diff_pct": diff_pct}
            except Exception as e:
                print(f"   ⚠️ 5년 MDD/시뮬레이션 계산 실패: {type(e).__name__}: {e}")

            try:
                recent_divs = ticker.dividends[ticker.dividends.index >= (pd.Timestamp.now(tz=ticker.dividends.index.tz) - pd.DateOffset(years=1))]
                cnt = len(recent_divs)
                div_cycle = "월 배당" if cnt >= 9 else "분기 배당" if cnt >= 3 else "연 배당" if cnt >= 1 else "정보 없음"
                if current_price > 0 and not recent_divs.empty: calculated_yield = f"{(recent_divs.sum() / current_price * 100):.2f}%"
                
                div_hist = ticker.dividends.sort_index(ascending=False).head(5) if not ticker.dividends.empty else pd.Series(dtype=float)
                dividends_list = []
                div_items = list(div_hist.items())
                for i in range(min(4, len(div_items))):
                    d, v = div_items[i]
                    change_str = "-"
                    if i + 1 < len(div_items):
                        prev_v = div_items[i+1][1]
                        if prev_v > 0:
                            change_pct = ((v - prev_v) / prev_v) * 100
                            sign = "+" if change_pct > 0 else ""
                            change_str = f"{sign}{change_pct:.2f}%"
                    dividends_list.append({"date": d.strftime("%Y-%m-%d"), "val": f"{v:.4f} {currency}", "change": change_str})
                calculated_div_growth = _calculate_dividend_growth_rate(ticker.dividends)

                # [신규] 배당 안정성 설명. 이미 계산된 dividends_list(최근 4회
                # 배당 지급액과 직전 대비 증감률)를 재사용해, 감소 횟수를 세는
                # 순수 계산으로 안정성을 판단한다. AI가 만드는 문장이 아니라
                # 코드가 직접 만든 완성 문구를 section_htmls로 그대로 삽입하므로
                # 지어낸 서술이 들어갈 여지가 없다.
                if dividends_list:
                    # [수정] change 값이 "-"(비교 대상 데이터 없음)인 경우도
                    # startswith('-')에 걸려 "감소"로 잘못 카운트되는 버그가 있었음.
                    # 실제로 퍼센트 형태("-1.00%")인 경우만 감소로 카운트.
                    decrease_count = sum(
                        1 for item in dividends_list
                        if item.get('change', '-').startswith('-') and item.get('change', '-') != '-'
                    )
                    if decrease_count == 0:
                        dividend_stability_desc = f"최근 {len(dividends_list)}회 배당 지급액이 감소 없이 유지되거나 증가했습니다."
                    elif decrease_count == len(dividends_list):
                        dividend_stability_desc = f"최근 {len(dividends_list)}회 배당 지급액이 모두 직전 대비 감소했습니다. 배당 안정성에 유의가 필요합니다."
                    else:
                        dividend_stability_desc = f"최근 {len(dividends_list)}회 중 {decrease_count}회는 배당 지급액이 직전 대비 감소했습니다."
            except Exception as e:
                print(f"   ⚠️ 배당 정보 수집/계산 실패: {type(e).__name__}: {e}")

            # ==========================================
            # 보수율(Expense Ratio) 동적 스크래핑 자동화
            # ==========================================
            raw_er = info.get('expenseRatio')
            if raw_er and raw_er > 0:
                expense_ratio = f"{raw_er * 100:.2f}%"
            else:
                # API 누락 시 브라우저가 야후 파이낸스 메인에서 직접 수치를 뜯어옵니다.
                try:
                    driver.get(f"https://finance.yahoo.com/quote/{raw_code}")
                    # 단순 시간 대기 대신, 'Expense Ratio' 텍스트가 로드될 때까지 최대 10초 대기
                    WebDriverWait(driver, 10).until(
                        lambda d: re.search(r'Expense Ratio', d.page_source, re.IGNORECASE)
                    )
                    time.sleep(0.5) # 브라우저 렌더링 안정화 여유 시간
                    
                    match = re.search(r'Expense Ratio.{0,150}?(\d+\.?\d*)\s*%', driver.page_source, re.IGNORECASE | re.DOTALL)
                    if match:
                        expense_ratio = f"{match.group(1)}%"
                except Exception as e:
                    print(f"   ⚠️ 보수율 스크래핑 실패: {e}")

            aum_str = _get_aum_trend(raw_code)

            # [신규] 일드 갭(배당수익률 - 국채금리) 계산. 이미 매개변수로 받은
            # macro_data(거시경제 지표)와 위에서 계산된 calculated_yield를
            # 재사용해 순수 산술로 계산한다. AI 개입 없이 코드가 직접 숫자를
            # 만들고 완성된 HTML로 삽입하므로 지어낸 값이 들어갈 여지가 없다.
            try:
                us_10y_str = macro_data.get('us_10y', '') if macro_data else ''
                us_10y_val = float(str(us_10y_str).replace('%', '').strip()) if us_10y_str else None
                div_yield_val = float(str(calculated_yield).replace('%', '').strip())
                if us_10y_val is not None:
                    yield_gap = f"{div_yield_val - us_10y_val:.2f}%"
            except (ValueError, TypeError):
                yield_gap = None

            try:
                driver.get(f"https://finance.yahoo.com/quote/{raw_code}/holdings")
                time.sleep(2)
                for df in pd.read_html(StringIO(driver.page_source)):
                    df_str = df.to_string().lower()
                    if 'symbol' in df_str and 'name' in df_str:
                        w_col = [col for col in df.columns if '%' in str(col) or 'assets' in str(col).lower()][0]
                        for _, row in df.head(5).iterrows():
                            try:
                                sym = str(row.get('Symbol', row.iloc[0]))
                                top_holdings.append({"symbol": sym, "name": str(row.get('Name', row.iloc[1])), "weight": float(str(row[w_col]).replace('%', ''))})
                            except Exception:
                                continue
                        break
            except Exception as e:
                print(f"   ⚠️ Yahoo 스크래핑 실패: {e}")

            for h in top_holdings[:3]:
                sym = h['symbol']
                if sym and sym != "-":
                    e_date = _get_upcoming_earnings(yf.Ticker(sym))
                    if e_date: earnings_info.append(f"{sym}: {e_date}")

        except Exception as e:
            print(f"⚠️ Yahoo 데이터 수집 실패 ({raw_code}): {e}")

    # ==========================================
    # 공통 메타데이터 조립 및 캐싱
    # ==========================================
    # [중요] 이 값은 실제 환헤지 비용을 계산한 것이 아니라, "해외 상장이면 환노출
    # 리스크가 있다/한국 상장이면 없다"는 이진 신호를 0.00/0.25라는 숫자로 대충
    # 표현한 프록시임. 그런데 필드명이 "환헤지 비용"이고 사람에게 그대로 노출되면,
    # 마치 실제로 환헤지를 하고 그 비용이 0.25%라는 뜻으로 오해를 줌(실제로는
    # IBIT처럼 환헤지 상품이 아닌 환노출형 ETF에도 "환헤지 비용 0.25%"로 표시되어
    # 있었음 - 라벨과 값 둘 다 오해를 부르는 상태였음). 채점 로직(아래
    # _compute_custom_attractiveness)에서는 이 이진 신호를 그대로 재사용하되,
    # 사람에게 보여지는 필드는 "환노출 여부"라는 사실 그대로의 라벨로 분리한다.
    is_fx_exposed = not is_kr
    hedge_cost = 0.00 if is_kr else 0.25  # 채점 로직용 내부 신호 (그대로 유지)
    div_growth_pct = calculated_div_growth
    mdd_pct = float(mdd_val.replace('%','')) if '%' in mdd_val else None
    expense_ratio_float = float(expense_ratio.replace('%','')) if '%' in expense_ratio else None
    custom_score, custom_rationale = _compute_custom_attractiveness(mdd_pct, div_growth_pct, expense_ratio_float, hedge_cost)
    
    result = {
        "name": short_name, "currency": currency,
        "yield": calculated_yield, "returns": returns, "mdd": mdd_val, "mdd_detail": mdd_detail,
        "div_cycle": div_cycle, "expense_ratio": expense_ratio,
        "top_holdings": top_holdings,
        "earnings_info": earnings_info,
        # [수정] yield_gap은 위에서 이미 "1.23%" 형태의 완성된 문자열로 계산되는데,
        # 여기서 다시 f"{yield_gap:.2f}%"로 포맷을 적용하면 문자열에 숫자 포맷
        # 지정자를 쓰는 셈이라 ValueError가 발생하는 버그였음. 이미 완성된
        # 문자열이므로 그대로 사용.
        "yield_gap": yield_gap,
        "aum_str": aum_str,
        "simulated_result": simulated_result,
        "cagr": cagr,  # 실제 데이터 기반 CAGR (계산 실패 시 None - 임의값으로 대체하지 않음)
        "div_history": dividends_list,
        "dividend_growth_rate": f"{div_growth_pct:.2f}%" if div_growth_pct is not None else "정보 없음",
        # [신규] MA200/배당안정성 - 이전에는 이 필드들이 result에 전혀 채워지지
        # 않아서 관련 섹션이 절대 실행되지 않는 죽은 코드였음. 순수 계산값을 반영.
        "ma200_info": ma200_info,
        "dividend_stability_desc": dividend_stability_desc,
        # [수정] "환헤지 비용"이라는 실제로 계산한 적 없는 값을 계산한 것처럼
        # 보여주던 필드를 "환노출 여부"라는 사실 그대로의 라벨로 변경.
        "fx_exposure": _fx_exposure_label(is_kr, short_name),
        "listing": "국내 상장" if is_kr else "해외 상장",
        # 하루 거래대금(네이버 모바일 자료, 전일 기준) - 거의 같은 두 국내 ETF를 고를 때 남는 차이(2026-11-08 운용사 비교)
        "trade_value": kr_info.get("대금") if is_kr else None,
        "hedge_cost": f"{hedge_cost:.2f}%",  # 하위 호환용으로 유지 (내부 채점/세금계산 참조)
        "custom_attractiveness_score": custom_score,
        "custom_attractiveness_notes": custom_rationale,
        "tax_metrics": _estimate_account_tax_impact(calculated_yield, d={'expense_ratio': expense_ratio, 'hedge_cost': hedge_cost}, overseas=is_fx_exposed),
        "fee_impact_100m_10y": _estimate_fee_impact(100_000_000, expense_ratio),
        "issuer": info.get('fundFamily', '정보 없음') if not is_kr else "정보 없음",
        # [수정] 이전에는 info.get('underlyingSymbol', ...)를 "추종 지수"로 썼는데,
        # 실제로 yfinance의 underlyingSymbol은 그 ETF 자기 자신의 티커를 반환하는
        # 필드였음(예: IBIT를 조회하면 'IBIT'가 그대로 나옴). 그 결과 "지수: IBIT"
        # 처럼 잘못된 값이 AI 팩트시트와 뉴스 검색 쿼리(_get_recent_news_for_etfs)에
        # 그대로 들어가, AI가 "이 ETF가 추종하는 지수는 IBIT입니다" 같은 이상한
        # 문장을 쓸 위험이 있었음. category(카테고리 분류)가 지수와 유사한 정보를
        # 담는 경우가 있어 대신 시도하고, 없으면 지어내지 않고 정직하게 "정보 없음"으로 처리.
        "index": info.get('category', '정보 없음') if not is_kr else (kr_index or "정보 없음"),
        "sector": info.get('sector', '정보 없음') if not is_kr else "정보 없음",
        "industry": info.get('industry', '정보 없음') if not is_kr else "정보 없음",
        "inception_date": inception_date_str if not is_kr else "정보 없음",
        "description": info.get('longBusinessSummary', '정보 없음')[:300] if not is_kr else "정보 없음",
        "tv_symbol": "KRX200" if is_kr else raw_code,
        "website": info.get('website', '공식 홈페이지 정보 없음') if not is_kr else "정보 없음",
        "investing_url": (f"{INVESTING_BASE}/{INVESTING_ETF_SLUGS[raw_code]}" if raw_code in INVESTING_ETF_SLUGS
                          else f"{INVESTING_SEARCH}{urllib.parse.quote(raw_code)}") if not is_kr else ""
    }
    _set_cached_record(cache, ticker_symbol, result)
    return result

# 세법 기준값. 세법이 바뀌면 여기만 고치면 된다. (확인 시점: TAX_RULES_BASIS)
TAX_RULES_BASIS = "2026년 10월 기준 세법"   # 2026-10-31 확인: ISA 한도는 2025년과 같음. 2027년 개편안은 국회 심의 중
TAX_DOMESTIC_DIVIDEND = 0.154          # 국내 일반계좌 배당소득세(해외지수·채권형 국내 ETF 매매차익 포함)
TAX_US_DIVIDEND_WITHHOLDING = 0.15     # 미국 상장 ETF 배당 원천징수(한미 조세조약)
TAX_OVERSEAS_CAPITAL_GAINS = 0.22      # 해외 상장 주식/ETF 양도소득세(지방세 포함)
OVERSEAS_CG_DEDUCTION = 2_500_000      # 해외 양도소득 연 기본공제
ISA_TAX_FREE_LIMIT = 2_000_000         # ISA 일반형 비과세 한도(서민형은 400만 원)
ISA_SEPARATE_TAX = 0.099               # ISA 비과세 한도 초과분 분리과세
PENSION_TAX = 0.055                    # 연금 수령 시 연금소득세 3.3~5.5% 중 최고치(보수적 가정)
OVERSEAS_ACCOUNT_NOTE = (
    "해외(미국 등) 상장 ETF는 ISA·연금저축·IRP 계좌로 직접 살 수 없습니다. "
    "이 계좌들의 세제 혜택을 쓰려면 같은 지수를 추종하는 국내 상장 ETF를 사야 합니다."
)


def _is_overseas_listed(d):
    """해외 상장인가(ISA·연금계좌로 직접 못 사는가). 환노출 여부와는 다른 질문이라 상장 위치로 판단한다."""
    d = d or {}
    if d.get('listing'):
        return d['listing'] == "해외 상장"
    return str(d.get('fx_exposure', '')).startswith('있음 (해외 상장')   # 예전 기록 호환


# 국내 상장이라도 해외 자산을 담으면 환율 영향을 받는다(예: 360750 TIGER 미국S&P500은 환노출형).
# 예전에는 "국내 상장 = 환노출 없음"으로 처리해서 글에 사실 오류가 나갔다(2026-10-31).
_FOREIGN_ASSET_WORDS = ("미국", "S&P", "나스닥", "NASDAQ", "다우", "글로벌", "선진국", "신흥국", "차이나", "중국",
                        "일본", "인도", "베트남", "유럽", "독일", "필라델피아", "반도체TOP", "빅테크", "MSCI",
                        "달러", "국채", "TLT", "금현물", "골드", "원유", "WTI")


def _fx_exposure_label(is_kr, name):
    if not is_kr:
        return "있음 (해외 상장, 달러로 거래)"
    n = str(name or "")
    if "(H)" in n or "헤지" in n:
        return "환헤지형 (국내 상장, 환율 영향을 줄인 상품)"
    if any(w.lower() in n.lower() for w in _FOREIGN_ASSET_WORDS):
        return "있음 (국내 상장이지만 해외 자산, 환헤지 안 함)"
    return "확인 필요"


def _estimate_account_tax_impact(yield_str, d=None, overseas=False):
    try:
        if not yield_str:
            return {"taxable_dividend_tax": "정보 없음", "isa_tax_saving": "정보 없음", "irp_tax_saving": "정보 없음", "pension_tax_saving": "정보 없음", "account_note": OVERSEAS_ACCOUNT_NOTE if overseas else ""}

        yield_val = float(str(yield_str).replace('%','').strip())
        dividend_income = 100_000_000 * (yield_val / 100)

        if overseas:
            na = "해당 없음(해외 상장 ETF는 이 계좌로 매수 불가)"
            return {
                "taxable_dividend_tax": f"{dividend_income * TAX_US_DIVIDEND_WITHHOLDING:,.0f}원(미국 원천징수 15%)",
                "isa_tax_saving": na,
                "irp_tax_saving": na,
                "pension_tax_saving": na,
                "account_note": OVERSEAS_ACCOUNT_NOTE,
                "notes": f"{TAX_RULES_BASIS}. 배당은 미국에서 15% 원천징수, 매매차익은 연 250만 원 공제 후 22% 양도소득세(다음 해 5월 직접 신고)."
            }

        taxable_tax = dividend_income * TAX_DOMESTIC_DIVIDEND
        isa_tax = max(0.0, dividend_income - ISA_TAX_FREE_LIMIT) * ISA_SEPARATE_TAX
        pension_tax = dividend_income * PENSION_TAX
        return {
            "taxable_dividend_tax": f"{taxable_tax:,.0f}원",
            "isa_tax_saving": f"{(taxable_tax - isa_tax):,.0f}원",
            "irp_tax_saving": f"{(taxable_tax - pension_tax):,.0f}원",
            "pension_tax_saving": f"{(taxable_tax - pension_tax):,.0f}원",
            "account_note": "",
            "notes": f"{TAX_RULES_BASIS}. ISA는 200만 원(서민형 400만 원)까지 비과세, 초과분 9.9% 분리과세, 3년 의무가입. 연금저축/IRP는 인출 전까지 과세 이연, 연금 수령 시 3.3~5.5%."
        }
    except (ValueError, TypeError):
        return {"taxable_dividend_tax": "계산 실패", "isa_tax_saving": "계산 실패", "irp_tax_saving": "계산 실패", "pension_tax_saving": "계산 실패", "account_note": OVERSEAS_ACCOUNT_NOTE if overseas else ""}


def _estimate_fee_impact(principal, expense_ratio):
    try:
        er = float(str(expense_ratio).replace('%','').strip()) if expense_ratio and isinstance(expense_ratio, str) else float(expense_ratio or 0)
        diff_er = 0.1
        future_value_base = principal * ((1 + (er/100)) ** 10)
        future_value_lower = principal * ((1 + ((er - diff_er)/100)) ** 10)
        loss = future_value_base - future_value_lower
        return f"약 {loss:,.0f}원 (0.1% 포인트 차이로 10년 후 잠재 손실)"
    except (ValueError, TypeError):
        return "정보 없음"

# ============================================================
# [신규] 예산/한도 감시 부서 - API 호출 통계를 자동 수집해서 주간 리포트에 반영
#
# 지금까지는 429가 실제로 떠야만 반응하는 "사후 대응"이었다. 이 통계는
# 매 실행마다 "무슨 모델을 몇 번 썼고, 몇 번 소진돼서 다음 모델로
# 넘어갔는지"를 조용히 기록해뒀다가, 상태점검 부서가 주간 리포트에 같이
# 보여준다. atexit로 등록해서, 어떤 CLI 경로(--topic, --discover-and-notify,
# --check-approval 등)로 실행되든 프로세스가 끝날 때 자동으로 기록이
# 저장된다 - 호출부마다 일일이 저장 코드를 넣을 필요가 없다.
# ============================================================











# [신규] 키 로테이션을 위한 현재 키 인덱스. 마지막으로 성공했던 키부터
# 다음 호출을 시작하도록 함수 호출 사이에 유지되는 전역 상태.


# [신규] "모든 API 키가 완전히 소진된 상태"를 전역으로 기억하는 플래그.
# 이전에는 각 함수(Part 생성, Part 검수, 최종 검수)가 서로 독립적으로 "이번엔
# 되겠지"라며 각자 최대 10번씩 재시도를 반복해서, 실제로 무료 티어의 일일
# 한도(RPD)가 이미 소진된 상황에서도 수십~수백 번의 헛된 API 요청이 계속
# 나가는 문제가 있었음(실제로 한 편에 100회 이상 요청이 발생한 사례 확인).
# 한 번이라도 "모든 키를 다 순회했는데도 실패"가 확인되면, 이 플래그를 세워서
# 이후의 모든 호출이 재시도 없이 즉시 포기하도록 한다.

# [추가] 모든 키가 소진된 것으로 확인된 "시각"을 기록. 이 시각으로부터 일정
# 시간이 지나면 한 번 더 전체 키를 시도해볼 수 있게 한다. 여러 키가 서로 다른
# Google 계정/프로젝트에서 발급된 경우, 하루 한도(RPD, 자정까지 회복 안 됨)가
# 아니라 분당 한도(RPM, 1분 이내 회복)에 짧은 시간 동안 몰려서 걸렸을 가능성이
# 있으므로, 무조건 포기하지 않고 한 번 더 기회를 준다.
# 재시도까지 기다릴 시간(초). RPM 제한이면 1분이면 충분하지만, 여러 키가
# 겹쳐서 몰린 경우를 대비해 여유 있게 5분으로 설정.
# [추가] "5분 대기 후 재시도"를 몇 번이나 반복했는지 세는 카운터. RPD(일일
# 한도) 소진이라면 5분을 아무리 기다려도 계속 실패하므로, 무한정 5분마다
# 재시도하는 것을 막기 위해 최대 반복 횟수를 둔다. 이 횟수를 넘기면 진짜로
# 하루 한도 소진으로 보고 완전히 포기한다.

# [추가] 403(PERMISSION_DENIED)을 받아 이번 실행 동안 완전히 제외된 키 목록.
# 429(한도초과)는 시간이 지나면 풀릴 수 있어 순환 대상으로 유지하지만, 403은
# 프로젝트 자체가 접근을 거부당한 상태라 재시도해도 절대 성공하지 않으므로
# 순환 목록에서 아예 빼야 불필요한 재시도를 막을 수 있다.

# [신규] 모델 로테이션을 위한 현재 모델 인덱스. 키 로테이션(_current_key_index)과
# 마찬가지로 함수 호출 사이에 유지되는 전역 상태 - 우선순위 리스트에서 지금
# 몇 번째 모델을 쓰고 있는지 가리킨다.

# [신규] 이번 프로세스 실행 동안 계산한 모델 우선순위를 캐싱해서, 매 호출마다
# .env를 다시 파싱하지 않게 한다.

















def _compute_custom_attractiveness(mdd_percent, div_growth_rate, expense_ratio, hedge_cost):
    score = 5.0
    rationale = []

    if expense_ratio is not None:
        if expense_ratio <= 0.2:
            score += 1.5; rationale.append("운용보수 낮음(+1.5)")
        elif expense_ratio <= 0.4:
            score += 0.5; rationale.append("운용보수 보통(+0.5)")
        else:
            score -= 1.0; rationale.append("운용보수 높음(-1.0)")

    if mdd_percent is not None:
        # [수정] mdd_percent는 "-53.30"처럼 음수로 들어오는데, 기존 조건문이
        # 양수 기준(mdd_percent <= 20)으로 짜여있어서 음수는 항상 조건을
        # 통과해버림 - 즉 MDD가 -90%여도 "안정적(+1.0)" 가점을 받는 버그가
        # 있었음(IBIT의 MDD -53.30%가 "안정적"으로 잘못 채점된 실제 사례로 확인).
        # 절대값으로 변환해 낙폭의 "크기"를 기준으로 채점하도록 수정.
        mdd_abs = abs(mdd_percent)
        if mdd_abs <= 20:
            score += 1.0; rationale.append("MDD 안정적(+1.0)")
        elif mdd_abs <= 30:
            rationale.append("MDD 보통(0)")
        else:
            score -= 1.2; rationale.append("MDD 높음(-1.2)")

    if div_growth_rate is not None:
        if div_growth_rate >= 5:
            score += 1.0; rationale.append("배당성장률 강세(+1.0)")
        elif div_growth_rate >= 0:
            score += 0.3; rationale.append("배당성장률 양호(+0.3)")
        else:
            score -= 0.8; rationale.append("배당성장률 하락(-0.8)")

    if hedge_cost is not None:
        if hedge_cost >= 0.15:
            score -= 0.6; rationale.append("환헤지 비용 높음(-0.6)")
        else:
            score += 0.2; rationale.append("환헤지 비용 적정(+0.2)")

    score = max(1.0, min(10.0, score))
    return round(score, 1), rationale






def _create_widget_html(ticker, data, wrapper_style, usd_krw_rate=1300.0):
    """티스토리 환경에 최적화된 JS 인터랙티브 차트 (렌지슬라이더 제거, 날짜 정렬, 버튼 보안 우회)"""
    is_kr = ticker.endswith('.KS')
    raw_code = ticker.replace('.KS', '') if is_kr else ticker
    safe_id = raw_code.replace('.', '_')

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        hist = ticker_obj.history(period="5y") 
        
        if not hist.empty:
            hist[['Open', 'High', 'Low', 'Close']] = hist[['Open', 'High', 'Low', 'Close']].apply(pd.to_numeric, errors='coerce')
            hist = hist.dropna(subset=['Open', 'High', 'Low', 'Close'])
            if len(hist) > 21: hist = hist.iloc[:-21]
        
        if hist.empty:
            return f'<div style="{wrapper_style}"><p>📊 차트 데이터가 없습니다.</p></div>'
            
        currency_symbol = "₩" if is_kr else "$"
        if not is_kr and usd_krw_rate > 1.0:
            hist[['Open', 'High', 'Low', 'Close']] *= usd_krw_rate
            currency_symbol = "₩"
            
        monthly = hist.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        weekly = hist.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()

        if monthly.empty or weekly.empty:
            return f'<div style="{wrapper_style}"><p>📊 데이터가 부족합니다.</p></div>'

        # 문자열 리스트로 추출
        monthly_idx_str = monthly.index.strftime('%Y-%m-%d').tolist()
        weekly_idx_str = weekly.index.strftime('%Y-%m-%d').tolist()
        
        chart_title = data.get("name", ticker)
        full_title = f"{chart_title}" if is_kr else f"{chart_title} ({ticker})"
        
        chart_id = f"chart_{safe_id}"
        plotly_script_id = f"plotly_script_{safe_id}"
        btn_m_id = f"btn_m_{safe_id}"
        btn_w_id = f"btn_w_{safe_id}"

        # 1. JS 데이터 구성
        chart_data = [
            {
                'type': 'candlestick',
                'x': monthly_idx_str,
                'open': monthly['Open'].tolist(),
                'high': monthly['High'].tolist(),
                'low': monthly['Low'].tolist(),
                'close': monthly['Close'].tolist(),
                'name': '월봉',
                'visible': True
            },
            {
                'type': 'candlestick',
                'x': weekly_idx_str,
                'open': weekly['Open'].tolist(),
                'high': weekly['High'].tolist(),
                'low': weekly['Low'].tolist(),
                'close': weekly['Close'].tolist(),
                'name': '주봉',
                'visible': False
            }
        ]

        # 2. JS 레이아웃 구성 (정신없는 UI 수정)
        chart_layout = {
            'title': f"{full_title} - 월봉",
            'yaxis': {'title': f"가격 ({currency_symbol})"},
            'xaxis': {
                'title': '날짜', 
                'type': 'category', 
                'rangeslider': {'visible': False}, # 🚨 렌지 슬라이더 강제 제거
                'nticks': 8,                       # 🚨 틱(날짜) 개수를 8개로 줄여서 여백 확보
                'tickangle': 0                     # 🚨 세로로 눕는 현상을 막고 가로 텍스트로 고정
            },
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'height': 450, 
            'margin': {'t': 60, 'b': 45, 'l': 50, 'r': 20}
        }

        # 3. 티스토리 보안 우회를 위한 Script 바인딩
        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initPlotly_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'    var btn_m = document.getElementById("{btn_m_id}");'
            f'    var btn_w = document.getElementById("{btn_w_id}");'
            f'    if(btn_m) btn_m.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [true, false]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 월봉"}}); }});'
            f'    if(btn_w) btn_w.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [false, true]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 주봉"}}); }});'
            f'  }}'
            f'  if(window.Plotly) initPlotly_{safe_id}();'
            f'  else if(!document.getElementById("{plotly_script_id}")) {{'
            f'    var s = document.createElement("script");'
            f'    s.id = "{plotly_script_id}";'
            f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'    s.onload = initPlotly_{safe_id};'
            f'    document.head.appendChild(s);'
            f'  }} else {{'
            f'    document.getElementById("{plotly_script_id}").addEventListener("load", initPlotly_{safe_id});'
            f'  }}'
            f'}})();'
            f'</script>'
        )

        chart_aria_label = f"{full_title} 월봉 및 주봉 캔들스틱 차트, 5년치 가격 추이"

        if CHART_MODE == "image":
            # [신규] <script> 태그가 실행되지 않는 환경(무료 워드프레스 등)을
            # 위해, 월봉/주봉을 각각 정적 PNG 이미지로 렌더링한다. "버튼으로
            # 전환"하는 인터랙션은 이미지로는 구현 불가능하므로, 대신 각각을
            # <details>(순수 HTML, JS 불필요)로 감싸 접어두고 클릭하면
            # 펼쳐서 보는 방식으로 대체한다.
            monthly_layout = dict(chart_layout)
            monthly_layout['title'] = f"{full_title} - 월봉"
            monthly_data = [{**chart_data[0], 'visible': True}]
            monthly_img = _plotly_fig_to_img_tag(monthly_data, monthly_layout, f"{full_title} 월봉 캔들스틱 차트", width=700, height=450)

            weekly_layout = dict(chart_layout)
            weekly_layout['title'] = f"{full_title} - 주봉"
            weekly_data = [{**chart_data[1], 'visible': True}]
            weekly_img = _plotly_fig_to_img_tag(weekly_data, weekly_layout, f"{full_title} 주봉 캔들스틱 차트", width=700, height=450)

            if not monthly_img and not weekly_img:
                return ""  # 둘 다 실패하면 이 섹션 자체를 조용히 생략

            sections_html = ""
            if monthly_img:
                sections_html += f'''
<details open style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📈 {full_title} 월봉 차트 보기 (클릭)</summary>
<div style="margin-top:15px;">{monthly_img}</div>
</details>
'''
            if weekly_img:
                sections_html += f'''
<details style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📈 {full_title} 주봉 차트 보기 (클릭)</summary>
<div style="margin-top:15px;">{weekly_img}</div>
</details>
'''
            return f'<div style="{wrapper_style}">{sections_html}</div>'

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{chart_aria_label}" style="width:100%;min-height:450px;"></div>'
        button_html = (
            f'<div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; margin-top:5px; margin-bottom:15px;">'
            f'<button id="{btn_m_id}" type="button" style="padding:8px 14px; border:1px solid #4A90E2; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">월봉</button>'
            f'<button id="{btn_w_id}" type="button" style="padding:8px 14px; border:1px solid #4A90E2; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">주봉</button>'
            f'</div>'
        )

        safe_wrapper_style = wrapper_style + " overflow: visible !important;"
        return f'<div style="{safe_wrapper_style}">{chart_div}{button_html}{chart_js}</div>'
        
    except Exception as e:
        print(f"⚠️ {ticker} Plotly 차트 생성 실패: {type(e).__name__}: {e}")
        fallback_url = f"https://finance.naver.com/item/main.naver?code={raw_code}" if is_kr else f"https://finance.yahoo.com/quote/{ticker}"
        fallback_name = "네이버 금융" if is_kr else "Yahoo Finance"
        return (
            f'<div style="{wrapper_style} text-align: center; padding: 30px; background: #f9f9f9; border-radius: 8px;">'
            f'<h4 style="color: #333; margin-bottom: 15px;">📊 {data.get("name", ticker)}</h4>'
            f'<p style="color: #666; margin-bottom: 20px;">차트 데이터를 생성할 수 없습니다. 아래 링크에서 확인하세요.</p>'
            f'<a href="{fallback_url}" target="_blank" style="display: inline-block; background: #2ecc71; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold;">📈 {fallback_name}에서 보기</a>'
            f'</div>'
        )

def _plotly_fig_to_img_tag(chart_data, chart_layout, alt_text, width=700, height=400):
    """[신규] Plotly 차트 데이터를 정적 PNG 이미지로 렌더링해 <img> 태그로
    반환한다. CHART_MODE=image일 때 사용되며, <script> 태그 없이 순수 HTML
    <img>만으로 차트를 보여줄 수 있어 무료 워드프레스 요금제에서도 작동한다.

    이미지는 파일로 저장해 별도 업로드하는 대신 base64로 인코딩해 <img
    src="data:image/png;base64,...">로 직접 HTML에 심는다 - 이러면 이미지
    업로드라는 별도 반자동 단계 없이, 완성된 HTML 하나만 붙여넣으면 된다.

    실패 시(kaleido 미설치, Chrome 없음 등) 빈 문자열을 반환하고 원인을
    로그로 남긴다 - 이 경우 호출부가 안전하게 이 섹션을 생략해야 한다."""
    try:
        import plotly.graph_objects as go
        import base64

        fig = go.Figure(data=chart_data, layout=chart_layout)
        img_bytes = fig.to_image(format="png", width=width, height=height, scale=2)
        b64_data = base64.b64encode(img_bytes).decode('utf-8')
        return f'<img src="data:image/png;base64,{b64_data}" alt="{alt_text}" style="width:100%;max-width:{width}px;height:auto;display:block;margin:0 auto;" />'
    except ImportError:
        print("⚠️ 이미지 차트 생성 실패: plotly 또는 kaleido가 설치되지 않았습니다. (pip install plotly kaleido)")
        return ""
    except Exception as e:
        print(f"⚠️ 이미지 차트 생성 실패: {type(e).__name__}: {e}")
        print("   Chrome이 설치되어 있는지 확인해보세요 (kaleido 1.0+는 Chrome이 필요합니다).")
        return ""


def _create_return_calendar_heatmap(ticker, data, wrapper_style, usd_krw_rate=1300.0, months=3):
    """[신규] '존버 캘린더' - 최근 N개월 일별 수익률을 깃허브 잔디밭 스타일 히트맵으로 시각화.
    - 예측이 아니라 100% 확정된 과거 종가 기반 계산이라 정보 왜곡/오류 위험이 낮음.
    - 한국 증시 관행에 맞춰 상승(+)=빨강, 하락(-)=파랑으로 색상 지정
      (기존 코드가 미국식 초록/빨강 관행을 쓰고 있던 것과는 별개로, 이 위젯은
      처음부터 한국 독자에게 익숙한 배색으로 만듦).
    - <details>/<summary>로 기본은 접힌 상태 - 본문이 어수선해지지 않도록 함.
    """
    is_kr = ticker.endswith(".KS")
    raw_code = ticker.replace(".KS", "") if is_kr else ticker
    safe_id = raw_code.replace(".", "_")

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        # 주말/공휴일을 감안해 여유 있게 가져온 뒤 최근 N개월만 자름
        hist = ticker_obj.history(period="9mo")
        if hist.empty:
            return ""

        hist = hist.copy()
        hist['Close'] = pd.to_numeric(hist['Close'], errors='coerce')
        hist = hist.dropna(subset=['Close'])

        cutoff = hist.index.max() - pd.DateOffset(months=months)
        hist = hist[hist.index >= cutoff]
        if len(hist) < 5:
            return ""

        daily_ret = hist['Close'].pct_change().dropna() * 100
        if daily_ret.empty:
            return ""

        # 요일(월~금)을 y축, ISO 주차를 x축으로 배치해 달력형 격자를 구성
        weekday_labels = ['월', '화', '수', '목', '금']
        iso = daily_ret.index.isocalendar()
        week_keys = [f"{y}-W{w:02d}" for y, w in zip(iso['year'], iso['week'])]
        unique_weeks = sorted(set(week_keys), key=lambda s: (int(s[:4]), int(s[6:])))

        z = [[None] * len(unique_weeks) for _ in range(5)]
        hover = [[""] * len(unique_weeks) for _ in range(5)]
        week_index = {w: i for i, w in enumerate(unique_weeks)}

        for date, ret, wk in zip(daily_ret.index, daily_ret.values, week_keys):
            weekday = date.weekday()  # 0=월 ... 4=금
            if weekday > 4:
                continue
            col = week_index[wk]
            z[weekday][col] = round(float(ret), 2)
            sign = "+" if ret >= 0 else ""
            hover[weekday][col] = f"{date.strftime('%Y-%m-%d')}<br>{sign}{ret:.2f}%"

        max_abs = max((abs(v) for row in z for v in row if v is not None), default=1.0) or 1.0

        # 한국 증시 관행: 상승(+)=빨강, 하락(-)=파랑
        colorscale = [
            [0.0, "#2166ac"],   # 최대 하락 - 진한 파랑
            [0.5, "#f7f7f7"],   # 보합(0%) - 회색
            [1.0, "#b2182b"],   # 최대 상승 - 진한 빨강
        ]

        chart_id = f"calendar_{safe_id}"
        plotly_script_id = f"calendar_plotly_script_{safe_id}"
        chart_name = data.get("name", ticker)

        chart_data = [{
            "type": "heatmap",
            "z": z,
            "x": unique_weeks,
            "y": weekday_labels,
            "text": hover,
            "hoverinfo": "text",
            "zmin": -max_abs,
            "zmax": max_abs,
            "colorscale": colorscale,
            "showscale": True,
            "xgap": 3,
            "ygap": 3,
            "colorbar": {"title": "%", "thickness": 12},
        }]
        chart_layout = {
            "title": f"{chart_name} 최근 {months}개월 일별 손익 캘린더",
            "xaxis": {"title": "", "type": "category", "tickangle": -45, "nticks": 10},
            "yaxis": {"title": "", "autorange": "reversed"},
            "template": "plotly_white",
            "height": 300,
            "margin": {"t": 50, "b": 60, "l": 40, "r": 20},
        }

        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initCalendar_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'  }}'
            f'  var trigger = document.getElementById("details_{chart_id}");'
            f'  var rendered_{safe_id} = false;'
            f'  function renderOnce_{safe_id}() {{'
            f'    if(rendered_{safe_id}) return;'
            f'    rendered_{safe_id} = true;'
            f'    if(window.Plotly) initCalendar_{safe_id}();'
            f'    else if(!document.getElementById("{plotly_script_id}")) {{'
            f'      var s = document.createElement("script");'
            f'      s.id = "{plotly_script_id}";'
            f'      s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'      s.onload = initCalendar_{safe_id};'
            f'      document.head.appendChild(s);'
            f'    }} else {{'
            f'      document.getElementById("{plotly_script_id}").addEventListener("load", initCalendar_{safe_id});'
            f'    }}'
            f'  }}'
            # <details>가 펼쳐질 때만 렌더링 - 접힌 상태에서 불필요하게 차트를 그리지 않음
            f'  if(trigger) trigger.addEventListener("toggle", function(){{ if(trigger.open) renderOnce_{safe_id}(); }});'
            f'}})();'
            f'</script>'
        )

        aria_label = f"{chart_name} 최근 {months}개월 일별 수익률 달력형 히트맵"

        if CHART_MODE == "image":
            # [신규] <script> 태그가 실행되지 않는 환경(무료 워드프레스 등)을
            # 위해, 정적 PNG 이미지로 렌더링해 <img> 태그로 보여준다.
            # <details> 접기/펼치기는 포기하고 항상 펼쳐진 상태로 보여준다
            # (JS 없이는 toggle 이벤트를 걸 수 없으므로).
            img_tag = _plotly_fig_to_img_tag(chart_data, chart_layout, aria_label, width=700, height=300)
            if not img_tag:
                return ""  # 이미지 생성 실패 시 이 섹션 자체를 조용히 생략
            return f'''
<div style="{wrapper_style}margin-top:20px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<p style="margin:0 0 12px 0;font-weight:bold;color:#1f3c88;">📅 {chart_name} 최근 {months}개월 손익 캘린더</p>
{img_tag}
<p style="font-size:11px;color:#888;margin-top:8px;text-align:center;">
※ 실제 과거 종가 기준 일별 등락률입니다(예측 아님). 빨강=상승, 파랑=하락 (국내 증시 표기 관행).
</p>
</div>
'''

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{aria_label}" style="width:100%;min-height:300px;"></div>'

        return f'''
<details id="details_{chart_id}" style="{wrapper_style}margin-top:20px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📅 {chart_name} 최근 {months}개월 손익 캘린더 보기 (클릭)</summary>
<div style="margin-top:15px;">
{chart_div}
{chart_js}
<p style="font-size:11px;color:#888;margin-top:8px;text-align:center;">
※ 실제 과거 종가 기준 일별 등락률입니다(예측 아님). 빨강=상승, 파랑=하락 (국내 증시 표기 관행).
</p>
</div>
</details>
'''
    except Exception as e:
        print(f"⚠️ {ticker} 손익 캘린더 생성 실패: {type(e).__name__}: {e}")
        return ""






MACRO_THERMOMETER_CACHE_TTL = 60 * 60 * 6  # 6시간 캐시 (지표 자체가 하루 여러 번 바뀌지 않음)


def get_macro_thermometer_indicators():
    """
    [신규] 4대 거시 온도계(변동성/밸류에이션/환율/인플레이션)에 필요한 원본 데이터를
    수집하고, 각각을 0~100 백분위/환산 점수로 만든다.

    ⚠️ 정확도에 대한 한계를 반드시 알고 있어야 함 (안내 문구에도 그대로 노출됨):
    - 변동성(VIX)과 환율은 최근 실제 데이터 대비 진짜 백분위 계산이라 근거가 탄탄함.
    - 인플레이션은 FRED(미 연준 경제데이터)의 공개 CSV 엔드포인트(API 키 불필요)에서
      최신 CPI(도시 소비자물가지수) 시계열을 받아 전년동월대비(YoY)로 계산.
    - 밸류에이션은 S&P500의 "진짜" 장기 PER 시계열을 무료로 안정적으로 주는 공식 API가
      없어서, SPY ETF의 현재 trailingPE를 고정 참고밴드(15~30, 장기 평균 근사치)와
      비교하는 **근사치**다. 학술적으로 검증된 백분위가 아니므로 절대 그렇게 포장하지
      말 것 - 본문/캡션에 "참고용 근사치"임을 항상 함께 노출해야 함.
    """
    cache = _load_cache()
    cached = _get_cached_record(cache, 'macro_thermometers', MACRO_THERMOMETER_CACHE_TTL)
    if cached:
        print("✅ 거시 온도계 데이터 캐시 사용")
        return cached

    result = {
        'volatility': None, 'valuation': None, 'fx': None, 'inflation': None,
        'volatility_raw': None, 'valuation_raw': None, 'fx_raw': None, 'inflation_raw': None,
    }

    # 1) 변동성 온도 (VIX 최근 5년 백분위)
    try:
        vix_hist = yf.Ticker("^VIX").history(period="5y")['Close'].dropna()
        if len(vix_hist) > 30:
            current = float(vix_hist.iloc[-1])
            pct = float((vix_hist < current).mean() * 100)
            result['volatility'] = round(pct, 1)
            result['volatility_raw'] = round(current, 2)
    except Exception as e:
        print(f"⚠️ 변동성(VIX) 온도계 조회 실패: {type(e).__name__}: {e}")

    # 2) 환율 온도 (USD/KRW 최근 2년 백분위)
    try:
        fx_hist = yf.Ticker("KRW=X").history(period="2y")['Close'].dropna()
        if len(fx_hist) > 30:
            current = float(fx_hist.iloc[-1])
            pct = float((fx_hist < current).mean() * 100)
            result['fx'] = round(pct, 1)
            result['fx_raw'] = round(current, 2)
    except Exception as e:
        print(f"⚠️ 환율 온도계 조회 실패: {type(e).__name__}: {e}")

    # 3) 밸류에이션 온도 (SPY trailingPE를 고정 참고밴드와 비교하는 근사치)
    try:
        pe = yf.Ticker("SPY").info.get('trailingPE')
        if pe:
            low, high = 15.0, 30.0  # 장기 평균 근사 밴드 (절대적 기준 아님)
            pct = (float(pe) - low) / (high - low) * 100
            result['valuation'] = round(max(0.0, min(100.0, pct)), 1)
            result['valuation_raw'] = round(float(pe), 2)
    except Exception as e:
        print(f"⚠️ 밸류에이션 온도계 조회 실패: {type(e).__name__}: {e}")

    # 4) 인플레이션 온도 (FRED CPIAUCSL 공개 CSV, API 키 불필요)
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            df = pd.read_csv(StringIO(r.text))
            df.columns = ['date', 'value']
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df = df.dropna().tail(14)  # YoY 계산에 최소 13개월 필요
            if len(df) >= 13:
                latest = float(df['value'].iloc[-1])
                year_ago = float(df['value'].iloc[-13])
                yoy = (latest - year_ago) / year_ago * 100
                # 연준 목표치 2%를 기준으로: 0~2%→0~40점, 2~6%→40~100점 선형 환산
                if yoy <= 2.0:
                    pct = (yoy / 2.0) * 40
                else:
                    pct = 40 + min((yoy - 2.0) / 4.0, 1.0) * 60
                result['inflation'] = round(max(0.0, min(100.0, pct)), 1)
                result['inflation_raw'] = round(yoy, 2)
    except Exception as e:
        print(f"⚠️ 인플레이션(CPI) 온도계 조회 실패: {type(e).__name__}: {e}")

    _set_cached_record(cache, 'macro_thermometers', result)
    return result


def _build_macro_thermometers_chart(indicators):
    """
    [신규] 변동성/밸류에이션/환율/인플레이션 4개 온도계 + 가중평균(30/30/20/20)
    종합 온도계를 Plotly 'indicator'(gauge+number) 트레이스로 그린다.

    기존 CHART_MODE 분기를 그대로 재사용한다:
    - CHART_MODE=script: 인터랙티브 Plotly (백테스트/캔들 차트와 동일한 패턴)
    - CHART_MODE=image: kaleido로 렌더링한 정적 PNG (_plotly_fig_to_img_tag 재사용)

    누락된 지표는 조용히 빼고 있는 지표만으로 종합 온도를 계산한다(가중치 정규화).
    지표가 하나도 없으면 빈 문자열을 반환해 섹션 자체를 생략한다(필수 요소 아님).
    """
    labels = {
        'volatility': '변동성',
        'valuation': '밸류에이션',
        'fx': '환율',
        'inflation': '인플레이션',
    }
    weights = {'volatility': 0.3, 'valuation': 0.3, 'fx': 0.2, 'inflation': 0.2}

    available = {k: v for k, v in indicators.items() if k in labels and isinstance(v, (int, float))}
    if not available:
        return ""

    total_weight = sum(weights[k] for k in available)
    composite = sum(available[k] * weights[k] for k in available) / total_weight

    def gauge_color(val):
        if val < 34: return '#3498db'   # 안정
        if val < 67: return '#f1c40f'   # 중립
        return '#e74c3c'                 # 과열/위험

    steps = [
        {'range': [0, 34], 'color': '#eaf4fc'},
        {'range': [34, 67], 'color': '#fdf6e3'},
        {'range': [67, 100], 'color': '#fdecea'},
    ]

    traces = []
    n = len(available)
    for i, (key, val) in enumerate(available.items()):
        traces.append({
            'type': 'indicator',
            'mode': 'gauge+number',
            'value': val,
            'title': {'text': labels[key], 'font': {'size': 14}},
            'number': {'suffix': '°'},
            'gauge': {'axis': {'range': [0, 100]}, 'bar': {'color': gauge_color(val)}, 'steps': steps},
            'domain': {'row': 0, 'column': i},
        })

    traces.append({
        'type': 'indicator',
        'mode': 'gauge+number',
        'value': round(composite, 1),
        'title': {'text': '종합 시장환경 온도계', 'font': {'size': 16}},
        'number': {'suffix': '°', 'font': {'size': 28}},
        'gauge': {'axis': {'range': [0, 100]}, 'bar': {'color': gauge_color(composite)}, 'steps': steps},
        'domain': {'row': 1, 'column': 0, 'x': [0.25, 0.75]},
    })

    layout = {
        'grid': {'rows': 2, 'columns': n, 'pattern': 'independent'},
        'template': 'plotly_white',
        'height': 480,
        'margin': {'t': 40, 'b': 20, 'l': 20, 'r': 20},
    }

    caption = (
        '<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
        '※ 변동성·환율은 최근 실제 데이터 대비 백분위, 인플레이션은 최신 CPI 전년동월대비, '
        '밸류에이션은 참고 밴드 기반 근사치입니다. 종합 온도는 변동성 30%+밸류에이션 30%+환율 20%+인플레이션 20% '
        '가중 평균이며, 자체 산출 방식으로 투자 판단의 근거가 아닌 참고용입니다.'
        '</p>'
    )

    if CHART_MODE == "image":
        img_tag = _plotly_fig_to_img_tag(traces, layout, "시장환경 4대 지표 온도계 및 종합 온도계", width=760, height=480)
        if not img_tag:
            return ""
        return f'<div style="margin:20px auto;max-width:780px;">{img_tag}{caption}</div>'

    chart_id = "macro_thermo_chart"
    plotly_script_id = "macro_thermo_plotly_script"
    chart_js = (
        f'<script>'
        f'(function(){{'
        f'  function initMacroThermo() {{'
        f'    var gd = document.getElementById("{chart_id}");'
        f'    if(!gd) return;'
        f'    var data = {json.dumps(traces, ensure_ascii=False)};'
        f'    var layout = {json.dumps(layout, ensure_ascii=False)};'
        f'    var config = {{responsive: true, displaylogo: false}};'
        f'    Plotly.newPlot(gd, data, layout, config);'
        f'  }}'
        f'  if(window.Plotly) initMacroThermo();'
        f'  else if(!document.getElementById("{plotly_script_id}")) {{'
        f'    var s = document.createElement("script");'
        f'    s.id = "{plotly_script_id}";'
        f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
        f'    s.onload = initMacroThermo;'
        f'    document.head.appendChild(s);'
        f'  }} else {{'
        f'    document.getElementById("{plotly_script_id}").addEventListener("load", initMacroThermo);'
        f'  }}'
        f'}})();'
        f'</script>'
    )

    return (
        f'<div style="margin:20px auto;max-width:780px;">'
        f'<div id="{chart_id}" style="width:100%;"></div>'
        f'{chart_js}'
        f'{caption}'
        f'</div>'
    )


















def _last_written_dates_by_group():
    """같은 지수/자산 묶음(group) 단위로 가장 최근에 쓴 날짜를 돌려준다."""
    by_group = {}
    for article in _load_state().get('articles', []):
        try:
            dt = datetime.fromisoformat(article.get('timestamp', ''))
        except (ValueError, TypeError):
            continue
        names = _article_ticker_names(article)
        for t in _article_tickers(article):
            g = _etf_group(t, names.get(t))
            if g not in by_group or dt > by_group[g]:
                by_group[g] = dt
    return by_group


def _recent_articles(n):
    state = _load_state()
    return sorted(state.get('articles', []), key=lambda a: a.get('timestamp', ''), reverse=True)[:n]


def _recent_theme_counts(n=RECENT_THEME_WINDOW):
    """최근 n편에서 주제별로 몇 편이었는지 센다. 비교 글처럼 한 글이 여러 주제를
    다루면 각 주제를 한 번씩 센다."""
    from collections import Counter
    counts = Counter()
    for article in _recent_articles(n):
        names = _article_ticker_names(article)
        for theme in {_etf_theme(t, names.get(t)) for t in _article_tickers(article)}:
            counts[theme] += 1
    return counts


def _saturated_themes():
    return {th for th, c in _recent_theme_counts().items() if c >= MAX_SAME_THEME_IN_WINDOW}


# [신규] 중복 방지 3단계 규칙에 쓰이는 기준값들. 대화로 합의된 대로:
# - 30일 안에 쓴 건 기본적으로 제외
# - 7일 안에 쓴 건 아무리 신호가 강해도 절대 제외 (하한선)
# - 7~30일 사이는 "숫자로 증명된 극단적 신호"일 때만 예외로 허용
# 숫자가 안 맞으면 이 4개 상수만 조정하면 된다.
COOLDOWN_NORMAL_DAYS = 30
COOLDOWN_HARD_FLOOR_DAYS = 7
EXCEPTION_PCT_CHANGE_THRESHOLD = 3.0    # 하루 등락률(%) 이 정도는 넘어야 "극단적"으로 인정
EXCEPTION_VOLUME_RATIO_THRESHOLD = 2.5  # 20일 평균 거래량 대비 배율이 이 정도는 넘어야 인정


def _classify_cooldown(days_since_last):
    """
    마지막으로 쓴 지 며칠 지났는지(days_since_last, 한 번도 안 썼으면 None)를
    보고 3단계 중 하나로 분류한다.
    반환값: "eligible"(자유롭게 후보 가능) / "exception_zone"(극단적 신호일 때만
    후보 가능) / "blocked"(무조건 후보 불가)
    """
    if days_since_last is None:
        return "eligible"
    if days_since_last < COOLDOWN_HARD_FLOOR_DAYS:
        return "blocked"
    if days_since_last < COOLDOWN_NORMAL_DAYS:
        return "exception_zone"
    return "eligible"


def _get_price_volume_signal(ticker):
    """
    yfinance로 해당 티커의 "오늘 등락률"과 "20일 평균 대비 거래량 배율"을 계산해서
    돌려준다. 실패하면 None (이 티커는 이번 발굴에서 그냥 건너뛴다는 뜻).

    signal_score는 두 수치를 하나의 점수로 합친 것으로, 후보들 사이의 순위를
    매기는 데만 쓰는 상대적인 값이다 (절대적인 의미는 없음). 등락률의 절댓값과
    거래량 배율(평소보다 얼마나 몰렸는지)을 함께 반영하도록 가중치를 대충
    잡아뒀다 - 실제로 써보면서 감이 안 맞으면 이 가중치(*1.0, *5.0)만
    조정하면 된다.
    """
    try:
        hist = yf.Ticker(ticker).history(period="2mo")
        if hist is None or len(hist) < 5:
            return None
        closes = hist['Close']
        volumes = hist['Volume']
        pct_change = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100)
        avg_volume_20 = float(volumes.iloc[-21:-1].mean()) if len(volumes) >= 21 else float(volumes.iloc[:-1].mean())
        today_volume = float(volumes.iloc[-1])
        volume_ratio = (today_volume / avg_volume_20) if avg_volume_20 > 0 else 1.0
        signal_score = abs(pct_change) * 1.0 + max(0.0, volume_ratio - 1.0) * 5.0
        return {
            "pct_change": round(pct_change, 2),
            "volume_ratio": round(volume_ratio, 2),
            "signal_score": round(signal_score, 2),
        }
    except Exception as e:
        print(f"⚠️ {ticker} 가격/거래량 신호 계산 실패: {type(e).__name__}: {e}")
        return None


def _get_recent_news_headlines(ticker, max_items=3):
    """
    yfinance의 .news 속성으로 해당 티커 관련 최근 뉴스 헤드라인을 가져온다
    (비공식 기능이라 형식이 가끔 바뀔 수 있음 - 실패해도 조용히 빈 리스트만
    돌려주고 나머지 로직에 지장 없게 함). 별도 API 키/가입이 필요 없어서
    지금 있는 yfinance 의존성만으로 바로 쓸 수 있다.
    """
    try:
        news_items = yf.Ticker(ticker).news or []
        headlines = []
        for item in news_items[:max_items]:
            # yfinance 버전에 따라 news 항목 구조가 최상위이거나 'content' 안에
            # 있을 수 있어 둘 다 시도한다.
            title = item.get('title') or item.get('content', {}).get('title')
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        print(f"⚠️ {ticker} 뉴스 헤드라인 조회 실패(무시하고 진행): {type(e).__name__}: {e}")
        return []


def discover_candidates(top_n=5):
    """
    [1번 부서: 발굴] 알려진 티커 전체를 대상으로 가격/거래량 신호를 계산하고,
    3단계 쿨다운 규칙을 적용해서 "오늘 후보로 낼 만한" 상위 top_n개를 뽑는다.

    반환: 후보 딕셔너리의 리스트, signal_score 내림차순.
    각 후보: {"ticker", "pct_change", "volume_ratio", "signal_score",
              "news": [...], "days_since_last", "cooldown_status"}
    후보가 하나도 없으면 빈 리스트를 돌려준다 (호출한 쪽이 재포스팅 로직으로
    폴백할지 판단).
    """
    now = datetime.now()
    load_dynamic_kr_etfs()
    last_by_group = _last_written_dates_by_group()
    universe = list(_universe().keys())
    saturated = _saturated_themes()
    if saturated:
        print(f"ℹ️ 최근 {RECENT_THEME_WINDOW}편에 몰린 주제라 오늘은 제외: {', '.join(sorted(saturated))}")

    candidates = []
    theme_skipped = []
    for ticker in universe:
        last_dt = last_by_group.get(_etf_group(ticker))
        days_since = (now - last_dt).days if last_dt else None
        status = _classify_cooldown(days_since)

        if status == "blocked":
            continue  # 7일 미만 - 무조건 제외, 신호 계산조차 안 함(호출 낭비 방지)

        signal = _get_price_volume_signal(ticker)
        if signal is None:
            continue

        if status == "exception_zone":
            # 7~30일 사이 - 숫자로 증명된 극단적 신호일 때만 통과
            is_extreme = (
                abs(signal["pct_change"]) >= EXCEPTION_PCT_CHANGE_THRESHOLD
                or signal["volume_ratio"] >= EXCEPTION_VOLUME_RATIO_THRESHOLD
            )
            if not is_extreme:
                continue

        entry = {
            "ticker": ticker,
            "theme": _etf_theme(ticker),
            "group": _etf_group(ticker),
            "days_since_last": days_since,
            "cooldown_status": status,
            **signal,
        }
        if entry["theme"] in saturated:
            theme_skipped.append(entry)
            continue
        candidates.append(entry)

    if not candidates and theme_skipped:
        # 주제 제한 때문에 후보가 0개가 되면 발행 자체가 멈추므로, 이때만 제한을 풀어준다.
        print("⚠️ 주제 제한을 적용하면 후보가 없어서, 오늘만 제한 없이 고릅니다.")
        candidates = theme_skipped

    candidates.sort(key=lambda c: c["signal_score"], reverse=True)
    # 같은 지수 묶음(예: SPY/VOO/IVV)은 신호가 가장 강한 하나만 남긴다.
    seen_groups = set()
    deduped = []
    for c in candidates:
        if c["group"] in seen_groups:
            continue
        seen_groups.add(c["group"])
        deduped.append(c)
    top_candidates = deduped[:top_n]

    # 뉴스는 최종 후보로 뽑힌 것들만 조회 (전체 12개마다 다 조회하면 느리고
    # 필요도 없음 - 어차피 후보에 못 들면 뉴스도 안 쓰임)
    for c in top_candidates:
        c["news"] = _get_recent_news_headlines(c["ticker"])
    _attach_search_trends(top_candidates)

    return top_candidates


def _recent_comparison_share(n=RECENT_TYPE_WINDOW):
    articles = _recent_articles(n)
    if not articles:
        return 0.0
    return sum(1 for a in articles if len(_article_tickers(a)) >= 2) / len(articles)


def _find_comparison_partner(ticker):
    """비교 글의 짝을 찾는다. 반환은 짝 티커 리스트(1~2개), 없으면 [].
    - 국내 ETF: 같은 지수의 다른 운용사 국내 상품이 있으면 1~2개(운용사 비교, 최대 3개 비교)
    - 같은 지수의 미국↔국내 상장
    - 같은 주제의 다른 묶음 중 최근 30일 안에 안 쓴 것
    이 중에서 무작위로 고른다."""
    load_dynamic_kr_etfs()
    universe = _universe()
    t = _normalize_ticker(ticker)
    group, theme, is_kr = _etf_group(t), _etf_theme(t), t.endswith('.KS')
    now = datetime.now()
    last_by_group = _last_written_dates_by_group()

    def group_is_fresh(x):
        dt = last_by_group.get(_etf_group(x))
        return dt is None or (now - dt).days >= COOLDOWN_NORMAL_DAYS

    same_group = [x for x in universe if x != t and _etf_group(x) == group]
    kr_siblings = [x for x in same_group if x.endswith('.KS')]
    cross_listed = [x for x in same_group if x.endswith('.KS') != is_kr]
    peers, seen = [], set()
    for x in universe:
        g = _etf_group(x)
        if x == t or g == group or _etf_theme(x) != theme or g in seen or not group_is_fresh(x):
            continue
        seen.add(g)
        peers.append(x)

    # 같은 지수 국내 운용사 비교(예: TIGER vs ACE vs SOL S&P500)는 검색 수요가 커서 절반 확률로 우선한다.
    if is_kr and kr_siblings and random.random() < 0.5:
        return random.sample(kr_siblings, min(2, len(kr_siblings)))
    options = []
    if is_kr and kr_siblings:
        options.append(random.sample(kr_siblings, min(2, len(kr_siblings))))
    if cross_listed:
        options.append([random.choice(cross_listed)])
    if peers:
        options.append([random.choice(peers)])
    return random.choice(options) if options else []


def _article_type_of(article):
    meta = (article.get('topic_data') or article.get('etf_data') or {}).get('_meta') or {}
    if meta.get('article_type') in ("guide", "issue"):
        return meta['article_type']
    return "comparison" if len(_article_tickers(article)) >= 2 else "analysis"


def _choose_explainer_topic(macro_data):
    """최근 글 종류 비율을 보고, 가이드/이슈 글이 목표 비율보다 모자라면 그 주제를 돌려준다.
    반환: ("GUIDE:id" 또는 "ISSUE:id", 글 종류 이름, 사유) 또는 None(오늘은 ETF 글)."""
    import explainer_engine as xe
    articles = _recent_articles(EXPLAINER_TYPE_WINDOW)
    if len(articles) < EXPLAINER_MIN_HISTORY:
        return None
    shares = {k: sum(1 for a in articles if _article_type_of(a) == k) / len(articles) for k in EXPLAINER_TARGET_SHARE}
    for kind in sorted(EXPLAINER_TARGET_SHARE, key=lambda k: EXPLAINER_TARGET_SHARE[k] - shares[k], reverse=True):
        if shares[kind] >= EXPLAINER_TARGET_SHARE[kind]:
            continue
        if kind == "guide":
            t = xe.pick_guide_topic()
            if t:
                return f"GUIDE:{t['id']}", "기초 가이드", f"최근 {len(articles)}편 중 가이드 비율 {shares[kind]:.0%} (목표 {EXPLAINER_TARGET_SHARE[kind]:.0%})"
        else:
            issue_kind, why = xe.pick_issue_kind(macro_data)
            if issue_kind:
                return f"ISSUE:{issue_kind}", "이슈 해설", why
    return None


def _topic_label(topic):
    if topic.startswith(("GUIDE:", "ISSUE:")):
        import explainer_engine as xe
        return xe.topic_label(topic)
    tickers = [x for x in topic.split(",") if x]
    return " vs ".join(f"{_etf_display_name(x)}({_etf_theme(x)})" for x in tickers)


def get_trending_candidates():
    """[하위 호환용] 예전 pick_next_topic()이 쓰던 단순 후보 목록.
    discover_candidates()로 대체됐지만, 혹시 다른 곳에서 참조할 경우를 대비해 남겨둠."""
    return list(_universe().keys())


def pick_next_topic(cooldown_days=14, repost_after_days=90):
    """
    [구버전, 하위 호환용] 발굴+토론 파이프라인(discover_candidates +
    debate_and_select)을 쓰지 않는 간단한 경로(--topic 없이 그냥 실행하는
    구버전 흐름)에서 쓰인다. 새 3단계 쿨다운 규칙을 간략화해서 반영한다.
    """
    now = datetime.now()
    last_by_group = _last_written_dates_by_group()
    saturated = _saturated_themes()
    universe = get_trending_candidates()

    def days_since(t):
        dt = last_by_group.get(_etf_group(t))
        return (now - dt).days if dt else None

    fresh = [t for t in universe if days_since(t) is None or days_since(t) >= COOLDOWN_NORMAL_DAYS]
    fresh_unsaturated = [t for t in fresh if _etf_theme(t) not in saturated]
    if fresh_unsaturated or fresh:
        return {"ticker": (fresh_unsaturated or fresh)[0], "reason": "new"}

    stale = [t for t in universe if (days_since(t) or 0) >= repost_after_days]
    if stale:
        return {"ticker": max(stale, key=lambda t: days_since(t) or 0), "reason": "repost"}

    # 모두 최근에 썼다면, 가장 오래전에 쓴 묶음을 고른다(방금 쓴 종목 반복 방지).
    return {"ticker": max(universe, key=lambda t: days_since(t) or 0), "reason": "fallback"}


# ============================================================
# [2번 부서: 토론] 후보별 독립 옹호 논거 생성 -> 심사(최종 선정)
# ============================================================

def _trend_keyword(ticker):
    """구글 트렌드에서 검색할 단어. 미국 ETF는 티커(한국에서도 SCHD·QQQ처럼 티커로 많이 검색),
    국내 ETF는 상품명보다 검색량이 잡히는 지수/주제 이름을 쓴다."""
    t = _normalize_ticker(ticker)
    if not t.endswith(".KS"):
        return t
    meta = _etf_meta(t)
    if meta["theme"] == "커버드콜":
        return "커버드콜 ETF"
    group = re.sub(r"\(.*?\)", "", meta["group"]).strip()
    if group in (t, meta.get("name")):
        return meta.get("name") or t
    return f"{group} ETF" if len(group) <= 4 else group


def _attach_search_trends(candidates):
    """후보마다 구글 검색 관심도(최근 7일 vs 3개월 평균)를 붙인다. 실패하면 조용히 건너뜀."""
    try:
        import trend_engine
        keywords = {c["ticker"]: _trend_keyword(c["ticker"]) for c in candidates}
        interest = trend_engine.get_interest(list(keywords.values()), geo="KR", timeframe="today 3-m")
    except Exception as e:
        print(f"ℹ️ 검색 트렌드 조회 건너뜀: {type(e).__name__}: {e}")
        return candidates
    for c in candidates:
        kw = keywords.get(c["ticker"])
        if kw in interest:
            c["search_trend"] = {"keyword": kw, **interest[kw]}
    return candidates


def _trend_line(candidate):
    tr = candidate.get("search_trend")
    if not tr:
        return ""
    return (f"구글 검색 관심도(한국, '{tr['keyword']}'): 최근 7일 평균이 3개월 평균 대비 "
            f"{tr['momentum_pct']:+.1f}% (참고 신호일 뿐, 숫자가 작으면 큰 의미를 두지 마세요)\n")


def _build_advocate_prompt(candidate):
    news_lines = "\n".join(f"- {h}" for h in candidate.get("news", [])) or "(관련 뉴스 헤드라인을 찾지 못함)"
    return f"""당신은 ETF 분석 블로그의 콘텐츠 기획자입니다.
아래 후보 하나에 대해서만, "오늘 이 종목을 다뤄야 하는 이유"를 데이터 근거로 논증해주세요.
다른 후보와 비교하지 말고, 이 후보 하나의 장점/시의성에만 집중하세요.

[후보 정보]
티커: {candidate['ticker']} ({_etf_display_name(candidate['ticker'])}, 주제: {candidate.get('theme', '')})
전일 대비 등락률: {candidate['pct_change']}%
20일 평균 대비 거래량 배율: {candidate['volume_ratio']}배
최근 관련 뉴스:
{news_lines}
마지막으로 이 티커를 다룬 지: {candidate['days_since_last']}일 전 (없으면 처음 다루는 것)
{_trend_line(candidate)}
[요청]
1) 이 종목이 오늘 시의성 있는 이유를 2~3문장으로 설명
2) 독자에게 어떤 흥미로운 이야깃거리를 줄 수 있는지 1~2문장으로 설명
반드시 JSON 형식으로만 답하세요: {{"ticker": "{candidate['ticker']}", "argument": "여기에 논거 전문"}}
"""


def _build_judge_prompt(candidate_arguments, performance_summary=None, diversity_note=None):
    blocks = []
    for arg in candidate_arguments:
        blocks.append(f"- 티커 {arg['ticker']}: {arg['argument']}")
    joined = "\n".join(blocks)

    # [신규] 성과 분석 부서가 활성화된(데이터가 충분히 쌓인) 경우에만 이 블록이
    # 채워진다. 아직 비활성 상태(None)면 그냥 빈 문자열이라 심사 프롬프트에
    # 어떤 영향도 주지 않는다 - 즉 지금 당장은 기존과 완전히 동일하게 동작한다.
    performance_block = f"\n{performance_summary}\n" if performance_summary else ""
    # [신규] 다양성 관리 부서 - 최근 카테고리 편중이 없으면 역시 빈 문자열.
    diversity_block = f"\n{diversity_note}\n" if diversity_note else ""

    return f"""당신은 ETF 분석 블로그의 편집장입니다.
아래는 서로 다른 담당자들이 각자 독립적으로 작성한, "오늘의 포스팅 주제로 이 종목을 선택해야 하는 이유" 논거들입니다.
이 중에서 오늘 포스팅할 주제로 가장 적합한 것 딱 하나를 선정하세요.

[후보별 논거]
{joined}
{performance_block}{diversity_block}
[판단 기준]
- 시의성(오늘/최근 며칠 안에 왜 지금 다뤄야 하는지)
- 독자 흥미도(뻔한 얘기가 아니라 실제로 읽을 만한 이야깃거리가 있는지)
- 논거 자체의 설득력과 구체성
- (성과 데이터가 주어졌다면) 과거 반응도 참고하되, 그것만으로 결정하지 말고 다른 기준과 종합할 것
- (다양성 경고가 주어졌다면) 특별한 이유가 없다면 편중을 완화하는 방향을 고려할 것

반드시 JSON 형식으로만 답하세요:
{{"selected_ticker": "선정된 티커", "reason": "선정 이유(2~4문장)", "rejected_summary": "나머지 후보들을 왜 탈락시켰는지 간단히"}}
"""



def debate_and_select(candidates):
    """
    [2번 부서: 토론] discover_candidates()가 뽑은 후보들을 놓고,
    후보마다 독립적으로 "옹호 논거"를 생성한 뒤(서로의 논거를 보지 못하게
    순서효과를 방지), 마지막에 한 번 더 호출해서 전체를 심사하고 최종 1개를
    선정한다.

    반환: {"ticker": "...", "reason": "...", "candidates": candidates}
    (candidates는 감사/로그용으로 원본 데이터를 그대로 담아둠)

    실패 시(API 소진 등)에는 이 함수가 조용히 무너지지 않고, 안전하게
    "그냥 signal_score 1위 후보를 이유 없이 선택"으로 폴백한다 - 파이프라인
    전체가 여기서 죽는 것보다는, 토론 없이라도 진행되는 게 낫기 때문.
    """
    if not candidates:
        return None

    # 1) 후보별 독립 옹호 논거 생성
    arguments = []
    for c in candidates:
        prompt = _build_advocate_prompt(c)
        raw = get_gemini_response(prompt, thinking_budget=0)
        if raw is None:
            print(f"⚠️ {c['ticker']} 옹호 논거 생성 실패(API 소진 등) - 이 후보는 논거 없이 진행")
            arguments.append({"ticker": c["ticker"], "argument": "(논거 생성 실패)"})
            continue
        try:
            parsed = json.loads(raw)
            arguments.append({"ticker": c["ticker"], "argument": parsed.get("argument", raw)})
        except (json.JSONDecodeError, TypeError):
            # JSON 파싱 실패해도 원문 텍스트를 그냥 논거로 사용 (완전 포기보다 나음)
            arguments.append({"ticker": c["ticker"], "argument": str(raw)})

    # 2) 심사 - 전체 논거 + (활성화됐다면) 성과 분석 요약 + 다양성 경고를 함께 보여주고 최종 선정
    performance_summary = get_performance_summary_for_judge()
    diversity_note = get_diversity_note()
    judge_prompt = _build_judge_prompt(arguments, performance_summary=performance_summary, diversity_note=diversity_note)
    judge_raw = get_gemini_response(judge_prompt, thinking_budget=24576)  # 비교판단이라 사고 예산을 줌
    if judge_raw is not None:
        try:
            judge_parsed = json.loads(judge_raw)
            selected = judge_parsed.get("selected_ticker")
            if selected in [c["ticker"] for c in candidates]:
                return {
                    "ticker": selected,
                    "reason": judge_parsed.get("reason", ""),
                    "rejected_summary": judge_parsed.get("rejected_summary", ""),
                    "candidates": candidates,
                }
        except (json.JSONDecodeError, TypeError):
            print("⚠️ 심사 결과 JSON 파싱 실패 - signal_score 1위로 폴백")

    # 3) 폴백: 심사 자체가 실패했으면 그냥 신호 점수 1위를 선택
    top = candidates[0]
    return {
        "ticker": top["ticker"],
        "reason": f"(토론 단계 실패로 자동 폴백) 가격/거래량 신호 점수 1위: {top['signal_score']}",
        "rejected_summary": "",
        "candidates": candidates,
    }


# ============================================================
# [신규] 성과 분석 부서 - Google Search Console 연동
#
# 지금 당장은 활성화 조건(발행 14일 이상 지난 글 5편 이상)을 못 채워서
# "아직 할 말 없음"만 반환하다가, 시간이 지나 데이터가 쌓이면 자동으로
# 심사(2번 토론) 단계에 참고자료로 끼어들기 시작한다. 사람이 나중에 다시
# 코드를 손댈 필요 없이, 기준을 넘는 순간부터 자연스럽게 활성화된다.
#
# [최초 1회 사람이 직접 해야 하는 설정 - 자동화 불가능한 부분]
# 1) Google Search Console에 이 워드프레스 사이트를 등록하고 소유권 인증
# 2) Google Cloud Console에서 서비스 계정을 만들고, 그 서비스 계정의 이메일
#    주소를 Search Console의 "설정 > 사용자 및 권한"에 "전체" 권한으로 추가
# 3) 그 서비스 계정의 JSON 키 파일 내용 전체를 GitHub Secret
#    GSC_SERVICE_ACCOUNT_JSON 에 등록 (파일 내용을 그대로 복사-붙여넣기)
# 4) GSC_SITE_URL 도 Secret으로 등록 (Search Console에 등록한 속성 그대로,
#    예: "https://내블로그주소.com/" 또는 "sc-domain:내블로그주소.com")
# ============================================================

SEARCH_PERFORMANCE_FILE = "search_performance.json"
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "")
GSC_SERVICE_ACCOUNT_JSON = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")

# [활성화 기준] 이 두 조건을 동시에 만족해야 성과 분석 부서가 실제로 발언한다.
PERFORMANCE_MIN_AGE_DAYS = 14   # 이보다 최근 글은 검색순위가 아직 안 안정됐을 수 있어 제외
PERFORMANCE_MIN_ARTICLE_COUNT = 5  # 최소 이 편수는 있어야 "패턴"이라고 부를 수 있음


def _get_search_console_service():
    """
    서비스 계정 인증정보로 Search Console API 클라이언트를 만든다.
    필요한 시크릿(GSC_SERVICE_ACCOUNT_JSON, GSC_SITE_URL)이 없으면 조용히
    None을 돌려준다 - 아직 연동 설정을 안 했어도 나머지 파이프라인은
    정상적으로 돌아가야 하기 때문(이 부서는 있으면 좋고 없어도 그만인
    "선택적" 참고자료이지, 없다고 전체가 멈추면 안 됨).
    """
    if not GSC_SERVICE_ACCOUNT_JSON or not GSC_SITE_URL:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        info = json.loads(GSC_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
        return service
    except Exception as e:
        print(f"⚠️ Search Console 연동 실패(설정을 다시 확인해주세요): {type(e).__name__}: {e}")
        return None


def sync_search_performance():
    """
    [주기적으로(예: 주 1회) 실행] 최근 28일간의 페이지별 검색 성과(클릭수,
    노출수, CTR, 평균순위)를 가져와서 search_performance.json에 저장한다.
    직전 데이터를 덮어쓰는 방식(누적 로그가 아니라 "최신 28일 스냅샷")이라,
    호출할 때마다 파일을 새로 갱신하면 된다.
    """
    service = _get_search_console_service()
    if service is None:
        print("ℹ️ Search Console 연동 설정이 없어 성과 동기화를 건너뜁니다. "
              "(GSC_SERVICE_ACCOUNT_JSON / GSC_SITE_URL을 등록하면 활성화됩니다)")
        return

    end_date = datetime.now().date()
    start_date = end_date - pd.Timedelta(days=28)

    try:
        request = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["page"],
            "rowLimit": 1000,
        }
        response = service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=request).execute()
        rows = response.get("rows", [])
    except Exception as e:
        print(f"⚠️ Search Console 데이터 조회 실패: {type(e).__name__}: {e}")
        return

    performance_by_url = {}
    for row in rows:
        page_url = row["keys"][0]
        performance_by_url[page_url] = {
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "position": round(row.get("position", 0), 1),
        }

    _save_json_file(SEARCH_PERFORMANCE_FILE, {
        "synced_at": datetime.now().isoformat(),
        "period_days": 28,
        "by_url": performance_by_url,
    })
    print(f"✅ Search Console 성과 데이터 {len(performance_by_url)}개 페이지 동기화 완료")


def get_performance_summary_for_judge():
    """
    [성과 분석 부서 본체] 활성화 기준을 스스로 체크해서:
    - 기준 미달이면 None을 돌려준다 (심사 프롬프트에서 이 부서는 그냥 생략됨)
    - 기준 충족이면, 티커별 성과를 집계해서 심사 참고용 요약 문자열을 돌려준다

    매칭은 article_state.json에 저장된 각 글의 url을 search_performance.json의
    페이지 URL과 그대로 대조하는 방식(추측 없이 정확히 일치하는 것만 인정).
    """
    perf_data = _load_json_file(SEARCH_PERFORMANCE_FILE, None)
    if perf_data is None:
        return None  # 아직 한 번도 동기화 안 됨

    state = _load_state()
    now = datetime.now()

    # 발행 14일 이상 지났고, 성과 데이터도 매칭되는 글만 집계 대상으로 삼는다.
    eligible_articles = []
    for article in state.get("articles", []):
        ts = article.get("timestamp", "")
        url = (article.get("url") or "").rstrip("/")
        title = article.get("title", "")
        if not ts or not url:
            continue
        try:
            published_at = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        if (now - published_at).days < PERFORMANCE_MIN_AGE_DAYS:
            continue

        matched_perf = None
        for perf_url, perf_values in perf_data.get("by_url", {}).items():
            if perf_url.rstrip("/") == url:
                matched_perf = perf_values
                break
        if matched_perf is None:
            continue

        ticker = ",".join(_article_tickers(article)) or None
        eligible_articles.append({"ticker": ticker, "title": title, **matched_perf})

    if len(eligible_articles) < PERFORMANCE_MIN_ARTICLE_COUNT:
        print(f"ℹ️ 성과 분석 부서: 아직 데이터 부족({len(eligible_articles)}/{PERFORMANCE_MIN_ARTICLE_COUNT}편) - 이번 심사에는 참여하지 않습니다.")
        return None

    # 티커별로 클릭수 합산 -> 상위/하위 정리
    by_ticker = {}
    for a in eligible_articles:
        if not a["ticker"]:
            continue
        by_ticker.setdefault(a["ticker"], {"clicks": 0, "impressions": 0, "count": 0})
        by_ticker[a["ticker"]]["clicks"] += a["clicks"]
        by_ticker[a["ticker"]]["impressions"] += a["impressions"]
        by_ticker[a["ticker"]]["count"] += 1

    ranked = sorted(by_ticker.items(), key=lambda x: x[1]["clicks"], reverse=True)
    if not ranked:
        return None

    top_lines = [f"- {t}: 최근 28일 클릭 {v['clicks']}회, 노출 {v['impressions']}회 (글 {v['count']}편)" for t, v in ranked[:3]]
    bottom_lines = [f"- {t}: 최근 28일 클릭 {v['clicks']}회, 노출 {v['impressions']}회 (글 {v['count']}편)" for t, v in ranked[-2:]] if len(ranked) > 3 else []

    summary = "[성과 분석 부서 - 최근 검색 성과 데이터]\n"
    summary += "반응이 좋았던 티커:\n" + "\n".join(top_lines)
    if bottom_lines:
        summary += "\n반응이 저조했던 티커:\n" + "\n".join(bottom_lines)
    summary += "\n(이 데이터는 참고용입니다. 과거에 반응이 좋았다고 오늘도 무조건 유리한 건 아니니, 다른 논거와 함께 종합적으로 판단하세요.)"

    print(f"✅ 성과 분석 부서 활성화됨 ({len(eligible_articles)}편 데이터 기반) - 이번 심사에 참여합니다.")
    return summary


# ============================================================
# 텔레그램 알림 / 승인 체크
# ============================================================

PENDING_RECOMMENDATION_FILE = "pending_recommendation.json"
TELEGRAM_OFFSET_FILE = "telegram_offset.json"
REMINDER_MAX_DAYS = int(os.environ.get("REMINDER_MAX_DAYS", "3"))  # C안: 이 날짜까지 리마인드, 넘으면 새로 발굴


# ============================================================
# [신규] 다양성 관리 부서 (무료 - API 호출 없이 코드 로직으로만 판단)
# ============================================================

def get_diversity_note(recent_n=RECENT_THEME_WINDOW):
    """
    [다양성 관리 부서] 최근 recent_n편의 주제 분포를 심사 담당에게 알려준다.
    몰린 주제는 이미 발굴 단계에서 후보에서 빠지므로, 여기서는 "덜 다룬 주제"를
    우선 고려하라는 참고 정보만 준다. API 호출 없이 기록 파일만 읽는다.
    """
    counts = _recent_theme_counts(recent_n)
    if sum(counts.values()) < 3:
        return None
    all_themes = {v["theme"] for v in ETF_UNIVERSE.values()}
    underrepresented = sorted(t for t in all_themes if counts.get(t, 0) == 0)
    dist = ", ".join(f"{t} {c}편" for t, c in counts.most_common())
    note = f"[다양성 관리 부서] 최근 {recent_n}편 주제 분포: {dist}."
    if underrepresented:
        note += f" 아직 안 다룬 주제: {', '.join(underrepresented)}. 다른 조건이 비슷하면 이쪽을 우선하세요."
    return note


# ============================================================
# [신규] 상태 점검 부서 (무료 - 주간 리포트를 텔레그램으로 전송)
# ============================================================

# ============================================================
# [신규] 3번 부서: 기획
# ============================================================





# ============================================================
# [신규] SEO/제목 최적화 부서
# ============================================================



def send_weekly_health_report():
    """
    [상태 점검 부서] 최근 7일간의 발행 현황을 집계해서 텔레그램으로 요약
    보고한다. API 호출 없이 article_state.json의 notes 필드(어떤 경로로
    발행됐는지 기록된 문자열)만 파싱하므로 완전 무료.
    """
    state = _load_state()
    now = datetime.now()
    week_ago = now - pd.Timedelta(days=7)

    recent = []
    for a in state.get('articles', []):
        ts = a.get('timestamp', '')
        if not ts:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        if ts_dt >= week_ago:
            recent.append(a)

    drafts_n = sum(1 for a in recent if a.get('status') == 'draft')
    recent = [a for a in recent if a.get('status') != 'draft']   # 임시글은 '발행'으로 세지 않는다(2026-11-02)
    total = len(recent)
    fallback_count = sum(1 for a in recent if 'selenium' in a.get('notes', '') or 'manual paste' in a.get('notes', ''))
    low_quality_count = sum(1 for a in recent if 'low quality override' in a.get('notes', ''))

    lines = [f"📊 이번 주 발행 현황 ({week_ago.date()} ~ {now.date()})", ""]
    lines.append(f"공개 발행: {total}편 / 임시글: {drafts_n}편")
    if total > 0:
        lines.append(f"API 완전자동 발행: {total - fallback_count}편")
        lines.append(f"반자동(Selenium/수동 붙여넣기) 폴백: {fallback_count}편")
        if low_quality_count:
            lines.append(f"⚠️ 품질 낮음에도 강제 발행된 글: {low_quality_count}편 - 한 번 확인해보시는 걸 추천해요")
    elif not drafts_n:
        lines.append("이번 주 쓴 글이 없습니다 - 워크플로우가 정상 실행되고 있는지 확인해보세요.")

    # [신규] 예산/한도 감시 부서 - 이번 주 API 호출 통계 집계
    usage_log = _load_json_file(API_USAGE_LOG_FILE, [])
    weekly_usage = [u for u in usage_log if u.get("timestamp") and datetime.fromisoformat(u["timestamp"]) >= week_ago]
    if weekly_usage:
        total_calls = sum(u.get("total_calls", 0) for u in weekly_usage)
        by_model_agg = {}
        switch_agg = {}
        for u in weekly_usage:
            for model, count in u.get("by_model", {}).items():
                by_model_agg[model] = by_model_agg.get(model, 0) + count
            for model, count in u.get("model_switch_events", {}).items():
                switch_agg[model] = switch_agg.get(model, 0) + count

        lines.append("")
        lines.append(f"🔧 이번 주 Gemini 호출: 총 {total_calls}회")
        for model, count in sorted(by_model_agg.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {model}: {count}회")
        if switch_agg:
            most_exhausted = max(switch_agg.items(), key=lambda x: x[1])
            lines.append(f"⚠️ 가장 자주 소진되어 전환된 모델: {most_exhausted[0]} ({most_exhausted[1]}회) - 우선순위를 낮추는 걸 고려해보세요")

    # 편집 기록부(logs/) 주간 요약: 쓰기 방식, 점수 변화, 막힌 모델, 거부된 키 번호, 자주 나온 지적
    try:
        from ondo.checks.editlog import weekly_summary
        lines += weekly_summary()
    except Exception as e:
        lines.append(f"(편집 기록 요약 실패: {type(e).__name__})")

    # 주간 점검(키·워드프레스 토큰·자료원·사이트 화면 캡처) - ondo/checks/weekly.py
    try:
        from ondo.checks import weekly
        from blog_engine import _telegram_send_photo
        from blog_engine import get_wordpress_recent_posts
        posts = get_wordpress_recent_posts() or []
        lines += weekly.run_all(send_photo=_telegram_send_photo, latest_url=posts[0].get("link") if posts else None)
    except Exception as e:
        lines.append(f"(주간 점검 실패: {type(e).__name__})")

    message = "\n".join(lines)
    _telegram_send_message(message)
    print("✅ 주간 상태 점검 리포트 전송 완료")
    print(message)


# ============================================================
# [신규] 홍보팀 - 발행 완료 시 Threads에 카드형 요약 자동 게시
# ============================================================



# 카드 이미지 크기. 1080x1350은 인스타/스레드에서 가장 무난하게 쓰이는
# 4:5 세로 비율 - 스레드 피드에서 화면을 많이 차지해 눈에 잘 띈다.


















# ============================================================
# [신규] 검색엔진 알림 - IndexNow 프로토콜
#
# 구글은 2023년에 자체 핑 엔드포인트를 없앴고 IndexNow도 지원하지 않는다
# (사이트맵으로만 발견됨 - 이미 워드프레스가 자동 생성해주므로 별도 조치 불필요).
# 대신 Bing/Yandex/네이버/Seznam/Yep은 공통으로 IndexNow 프로토콜을 지원해서,
# 한 번의 요청으로 이 검색엔진들에 동시에 "새 글 생겼다"고 알릴 수 있다.
# 완전 무료, API 키 발급 절차도 없다 - 키를 우리가 직접 만들고, 그 키가
# 진짜 이 사이트 소유자가 보낸 요청인지 확인할 수 있게 공개 URL에 올려두기만
# 하면 된다.
# ============================================================




















def _load_pending():
    return _load_json_file(PENDING_RECOMMENDATION_FILE, None)


def _save_pending(data):
    _save_json_file(PENDING_RECOMMENDATION_FILE, data)


def _record_pending_message(msg_id):
    """방금 보낸 ETF 추천 메시지 번호를 저장한다(답장 메모가 어느 추천 것인지 구분할 때 사용)."""
    pending = _load_pending()
    if pending and msg_id:
        pending["message_id"] = msg_id if msg_id is not True else None
        if msg_id is not True:
            pending["message_ids"] = (pending.get("message_ids") or []) + [msg_id]   # 첫 추천 + 리마인드 전부
        pending["sent_at"] = datetime.now().isoformat()
        _save_pending(pending)


def _is_current_message(rec, message_id):
    """눌린 버튼의 메시지가 이 추천을 보낸 메시지(첫 추천 또는 리마인드)인지. 기록이 없으면 그냥 인정."""
    known = set(rec.get("message_ids") or []) | ({rec.get("message_id")} - {None, True})
    return not known or message_id in known


def _mark_recommendation_approved(message_id, label):
    """승인한 추천 메시지의 버튼을 없애고 '승인됨'으로 바꿔서, 된 건지 한눈에 보이고 두 번 누르지 않게 한다."""
    if not message_id or message_id is True:
        return
    from blog_engine import _kst_now
    _telegram_edit_text(message_id, f"📌 {label}\n\n✅ 승인됨 ({_kst_now():%m/%d %H:%M}) - 글쓰기를 시작했어요.")


def _clear_pending():
    if os.path.exists(PENDING_RECOMMENDATION_FILE):
        os.remove(PENDING_RECOMMENDATION_FILE)


def _load_telegram_offset():
    data = _load_json_file(TELEGRAM_OFFSET_FILE, {"offset": None})
    return data.get("offset")


def _save_telegram_offset(offset):
    _save_json_file(TELEGRAM_OFFSET_FILE, {"offset": offset})


REPLY_HELP_TEXT = (
    "• 승인: [✅ 승인] 버튼 (누르면 10분 안에 '승인 확인' 답장이 와요)\n"
    "• 다른 종목으로: 티커를 답장 (예: SPY 또는 SPY,360750)\n"
    "• 운영자 메모(선택): '메모: 내용'으로 답장하면 글에 그대로 들어가요"
)


def run_discover_and_notify():
    """
    [매일 예약 실행되는 진입점] 1번(발굴) -> 2번(토론)까지만 진행하고,
    3번(기획) 이전에 멈춰서 텔레그램으로 알림만 보낸다.

    - 대기 중인 추천(pending)이 없으면: 새로 발굴+토론해서 알림
    - 대기 중인 추천이 있고 REMINDER_MAX_DAYS 안이면: 새로 발굴/토론 안 하고
      (=토큰 낭비 없이) 같은 후보로 리마인드만 다시 보냄
    - 대기 중인 추천이 REMINDER_MAX_DAYS를 넘겼으면: 그 추천은 폐기하고
      처음부터 새로 발굴+토론
    """
    pending = _load_pending()

    if pending:
        created_at = datetime.fromisoformat(pending["created_at"])
        age_days = (datetime.now() - created_at).days
        if age_days < REMINDER_MAX_DAYS:
            pending["reminder_count"] = pending.get("reminder_count", 0) + 1
            pending["last_reminded_at"] = datetime.now().isoformat()
            _save_pending(pending)
            _record_pending_message(_telegram_send_message(
                f"⏰ 아직 승인 안 하신 추천이 있어요 ({age_days}일째)\n\n"
                f"글 종류: {pending.get('article_type', '단일 분석')}\n"
                f"주제: {pending.get('label') or _topic_label(pending['ticker'])}\n"
                f"이유: {pending['reason']}\n\n"
                f"{REPLY_HELP_TEXT}\n"
                f"(이 알림은 {REMINDER_MAX_DAYS}일까지 반복되고, 넘기면 새로 추천해드려요)",
                with_approve_button=True,
            ))
            print(f"ℹ️ 기존 추천({pending['ticker']})이 아직 {REMINDER_MAX_DAYS}일 안이라 리마인드만 보냈습니다.")
            return
        else:
            print(f"ℹ️ 기존 추천({pending['ticker']})이 {REMINDER_MAX_DAYS}일을 넘겨서 폐기하고 새로 발굴합니다.")
            _clear_pending()

    explainer = _choose_explainer_topic(get_macro_data())
    if explainer:
        topic, article_type, why = explainer
        _save_pending({
            "ticker": topic,
            "label": _topic_label(topic),
            "article_type": article_type,
            "reason": why,
            "candidates": [],
            "created_at": datetime.now().isoformat(),
            "reminder_count": 0,
        })
        _record_pending_message(_telegram_send_message(
            f"📌 오늘의 추천 주제\n\n글 종류: {article_type}\n주제: {_topic_label(topic)}\n이유: {why}\n\n"
            f"{REPLY_HELP_TEXT}\n({REMINDER_MAX_DAYS}일간 리마인드되고, 그 안에 응답 없으면 자동으로 새로 추천해드려요)",
            with_approve_button=True,
        ))
        print(f"✅ 새 추천을 알림으로 보냈습니다: {topic} ({article_type})")
        return

    candidates = discover_candidates()
    if not candidates:
        # 발굴에서 아무 후보도 못 찾았을 때(전부 쿨다운에 걸림) - 재포스팅으로 폴백
        fallback = pick_next_topic()
        _save_pending({
            "ticker": fallback["ticker"],
            "article_type": "단일 분석",
            "reason": f"재포스팅 폴백: {fallback['reason']}",
            "candidates": [],
            "created_at": datetime.now().isoformat(),
            "reminder_count": 0,
        })
        _record_pending_message(_telegram_send_message(
            f"ℹ️ 오늘은 새로 다룰 만한 신호가 있는 종목이 없어서, 재포스팅(업데이트) 후보를 추천드려요.\n\n"
            f"주제: {_topic_label(fallback['ticker'])}\n"
            f"사유: {fallback['reason']}\n\n"
            f"{REPLY_HELP_TEXT}",
            with_approve_button=True,
        ))
        return

    decision = debate_and_select(candidates)
    topic, article_type = decision["ticker"], "단일 분석"
    comparison_share = _recent_comparison_share()
    if comparison_share < COMPARISON_TARGET_SHARE:
        partners = _find_comparison_partner(topic)
        if partners:
            topic, article_type = ",".join([topic] + partners), "비교"
            print(f"ℹ️ 최근 비교 글 비율 {comparison_share:.0%} → 오늘은 비교 글: {topic}")

    _save_pending({
        "ticker": topic,
        "label": _topic_label(topic),
        "article_type": article_type,
        "reason": decision["reason"],
        "candidates": [{"ticker": c["ticker"], "signal_score": c["signal_score"]} for c in candidates],
        "created_at": datetime.now().isoformat(),
        "reminder_count": 0,
    })

    candidate_summary = ", ".join(f"{c['ticker']}({c['signal_score']}점)" for c in candidates)
    _record_pending_message(_telegram_send_message(
        f"📌 오늘의 추천 주제\n\n"
        f"글 종류: {article_type}\n"
        f"주제: {_topic_label(topic)}\n"
        f"이유: {decision['reason']}\n\n"
        f"검토한 후보군: {candidate_summary}\n\n"
        f"{REPLY_HELP_TEXT}\n"
        f"({REMINDER_MAX_DAYS}일간 리마인드되고, 그 안에 응답 없으면 자동으로 새로 추천해드려요)",
        with_approve_button=True,
    ))
    print(f"✅ 새 추천을 알림으로 보냈습니다: {topic} ({article_type})")


MAX_OPERATOR_MEMO_CHARS = 300


def _parse_topic_reply(text):
    """텔레그램 답장이 종목 지정인지 판단한다. 맞으면 (정규화된 "A,B" 문자열, 강제 여부),
    아니면 None. "OK"처럼 짧은 영어 답장을 종목으로 착각하지 않도록 목록에 없는
    영문 티커는 2~5자이면서 흔한 답장 단어가 아닐 때만 인정한다."""
    t = (text or "").strip().upper()
    force = t.startswith("강제")
    if force:
        t = t[2:].strip()
    tokens = [x.strip() for x in t.split(",") if x.strip()]
    if not tokens or len(tokens) > 3:
        return None
    out = []
    for tok in tokens:
        if re.fullmatch(r"\d{6}(\.KS)?", tok):
            out.append(_normalize_ticker(tok[:6]))
        elif tok in ETF_UNIVERSE:
            out.append(tok)
        elif re.fullmatch(r"[A-Z]{2,5}", tok) and tok not in _TICKER_REPLY_STOPWORDS:
            out.append(tok)
        else:
            return None
    return ",".join(out), force


def _parse_memo_reply(text):
    m = re.match(r"^\s*(메모|memo)\s*[:：]?\s*(.+)$", text or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    memo = m.group(2).strip()
    return memo[:MAX_OPERATOR_MEMO_CHARS] if memo else None


def _recently_written_groups(topic, within_days=COOLDOWN_HARD_FLOOR_DAYS):
    """topic의 종목 중 within_days 안에 같은 지수 묶음 글이 있는 것을 (그룹, 일수)로 돌려준다."""
    now = datetime.now()
    last_by_group = _last_written_dates_by_group()
    hits = []
    for t in topic.split(","):
        g = _etf_group(t)
        dt = last_by_group.get(g)
        if dt and (now - dt).days < within_days:
            hits.append((g, (now - dt).days))
    return hits


def run_check_universe():
    """ETF_UNIVERSE의 각 티커가 야후 파이낸스에서 가격/이름을 받아오는지 점검한다.
    국내 ETF 코드가 맞는 상품인지도 이름으로 확인할 수 있다."""
    failed = []
    load_dynamic_kr_etfs()
    print("[자동 발굴 국내 ETF - 거래대금 상위, 레버리지·인버스 제외]")
    for t, meta in _DYNAMIC_UNIVERSE.items():
        print(f"   {t:10} {meta['theme']:8} {meta['group']:16} {meta['name']}")
    print("\n[고정 목록 데이터 점검]")
    for t, meta in ETF_UNIVERSE.items():
        name, rows = "", 0
        try:
            tk = yf.Ticker(t)
            rows = len(tk.history(period="1mo"))
            try:
                name = (tk.info or {}).get("shortName") or (tk.info or {}).get("longName") or ""
            except Exception:
                name = "(이름 조회 실패)"
        except Exception as e:
            name = f"(오류: {type(e).__name__})"
        mark = "✅" if rows else "❌"
        print(f"{mark} {t:10} {meta['theme']:8} {meta['group']:12} 가격 {rows:3}일  {name}")
        if not rows:
            failed.append(t)
    print(f"\n점검 결과: {len(ETF_UNIVERSE) - len(failed)}/{len(ETF_UNIVERSE)}개 정상"
          + (f", 실패: {', '.join(failed)}" if failed else ""))


PENDING_TOPIC_FILE = "pending_topic.json"            # 두 번째 글(ETF 외 분야) 추천 - topic_engine.py
CONFIRMED_TOPIC2_FILE = "confirmed_topic2_context.json"


def _memo_target(update, pending, pending2):
    """메모가 어느 추천 것인지: 그 추천 메시지에 답장했으면 그 추천, 아니면 가장 최근에 보낸 추천."""
    reply_id = (((update.get("message") or {}).get("reply_to_message")) or {}).get("message_id")
    if pending2 and reply_id and reply_id == pending2.get("message_id"):
        return "topic"
    if pending and reply_id and reply_id == pending.get("message_id"):
        return "etf"
    if pending and pending2:
        return "topic" if (pending2.get("sent_at") or "") > (pending.get("sent_at") or "") else "etf"
    return "topic" if pending2 else "etf"


def run_check_approval():
    """
    [자주 실행되는(예: 10분마다) 진입점] 텔레그램 응답을 확인해서:
    - ETF 추천의 [✅ 승인] → APPROVED_TICKER:{주제}
    - 두 번째 글(ETF 외 분야) 추천의 [✅ 승인] → APPROVED_TOPIC:{분야}
    - 종목 답장(예: "SPY" 또는 "SPY,360750") → ETF 추천을 그 종목으로 바꿔서 진행
      (단, 7일 안에 같은 지수 글이 있으면 거절. "강제 SPY"면 그래도 진행)
    - "메모: 내용" → 운영자 메모로 저장. 추천 메시지에 답장으로 보내면 그 추천에,
      그냥 보내면 가장 최근 추천에 붙는다. 글에 그대로 실린다.
    - 운영자 채팅방이 아닌 곳에서 온 메시지는 모두 무시
    GitHub Actions가 위 두 줄을 grep해서 각각의 글쓰기를 실행한다.
    """
    pending = _load_pending()
    pending2 = _load_json_file(PENDING_TOPIC_FILE, None)
    import media_engine
    if not pending and not pending2:
        # 추천이 없어도 텔레그램은 확인한다 - 썸네일 그림(설명에 글 주소를 붙이면 아무 글이나)이 올 수 있음
        print("ℹ️ 대기 중인 추천은 없습니다. 썸네일 그림이 왔는지만 확인합니다.")

    offset = _load_telegram_offset()
    updates = _telegram_get_updates(offset)
    if not updates:
        print("ℹ️ 새로운 텔레그램 응답이 없습니다.")
        return

    confirmed_topic, override, topic2_ok = None, False, False
    max_update_id = offset or 0
    changed, changed2 = False, False

    for update in updates:
        max_update_id = max(max_update_id, update.get("update_id", 0))
        if not _telegram_update_is_authorized(update):
            print("⚠️ 운영자 채팅방이 아닌 곳에서 온 텔레그램 메시지를 무시했습니다.")
            continue

        # 썸네일 그림 답장(ComfyUI로 만든 이미지) → 그 글의 대표 이미지 교체
        if media_engine.handle_image_reply(update):
            continue

        callback = update.get("callback_query")
        if callback:
            # 누른 사람 화면의 '로딩 중' 표시 끄기 (10분 뒤라 만료됐을 수 있음 - 실패해도 무시)
            _telegram_answer_callback(callback.get("id"), "승인 받았어요")
            # 버튼 신호만으로는 어느 추천 것인지 몰라서, 눌린 메시지가 지금 기다리는 추천(또는 그 리마인드)인지 확인한다.
            # 안 그러면 어제 지나간 추천의 버튼을 눌러도 오늘 추천이 승인돼 버린다.
            cb_mid = (callback.get("message") or {}).get("message_id")
            if callback.get("data") == "approve" and pending and _is_current_message(pending, cb_mid):
                confirmed_topic, override = pending["ticker"], False
            elif callback.get("data") == "approve_topic" and pending2 and _is_current_message(pending2, cb_mid):
                topic2_ok = True
            elif callback.get("data") in ("approve", "approve_topic"):
                # 이미 처리했거나 시간이 지나 사라진 추천의 버튼
                _telegram_edit_text((callback.get("message") or {}).get("message_id"),
                                    "이 추천은 이미 처리했거나 기간이 지났어요. 새 추천을 기다려주세요.")
            continue

        text = ((update.get("message") or {}).get("text") or "").strip()
        if not text:
            continue

        memo = _parse_memo_reply(text)
        if memo:
            if not pending and not pending2:
                # 썸네일만 기다리는 중이라 메모를 붙일 추천이 없다
                _telegram_send_message("📝 메모를 받았는데 지금 승인을 기다리는 추천이 없어서 저장하지 못했어요.")
                continue
            if _memo_target(update, pending, pending2) == "topic":
                pending2["memo"], changed2 = memo, True
                where = "두 번째 글"
            else:
                pending["memo"], changed = memo, True
                where = "ETF 글"
            _telegram_send_message(f"📝 운영자 메모를 저장했어요({where}). 이 글에 그대로 실립니다:\n\"{memo}\"")
            continue

        parsed = _parse_topic_reply(text) if pending else None
        if not parsed:
            continue
        topic, force = parsed
        recent = _recently_written_groups(topic)
        if recent and not force:
            detail = ", ".join(f"{g}({d}일 전)" for g, d in recent)
            _telegram_send_message(
                f"⛔ {topic.replace('.KS', '')}: 최근 {COOLDOWN_HARD_FLOOR_DAYS}일 안에 같은 지수 글이 있어 진행하지 않았어요 → {detail}\n"
                f"같은 내용이 반복되면 애드센스 심사에 불리해요. 그래도 진행하려면 '강제 {topic.replace('.KS', '')}'로 답장해주세요."
            )
            continue
        confirmed_topic, override = topic, True

    _save_telegram_offset(max_update_id + 1)
    if changed and not confirmed_topic:
        _save_pending(pending)
    if changed2 and not topic2_ok:
        _save_json_file(PENDING_TOPIC_FILE, pending2)

    if topic2_ok:
        print(f"APPROVED_TOPIC:{pending2['category']}")
        _save_json_file(CONFIRMED_TOPIC2_FILE, pending2)
        os.remove(PENDING_TOPIC_FILE)
        memo_note = "\n📝 운영자 메모도 함께 실려요." if pending2.get("memo") else ""
        _mark_recommendation_approved(pending2.get("message_id"), f"두 번째 글 - {pending2['title_seed']}")
        _telegram_send_message(f"✅ 승인 확인! 두 번째 글 '{pending2['title_seed']}' 글쓰기를 시작해요.\n"
                               f"보통 15~30분 뒤에 '발행 완료' 메시지와 글 링크가 와요.{memo_note}",
                               reply_to=pending2.get("message_id"))

    if not confirmed_topic:
        if not topic2_ok:
            print("ℹ️ 응답은 있었지만 승인/종목 지정으로 해석되지 않았습니다. 계속 대기합니다.")
        return

    print(f"✅ 확정된 주제: {confirmed_topic}")
    print(f"APPROVED_TICKER:{confirmed_topic}")
    # 3번(기획) 단계와 글쓰기가 선정 사유·글 종류·운영자 메모를 이어받을 수 있게 남겨둔다.
    # run_automation()이 읽어서 쓰고 지운다.
    _save_json_file("confirmed_topic_context.json", {
        "ticker": confirmed_topic,
        "reason": "사용자가 추천 대신 직접 지정한 주제" if override else pending.get("reason", ""),
        "article_type": ("비교" if "," in confirmed_topic else "단일 분석") if override else pending.get("article_type", "단일 분석"),
        "memo": pending.get("memo", ""),
    })
    _clear_pending()
    memo_note = "\n📝 운영자 메모도 함께 실려요." if pending.get("memo") else ""
    label = pending.get('label') if confirmed_topic == pending.get('ticker') else None
    shown = label or _topic_label(confirmed_topic)
    _mark_recommendation_approved(pending.get("message_id"), f"ETF - {shown}")
    _telegram_send_message(f"✅ 승인 확인! '{shown}' 글쓰기를 시작해요.\n"
                           f"보통 15~30분 뒤에 '발행 완료' 메시지와 글 링크가 와요.{memo_note}",
                           reply_to=pending.get("message_id"))


def _ask_yn(prompt, default_when_noninteractive='n'):
    """
    y/n 확인용 공통 헬퍼. 환경변수 NONINTERACTIVE=1이 설정되어 있으면
    (Cowork/스케줄러가 무인으로 돌릴 때) 사람 응답을 기다리며 멈추는 대신
    default_when_noninteractive를 그대로 쓰고 로그만 남긴다.
    default는 안전 쪽('n' = 발행 안 됐다고 간주)으로 잡는 게 원칙 -
    실제로 사람이 확인 안 한 걸 "발행됨"으로 잘못 기록하면 안 되기 때문.
    대화형 실행(터미널에서 직접 돌릴 때)에서는 기존과 완전히 동일하게 동작.
    """
    if os.environ.get("NONINTERACTIVE"):
        print(f"{prompt}[무인 실행 모드 - 자동 응답 '{default_when_noninteractive}' 적용]")
        return default_when_noninteractive
    return input(prompt).strip().lower()




def run_automation():
    print("="*45)
    print("온도(ondo) ETF 분석 시스템 (Selenium 정밀 스크래핑 모드)")
    print("="*45)

    _clean_stale_sessions()

    min_interval_hours = float(os.environ.get("MIN_PUBLISH_INTERVAL_HOURS", "20"))
    can_proceed, interval_msg = _check_publish_interval(min_interval_hours)
    print(interval_msg)
    if not can_proceed and os.environ.get("REPLACE_URL", "").strip():
        print("ℹ️ 다시 쓰기(REPLACE_URL)는 새 글이 아니라서 발행 간격과 상관없이 진행합니다.")
        can_proceed = True
    import blog_engine as _be
    if not can_proceed and not _be.auto_publish_enabled():
        print("ℹ️ 자동 발행이 꺼져 있어 임시글로만 올라가므로 발행 간격과 상관없이 진행합니다.")
        can_proceed = True
    if not can_proceed:
        force = _ask_yn("❓ 그래도 지금 진행하시겠습니까? (y/n): ", default_when_noninteractive='n')
        if force not in ['y', 'yes', '네', 'ㅇ']:
            print("ℹ️ 발행 간격 확보를 위해 실행을 중단합니다. 나중에 다시 실행해주세요.")
            return
    
    now = datetime.now()
    today_str = now.strftime("%Y년 %m월 %d일")
    current_year = now.strftime("%Y")
    
    # [신규] Cowork/스케줄 자동 실행과 연동하기 위한 5가지 모드.
    # 1) --detect-only        : (구버전 단순 로직) 후보만 계산해서 화면에 출력하고 종료
    # 2) --topic TICKER       : 후보 확정 없이 이 티커로 바로 진행 (1~2번 발굴/토론 건너뜀)
    # 3) --discover-and-notify: 1번(발굴)->2번(토론)까지 진행 후 텔레그램 알림만 보내고 종료
    #                            (3번 기획 이전에 멈춤 - 사람 승인 기다리는 지점)
    # 4) --check-approval     : 텔레그램 응답을 확인해서 승인/override 티커를 찾고,
    #                            APPROVED_TICKER:{ticker} 형식으로 출력 (GH Actions가 grep해서 사용)
    # 5) 인자 없음(기존 방식) : 터미널에서 직접 실행할 때는 지금처럼 손으로 입력 가능
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--detect-only", action="store_true",
                         help="(구버전) 다음 주제 후보만 계산해서 출력하고 종료")
    parser.add_argument("--topic", type=str, default=None,
                         help="이 티커로 바로 진행 (자동 감지/사람 확인 단계 생략)")
    parser.add_argument("--discover-and-notify", action="store_true",
                         help="1번(발굴)->2번(토론) 진행 후 텔레그램 알림만 보내고 종료")
    parser.add_argument("--if-due", action="store_true",
                         help="--discover-and-notify와 함께: 오늘 추천을 아직 안 보냈고 07:30(KST)이 지났을 때만 실행")
    parser.add_argument("--check-approval", action="store_true",
                         help="텔레그램 승인/override 응답을 확인하고 결과를 출력")
    parser.add_argument("--sync-performance", action="store_true",
                         help="Search Console 성과 데이터를 동기화하고 종료")
    parser.add_argument("--check-universe", action="store_true",
                         help="발굴 대상 ETF 목록이 실제로 데이터를 받아오는지 점검하고 종료")
    parser.add_argument("--check-trends", action="store_true",
                         help="구글 트렌드 조회 방법들이 실제로 데이터를 주는지 점검하고 종료")
    parser.add_argument("--health-report", action="store_true",
                         help="주간 상태 점검 리포트를 텔레그램으로 보내고 종료")
    cli_args, _unknown = parser.parse_known_args()

    if cli_args.health_report:
        send_weekly_health_report()
        return

    if cli_args.check_universe:
        run_check_universe()
        return

    if cli_args.check_trends:
        import trend_engine
        trend_engine.check()
        return

    if cli_args.sync_performance:
        sync_search_performance()
        return

    if cli_args.discover_and_notify:
        if cli_args.if_due and not _discover_due("etf", 7, 30):
            print("ℹ️ 오늘 ETF 추천은 이미 보냈거나 아직 시간이 안 됐습니다.")
            return
        _mark_discovered("etf")
        run_discover_and_notify()
        return

    if cli_args.check_approval:
        run_check_approval()
        return

    if cli_args.detect_only:
        candidate = pick_next_topic()
        # Cowork가 이 한 줄만 파싱하면 되도록 JSON 한 줄로 고정 출력.
        print("TOPIC_CANDIDATE_JSON:" + json.dumps(candidate, ensure_ascii=False))
        return

    if cli_args.topic:
        raw_inputs = cli_args.topic
        print(f"ℹ️ 지정된 티커로 바로 진행합니다: {raw_inputs}")
    elif not os.environ.get("NONINTERACTIVE"):
        raw_inputs = input("ETF 티커를 입력하세요: ")
    else:
        # 무인 실행인데 --topic도 없으면, 자동 선정 결과를 그대로 사용
        auto_pick = pick_next_topic()
        raw_inputs = auto_pick["ticker"]
        print(f"ℹ️ 무인 실행 모드 - 자동 선정된 티커로 진행합니다: {raw_inputs} (사유: {auto_pick['reason']})")

    if raw_inputs.strip().upper().startswith(("GUIDE:", "ISSUE:")):
        import explainer_engine as xe
        kind, _, topic_id = raw_inputs.strip().partition(":")
        xe.run_explainer(f"{kind.upper()}:{topic_id.strip()}", sys.modules[__name__])
        return

    etf_list = [n.strip().upper() + (".KS" if len(n.strip()) == 6 and any(char.isdigit() for char in n.strip()) else "") for n in raw_inputs.split(",")]

    write_etf_article(etf_list, today_str, now)


def write_etf_article(etf_list, today_str, now):
    """종목 분석·비교 글: 코드가 자료·그래프를 만들고, 글은 편집국(ondo/writing/desk.py)이 쓴다.
    2026-11-09: 예전 5조각 글쓰기(ANALYSIS_WRITER=legacy)와 그것만 쓰던 준비 단계(명언·기획·제목 최적화 -
    글마다 AI 호출 3번 낭비)를 걷어냄. 옛 코드는 git 기록에 있다."""
    from ondo.writing import analysis as _analysis
    from ondo.media import charts as _charts
    from topic_engine import produce_article

    # 시리즈 추적: 같은 종목의 지난 분석(실제 글 주소는 RSS로 보정)
    rss_target_site = WP_SITE_URL if PLATFORM == "wordpress" else BLOG_NAME
    rss_posts = get_tistory_rss_links(rss_target_site) if rss_target_site else []
    previous_analyses = _get_previous_analysis(etf_list, today_str, rss_posts=rss_posts)
    print(f"✅ 시리즈 추적 완료 - {'업데이트' if any(a['previous'] for a in previous_analyses.values()) else '첫 분석'}")

    macro_data = get_macro_data()
    print(f"✅ 수집 완료 - 환율: {macro_data['usd_krw']} / 금리: {macro_data['us_10y']} / 공포탐욕지수: {macro_data['fear_greed']}")
    driver = _create_chrome_driver()
    try:
        is_multi = len(etf_list) >= 2
        wrapper_style = ("flex: 1 1 45%; max-width: 48%; min-width: 320px; margin: 10px; box-sizing: border-box;" if is_multi
                         else "width: 100%; max-width: 700px; margin: 30px auto;")
        title_tickers = ", ".join(t.replace(".KS", "").replace(".US", "") for t in etf_list)
        try:
            usd_krw_rate = float(str(macro_data.get('usd_krw', '1300')).replace('원', '').replace(',', ''))
        except (ValueError, AttributeError):
            usd_krw_rate = 1300.0

        etf_data_cache, widget_items, backtest_charts, calendar_charts = {}, [], [], []
        for ticker in etf_list:
            d = get_etf_real_data(ticker, driver, macro_data)
            if not d:
                continue
            etf_data_cache[ticker] = d
            widget_items.append(_create_widget_html(ticker, d, wrapper_style, usd_krw_rate))
        for ticker, d in etf_data_cache.items():
            chart_html, _result = _create_backtest_simulation_chart(ticker, d, wrapper_style, usd_krw_rate)
            if chart_html:
                backtest_charts.append(chart_html)
            cal_html = _create_return_calendar_heatmap(ticker, d, wrapper_style, usd_krw_rate)
            if cal_html:
                calendar_charts.append(cal_html)
        widgets_html_block = (f'<div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; width: 100%; '
                              f'margin: 30px auto;">{"".join(widget_items)}</div>' if is_multi else "".join(widget_items) + "<br>")

        recent_news = _get_recent_news_for_etfs(etf_data_cache, macro_data)
        print(f"✅ 최근 뉴스 {len(recent_news)}건 수집 완료" if recent_news else "⚠️ 최근 뉴스 수집 실패")

        macro_thermo_indicators = get_macro_thermometer_indicators()

        # 텔레그램으로 승인된 주제에 붙은 운영자 메모(같은 종목일 때만), 쓰고 나면 지움
        operator_memo = ""
        confirmed_context = _load_json_file("confirmed_topic_context.json", None)
        if confirmed_context:
            confirmed_set = {_normalize_ticker(x) for x in str(confirmed_context.get("ticker", "")).split(",") if x.strip()}
            if confirmed_set == {_normalize_ticker(x) for x in etf_list}:
                operator_memo = (confirmed_context.get("memo") or "").strip()
            if os.path.exists("confirmed_topic_context.json"):
                os.remove("confirmed_topic_context.json")

        def _tax_visual():
            import explainer_engine as _xe
            _xe.ea = sys.modules[__name__]
            try:
                return _xe.tax_scenarios()[1]
            except Exception as e:
                print(f"ℹ️ 세금 계산표 실패: {type(e).__name__}")
                return ""

        # 코드가 만든 그래프·표는 "시각 자료 서랍"에 넣고, 기획이 2~3개를 골라 배치한다
        drawer, drawer_html = _analysis.build_drawer({
            "basic": widgets_html_block, "backtest": "".join(backtest_charts),
            "competition": _add_competitive_comparison(etf_data_cache),
            "risk": _add_risk_scenarios(etf_data_cache)[0], "tax": _tax_visual(), "calendar": "".join(calendar_charts),
            "sector": _add_sector_deep_analysis(etf_data_cache, macro_data),
            "scenario": _add_scenario_analysis(etf_data_cache, title_tickers),
            "macro": _build_macro_thermometers_chart(macro_thermo_indicators),
        })
        kind = "comparison" if is_multi else "analysis"
        _facts = _analysis.fact_sheet(etf_list, etf_data_cache, sys.modules[__name__], macro_data, recent_news,
                                      drawer_html, now.strftime("%Y년 %m월 %d일"), previous_analyses)
        # 거의 같이 움직이는 두 상품이면 필수 질문을 '얼마나 같고 무엇이 다른가'로(11-08 TIGER vs ACE)
        must_key = "comparison_twin" if kind == "comparison" and _analysis.is_twin(_facts) else kind
        produce_article(
            kind_label="ETF 비교" if kind == "comparison" else "ETF 분석",
            # 검색용 제목 최적화가 "환율과 금리가 S&P500 수익률에 미치는 영향"처럼 자료가 답하지 못하는 것을 약속해서
            # 필수 질문(제목에 답하기)에서 계속 걸렸다(2026-11-05 VOO). 편집국에는 자료가 답하는 것만 약속하는 제목을 준다.
            title_seed=(f"{title_tickers} 비교: 수익·낙폭·보수·세금을 같은 기준으로 보기" if kind == "comparison"
                        else f"{title_tickers} 점검: 수익·낙폭·배당·세금을 숫자로 보기"),
            facts_text=_facts,
            rules=_analysis.ANALYSIS_RULES, must_answer=_analysis.MUST_ANSWER[must_key],
            category_label=f"ETF/{'비교' if kind == 'comparison' else '종목 분석'}", article_type=kind,
            topic_id=",".join(t.replace(".KS", "") for t in etf_list), memo=operator_memo,
            closing_html=_analysis.closing_html(recent_news), drawer=drawer, drawer_html=drawer_html,
            top_html=_charts.thermo_strip(macro_thermo_indicators, now.strftime("%m월 %d일")),
            extra_data=etf_data_cache, meta={"tickers": list(etf_list)},
        )
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    run_automation()