import sys
import time
import requests
from datetime import datetime
import pyperclip
import re
import random
import pandas as pd
import os
import json
import urllib.parse
import base64
import yfinance as yf
import FinanceDataReader as fdr  # <-- 이거 한 줄 추가
from io import StringIO
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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
    WP_SITE_URL, WP_EMAIL, WP_PASSWORD,
    GEMINI_API_KEYS, API_USAGE_LOG_FILE,
    _card_html_shell,
    _load_json_file, _save_json_file, _load_generation_state, _save_generation_state,
    _load_raw_part_response, _clear_generation_state,
    _load_cache, _get_cached_record, _set_cached_record,
    _get_text_hash, _extract_section_titles,
    _inject_table_of_contents, _post_process_blog_content, _safe_html_filter,
    _build_previous_content_block, _llm_quality_check,
    _llm_targeted_fix, get_gemini_response, _extract_facts_from_response, _generate_part_with_check,
    get_unique_quote,
    _print_final_quality_summary, publish_to_wordpress_selenium, publish_to_wordpress,
    _upload_image_to_wordpress, _check_publish_interval, _clean_stale_sessions,
    ping_indexnow,
    _render_html_to_image, _threads_post_carousel, _threads_post,
    _telegram_send_message, _telegram_get_updates, _telegram_update_is_authorized, _insert_operator_memo,
    _telegram_answer_callback, _telegram_edit_text,
    _check_duplicate, _save_published_article_file, _register_article,
    _load_state,
    generate_optimized_title,
    _discover_due, _mark_discovered,
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

# [중요] ETF 전용 shared_base(_generate_chained_article 안)의 핵심 지시를 수정할
# 때마다 이 숫자를 올려야 함. 세션 캐시에 이 버전이 함께 저장되고, 코드의 현재
# 버전과 다르면 그 세션은 자동으로 무효화되어 재생성된다. blog_engine.py의
# 공용 세션 캐싱 로직과는 별개로, ETF 고유 프롬프트 개정 이력을 추적하는 용도라
# etf_auto.py에만 둔다(뉴스 카테고리는 이 방식의 세션 버전 관리를 쓰지 않음).
PROMPT_LOGIC_VERSION = 34

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



def _get_recent_economic_issues(macro_data):
    """최근 거시 지표를 '완성된 문장'이 아닌 원시 신호(raw signal)로 정리.
    완성 문장을 반환하면 AI가 그대로 복붙해 여러 ETF 글에 재사용하는 문제가 생기므로,
    분류 라벨 + 실제 수치만 넘기고 ETF별 해석은 프롬프트에서 AI가 직접 하도록 강제한다."""
    signals = []
    try:
        usdkrw = float(str(macro_data.get('usd_krw','0').replace('원','').replace(',','')))
        us10y = float(str(macro_data.get('us_10y','0').replace('%','')))
        feargreed = macro_data.get('fear_greed','').split()[0]

        fx_label = '고환율 국면' if usdkrw > 1450 else '환율 안정 국면'
        signals.append(f"환율={macro_data.get('usd_krw','N/A')}({fx_label})")

        rate_label = '고금리 국면' if us10y > 4.0 else '금리 둔화 국면'
        signals.append(f"미10년물={macro_data.get('us_10y','N/A')}({rate_label})")

        if feargreed and feargreed.isdigit():
            score = int(feargreed)
            fg_label = '공포' if score < 40 else ('탐욕' if score > 60 else '중립')
            signals.append(f"공포탐욕지수={score}({fg_label})")
    except (ValueError, TypeError):
        signals.append('거시 데이터 파싱 실패 - 원본 수치를 직접 확인 필요')

    return ' / '.join(signals) if signals else '거시 지표 수집 중'




def _inject_static_sections(blog_content, section_htmls):
    """작가 프로필과 면책조항을 고정된 HTML 블록으로 합성.

    [수정] 예전엔 blog_content.replace(block, '')로 "AI가 만든 텍스트가
    section_htmls의 원본과 한 글자도 다르지 않을 때만" 중복을 지웠다. 그런데
    AI는 "그대로 삽입하라"는 지시를 받아도 따옴표 스타일이나 공백, 줄바꿈이
    미세하게 달라지는 경우가 흔해서, 실제로는 원본 위치의 블록이 지워지지
    않고 이 함수가 끝에 또 하나를 붙여 결과적으로 "온도(ondo)" 소개가
    2번 나오는 문제가 발생했다(작가 프로필의 원본에 발행 이력 카운트 같은
    동적 값이 섞여있어 더더욱 완전일치가 어려웠음).

    이제는 완전일치 대신, 각 블록의 "식별 마커"(작가 프로필은 '온도(ondo)'
    제목이 들어간 <h4> 태그, 면책조항은 그 제목 문구)가 포함된 <div>...</div>
    블록을 정규식으로 통째로 찾아 전부 제거한 뒤, 고정 버전을 맨 끝에 한 번만
    붙인다. 태그 안에 태그가 중첩된 형태이므로 가장 바깥쪽 <div>만 정확히
    잡기 위해 non-greedy 매칭과 후처리 균형 검사를 함께 쓴다.
    """
    fixed_blocks = []
    markers = {
        '작가 프로필': r'<h4[^>]*>\s*온도\(ondo\)\s*</h4>',
        '면책조항': r'<strong>[^<]*면책\s*조항[^<]*</strong>',
    }

    def _find_outer_div(content, marker_pattern):
        """content 안에서 marker_pattern에 처음 매칭되는 위치를 포함하는,
        그 지점을 감싸는 "최상위(depth 0)" <div>...</div>의 [start, end) 범위를
        찾아 반환한다. 못 찾으면 None."""
        m = re.search(marker_pattern, content)
        if not m:
            return None
        marker_pos = m.start()
        stack = []
        for tag_m in re.finditer(r'<div\b[^>]*>|</div>', content):
            if tag_m.group(0).startswith('</div'):
                if stack:
                    open_start = stack.pop()
                    if not stack and open_start <= marker_pos <= tag_m.end():
                        return (open_start, tag_m.end())
            else:
                stack.append(tag_m.start())
        return None

    for key in ['작가 프로필', '면책조항']:
        block = section_htmls.get(key)
        if not block:
            continue
        fixed_blocks.append(block)

        marker = markers[key]
        # 마커가 더 이상 발견되지 않을 때까지 반복 제거 (AI가 실수로 여러 번
        # 삽입했을 가능성까지 대비)
        while True:
            found = _find_outer_div(blog_content, marker)
            if not found:
                break
            start, end = found
            blog_content = blog_content[:start] + blog_content[end:]

    if not fixed_blocks:
        return blog_content

    cleaned_content = blog_content.strip()
    if cleaned_content:
        cleaned_content += '\n\n'
    cleaned_content += '\n\n'.join(fixed_blocks)
    return cleaned_content




def _technical_term_glossary():
    return {
        "MDD": "Maximum Drawdown의 약자로, 고점 대비 저점까지 떨어진 비율을 뜻합니다.",
        "배당수익률": "투자자가 받는 연간 배당금 총액을 현재 주가로 나눈 비율입니다.",
        "운용보수": "ETF를 운용하는 자산운용사가 받는 수수료로, 수익률에 직접 영향을 줍니다.",
        "추적오차": "ETF 수익률과 추종 대상 지수 수익률 간의 차이를 뜻합니다.",
        "환헤지": "외화 환율 변동 리스크를 줄이기 위해 통화 약정을 사용하는 전략입니다.",
        "커버드콜": "기초자산을 보유한 상태에서 콜옵션을 매도해 추가 수익을 얻는 전략입니다.",
        "IRP": "개인형 퇴직연금으로, 세제 혜택과 함께 노후 자산을 운용하는 계좌입니다.",
        "ISA": "개인종합자산관리계좌로, 일정 한도 내에서 금융소득 비과세 혜택을 받는 계좌입니다.",
        "DCA": "Dollar Cost Averaging의 약자로, 정기적으로 일정 금액을 투자하는 방식입니다.",
        "리밸런싱": "포트폴리오 자산 비중을 목표 비중으로 재조정하는 작업입니다.",
        "과세계좌": "과세되는 일반 투자 계좌를 뜻하며, 배당금과 양도소득에 세금이 부과됩니다.",
        "세금이연": "현 시점에서 세금을 내지 않고, 나중에 인출 시점에 세금을 내는 구조입니다.",
        "벤치마크": "ETF가 추종하는 기준 지수를 의미합니다.",
        "백테스트": "과거 데이터를 기준으로 투자 전략을 시뮬레이션하는 분석입니다.",
        "변동성": "가격 변동의 크기를 뜻하며, 높을수록 위험도도 큽니다.",
        "총보수비율": "TER이라고도 하며, 운용보수 외에 매매수수료 등을 포함한 ETF의 연간 총 비용 비율입니다.",
        "순자산총액": "AUM이라고도 하며, ETF가 운용하는 전체 자산의 규모를 뜻합니다.",
        "괴리율": "ETF 시장가격과 순자산가치(NAV) 사이의 차이 비율입니다.",
        "NAV": "순자산가치를 뜻하며, ETF가 보유한 자산에서 부채를 뺀 뒤 발행 좌수로 나눈 값입니다.",
        "섹터로테이션": "경기 국면에 따라 유망한 산업 섹터로 투자 비중을 옮겨가는 전략입니다.",
        "듀레이션": "채권 가격이 금리 변화에 얼마나 민감하게 반응하는지를 나타내는 지표입니다.",
        "롤오버": "선물 계약 만기 시 다음 만기 계약으로 포지션을 이전하는 것을 뜻합니다.",
        "액티브ETF": "지수를 그대로 추종하지 않고 운용사가 재량으로 종목을 선정하는 ETF입니다.",
        "합성ETF": "실물 자산 대신 스왑 계약 등 파생상품을 활용해 지수 수익률을 추종하는 ETF입니다.",
        "시가총액가중": "종목별 시가총액 비중에 따라 지수 내 편입 비중을 정하는 방식입니다.",
        "동일가중": "종목 규모와 무관하게 모든 종목에 동일한 비중을 부여하는 방식입니다.",
        "레버리지ETF": "기초지수 일간 수익률의 2배, 3배 등을 추종하도록 설계된 ETF입니다.",
        "인버스ETF": "기초지수가 하락할 때 수익이 나도록 설계된 ETF입니다.",
        "분배금": "ETF가 보유 자산에서 발생한 이익을 투자자에게 지급하는 금액입니다.",
        "장기보유특별공제": "일정 기간 이상 자산을 보유했을 때 양도소득세를 줄여주는 세제 혜택입니다.",
        "금융소득종합과세": "이자·배당 등 금융소득이 연간 일정 금액을 넘으면 다른 소득과 합산해 과세하는 제도입니다.",
        "복리효과": "원금뿐 아니라 이미 발생한 수익에도 다시 수익이 붙어 자산이 가속도로 불어나는 효과입니다.",
        "샤프지수": "투자자산이 부담한 위험 대비 초과수익이 얼마나 되는지를 나타내는 지표입니다.",
        "베타": "시장 전체 움직임 대비 개별 자산의 민감도를 나타내는 지표입니다.",
        "알파": "벤치마크 대비 초과 달성한 수익률을 뜻합니다.",
        "유동성공급자": "LP라고도 하며, ETF의 시장가격이 순자산가치와 크게 벌어지지 않도록 매수·매도 호가를 지속적으로 제시하는 참여자입니다.",
        "설정환매": "ETF 좌수를 새로 만들거나(설정) 없애는(환매) 과정을 뜻합니다.",
        "기초지수": "ETF가 추종하도록 설계된 대상 지수입니다.",
        "상장폐지": "ETF가 거래소에서 더 이상 거래되지 않도록 상장이 취소되는 것을 뜻합니다.",
        "테마ETF": "특정 산업이나 트렌드에 집중 투자하도록 구성된 ETF입니다.",
        "원자재ETF": "금, 원유 등 원자재 가격을 추종하도록 설계된 ETF입니다.",
        "채권ETF": "국채, 회사채 등 채권에 투자하는 ETF입니다.",
        "배당성장ETF": "배당금을 꾸준히 늘려온 기업들에 투자하는 ETF입니다.",
        "가치주": "현재 주가가 기업의 내재가치보다 저평가된 것으로 평가되는 주식입니다.",
        "성장주": "매출과 이익이 시장 평균보다 빠르게 성장할 것으로 기대되는 주식입니다.",
    }


def _highlight_technical_terms(html):
    glossary = _technical_term_glossary()
    if not glossary:
        return html

    title_match = re.search(r'(<h1[^>]*>.*?</h1>)', html, flags=re.DOTALL | re.IGNORECASE)
    prefix = ''
    title_html = ''
    rest_html = html
    if title_match:
        prefix = html[:title_match.start()]
        title_html = title_match.group(1)
        rest_html = html[title_match.end():]

    terms = sorted(glossary.keys(), key=len, reverse=True)

    def make_tooltip(term, explanation):
        safe_explanation = explanation.replace('"', '&quot;')
        return (
            f'<span class="finq-tip" tabindex="0">{term}'
            f'<span class="finq-tip-text">{safe_explanation}</span>'
            f'</span>'
        )

    # [수정] 이전에는 같은 용어(예: MDD)가 본문에 등장할 때마다 매번 툴팁 전체를
    # 다시 씌워서, 15번 넘게 반복되면 그때마다 전체 설명 문구가 통째로 붙어
    # 본문이 실제보다 훨씬 길고 늘어진 느낌을 줬음. 각 용어는 처음 등장할 때만
    # 툴팁을 씌우고, 이후 등장은 일반 텍스트로 남긴다(위키백과 등에서 첫 등장에만
    # 링크를 다는 것과 같은 원리 - 독자가 이미 뜻을 확인했다고 가정).
    already_tagged = set()

    def replace_text_segment(segment):
        for term in terms:
            if term in already_tagged:
                continue
            pattern = re.compile(rf'(?<![0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]){re.escape(term)}(?![0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ])')
            match = pattern.search(segment)
            if not match:
                continue
            replacement = make_tooltip(term, glossary[term])
            # count=1: 이 세그먼트 안에서 딱 첫 번째 등장만 치환
            segment = pattern.sub(replacement, segment, count=1)
            already_tagged.add(term)
        return segment

    parts = re.split(r'(<[^>]+>)', rest_html)
    for idx, part in enumerate(parts):
        if not part.startswith('<'):
            parts[idx] = replace_text_segment(part)

    processed_html = ''.join(parts)
    return prefix + title_html + processed_html





MACRO_CACHE_TTL = 3600
TICKER_CACHE_TTL = 1800






def _get_operating_history():
    """[신규] 저자 프로필에 "운영 이력"을 표시하기 위해, 실제 발행 기록에서
    첫 발행일과 누적 발행 수를 계산한다. 지어낸 숫자가 아니라
    article_state.json에 실제로 쌓인 published 상태 글만 센다.

    반환값: {'first_date': str 또는 None, 'count': int, 'months_active': int}
    글이 하나도 없으면 count=0, first_date=None을 반환하고, 호출부는 이 경우
    운영 이력 문구 자체를 표시하지 않아야 한다(0개월/0편이라는 어색한 문구 방지).
    """
    state = _load_state()
    published = [a for a in state.get('articles', []) if a.get('status') == 'published']
    if not published:
        return {'first_date': None, 'count': 0, 'months_active': 0}

    timestamps = []
    for a in published:
        try:
            timestamps.append(datetime.fromisoformat(a['timestamp']))
        except (ValueError, KeyError, TypeError):
            continue

    if not timestamps:
        return {'first_date': None, 'count': len(published), 'months_active': 0}

    first_dt = min(timestamps)
    months_active = max(1, (datetime.now().year - first_dt.year) * 12 + (datetime.now().month - first_dt.month))

    return {
        'first_date': first_dt.strftime('%Y년 %m월'),
        'count': len(published),
        'months_active': months_active,
    }


























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


def _find_near_percent_in_text(text, target, tolerance=0.5, context_keywords=None, context_window=60):
    """
    본문에 target과 비슷한 숫자가 있는지 확인합니다.

    [중요] 이전에는 "본문 어딘가에 비슷한 숫자가 존재하는가"만 확인했는데, 이러면
    서로 다른 항목의 값이 우연히 비슷할 때(예: MDD -53.30%와 1년 수익률 -53.93%처럼
    소수점만 다른 경우) 실제로는 그 숫자가 엉뚱한 항목에 대해 쓰인 것이어도
    "반영됨"으로 잘못 판정할 위험이 있었음.

    context_keywords가 주어지면, 숫자가 등장하는 위치 앞뒤 context_window자 안에
    해당 키워드 중 하나라도 있는지까지 확인해 오탐지를 줄인다. context_keywords가
    없으면 기존처럼 숫자 존재 여부만 확인(하위 호환).
    """
    try:
        target_val = float(str(target).replace('%', '').strip())
    except (ValueError, TypeError):
        return False

    for match in re.finditer(r'([+-]?\d+\.?\d*)%', text):
        try:
            match_val = float(match.group(1))
        except ValueError:
            continue
        if abs(match_val - target_val) > tolerance:
            continue
        if not context_keywords:
            return True
        # 숫자 등장 위치 주변 문맥에서 관련 키워드가 있는지 확인
        start = max(0, match.start() - context_window)
        end = min(len(text), match.end() + context_window)
        surrounding = text[start:end]
        if any(kw in surrounding for kw in context_keywords):
            return True
    return False


def _detect_text_anomalies(html_text):
    """[신규] 후처리 단어 치환 과정에서 생기는 명백한 문법 오류 패턴을 정규식으로
    감지한다. 실제로 겪었던 사례: "하지만"->"다만" 치환이 "~하지만"에 걸려
    "~다만하지 않습니다"처럼 겹치거나, "발생다만"처럼 단어가 끊기는 경우.
    AI가 다시 검수하기 전에, 코드만으로 100% 확정적으로 잡을 수 있는 패턴이라
    비용 없이 빠르게 걸러낼 수 있다."""
    anomalies = []

    # 1. 같은 한 글자~세 글자가 바로 반복되는 패턴 (예: "다만다만", "그리고그리고")
    #    단, 숫자나 특수문자 반복(예: "!!", "1000")은 제외
    repeat_pattern = re.compile(r'([가-힣]{2,4})\1')
    for match in repeat_pattern.finditer(html_text):
        anomalies.append(f"반복 패턴 발견: '{match.group(0)}'")

    # 2. 단어가 중간에 끊긴 것으로 보이는 패턴 (예: "발생다만", "제공다만", "미 미칩니다")
    #    "~다만" 앞에 조사 없이 바로 동사 어간이 오는 경우 (실제로 겪었던 버그 유형)
    broken_pattern = re.compile(r'[가-힣]+(?:하다만|되다만|지다만)')
    for match in broken_pattern.finditer(html_text):
        anomalies.append(f"단어 중간 끊김 의심: '{match.group(0)}'")

    # 3. 같은 글자가 공백을 사이에 두고 반복되는 패턴 (예: "미 미칩니다")
    # [수정] 기존 정규식이 너무 광범위해서, 정상적인 한국어 문장(예: "환율
    # 리스크를"에서 "리"와 그 뒤 조사/단어의 첫 글자가 우연히 겹치는 경우,
    # "가 가진", "시 시뮬레이션" 등)을 계속 오탐지하고 있었음. 실제로 겪었던
    # 버그 사례("미 미칩니다")는 "글자 + 공백 + 같은 글자로 시작하는 완전히
    # 같은 단어(2자 이상)"가 반복되는 형태라, 이 조건에 더 가깝게 좁혀서
    # 오탐지를 제거한다. 이 오탐지가 실제로 Part5를 매번 강제 재생성시켜
    # API 호출이 걷잡을 수 없이 폭증하는 원인이었음(재생성마다 파트 생성+
    # 검수가 반복되며 한 편에 100회 이상의 API 요청이 발생한 사례 확인됨).
    space_repeat_pattern = re.compile(r'([가-힣])\s(\1[가-힣]{1,})\2\b')
    for match in space_repeat_pattern.finditer(html_text):
        anomalies.append(f"공백 삽입 반복 의심: '{match.group(0)}'")

    return anomalies


def _validate_blog_content(html_text, macro_data, etf_data_cache):
    warnings = []

    # [신규] 수치 검증과 별개로, 데이터 유무와 무관하게 항상 문법 이상 패턴을 검사.
    text_anomalies = _detect_text_anomalies(html_text)
    if text_anomalies:
        warnings.extend([f"[문법 이상 감지] {a}" for a in text_anomalies])

    if not etf_data_cache:
        return warnings

    for ticker, data in etf_data_cache.items():
        if data.get('expense_ratio') and data['expense_ratio'] != '정보 없음':
            if not _find_near_percent_in_text(html_text, data['expense_ratio'], context_keywords=['운용보수', '보수']):
                warnings.append(f"{ticker} 운용보수({data['expense_ratio']})가 본문에 명확히 반영되지 않았습니다.")
        if data.get('yield') and data['yield'] != '정보 없음':
            if not _find_near_percent_in_text(html_text, data['yield'], context_keywords=['배당', '수익률', '분배']):
                warnings.append(f"{ticker} 배당 수익률({data['yield']})가 본문에 명확히 반영되지 않았습니다.")
        returns = data.get('returns', {})
        for label, pct in [('1개월', returns.get('1개월')), ('3개월', returns.get('3개월')), ('1년', returns.get('1년'))]:
            if pct is not None:
                if not _find_near_percent_in_text(html_text, pct, context_keywords=[label, '수익률']):
                    warnings.append(f"{ticker} {label} 수익률({pct:.2f}%)가 본문에 명확히 반영되지 않았습니다.")
        if data.get('mdd') and data['mdd'] != '정보 없음':
            if not _find_near_percent_in_text(html_text, data['mdd'], context_keywords=['MDD', '낙폭', '최대낙폭']):
                warnings.append(f"{ticker} 최대 낙폭({data['mdd']})가 본문에 명확히 반영되지 않았습니다.")

    return warnings




















PREVIOUS_CONTENT_BLOCK_CAP = 40000  # _llm_part_check(PART_CHECK_SAFE_CAP)와 동일한 상한을 씀



















def _add_data_citation(today_str, etf_list, etf_data_cache=None):
    """출처 명시 및 신뢰성 강화.
    [개선] 이전에는 '각 운용사 공식 팩트시트 기준'이라는 텍스트만 있고 실제 링크가
    없었음. etf_data_cache에 이미 각 ETF의 공식 홈페이지(website)와 인베스팅닷컴
    실시간 데이터 URL(investing_url)이 있으므로, 이를 실제 하이퍼링크로 연결해
    독자가 원본 데이터를 직접 확인할 수 있게 하고 신뢰성(E-E-A-T) 신호를 강화한다."""
    etf_data_cache = etf_data_cache or {}
    ticker_str = ", ".join([t.replace(".KS", "").replace(".US", "") for t in etf_list])

    # 실제 공식 출처 링크 목록 구성 (정보가 없는 경우는 건너뜀)
    source_links = []
    for ticker, d in etf_data_cache.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        website = d.get('website', '')
        investing_url = d.get('investing_url', '')
        if website and website not in ('정보 없음', '공식 홈페이지 정보 없음', ''):
            source_links.append(f'<li>{ticker_clean} 공식 팩트시트: <a href="{website}" target="_blank" style="color:#2980b9;">{d.get("issuer", "운용사")} 공식 페이지</a></li>')
        if investing_url:
            source_links.append(f'<li>{ticker_clean} 실시간 시세/지표: <a href="{investing_url}" target="_blank" style="color:#2980b9;">Investing.com</a></li>')
    source_links_html = "\n".join(source_links) if source_links else '<li>ETF 상세정보: 각 운용사 공식 팩트시트 기준</li>'

    return f"""
<div style="background:#f0f4f8;padding:15px;border-left:4px solid #2c3e50;margin:20px 0;border-radius:4px;">
<p style="margin:0;font-size:13px;color:#34495e;"><strong>📌 데이터 출처 및 기준일</strong></p>
<ul style="margin:8px 0;padding-left:20px;font-size:12px;color:#555;line-height:1.6;">
<li>주가/배당 데이터: <a href="https://finance.yahoo.com" target="_blank" style="color:#2980b9;">Yahoo Finance</a> (기준: {today_str})</li>
<li>한국 ETF 운용보수: <a href="https://www.kliquidity.com" target="_blank" style="color:#2980b9;">한국거래소 실시간시세</a></li>
{source_links_html}
<li>분석 대상: {ticker_str}</li>
</ul>
<p style="margin:8px 0;font-size:11px;color:#e74c3c;"><strong>⚠️ 중요 공시:</strong> 이 분석은 작성일({today_str}) 기준입니다. 3개월 경과 후 데이터 재검토를 권장합니다. 모든 투자는 본인 책임입니다.</p>
</div>
"""


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


def _detect_etf_structural_traits(ticker, data):
    """[신규] 이 ETF의 구조적 특성을 자동 판단해, "나이"가 아니라 "이 자산만의
    특징"으로 페르소나를 재정의할 수 있게 하는 헬퍼.

    나이 구간(20대/40대/50대)은 모든 ETF 글에 재사용 가능한 템플릿이라 그
    자체로는 차별화가 안 됨. 대신 이 ETF이기 때문에만 성립하는 구분(무배당
    자산인지, 레버리지/인버스 상품인지, 암호화�지 연동 자산인지)으로 페르소나를
    바꾸면, 그 페르소나 설명 자체가 다른 ETF 글에는 못 쓰는 내용이 된다.

    반환값: {'is_no_dividend': bool, 'is_leveraged': bool, 'is_crypto': bool,
             'is_high_volatility': bool} - 여러 특성이 동시에 True일 수 있음
             (예: 레버리지+무배당 모두 해당하는 상품도 있음).
    """
    data = data or {}
    ticker_upper = (ticker or "").upper()
    sector = str(data.get('sector', '') or '').lower()
    industry = str(data.get('industry', '') or '').lower()
    description = str(data.get('description', '') or '').lower()
    combined_text = f"{sector} {industry} {description}"

    # 무배당 여부: 이미 계산된 실제 배당수익률로 100% 정확히 판단 가능
    yield_str = str(data.get('yield', '0') or '0').replace('%', '').strip()
    try:
        yield_val = float(yield_str)
    except (ValueError, TypeError):
        yield_val = 0.0
    is_no_dividend = yield_val <= 0.0

    # 레버리지/인버스 상품 여부: 티커명 관행(3x, 2x 등)과 설명 텍스트로 판단
    leverage_keywords = ['leveraged', 'leverage', '3x', '2x', 'inverse', 'ultrapro', 'daily target']
    is_leveraged = any(kw in combined_text for kw in leverage_keywords) or \
        any(kw in ticker_upper for kw in ['TQQQ', 'SOXL', 'SQQQ', 'SPXU', 'UPRO', 'SOXS'])

    # 암호화폐 연동 자산 여부: 섹터/설명 텍스트 기반 판단
    crypto_keywords = ['bitcoin', 'crypto', 'digital asset', 'blockchain', 'ethereum']
    is_crypto = any(kw in combined_text for kw in crypto_keywords) or \
        ticker_upper in ['IBIT', 'FBTC', 'ARKB', 'GBTC', 'ETHA', 'BITO']

    # 실제 MDD 기반 고변동성 여부 (위 세 특성에 안 걸려도, 실제 데이터로 변동성이
    # 크다고 확인되면 별도 페르소나를 적용할 근거가 됨)
    mdd_str = str(data.get('mdd', '0') or '0').replace('%', '').strip()
    try:
        mdd_val = abs(float(mdd_str))
    except (ValueError, TypeError):
        mdd_val = 0.0
    is_high_volatility = mdd_val >= 30.0

    return {
        'is_no_dividend': is_no_dividend,
        'is_leveraged': is_leveraged,
        'is_crypto': is_crypto,
        'is_high_volatility': is_high_volatility,
    }


def _build_structural_persona_section(primary, traits):
    """[신규] _detect_etf_structural_traits가 판단한 특성에 맞춰, "나이" 대신
    "이 자산의 구조적 특징"으로 정의된 페르소나 섹션을 만든다. 해당하는 특성이
    하나도 없으면 빈 문자열을 반환해(안전한 폴백) 이 섹션 자체를 생략한다."""
    personas = []

    if traits.get('is_crypto'):
        personas.append((
            "🪙 비트코인 반감기 사이클을 믿는 사람 vs 단기 트레이딩 목적인 사람",
            f"{primary}는 비트코인 가격에 연동되는 자산이라, 장기 보유 근거가 '반감기 이후 상승 사이클'에 대한 믿음인지, "
            f"아니면 단기 변동성을 이용한 트레이딩인지에 따라 전략이 완전히 달라집니다. 전자라면 지금 같은 조정 구간을 "
            f"매집 기회로 볼 수 있지만, 후자라면 손절 기준을 미리 정해두는 게 우선입니다."
        ))
        personas.append((
            "⚠️ 이미 코인 거래소에 비트코인을 직접 보유한 사람",
            f"이미 코인 거래소에서 비트코인 현물을 들고 있다면, {primary}를 추가로 담는 것은 자산 분산이 아니라 "
            f"비트코인이라는 동일 자산에 대한 노출을 중복시키는 것입니다. 포트폴리오 전체에서 비트코인 관련 비중을 "
            f"합산해서 관리해야 하며, 세금 계좌 활용을 위해 {primary}를 추가하려는 것이 아니라면 굳이 중복할 필요는 없습니다."
        ))

    if traits.get('is_no_dividend') and not traits.get('is_crypto'):
        personas.append((
            "💰 배당 재투자 복리 효과를 노리는 사람에게는 맞지 않는 상품",
            f"{primary}는 배당을 지급하지 않는 자산입니다. 배당금을 재투자해 복리 효과를 노리는 전략을 원한다면 "
            f"이 상품은 애초에 그 목적에 맞지 않으며, 수익은 오직 가격 상승분(자본 이득)에서만 나옵니다. "
            f"정기적인 현금 흐름이 필요하다면 배당형 ETF를 별도로 고려해야 합니다."
        ))

    if traits.get('is_leveraged'):
        personas.append((
            "⚡ 단기 방향성 베팅과 장기 보유는 전혀 다른 이야기",
            f"{primary}처럼 배율이 적용된 레버리지/인버스 상품은 매일 수익률을 재조정(리밸런싱)하는 구조라, "
            f"기초 지수가 장기간 횡보하기만 해도 복리 효과 때문에 원금이 계속 깎여나갈 수 있습니다. "
            f"단기 방향성에 확신이 있을 때 짧게 활용하는 도구이지, 일반적인 장기 적립식 투자 대상으로는 "
            f"설계되지 않았다는 점을 반드시 감안해야 합니다."
        ))

    if not personas and traits.get('is_high_volatility'):
        personas.append((
            "📉 실제 낙폭을 감내할 수 있는 사람인지가 핵심",
            f"{primary}는 실제 과거 데이터 기준으로 최대 낙폭이 30%를 넘는 고변동성 자산입니다. "
            f"일반적인 '분산 투자의 일부'로 접근하기보다는, 이 정도 낙폭을 실제로 감내할 수 있는지를 "
            f"먼저 자문해보고 비중을 정하는 것이 순서입니다."
        ))

    if not personas:
        return ""  # 특별히 해당하는 구조적 특성이 없으면 이 섹션 자체를 생략

    items_html = "".join(
        f'<div style="margin-bottom:16px;padding:14px;background:#fff;border:1px solid #e0e0e0;border-radius:6px;">'
        f'<p style="margin:0 0 6px 0;font-weight:bold;color:#2c3e50;">{title}</p>'
        f'<p style="margin:0;font-size:13px;color:#555;line-height:1.6;">{desc}</p>'
        f'</div>'
        for title, desc in personas
    )

    return f"""
<div style="margin-top:24px;padding:18px;background:#f4f6f8;border-radius:8px;">
<p style="margin:0 0 14px 0;font-weight:bold;color:#2c3e50;font-size:15px;">🎯 {primary}, 나이보다 이런 기준으로 나를 점검해보세요</p>
{items_html}
</div>
"""


def _add_age_based_portfolio_guide(etf_list=None, etf_data_cache=None,
                                    backtest_results_by_ticker=None,
                                    risk_results_by_ticker=None,
                                    tax_comparison_result=None):
    """연령/라이프스테이지별 포트폴리오 가이드.
    [중요] 이전 버전은 인자 없이 SPY/IVV/SCHD를 하드코딩해, 어떤 ETF를 다루는 글이든
    똑같은 HTML이 그대로 삽입되는 중복 콘텐츠 문제가 있었음. 그 다음 버전은 티커/
    배당수익률 정도만 반영했지만, 각 연령대 섹션의 서술 자체("비중 확대", "리밸런싱")는
    여전히 어떤 고변동성 자산에도 통하는 일반론이었음(구조가 여전히 프로그래매틱함).

    [이번 개선 1] 이미 다른 섹션(백테스트 시뮬레이션, 위험 시나리오, 실수료 비교표)이
    계산해둔 이 ETF만의 실제 숫자를 연령대별로 다르게 끌어와 서술한다:
    - 20~30대: 적립식 vs 거치식 실제 평가금액 비교 (백테스트 결과)
    - 40대: 계좌 유형별 실질 수익률 차이 (세금 비교표 결과)
    - 50대: 실제 MDD 기준 최대 손실 금액 (위험 시나리오 결과)
    이렇게 하면 각 문단이 "이 ETF의 실제 계산값이 있어야만 쓸 수 있는 문장"이 되어,
    다른 ETF 글에 그대로 갖다 붙일 수 없다. 계산 결과가 없는 경우(데이터 부족 등)에는
    안전하게 기존의 원칙 기반 서술로 폴백해, 어떤 경우에도 오류 없이 섹션이 생성된다.

    [이번 개선 2] "나이"는 모든 ETF 글에 재사용 가능한 템플릿 구분이라 그 자체로는
    차별화가 안 됨. _detect_etf_structural_traits로 이 ETF의 구조적 특성(무배당,
    레버리지, 암호화폐 연동 여부 등)을 자동 판단해, 나이 구간 대신 "이 자산이기
    때문에만 성립하는 페르소나"를 유동적으로 추가한다. 해당 특성이 없는 일반
    ETF(지수추종형, 배당형 등)라면 이 섹션 자체가 조용히 생략되어, 억지로 특이한
    페르소나를 만들어내지 않는다.
    """
    etf_list = etf_list or []
    etf_data_cache = etf_data_cache or {}
    backtest_results_by_ticker = backtest_results_by_ticker or {}
    risk_results_by_ticker = risk_results_by_ticker or {}
    tax_comparison_result = tax_comparison_result or {}

    def _clean(t):
        return t.replace(".KS", "").replace(".US", "")

    primary = _clean(etf_list[0]) if etf_list else "핵심 성장 ETF"
    primary_raw = etf_list[0] if etf_list else None
    if _is_overseas_listed(etf_data_cache.get(primary_raw)):
        account_plan_text = f"{primary}는 해외 상장이라 ISA·연금계좌로 직접 살 수 없음. 절세 계좌를 쓰려면 같은 지수의 국내 상장 ETF로 ISA → 연금저축/IRP 순"
    else:
        account_plan_text = "ISA 우선, 차후 연금저축/IRP"

    # 이 글이 다루는 ETF 중 배당수익률이 가장 높은 것을 '배당 축' 후보로 선정
    div_ticker = primary
    best_yield = -1.0
    for ticker, d in etf_data_cache.items():
        try:
            y = float(str(d.get('yield', '0')).replace('%', '').strip())
        except (ValueError, TypeError):
            y = 0.0
        if y > best_yield:
            best_yield = y
            div_ticker = _clean(ticker)

    # --- 20~30대: 적립식 vs 거치식 실제 백테스트 숫자로 서술 ---
    backtest = backtest_results_by_ticker.get(primary_raw) if primary_raw else None
    if backtest:
        cur = backtest['currency_symbol']
        dca_val = f"{backtest['dca_final_value']:,.0f}{cur}"
        dca_pct = backtest['dca_return_pct']
        lump_val = f"{backtest['lump_final_value']:,.0f}{cur}"
        lump_pct = backtest['lump_return_pct']
        dca_pct_str = f"{'+' if dca_pct >= 0 else ''}{dca_pct:.1f}%"
        lump_pct_str = f"{'+' if lump_pct >= 0 else ''}{lump_pct:.1f}%"
        young_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>실제 시뮬레이션 근거</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">앞서 백테스트에서 본 것처럼, 같은 기간 매달 나눠 적립식으로 넣었다면 평가액 약 {dca_val}({dca_pct_str}), '
            f'반대로 한 번에 거치식으로 넣었다면 약 {lump_val}({lump_pct_str})이었습니다. 변동성이 큰 구간에서는 분할 매수 쪽이 심리적으로 버티기 쉬웠다는 걸 이 숫자가 보여줍니다.</td></tr>'
        )
        young_strategy_note = f"위 백테스트 결과(적립식 {dca_pct_str} vs 거치식 {lump_pct_str})를 참고해, 이번 사이클에서는 분할 매수 비중을 우선 고려하세요."
    else:
        young_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>{primary} 비중</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">투자 가능 자산의 상당 부분 (공격형, 남은 투자 기간이 길어 변동성을 감내할 여력이 상대적으로 큼)</td></tr>'
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>매수 방식</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">본인 소득 대비 감당 가능한 금액을 정해 매달 자동이체로 꾸준히</td></tr>'
        )
        young_strategy_note = f"시간을 무기로 삼기. 무리하지 않는 선에서 정한 금액을 꾸준히 {primary}에 넣어 평단가를 낮추세요."

    # --- 40대: 계좌별 실질 수익률 차이로 서술 ---
    account_returns = tax_comparison_result.get('account_returns', {})
    if account_returns and len(account_returns) >= 2:
        sorted_accounts = sorted(account_returns.items(), key=lambda x: x[1], reverse=True)
        best_name, best_return = sorted_accounts[0]
        worst_name, worst_return = sorted_accounts[-1]
        gap = round(best_return - worst_return, 1)
        mid_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>실제 계좌별 실질 수익률</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">앞서 계산된 계좌별 비교표에서, {best_name}는 실질 수익률 {best_return:.1f}%인 반면 {worst_name}는 {worst_return:.1f}%로 '
            f'{gap:.1f}%p 차이가 났습니다. 40대라면 세액공제 한도보다 이 실질 수익률 차이부터 먼저 따져보는 게 순서입니다.</td></tr>'
        )
        mid_strategy_note = f"{best_name}와 {worst_name}의 실질 수익률 차이({gap:.1f}%p)를 먼저 확인하고 계좌를 배분하세요."
    else:
        mid_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>포트폴리오</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">{primary} 약 60% / 배당형({div_ticker}) 약 40% (본인 리스크 성향에 따라 조정)</td></tr>'
        )
        mid_strategy_note = "곱하기(수익) + 나누기(배당) 균형. 이때부터 배당 현금흐름을 함께 고려하세요."

    # --- 50대: 실제 위기 시나리오 최대손실 금액으로 서술 ---
    risk = risk_results_by_ticker.get(primary_raw) if primary_raw else None
    if risk and risk.get('mdd_pct'):
        loss_man = int(risk['loss_amount'] / 10000)
        remain_man = int(risk['remaining'] / 10000)
        old_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>실제 위기 시나리오 기준</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">앞서 계산된 위기 시나리오대로면, {primary}에 1억 원을 넣었을 때 실제 과거 MDD({risk["mdd_pct"]:.1f}%) 기준 '
            f'최대 손실은 {loss_man:,}만원(잔액 {remain_man:,}만원)입니다. 은퇴가 머지않은 시점이라면, 이 손실을 실제로 감내할 수 있는지가 비중 결정의 핵심입니다.</td></tr>'
        )
        old_strategy_note = f"위 최대손실 금액({loss_man:,}만원)을 실제로 감내 가능한지를 기준으로 비중을 정하세요."
    else:
        old_body = (
            f'<tr><td style="border:1px solid #ddd;padding:10px;"><strong>포트폴리오</strong></td>'
            f'<td style="border:1px solid #ddd;padding:10px;">{primary} 약 40% / {div_ticker} 약 60% (배당중심, 은퇴 시점에 맞춰 조정)</td></tr>'
        )
        old_strategy_note = "현금흐름 중심. 배당금으로 생활비 일부를 충당하는 구조를 검토하세요."

    # [신규] 나이 대신 이 ETF의 구조적 특성으로 페르소나를 유동적으로 추가.
    # etf_list의 첫 번째 티커(대표 종목) 기준으로 판단하며, 해당 특성이 없는
    # 일반 ETF라면 _build_structural_persona_section이 빈 문자열을 반환해
    # 이 섹션이 조용히 생략된다.
    primary_data = etf_data_cache.get(primary_raw) if primary_raw else None
    structural_traits = _detect_etf_structural_traits(primary_raw, primary_data)
    structural_persona_html = _build_structural_persona_section(primary, structural_traits)

    return f"""
<h3 style="margin-top:40px;">👥 연령별 추천 포트폴리오 구성 및 운영 전략 ({primary} 기준)</h3>
<p style="color:#555;font-size:13px;">※ 아래 비중/수치는 이 글에서 계산된 {primary}의 실제 데이터를 참고한 예시이며, 실제 투자 금액은 개인의 소득·자산·목표에 따라 직접 정해야 합니다.</p>
<div style="margin-top:20px;padding:0;">

<div style="margin-bottom:20px;padding:18px;background:#f8f9fa;border-left:4px solid #3498db;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0;font-weight:bold;color:#2c3e50;font-size:15px;">📌 20~30대(장기자산 축적기, 30~40년 투자)</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;margin-top:15px;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:10px;">항목</th><th style="border:1px solid #ddd;padding:10px;">권장</th></tr>
{young_body}
<tr><td style="border:1px solid #ddd;padding:10px;"><strong>계좌 구성</strong></td><td style="border:1px solid #ddd;padding:10px;">{account_plan_text}</td></tr>
</table></div>
<p style="font-size:13px;color:#555;margin-top:12px;"><em>💡 전략: {young_strategy_note}</em></p>
</div>

<div style="margin-bottom:20px;padding:18px;background:#f8f9fa;border-left:4px solid #f39c12;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0;font-weight:bold;color:#2c3e50;font-size:15px;">📌 40대 (자산 적립 + 안정화기, 20~25년 투자)</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;margin-top:15px;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:10px;">항목</th><th style="border:1px solid #ddd;padding:10px;">권장</th></tr>
{mid_body}
<tr><td style="border:1px solid #ddd;padding:10px;"><strong>리밸런싱</strong></td><td style="border:1px solid #ddd;padding:10px;">목표 비중 대비 ±10%p 이상 벗어나면 조정 (분기별 점검 권장)</td></tr>
</table></div>
<p style="font-size:13px;color:#555;margin-top:12px;"><em>💡 전략: {mid_strategy_note}</em></p>
</div>

<div style="margin-bottom:20px;padding:18px;background:#f8f9fa;border-left:4px solid #9c27b0;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0;font-weight:bold;color:#2c3e50;font-size:15px;">📌 50대 (수익현금화기, 10~15년 투자)</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;margin-top:15px;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:10px;">항목</th><th style="border:1px solid #ddd;padding:10px;">권장</th></tr>
{old_body}
<tr><td style="border:1px solid #ddd;padding:10px;"><strong>매매 전략</strong></td><td style="border:1px solid #ddd;padding:10px;">변동성 제한, 보수적 운영</td></tr>
</table></div>
<p style="font-size:13px;color:#555;margin-top:12px;"><em>💡 전략: {old_strategy_note}</em></p>
</div>

</div>
{structural_persona_html}
"""


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


def _add_trading_timing_framework(macro_data, today_str, etf_list=None):
    """실시간 매매 타이밍 프레임.
    [중요] 이전 버전은 ETF 정보 없이 환율만으로 분기해, 환율 급변동이 있는 날엔
    그날 발행되는 모든 글에 진입전략/손절 문구가 토씨 하나 안 틀리고 동일하게
    삽입되는 문제가 있었음. 이 글이 다루는 티커를 문구에 반영하도록 수정."""
    etf_list = etf_list or []
    primary = etf_list[0].replace(".KS", "").replace(".US", "") if etf_list else "이 ETF"
    try:
        usdkrw_str = macro_data.get('usd_krw', '1250원')
        usdkrw = float(usdkrw_str.replace('원', '').replace(',', ''))
    except Exception:
        usdkrw = 1250.0
    
    html = f"""
<h3 style="margin-top:40px;">📈 {primary} 실시간 매매 타이밍 프레임</h3>
<p style="color:#555;">현재 환율({usdkrw:.0f}원) 기준, 지금({today_str}) {primary}의 최적 진입 전략</p>

<div style="margin-top:20px;padding:18px;background:#f8f9fa;border-left:4px solid #1abc9c;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0 0 15px 0;font-weight:bold;color:#16a085;font-size:15px;">✅ 현재 환율 평가</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:10px;">기준점</th><th style="border:1px solid #ddd;padding:10px;">평가</th><th style="border:1px solid #ddd;padding:10px;">권장도</th></tr>
"""
    if usdkrw < 1200:
        html += """<tr><td style="border:1px solid #ddd;padding:10px;">환율 1,200원 이하</td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#c0392b;font-weight:bold;">절호의 기회</span></td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#c0392b;">강력 매수 ⭐⭐⭐⭐⭐</span></td></tr>"""
    elif usdkrw < 1250:
        html += """<tr><td style="border:1px solid #ddd;padding:10px;">환율 1,200~1,250원</td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#f39c12;">적정 수준</span></td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#f39c12;">중간 매수 ⭐⭐⭐</span></td></tr>"""
    elif usdkrw < 1350:
        html += """<tr><td style="border:1px solid #ddd;padding:10px;">환율 1,250~1,350원</td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#e67e22;">높은 수준</span></td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#e67e22;">신중한 매수 ⭐⭐</span></td></tr>"""
    else:
        html += """<tr><td style="border:1px solid #ddd;padding:10px;">환율 1,350원 이상</td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#2166ac;">위험 수준</span></td><td style="border:1px solid #ddd;padding:10px;"><span style="color:#2166ac;">관찰 모드 ⭐</span></td></tr>"""
    
    html += f"""
</table></div>
</div>

<div style="margin-top:20px;padding:18px;background:#f8f9fa;border-left:4px solid #f39c12;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0 0 15px 0;font-weight:bold;color:#d68910;font-size:15px;">📊 {primary} 진입 전략</p>
<ul style="font-size:14px;margin:0;padding-left:20px;line-height:1.8;">
<li><strong>거치식(일시 매수)</strong>: 계획한 투자금 전액을 한 번에 매수<br/>→ 평균적으로는 나쁘지 않은 방법이지만, 완벽한 타이밍을 노리다 기회를 놓치는 경우가 더 흔합니다.</li>
<li><strong>분할매수(DCA)</strong>: 계획한 투자금을 여러 달에 걸쳐 나누어 매수<br/>→ 평단가 안정, 심리적 부담 완화, 변동성이 큰 자산일수록 유리</li>
<li><strong>추천</strong>: 본인의 자금 사정과 이 ETF의 변동성을 고려해 분할 매수 기간을 정하고, 정기적으로 자동이체 설정</li>
</ul>
</div>

<div style="margin-top:20px;padding:18px;background:#f8f9fa;border-left:4px solid #e74c3c;border-radius:6px;border-top:1px solid #eee;border-right:1px solid #eee;border-bottom:1px solid #eee;">
<p style="margin:0 0 15px 0;font-weight:bold;color:#c0392b;font-size:15px;">⚠️ {primary} 손절/리밸런싱</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:10px;">상황</th><th style="border:1px solid #ddd;padding:10px;">액션</th></tr>
<tr><td style="border:1px solid #ddd;padding:10px;">환율 1,400원 이상</td><td style="border:1px solid #ddd;padding:10px;">기존 {primary} 보유분의 일부를 분할 정산해 수익 실현 검토</td></tr>
<tr><td style="border:1px solid #ddd;padding:10px;">{primary} 평가손실 확대</td><td style="border:1px solid #ddd;padding:10px;">이 ETF의 과거 MDD 수준을 감안해 감내 가능한 범위인지 재점검 (즉시 손절보다는 원래 투자 이유가 유효한지 우선 확인)</td></tr>
<tr><td style="border:1px solid #ddd;padding:10px;">정기 점검 시점(예: 연초)</td><td style="border:1px solid #ddd;padding:10px;">목표 자산배분 비중 대비 실제 비중이 크게 벗어났다면 리밸런싱</td></tr>
</table></div>
</div>

<p style="font-size:13px;color:#888;margin-top:20px;line-height:1.6;">
<em>💡 핵심: "시장 타이밍은 불가능하다" (전설의 투자자들의 합의).<br/>
{primary}도 마찬가지로 "꾸준한 매수 + 리밸런싱 + 심리 안정"의 조합이 높은 수익률을 만든다.</em>
</p>
"""
    return html


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


def _build_revision_history_section(previous_analyses, etf_data_cache, today_str):
    """[신규] "정정 이력" 섹션 - AI 서술에만 맡기지 않고, 코드가 직접 계산한
    명시적인 "이전 분석 대비 실제 변화" 표를 만든다. "예측이 맞았다/틀렸다"가
    아니라 "실제 수치가 이렇게 바뀌었다"는 객관적 사실만 다룬다(이 코드는
    예측을 하지 않는 구조이므로 예측 적중 여부를 다루는 건 애초에 맞지 않음).

    반드시 etf_data_cache가 완전히 채워진 뒤(모든 ETF 데이터 수집이 끝난 뒤)에
    호출해야 한다. 이전 분석 기록이 없으면 빈 문자열을 반환해 섹션 자체가
    조용히 생략된다(첫 분석 글에는 당연히 표시할 게 없음).
    """
    revision_blocks = []
    for ticker_clean, analysis in previous_analyses.items():
        if not analysis.get('previous'):
            continue
        prev = analysis['previous']
        past_data = None
        for key, val in prev.get('etf_data', {}).items():
            if ticker_clean in key:
                past_data = val
                break
        if not past_data:
            continue

        current_data = etf_data_cache.get(ticker_clean) or next(
            (v for k, v in etf_data_cache.items() if ticker_clean in k), None
        )
        if not current_data:
            continue

        past_yield = past_data.get('yield', '기록 없음')
        past_mdd = past_data.get('mdd', '기록 없음')
        past_1y_ret = past_data.get('returns', {}).get('1년', '기록 없음')
        if isinstance(past_1y_ret, float):
            past_1y_ret = f"{past_1y_ret:.2f}%"

        cur_yield = current_data.get('yield', '정보 없음')
        cur_mdd = current_data.get('mdd', '정보 없음')
        cur_1y_ret = current_data.get('returns', {}).get('1년')
        cur_1y_ret_str = f"{cur_1y_ret:.2f}%" if isinstance(cur_1y_ret, (int, float)) else "정보 없음"

        revision_blocks.append(f"""
<div style="margin-bottom:16px;padding:14px;background:#fff;border:1px solid #e0e0e0;border-radius:6px;">
<p style="margin:0 0 8px 0;font-weight:bold;color:#2c3e50;">{ticker_clean} — {prev['date_display']} 분석 대비 변화</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<tr style="background:#f1f5f9;"><th style="border:1px solid #ddd;padding:6px;">지표</th><th style="border:1px solid #ddd;padding:6px;">{prev['date_display']} (v{prev['version']})</th><th style="border:1px solid #ddd;padding:6px;">{today_str} (현재)</th></tr>
<tr><td style="border:1px solid #ddd;padding:6px;">배당수익률</td><td style="border:1px solid #ddd;padding:6px;">{past_yield}</td><td style="border:1px solid #ddd;padding:6px;">{cur_yield}</td></tr>
<tr><td style="border:1px solid #ddd;padding:6px;">최대낙폭(MDD)</td><td style="border:1px solid #ddd;padding:6px;">{past_mdd}</td><td style="border:1px solid #ddd;padding:6px;">{cur_mdd}</td></tr>
<tr><td style="border:1px solid #ddd;padding:6px;">1년 수익률</td><td style="border:1px solid #ddd;padding:6px;">{past_1y_ret}</td><td style="border:1px solid #ddd;padding:6px;">{cur_1y_ret_str}</td></tr>
</table>
</div>
""")

    if not revision_blocks:
        return ""  # 이전 분석 기록이 없으면(첫 분석) 섹션 자체를 생략

    return f"""
<div style="margin-top:24px;padding:18px;background:#f4f6f8;border-radius:8px;">
<p style="margin:0 0 14px 0;font-weight:bold;color:#2c3e50;font-size:15px;">📋 이전 분석 대비 실제 데이터 변화</p>
{"".join(revision_blocks)}
<p style="margin:10px 0 0 0;font-size:12px;color:#888;">※ 이 표는 예측의 적중 여부가 아니라, 이전 분석 시점과 현재 시점의 실제 수치 변화를 그대로 보여드리는 것입니다.</p>
</div>
"""


def _add_fee_comparison_table(etf_data_cache, principal=100_000_000):
    """실제 CAGR 기반 계좌별 실수료 비교표.
    [중요] 이전에는 모든 ETF에 "과세계좌=매년 배당 15.4% 세금"을 고정으로
    표시했는데, IBIT처럼 배당을 지급하지 않는 ETF는 배당소득세가 애초에
    발생하지 않고, 대신 매매차익에 대한 양도소득세(해외 ETF는 22%)가
    적용된다. 이 구분이 없어서 실제로 "IBIT는 배당이 없다고 앞서 명시했는데
    왜 배당세를 매기냐"는 치명적 모순으로 검수에서 지적된 사례가 확인됨.
    지금은 배당 여부가 아니라 상장 위치로 나눈다: 해외 상장 ETF는 ISA·연금
    계좌로 살 수 없어서(예전 글에서 사실 오류로 나갔음), 그 계좌들은 같은
    지수의 국내 상장 ETF를 산다는 대안으로만 비교한다."""
    html = '<h3 style="margin-top:30px;">💰 계좌별 실수료 비교: 1억 원 투자 시 실제 비용</h3>'

    # 대표 ETF(첫 번째)가 해외 상장인지에 따라 비교할 계좌 자체가 달라진다.
    # 해외 상장 ETF는 ISA/연금저축/IRP로 직접 살 수 없으므로, 그 계좌들은
    # "같은 지수를 추종하는 국내 상장 ETF를 산다면"이라는 대안으로만 보여준다.
    primary_d = next(iter(etf_data_cache.values()), {})
    overseas = _is_overseas_listed(primary_d)

    if overseas:
        html += f'<p style="color:#555;">{OVERSEAS_ACCOUNT_NOTE} 아래 표는 직접 투자와, 같은 지수의 국내 상장 ETF를 계좌별로 샀을 때를 비교합니다.</p>'
    else:
        html += '<p style="color:#555;">같은 ETF라도 어떤 계좌로 사느냐에 따라 세금 부담이 크게 달라집니다.</p>'
    html += '''
<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:15px;">
<tr style="background:#f0f7ff;">
<th style="border:1px solid #ddd;padding:12px;text-align:center;">계좌 유형</th>
<th style="border:1px solid #ddd;padding:12px;text-align:center;">세금 부담</th>
<th style="border:1px solid #ddd;padding:12px;text-align:center;">운용보수<br/>(10년 누적)</th>
<th style="border:1px solid #ddd;padding:12px;text-align:center;">총 비용</th>
<th style="border:1px solid #ddd;padding:12px;text-align:center;">실제 수익률</th>
</tr>
'''
    avg_expense_ratio = 0
    count = 0
    cagrs = []
    for d in etf_data_cache.values():
        if d.get('expense_ratio'):
            try:
                ratio = float(d['expense_ratio'].replace('%', ''))
                avg_expense_ratio += ratio
                count += 1
            except Exception:
                pass
        # [수정] 기본값 8%로 채우지 않고, 실제로 계산된 cagr만 모음.
        # 전부 계산 실패한 경우에만(cagrs가 비었을 때) 아래에서 8%를 최후의
        # fallback으로 쓰되, 이 경우 표에 "추정치" 성격임을 명시해야 함.
        if d.get('cagr') is not None:
            cagrs.append(d['cagr'])

    avg_expense_ratio = avg_expense_ratio / count if count > 0 else 0.1
    annual_return = sum(cagrs) / len(cagrs) if cagrs else 0.08
    used_estimated_return = not cagrs  # 실제 데이터가 하나도 없어 8% 추정치를 쓴 경우
    
    future_value = principal * (1 + annual_return) ** 10

    def _overseas_direct_tax(gain):
        return max(0.0, gain - OVERSEAS_CG_DEDUCTION) * TAX_OVERSEAS_CAPITAL_GAINS

    def _isa_tax(gain):
        return max(0.0, gain - ISA_TAX_FREE_LIMIT) * ISA_SEPARATE_TAX

    def _general_tax(gain):
        return gain * TAX_DOMESTIC_DIVIDEND

    def _pension_tax(gain):
        return gain * PENSION_TAX

    alt = "국내 상장 같은 지수 ETF"
    if overseas:
        accounts = [
            {"name": "해외 직접투자(일반계좌)", "rate_label": "22%", "tax_timing": "250만 원 공제 후 매매차익", "color": "#2166ac", "tax_fn": _overseas_direct_tax},
            {"name": f"{alt}(일반계좌)", "rate_label": "15.4%", "tax_timing": "매매차익·분배금", "color": "#7f8c8d", "tax_fn": _general_tax},
            {"name": f"{alt}(ISA)", "rate_label": "9.9%", "tax_timing": "200만 원 초과분", "color": "#c0392b", "tax_fn": _isa_tax},
            {"name": f"{alt}(연금저축/IRP)", "rate_label": "3.3~5.5%", "tax_timing": "연금 수령 시", "color": "#f39c12", "tax_fn": _pension_tax},
        ]
    else:
        accounts = [
            {"name": "일반계좌", "rate_label": "15.4%", "tax_timing": "매매차익·분배금", "color": "#2166ac", "tax_fn": _general_tax},
            {"name": "ISA", "rate_label": "9.9%", "tax_timing": "200만 원 초과분", "color": "#c0392b", "tax_fn": _isa_tax},
            {"name": "연금저축/IRP", "rate_label": "3.3~5.5%", "tax_timing": "연금 수령 시", "color": "#f39c12", "tax_fn": _pension_tax},
        ]

    # [신규] 연령별 포트폴리오 가이드 등 다른 섹션에서 "이 ETF 기준 계좌별 실질
    # 수익률 차이"를 직접 인용할 수 있도록, 계좌별 actual_return을 함께 반환한다.
    account_returns = {}
    
    for account in accounts:
        annual_fee = principal * (avg_expense_ratio / 100)
        total_fee_10y = sum([annual_fee * (1 + annual_return) ** i for i in range(10)])
        gain = future_value - principal
        tax_amount = account['tax_fn'](gain)
        total_cost = total_fee_10y + tax_amount
        net_value = future_value - total_cost
        actual_return = ((net_value / principal) ** (1/10) - 1) * 100

        account_returns[account['name']] = round(actual_return, 2)
        
        html += f'''
<tr>
<td style="border:1px solid #ddd;padding:12px;text-align:center;font-weight:bold;color:{account['color']};">{account['name']}</td>
<td style="border:1px solid #ddd;padding:12px;text-align:center;">
    <span style="color:{account['color']};font-weight:bold;">{account['rate_label']}</span><br/>
    <span style="font-size:10px;color:#666;">{account['tax_timing']}</span>
</td>
<td style="border:1px solid #ddd;padding:12px;text-align:center;">
    <span style="color:#e67e22;font-weight:bold;">{total_fee_10y:,.0f}원</span><br/>
    <span style="font-size:10px;color:#666;">(연 {avg_expense_ratio:.2f}%)</span>
</td>
<td style="border:1px solid #ddd;padding:12px;text-align:center;">
    <span style="color:#2166ac;font-weight:bold;">{total_cost:,.0f}원</span>
</td>
<td style="border:1px solid #ddd;padding:12px;text-align:center;">
    <span style="color:#c0392b;font-weight:bold;">{actual_return:.1f}%</span>
</td>
</tr>
'''
    html += '</table>'
    return_basis_note = "예시 추정치 (실제 과거 데이터 확보 실패)" if used_estimated_return else "과거 실제 데이터 반영"
    html += f'''
<p style="font-size:11px;color:#888;margin-top:15px;line-height:1.6;">
<strong>💡 계산 기준:</strong><br/>
- 투자원금: 1억 원<br/>
- 연 수익률: {annual_return*100:.1f}% ({return_basis_note})<br/>
- 운용보수: ETF 평균 {avg_expense_ratio:.2f}% 적용<br/>
- 세금: {TAX_RULES_BASIS}, 10년 뒤 한 번에 매도한다고 단순 가정 (연금은 최고 세율 5.5% 적용)<br/>
- ISA는 연 2,000만 원 납입 한도가 있어 1억 원을 한 번에 넣을 수 없습니다. 세율 차이를 보여주기 위한 비교입니다.<br/>
- 국내 주식형 ETF의 매매차익은 일반계좌에서도 비과세라, 그 경우 일반계좌 세금은 이보다 적습니다.<br/>
</p>
'''
    tax_comparison_result = {
        "principal": principal,
        "annual_return_pct": round(annual_return * 100, 2),
        "avg_expense_ratio_pct": round(avg_expense_ratio, 2),
        "account_returns": account_returns,  # 예: {"과세계좌": 10.1, "ISA 계좌": 11.3, "IRP/연금저축": 10.8}
    }
    return html, tax_comparison_result


def _add_calculator_widget():
    """자동 투자 계산기 위젯 (사용자 입력 → 실시간 계산)"""
    html = '''
<div style="margin:30px 0;padding:20px;border:1px solid #e9ecef;border-radius:8px;background:#f8f9fa;">
<h3 style="margin:0 0 15px 0;color:#333;">🧮 ETF 투자 수익 계산기</h3>
<p style="margin:0 0 15px 0;font-size:13px;color:#666;">원하는 투자금액과 기간을 입력하면 예상 수익을 계산해드립니다.</p>

<div style="display:flex;flex-wrap:wrap;gap:15px;margin-bottom:15px;">
<div style="flex:1;min-width:200px;">
<label style="display:block;font-weight:bold;margin-bottom:5px;color:#333;">투자금액 (원)</label>
<input type="number" id="calc_investment" value="10000000" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;">
</div>
<div style="flex:1;min-width:200px;">
<label style="display:block;font-weight:bold;margin-bottom:5px;color:#333;">연간 수익률 (%)</label>
<input type="number" id="calc_return" value="8" step="0.1" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;">
</div>
<div style="flex:1;min-width:200px;">
<label style="display:block;font-weight:bold;margin-bottom:5px;color:#333;">투자 기간 (년)</label>
<input type="number" id="calc_years" value="10" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;">
</div>
</div>

<button onclick="calculateReturns()" style="background:#007bff;color:white;border:none;padding:10px 20px;border-radius:4px;cursor:pointer;font-weight:bold;">계산하기</button>

<div id="calc_results" style="margin-top:20px;padding:15px;background:white;border-radius:4px;display:none;">
<h4 style="margin:0 0 10px 0;color:#333;">📊 계산 결과</h4>
<div id="calc_output"></div>
</div>

<script>
function calculateReturns() {
    const investment = parseFloat(document.getElementById('calc_investment').value);
    const annualReturn = parseFloat(document.getElementById('calc_return').value) / 100;
    const years = parseInt(document.getElementById('calc_years').value);
    
    if (investment <= 0 || annualReturn < 0 || years <= 0) {
        alert('올바른 값을 입력해주세요.');
        return;
    }
    
    const futureValue = investment * Math.pow(1 + annualReturn, years);
    const totalReturn = futureValue - investment;
    const totalReturnPercent = ((futureValue / investment - 1) * 100);
    
    const output = `
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <tr style="background:#f8f9fa;">
        <th style="border:1px solid #ddd;padding:8px;text-align:left;">항목</th>
        <th style="border:1px solid #ddd;padding:8px;text-align:right;">금액</th>
        </tr>
        <tr>
        <td style="border:1px solid #ddd;padding:8px;">최종 금액</td>
        <td style="border:1px solid #ddd;padding:8px;text-align:right;font-weight:bold;color:#c0392b;">${futureValue.toLocaleString()}원</td>
        </tr>
        <tr>
        <td style="border:1px solid #ddd;padding:8px;">총 수익</td>
        <td style="border:1px solid #ddd;padding:8px;text-align:right;font-weight:bold;color:#c0392b;">${totalReturn.toLocaleString()}원</td>
        </tr>
        <tr>
        <td style="border:1px solid #ddd;padding:8px;">총 수익률</td>
        <td style="border:1px solid #ddd;padding:8px;text-align:right;font-weight:bold;color:#c0392b;">${totalReturnPercent.toFixed(1)}%</td>
        </tr>
        <tr>
        <td style="border:1px solid #ddd;padding:8px;">연평균 수익률</td>
        <td style="border:1px solid #ddd;padding:8px;text-align:right;">${annualReturn*100}%</td>
        </tr>
        </table>
        <p style="margin:10px 0 0 0;font-size:12px;color:#666;">
        * 세금, 수수료 등은 고려하지 않은 단순 계산 결과입니다.
        </p>
    `;
    
    document.getElementById('calc_output').innerHTML = output;
    document.getElementById('calc_results').style.display = 'block';
}
</script>
</div>
'''
    return html


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


def _add_temporal_markers(today_str):
    """거시경제 환경별 투자 나침반"""
    return f'''
<div style="margin:30px 0;padding:20px;border:1px solid #e9ecef;border-radius:8px;background:#f8f9fa;">
<h3 style="margin:0 0 15px 0;color:#333;">🧭 거시경제 환경별 투자 나침반</h3>
<p style="margin:0 0 15px 0;font-size:13px;color:#666;">시장 환경 변화에 따른 확실한 대응 매뉴얼을 정리했습니다. ({today_str} 기준)</p>
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#e9ecef;"><th style="border:1px solid #ddd;padding:10px;">시나리오</th><th style="border:1px solid #ddd;padding:10px;">시장 반응</th><th style="border:1px solid #ddd;padding:10px;">대응 전략</th></tr>
<tr style="background:#fff;"><td style="border:1px solid #ddd;padding:10px;font-weight:bold;color:#2166ac;">금리 인상</td><td style="border:1px solid #ddd;padding:10px;">성장주 밸류에이션 부담 증가</td><td style="border:1px solid #ddd;padding:10px;">방어주, 고배당 ETF 비중 확대</td></tr>
<tr style="background:#f8f9fa;"><td style="border:1px solid #ddd;padding:10px;font-weight:bold;color:#c0392b;">금리 인하</td><td style="border:1px solid #ddd;padding:10px;">유동성 유입, 기술주 강세</td><td style="border:1px solid #ddd;padding:10px;">지수 추종 주식 비중 확대</td></tr>
<tr style="background:#fff;"><td style="border:1px solid #ddd;padding:10px;font-weight:bold;color:#e67e22;">환율 급등</td><td style="border:1px solid #ddd;padding:10px;">해외 직투 및 환노출(UH) 환차익</td><td style="border:1px solid #ddd;padding:10px;">환차익 익절 및 신규 환헤지(H) 고려</td></tr>
<tr style="background:#f8f9fa;"><td style="border:1px solid #ddd;padding:10px;font-weight:bold;color:#1f3c88;">환율 하락</td><td style="border:1px solid #ddd;padding:10px;">환노출 상품 수익률 감소</td><td style="border:1px solid #ddd;padding:10px;">달러 저점 매수 기회, 환노출(UH) 확대</td></tr>
</table>
</div>
'''


def _add_counter_arguments(etf_data_cache, macro_data):
    """실제 데이터 기반 반박 및 리스크 섹션 (단일 종목 시 경쟁사 MDD 비교 포함)"""
    html = '<h3 style="margin-top:30px;">⚖️ 투자 전 반드시 확인해야 할 리스크</h3>'
    html += '<p style="color:#555;">모든 투자는 장점만 존재하지 않습니다. 이 ETF의 구조적 단점과 리스크를 짚어봅니다.</p>'
    
    primary_etf = list(etf_data_cache.values())[0]
    # [수정] primary_etf(딕셔너리 값) 안에는 'ticker' 키가 존재하지 않아 항상
    # fallback인 'UNKNOWN'으로 떨어지고 있었음. 그 결과 아래 endswith('.KS')/
    # isdigit() 체크가 항상 실패해 한국 ETF의 경쟁사 MDD 비교 기능이 절대
    # 작동하지 않는 버그였음. etf_data_cache의 실제 키(티커)를 사용하도록 수정.
    # raw_ticker는 .KS 포함 원본(한국/미국 판별용), ticker는 화면 표시용 정제본.
    raw_ticker = list(etf_data_cache.keys())[0]
    ticker = raw_ticker.replace('.KS', '').replace('.US', '')
    mdd = primary_etf.get('mdd', '데이터 없음')
    expense = primary_etf.get('expense_ratio', 'N/A')

    # --- 단일 종목 입력 시에만 MDD 비교용 문구 생성 ---
    mdd_comparison_text = ""
    if len(etf_data_cache) == 1:
        us_comp = {"QQQ": "QQQM", "QQQM": "QQQ", "SPY": "VOO", "VOO": "IVV", "IVV": "SPY", "VTI": "ITOT", "ITOT": "VTI", "SCHD": "VYM", "VYM": "SCHD"}
        kr_comp = {"069500": "122630", "122630": "069500", "133690": "379810", "379810": "133690", "360750": "379800", "379800": "360750"}
        
        comp_ticker = None
        base_ticker = ticker
        
        if raw_ticker.endswith(".KS") or ticker.isdigit():
            base_ticker = ticker
            if base_ticker in kr_comp:
                comp_ticker = kr_comp[base_ticker] + ".KS"
        else:
            if base_ticker in us_comp:
                comp_ticker = us_comp[base_ticker]

        if comp_ticker:
            try:
                comp_obj = yf.Ticker(comp_ticker)
                comp_hist = comp_obj.history(period="5y")
                if not comp_hist.empty:
                    comp_roll_max = comp_hist['Close'].cummax()
                    comp_mdd = (comp_hist['Close'] / comp_roll_max - 1.0).min() * 100
                    mdd_comparison_text = f" 참고로 동일/유사 지수를 추종하는 경쟁 ETF인 {comp_ticker.replace('.KS','')}의 최근 5년 MDD는 {comp_mdd:.2f}% 수준입니다."
            except Exception:
                pass
    # ---------------------------------------------------
    
    counter_points = []
    if macro_data.get('is_fx_volatile'):
        diff_pct = macro_data.get('usd_krw_diff_pct', 0)
        direction = macro_data.get('usd_krw_direction', '')
        counter_points.append({
            "title": f"환율 급변동 리스크 (전일 대비 {diff_pct:.2f}% {direction})",
            "description": f"현재 환율이 전일 대비 {diff_pct:.2f}% {direction}하며 변동성이 커진 상태입니다. 환노출(UH) 상품의 경우 원화 가치 변동에 따른 환차손 리스크를 반드시 점검해야 합니다.",
            "evidence": f"전일 대비 {diff_pct:.2f}% {direction} 발생",
            "mitigation": "포트폴리오 내 분산 및 환헤지(H) 상품 혼합 고려"
        })
    counter_points.extend([
        {"title": "운용보수 및 숨은 비용", "description": "공시된 운용보수 외에 기타비용, 매매중개수수료가 추가 발생합니다.", "evidence": f"공시 보수({expense})와 실제 부담하는 총비용(TER)은 차이가 존재함.", "mitigation": "금융투자협회 공시를 통해 '실부담비용' 정기 확인"},
        {"title": "과거 최대 낙폭(MDD) 경고", "description": "시장 위기 시 큰 폭의 자산 감소를 감내해야 합니다.", "evidence": f"이 ETF의 최근 5년 최대 낙폭(MDD)은 {mdd} 수준입니다.{mdd_comparison_text}", "mitigation": "DCA(적립식 분할매수)를 통한 매입 단가 평준화"}
    ])
    
    for i, point in enumerate(counter_points, 1):
        html += f'''
<div style="margin:20px 0;padding:15px;border:1px solid #f5c6cb;border-radius:8px;background:#f8d7da;">
<h4 style="margin:0 0 10px 0;color:#721c24;">{i}. {point['title']}</h4>
<p style="margin:0 0 8px 0;font-size:13px;color:#721c24;"><strong>문제점:</strong> {point['description']}</p>
<p style="margin:0 0 8px 0;font-size:12px;color:#721c24;"><strong>실제 사례:</strong> {point['evidence']}</p>
<p style="margin:0 0 0 0;font-size:12px;color:#155724;"><strong>대응 방안:</strong> {point['mitigation']}</p>
</div>
'''
    return html


def _add_economic_cycle_analysis(macro_data, etf_list=None, etf_data_cache=None):
    """경제 사이클별 투자 전략 분석.
    [중요] 이전 버전은 매크로 지표로만 분기해 표/조언 박스가 어떤 ETF 글이든,
    같은 날 발행되는 모든 글에 사실상 100% 동일하게 삽입되는 문제가 있었음.
    지금은 이 글이 다루는 ETF의 실제 자산군(주식/채권/금 등)에 맞춰
    전략 문구와 조언이 달라지도록 함."""
    etf_list = etf_list or []
    etf_data_cache = etf_data_cache or {}

    def _clean(t):
        return t.replace(".KS", "").replace(".US", "")

    primary = _clean(etf_list[0]) if etf_list else "이 ETF"
    # 이 ETF의 섹터/자산군 정보로 조언 문구를 다르게 구성
    sector_hint = ""
    for ticker, d in etf_data_cache.items():
        if _clean(ticker) == primary:
            sector_hint = d.get('sector', '') or d.get('industry', '')
            break

    html = f'<h3 style="margin-top:30px;">📈 경제 사이클에 따른 {primary} 투자 전략</h3>'
    if sector_hint:
        html += f'<p style="color:#555;">{primary}({sector_hint} 자산군)의 특성을 고려해 현재 경제 상황에 맞는 전략을 제시합니다.</p>'
    else:
        html += f'<p style="color:#555;">{primary}의 특성을 고려해 현재 경제 상황에 맞는 전략을 제시합니다.</p>'
    
    # 현재 경제 상황 분석
    usd_krw = float(macro_data.get('usd_krw', '1300원').replace('원', '').replace(',', ''))
    us_10y = float(macro_data.get('us_10y', '4.0%').replace('%', ''))
    fear_greed = macro_data.get('fear_greed', '중립')
    
    # 경제 사이클 판정
    # [수정] fear_greed 값은 실제로 "31점 (공포)"처럼 한글로 저장되는데,
    # 이전에는 'Greed'/'Neutral'/'Fear' 같은 영어 단어로 매칭을 시도해서
    # 이 조건이 항상 거짓으로 평가되고 있었음 - 즉 공포/탐욕 지수가 실질적으로
    # 판정에 전혀 반영되지 않고 환율/금리만으로 사이클이 결정되던 버그.
    if usd_krw < 1200 and us_10y < 3.5 and ('탐욕' in fear_greed):
        current_cycle = "호황기"
        current_color = "#c0392b"
        strategy = "공격적 투자"
    elif usd_krw < 1300 and us_10y < 4.5 and '중립' in fear_greed:
        current_cycle = "안정기" 
        current_color = "#ffc107"
        strategy = "중립적 투자"
    elif usd_krw > 1400 or us_10y > 5.0 or '공포' in fear_greed:
        current_cycle = "불황기"
        current_color = "#2166ac"
        strategy = "방어적 투자"
    else:
        current_cycle = "전환기"
        current_color = "#6c757d"
        strategy = "관망 모드"
    
    html += f'''
<div style="margin:15px 0;padding:20px;border:2px solid {current_color};border-radius:8px;background:#f8f9fa;">
<h4 style="margin:0 0 10px 0;color:{current_color};">현재 경제 사이클: {current_cycle}</h4>
<p style="margin:0 0 10px 0;font-size:14px;">
<strong>{primary}에 대한 추천 전략: <span style="color:{current_color};font-size:16px;">{strategy}</span></strong>
</p>
<p style="margin:0 0 10px 0;font-size:13px;">
현재 환율({usd_krw:.0f}원), 금리({us_10y:.1f}%), 시장 심리({fear_greed})를 종합 분석한 결과입니다.
</p>
</div>

<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:20px;">
<tr style="background:#e9ecef;">
<th style="border:1px solid #ddd;padding:12px;">경제 사이클</th>
<th style="border:1px solid #ddd;padding:12px;">특징</th>
<th style="border:1px solid #ddd;padding:12px;">{primary} 대응 전략</th>
<th style="border:1px solid #ddd;padding:12px;">리스크 관리</th>
</tr>
'''
    
    cycles = [
        {
            "name": "호황기",
            "features": "저환율, 저금리, 탐욕지수 높음",
            "strategy": f"{primary} 비중 확대 검토",
            "risk": "거품 형성 주의, 차익 실현 고려",
            "color": "#c0392b"
        },
        {
            "name": "안정기",
            "features": "적정 환율, 안정 금리, 중립 심리",
            "strategy": f"{primary} 비중 유지",
            "risk": "시장 변동성 대비, 분산 투자",
            "color": "#ffc107"
        },
        {
            "name": "불황기",
            "features": "고환율, 고금리, 공포지수 높음",
            "strategy": f"{primary} 비중 축소 검토",
            "risk": "현금 비중 확대, 안전 자산 선호",
            "color": "#2166ac"
        },
        {
            "name": "전환기",
            "features": "불확실성 높음, 방향성 모호",
            "strategy": f"{primary} 비중 관망",
            "risk": "단기 매매 자제, 장기적 관점",
            "color": "#6c757d"
        }
    ]

    for cycle in cycles:
        highlight = "background:#fff3cd;" if cycle['name'] == current_cycle else ""
        html += f'''
<tr style="{highlight}">
<td style="border:1px solid #ddd;padding:12px;font-weight:bold;color:{cycle['color']};">{cycle['name']}</td>
<td style="border:1px solid #ddd;padding:12px;">{cycle['features']}</td>
<td style="border:1px solid #ddd;padding:12px;">{cycle['strategy']}</td>
<td style="border:1px solid #ddd;padding:12px;">{cycle['risk']}</td>
</tr>
'''

    html += '</table>'
    html += f'<p style="font-size:12px;color:#888;margin-top:10px;">※ 구체적인 비중 조정 폭은 {primary}의 실제 변동성(MDD)과 본인의 위험 감내 수준에 따라 달라집니다. 위 표는 방향성 참고용입니다.</p>'

    html += f'''
<div style="margin:20px 0;padding:15px;border:1px solid #d1ecf1;border-radius:8px;background:#d1ecf1;">
<h4 style="margin:0 0 10px 0;color:#0c5460;">🎯 {primary} 투자자를 위한 현재 상황별 조언</h4>
<ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.6;color:#0c5460;">
<li><strong>단기(1-3개월):</strong> {primary} 단기 변동성에 흔들리지 말고 계획된 전략 유지</li>
<li><strong>중기(3-12개월):</strong> 경제 지표 변화에 따라 {primary} 비중 조정 고려</li>
<li><strong>장기(1년+):</strong> 시간의 힘을 믿고 {primary} 꾸준한 투자 지속</li>
<li><strong>리스크 관리:</strong> 분산 투자 + 리밸런싱 + 현금 비중 적절히 유지</li>
</ul>
</div>
'''

    return html


def _add_virtual_portfolio_showcase(etf_list, driver):
    """가상 포트폴리오 공개 (실제 데이터 가중평균 기반).
    [중요] 이 섹션은 "여러 ETF를 조합했을 때의 포트폴리오 수익률"을 보여주는
    것이 목적인데, ETF가 1개뿐이면 그 ETF의 수익률과 100% 동일한 값이
    "포트폴리오 수익률"이라는 이름으로 그대로 반복될 뿐이라 실질적 정보가
    없다(이미 다른 섹션에서 같은 수익률을 다룸). 호출부에서 etf_list가 2개
    이상일 때만 이 함수를 부르도록 해야 하며, 이 함수 자체도 안전장치로
    1개 이하면 빈 문자열을 반환한다."""
    if not etf_list or len(etf_list) < 2:
        return ""

    html = '<h3 style="margin-top:30px;">📊 내 가상 포트폴리오 현황 (실제 데이터 기반)</h3>'
    html += '<p style="color:#555;">분석 대상 ETF들을 동일 비중으로 조합했을 때의 실제 과거 수익률입니다.</p>'
    
    portfolio = {}
    weight = round(100.0 / len(etf_list), 2) if etf_list else 100.0
    for t in etf_list:
        ticker_clean = t.replace(".KS", "").replace(".US", "")
        portfolio[ticker_clean] = weight
    
    html += '<div style="margin:15px 0;padding:15px;background:#f8f9fa;border-radius:8px;">'
    html += '<h4 style="margin:0 0 10px 0;color:#333;">포트폴리오 구성</h4>'
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
    html += '<tr style="background:#e9ecef;"><th style="border:1px solid #ddd;padding:8px;">종목</th><th style="border:1px solid #ddd;padding:8px;">비중</th><th style="border:1px solid #ddd;padding:8px;">현재가(약)</th></tr>'
    
    total_invested = 0
    port_ret = {'1개월': 0.0, '3개월': 0.0, '6개월': 0.0, '1년': 0.0}
    
    for ticker, w in portfolio.items():
        try:
            stock = yf.Ticker(ticker)
            avg_price = stock.fast_info['last_price']
        except Exception:
            avg_price = 0.0

        invested = 10_000_000 * (w / 100)
        total_invested += invested
        html += f'<tr><td style="border:1px solid #ddd;padding:8px;font-weight:bold;">{ticker}</td><td style="border:1px solid #ddd;padding:8px;text-align:center;">{w}%</td><td style="border:1px solid #ddd;padding:8px;text-align:right;">${avg_price:.2f}</td></tr>'
    
    cache = _load_cache()
    for ticker, w in portfolio.items():
        for orig_t, cached_data in cache.items():
            if orig_t.replace(".KS", "").replace(".US", "") == ticker:
                real_data = cached_data.get('data', {}).get('returns', {})
                port_ret['1개월'] += real_data.get('1개월', 0) * (w / 100)
                port_ret['3개월'] += real_data.get('3개월', 0) * (w / 100)
                port_ret['6개월'] += real_data.get('6개월', 0) * (w / 100)
                port_ret['1년'] += real_data.get('1년', 0) * (w / 100)
                break

    html += '''
<div style="margin:15px 0;padding:15px;background:#e8f5e8;border:1px solid #d4edda;border-radius:8px;">
<h4 style="margin:0 0 10px 0;color:#155724;">💰 성과 요약 (실제 데이터 가중평균)</h4>
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#d4edda;"><th style="border:1px solid #ddd;padding:8px;">기간</th><th style="border:1px solid #ddd;padding:8px;">포트폴리오 수익률</th></tr>
'''
    for period in ['1개월', '3개월', '6개월', '1년']:
        val = port_ret[period]
        color = "#c0392b" if val >= 0 else "#2166ac"
        sign = "+" if val > 0 else ""
        html += f'<tr><td style="border:1px solid #ddd;padding:8px;text-align:center;">{period}</td><td style="border:1px solid #ddd;padding:8px;text-align:center;color:{color};font-weight:bold;">{sign}{val:.2f}%</td></tr>'

    html += '</table></div>'
    return html


def _img_file_to_data_uri(file_path):
    try:
        with open(file_path, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        return f'data:image/png;base64,{encoded}'
    except Exception:
        return None




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
                    macro_info["usd_krw_diff_pct"] = diff_pct
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
    simulated_result = "정보 없음"
    cagr = None  # 실제 데이터로 계산 성공한 경우에만 값이 채워짐 (임의 기본값 없음)
    current_price = 0.0
    calculated_yield = "0.00%"
    div_cycle = "정보 없음"
    expense_ratio = "N/A"
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

        # 2. 메타 정보 (네이버 금융 스크래핑)
        try:
            driver.get(f"https://finance.naver.com/item/main.naver?code={raw_code}")
            time.sleep(2)
            
            try:
                short_name = driver.find_element(By.XPATH, "//div[@class='wrap_company']/h2/a").text
            except Exception:
                short_name = raw_code
            
            # AUM (시가총액으로 대체)
            try:
                market_cap_text = driver.find_element(By.ID, "_market_sum").text
                aum_str = f"약 {market_cap_text}억 원"
            except Exception as e:
                print(f"   ⚠️ AUM 스크래핑 실패: {type(e).__name__}: {e}")
            
            dfs = pd.read_html(StringIO(driver.page_source))
            for df in dfs:
                df_str = df.to_string()
                if "펀드보수" in df_str or "총보수" in df_str:
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
            short_name = info.get('shortName', raw_code)
            
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
        "yield": calculated_yield, "returns": returns, "mdd": mdd_val,
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
        "fx_exposure": "있음 (해외 상장, 환노출형)" if is_fx_exposed else "없음 (국내 상장)",
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
        "index": info.get('category', '정보 없음') if not is_kr else "정보 없음",
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
TAX_RULES_BASIS = "2025년 세법 기준"
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
    return str((d or {}).get('fx_exposure', '')).startswith('있음')


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












def _generate_chained_article(today_str, collected_context, series_context, widgets_html_block, recent_issues, section_htmls, usd_krw, us_10y, fear_greed, crisis_guidance, title_pattern_hint, investment_temperature_html, include_toc=True, include_quote=True, include_bio=True, include_glossary=True, chosen_summary_style=None, force_regenerate_from=None, intro_style=None, session_label=None, final_review_issues=None, macro_thermo_html="", forced_title=None):
    """
    5단 분할(Chaining) 생성: Part1~5

    개선사항:
    - Part 1 생성 후 JSON 팩트 추출
    - Part N 생성 시 [누적 JSON 팩트] 주입
    - 논리는 원문으로, 숫자는 JSON으로 검증 (환각 방지)
    - 상단 온도계 HTML을 그대로 유지하면서 매수 분위기를 반영

    force_regenerate_from: 정수(1~5)를 넘기면 해당 Part 번호부터 그 이후 Part까지
    세션 캐시를 무시하고 강제로 새로 생성합니다.

    이게 필요한 이유: 완성본 최종 품질 검수(_llm_quality_check)에서 점수가 낮아
    "재생성"이 트리거되어도, 이 함수는 날짜+컨텍스트 기반 세션 캐시를 쓰기 때문에
    같은 날 같은 티커로 다시 호출하면 Part1~5가 전부 "이전 실행 결과 재사용"으로
    그대로 캐시에서 나와버려 실제로는 아무것도 바뀌지 않는 문제가 있었음(예: FAQ의
    h4 태그가 깨진 채로 몇 번을 재시도해도 똑같이 깨진 채로 나옴). 품질 문제로
    재생성이 필요할 때는 반드시 이 옵션으로 실제 재생성이 일어나게 해야 함.
    """

    # [추가] 이전에는 최종 검수(_llm_quality_check)가 "Part2와 Part4의 배당
    # 정보가 서로 모순된다"처럼 정확하고 구체적인 문제를 찾아내도, 그 내용이
    # 재생성 프롬프트에 전혀 전달되지 않고 로그에 출력만 되고 버려졌다. 그래서
    # 재생성은 "무작정 다시 써보고 운을 바라는" 식이 되어, 같은 이유로 계속
    # 실패가 반복됐다. 이제 최종 검수의 구체적 지적사항(issues)을 전달받으면,
    # 이를 모든 파트 공통 지시(shared_base)에 명시적으로 포함시켜 같은 실수를
    # 반복하지 않도록 한다.
    final_review_block = ""
    if final_review_issues:
        issues_text = "\n".join(f"- {issue}" for issue in final_review_issues)
        final_review_block = (
            "\n[매우 중요 - 직전 최종 검수에서 지적된 문제. 반드시 아래 사항을 실제로 고쳐서 "
            "다시는 반복하지 마세요]\n"
            f"{issues_text}\n"
            "특히 여러 파트에 걸친 수치나 사실관계 언급이 있다면, 반드시 위쪽 [핵심 데이터]에 있는 "
            "원본 값과 정확히 일치시키고, 스스로 새로 요약하거나 판단하지 마세요.\n"
        )

    shared_base = (
        "당신은 금융 전문 블로거 '온도(ondo)'입니다.\n"
        "- AI 기계어투를 피하고 사람 냄새 나는 문체로 작성하세요.\n"
        "- [가독성 절대 원칙] 글이 빽빽하고 어지럽지 않도록 문단을 2~3문장 단위로 짧게 나누세요.\n"
        "- [가독성 절대 원칙] 1-1, 1-2 같은 딱딱한 숫자 넘버링은 절대 금지합니다.\n"
        "- [가독성 절대 원칙] 대제목은 `<h3>` 태그로 작성하세요. 세부 소제목은 반드시 이 형식 그대로 작성하세요: `<h4>🔸 소제목 내용</h4>` (여는 태그와 닫는 태그 사이에 이모지와 텍스트만 넣고, 태그 안에 다른 속성이나 단어를 추가하지 마세요). "
        "올바른 예: `<h4>🔸 지금 투자해도 될까요?</h4>`. 잘못된 예(절대 이렇게 쓰지 마세요): `<h4 h4=\"\" 될까요?<=\"\" 지금=\"\" 투자해도=\"\" 🔸=\"\">`.\n"
        "- [가독성 절대 원칙] 대주제가 바뀔 때는 반드시 `<hr style='border:0; height:1px; background:#ddd; margin:35px 0;'>` 태그를 삽입해 시각적으로 분리하세요.\n"
        "- [가독성 절대 원칙] 핵심 내용은 `<div style='background:#f8f9fa; padding:15px; border-left:4px solid #1f3c88; margin:15px 0; border-radius:4px;'>` 같은 박스를 활용해 깔끔하게 강조하세요.\n"
        "- [출처 원칙] 수치는 제공된 데이터 그대로 쓰고, 출처는 실제로 제공된 것만 밝히세요(Yahoo Finance, 한국거래소, Investing.com). "
        "뉴스를 인용할 때는 [최근 주요 뉴스]에 있는 기사만 쓰고, 그 기사의 매체명과 주소를 `<a href=\"주소\" target=\"_blank\" rel=\"noopener\">매체명</a>` 형태로 다세요. "
        "'외신 보도', '업계에 따르면', '운용사 팩트시트', '전문가들은' 처럼 확인할 수 없는 출처는 절대 쓰지 마세요.\n"
        "- [사실 원칙] 제공된 데이터와 뉴스에 없는 사실(다른 운용사의 신상품 출시, 특정 기업의 실적·발표, 규제 진행 상황, 구성 종목 비중 등)은 단정해서 쓰지 마세요. "
        "필요하면 '~일 수 있습니다'처럼 일반적인 가능성으로만 짧게 언급하세요.\n"
        "- 결과는 반드시 HTML로 출력하세요. 모든 표는 `<table>`, `<tr>`, `<th>`, `<td>` HTML 태그로 작성해야 합니다. 텍스트표나 마크다운 표는 금지합니다.\n"
        "- [차별화 절대 원칙] 아래 [오늘의 거시경제 지표]/[최근 경제 이슈]는 참고용 원시 데이터일 뿐입니다. 이 문구를 그대로 복사하거나 다른 ETF 글에도 통째로 쓸 수 있는 일반론('환율 상승으로 부담 커진 상황' 등)으로 서술하지 마세요. 반드시 지금 다루는 ETF의 실제 구성종목·섹터 비중·통화 노출·배당 정책과 연결해, 이 ETF에서만 성립하는 문장으로 재구성하세요. 예: 금리 상황을 언급할 때는 이 ETF가 보유한 업종이 금리에 어떻게 반응하는지까지 써야 합니다.\n"
        f"- 이 분석은 {today_str} 기준입니다.\n"
        "- [자기소개 금지] '온도(ondo)의 시선', '저는 ~입니다' 같은 자기소개 박스나 블로거 소개 문구를 본문 중간에 스스로 만들지 마세요. 작가 소개는 지정된 파트에서 시스템이 별도로 삽입합니다. 그리고 어떤 경우에도 블로그 링크나 다른 글 링크(관련 글 URL)를 직접 지어내 삽입하지 마세요 - 실제로 존재하지 않는 글을 링크하면 깨진 링크가 되고, 관련 글 연결은 오직 지정된 파트(Part5)에서 실제 확인된 URL로만 이루어집니다.\n"
    )

    # [중요] 이전 버전은 목차/명언/작가프로필/용어사전 지시를 shared_base에 넣어
    # Part1~5 프롬프트 전부에 동일하게 삽입했음. 그 결과 "목차를 포함하세요" 같은
    # 지시가 Part1뿐 아니라 Part3, Part4에도 반복 노출되어, 각 파트가 독립적으로
    # 생성되는 과정에서 목차/설명이 여러 번 중복 생성되는 문제가 있었음.
    # 이 지시들은 Part1에서만 한 번 처리하면 되므로, Part1 전용 블록으로 분리하고
    # shared_base(모든 파트 공통)에서는 제거한다.
    part1_only_instructions = []
    if include_quote:
        part1_only_instructions.append("- 명언 박스: 아래 [블록 참고]의 \"명언\" 블록을 그대로(스타일이나 마크업을 절대 바꾸지 말고) 본문 서론 근처에 삽입하세요. 직접 다른 형태로 다시 만들지 마세요.")
    else:
        part1_only_instructions.append("- 명언/인용 섹션은 작성하지 마세요.")
    # 작가 프로필은 후처리 단계(_inject_static_sections)에서 항상 강제 삽입되므로,
    # AI에게도 일관되게 "항상 넣으라"고 지시한다 (이전에는 랜덤 On/Off였는데,
    # 어차피 코드가 강제로 붙이는 거라 AI에게 "넣지 말라"고 지시하는 게 모순이었음).
    part1_only_instructions.append("- 작가 프로필: 아래 [블록 참고]의 \"작가 프로필\" 블록을 그대로(스타일이나 마크업을 절대 바꾸지 말고) 글의 적절한 위치에 삽입하세요. 직접 다른 형태로 다시 만들지 마세요.")
    part1_only_block = "\n".join(part1_only_instructions)

    # Part5(마무리)에서만 필요한 지시. 용어사전은 글 끝부분 항목이라 마지막 파트에서,
    # 요약 박스 스타일도 3줄 요약이 실제로 만들어지는 Part5에서 적용되어야 함.
    part5_only_instructions = []
    if include_glossary:
        part5_only_instructions.append("- 용어사전: 아래 [블록 참고]의 \"용어사전\" 블록을 그대로(스타일이나 마크업을 절대 바꾸지 말고) 글 끝부분에 삽입하세요. 직접 다른 형태로 다시 만들지 마세요.")
    else:
        part5_only_instructions.append("- 용어사전 섹션은 작성하지 마세요.")
    if chosen_summary_style:
        part5_only_instructions.append(f"- 3줄 핵심 요약 박스는 배경색 {chosen_summary_style['bg']} 및 테두리 색 {chosen_summary_style['border']} 스타일로 작성하세요.")
    part5_only_block = "\n".join(part5_only_instructions)

    # shared_base(Part1~5 공통)에는 "이 요소들은 이미 처리되었으니 중복 생성 금지"만 남긴다.
    # [중요] 실제 생성 결과를 검토해보니, "3줄 핵심 요약"이 이 금지 목록에 빠져 있어서
    # Part2/3/5가 각자 자체적으로 요약 박스를 또 만드는 문제가 있었음. AI는 지시가 없으면
    # 각 파트를 스스로 "마무리하는 요약"으로 끝맺으려는 경향이 있으므로, 이런 마무리형
    # 블록 자체를 금지 목록에 명시적으로 포함시켜야 함.
    # [중요] 목차 금지 지시도 이전에는 Part1 전용 블록에만 있어서 Part2~5 프롬프트에는
    # 아예 이 지시가 전달되지 않았음(Part1 전용 블록은 Part1에만 삽입되므로). 목차는
    # 후처리 단계에서 완성된 전체 본문을 스캔해 한 번만 자동 삽입되므로, 모든 파트에서
    # AI가 직접 만들지 못하도록 공통 지시로 옮긴다.
    shared_base += (
        "\n- [목차 절대 금지] 목차(제목 링크 목록, <nav> 또는 '목차'라는 제목의 <div>)는 "
        "발행 시스템이 완성된 본문 전체를 스캔해 자동으로 한 번만 삽입합니다. 어떤 파트에서도 "
        "목차를 직접 작성하지 마세요.\n"
        "- [중복 생성 절대 금지] 명언 박스, 작가 프로필, 용어사전, 메타 설명, "
        "3줄 핵심 요약은 지정된 파트(Part1 또는 Part5)에서만 생성됩니다. 다른 파트에서는 "
        "이 요소들을 절대 다시 만들지 마세요.\n"
        "- [파트 마무리 금지] 각 파트의 끝에 그 파트 내용을 요약하는 별도의 박스, 표, "
        "체크리스트('✅ OOO 요약', '핵심 정리' 등 어떤 이름이든)를 스스로 만들지 마세요. "
        "요청받은 섹션만 작성하고 바로 끝내세요. 전체 글의 요약과 결론은 오직 Part5에서만 다룹니다.\n"
        + final_review_block
    )

    no_greeting_rule = "**[절대 규칙] 이미 서론에서 인사를 했으므로, '안녕하세요', '온도입니다' 같은 인사말이나 도입부는 절대 작성하지 말고 즉시 <h3> 소제목으로 본론을 시작하세요.**"

    # Part 템플릿 정의
    temperature_section = investment_temperature_html or ''
    gen_state = _load_generation_state()
    current_session_key = _get_text_hash(f"{today_str}|{collected_context[:300]}|{series_context[:300]}|{widgets_html_block[:300]}|{title_pattern_hint}")
    sessions = gen_state.setdefault('sessions', {})
    existing_session = sessions.get(current_session_key)
    if existing_session and existing_session.get('prompt_logic_version') != PROMPT_LOGIC_VERSION:
        # 프롬프트 로직이 바뀐 뒤라, 이전 버전으로 생성된 Part 캐시를 그대로 쓰면
        # 새 지시(예: 목차 금지)가 적용 안 된 조각이 섞여 나올 수 있으므로 폐기.
        print("🧹 프롬프트 로직이 업데이트되어 이전 세션 캐시를 폐기하고 새로 생성합니다.")
        sessions.pop(current_session_key, None)
    session = sessions.setdefault(current_session_key, {'created_at': time.time(), 'today': today_str, 'prompt_logic_version': PROMPT_LOGIC_VERSION})

    if force_regenerate_from:
        # 지정된 파트 번호부터 이후 파트까지 캐시를 실제로 지워서, 재시도해도
        # "이전 실행 결과 재사용"으로 그대로 나오는 문제를 막는다.
        for p in range(force_regenerate_from, 6):
            session.pop(f'p{p}', None)
            session.pop(f'p{p}_facts', None)
        print(f"🗑️ Part{force_regenerate_from}~5 캐시를 삭제하고 실제로 재생성합니다.")
        _save_generation_state(gen_state)

    # [신규] SEO/제목 최적화 부서가 미리 제목을 확정해뒀으면, Part1이 다시
    # 자유생성하지 않고 그 제목을 그대로 쓰게 한다. 실패해서 forced_title이
    # 없으면(None) 기존처럼 title_pattern_hint를 참고해 자유생성한다.
    if forced_title:
        title_instruction = (
            f"1) 제목 사용: <h1>으로 작성하세요. 제목은 이미 SEO 담당자가 여러 후보를 비교해 확정했으니, "
            f"절대 새로 만들지 말고 아래 제목을 토씨 하나 틀리지 않고 그대로 사용하세요.\n"
            f"   확정된 제목: {forced_title}\n"
        )
    else:
        title_instruction = (
            f"1) 제목 생성: <h1>으로 작성하세요. '{title_pattern_hint}'의 주제를 바탕으로, 본문 내용을 반영해 사람의 흥미를 끄는 독창적이고 새로운 제목을 생성하세요(그대로 복사 금지). 제목은 반드시 새로운 것이어야 하며, 제공된 패턴을 그대로 사용하지 말고, ETF의 구체적인 성과, 배당, 리스크 등을 고려하여 창의적으로 만들어야 합니다.\n"
        )

    part1 = (
        f"[Part 1/5 - 도입/기초: 제목, 메타, 서론, 기초정보, 커스텀 지표, 데이터 출처]\n"
        f"{temperature_section}\n"
        f"{shared_base}\n"
        f"{part1_only_block}\n"
        f"{collected_context}\n"
        f"{series_context}\n"
        f"작성 요구사항:\n"
        f"{title_instruction}"
        f"2) 메타 설명 작성: 120~160자 사이(Rank Math SEO 플러그인 권장 범위 - 너무 짧으면 정보 부족, 너무 길면 검색결과에서 잘림)로 이 글의 핵심을 요약하는 문장을 만드세요. HTML 주석(<!-- -->) 형식으로 본문 최상단에 삽입하세요 (화면에는 안 보이지만, 이후 Part5에서 이 문장을 Article 스키마의 description 필드에 그대로 재사용해야 실제로 검색엔진에 전달되니, 나중에 다시 쓸 수 있도록 명확한 문장으로 작성하세요).\n"
        f"3) 서론만 작성: {intro_style or '현재 거시경제 상황을 요약하며 시작하세요.'} 제공된 컨텍스트에 [시리즈 업데이트] 정보가 있을 경우에만 '지난번 분석 이후 현재 시점에서 어떤 변화가 있는지 점검해보겠습니다' 식으로 과거와 비교하는 언급을 추가하세요. 업데이트 정보가 없다면 첫 분석이므로 해당 멘트를 절대 넣지 말고, 서론 안에서 현재 거시경제(원/달러: {usd_krw}, 금리: {us_10y}, 공포/탐욕: {fear_greed}) 상황도 함께 자연스럽게 녹여 작성하세요. 인사말('안녕하세요' 등)은 사용하지 마세요.\n"
        f"4) 기초정보+차트: 주요 ETF 지표, 월봉 차트 설명, 고정 표를 작성하세요. 작성 후 차트가 들어갈 위치에 반드시 정확히 [[CHART_WIDGET_PLACEHOLDER]] 문구를 삽입하세요.\n"
        f"   [중복 금지] 기간별 수익률 표(1개월/3개월/1년)와 배당 지급 내역 표는 Part 2에서 정해진 양식으로 만듭니다. Part 1에서는 이 두 표를 만들지 말고, 기초정보 표에는 종목명·운용사·지수·운용보수·배당수익률·상장일·환노출 여부·MDD·배당성장률만 넣으세요. 수익률이나 배당 이야기는 한두 문장으로만 짧게 언급하세요.\n"
        f"5) [투자 온도계 - 절대 반복 금지] 위에 제시된 온도계 HTML 블록(단일 투자 온도계 및 변동성/밸류에이션/환율/인플레이션 4대 온도계+종합 온도계)은 이미 글 맨 앞(제목 위)에 자동으로 삽입되어 있습니다. 당신은 이 블록들을 다시 출력하지 마세요. 그리고 온도계의 메시지 문구(예: '투자 타이밍이 중립적입니다' 등)나 4대 온도계의 숫자를 서론이나 본문 어디에서도 그대로 반복하지 마세요. 온도계의 점수나 등급을 언급하고 싶다면, 그 숫자가 왜 그렇게 나왔는지 이 ETF/시장의 실제 데이터로 새롭게 풀어서 설명하되, 정해진 안내 문구를 재사용하지 마세요.\n"
        f"6) 커스텀 지표: 아래 [블록 참고]의 \"커스텀 지표\" 블록을 그대로(스타일, 수치, 마크업을 절대 바꾸지 말고) 삽입하세요. 이 표는 이미 정확히 계산되어 있으므로 직접 다시 만들거나 숫자를 재작성하지 마세요.\n"
        f"7) 데이터 출처: 아래 [블록 참고]의 \"데이터 출처\" 블록을 그대로(URL과 링크를 절대 바꾸지 말고) 삽입하세요. 직접 다른 형태로 다시 만들지 마세요.\n"
        f"[블록 참고]\n"
        f"커스텀 지표: {section_htmls.get('커스텀 지표', '')}\n"
        f"데이터 출처: {section_htmls.get('데이터 출처', '')}\n"
        f"명언: {section_htmls.get('명언', '')}\n"
        f"작가 프로필: {section_htmls.get('작가 프로필', '')}\n"
        f"[최소 1500자 이상 작성 필수]\n"
        f"\n[JSON Mode 지시사항]\n"
        f"응답을 JSON 형식으로 출력하세요: {{\"html\": \"생성된 HTML 콘텐츠\", \"facts\": {{\"recommended_url\": \"주제에맞는-영문소문자-하이픈-url\", \"yields\": \"배당률\", \"expense_ratio\": \"운용보수\", \"returns_1m\": \"1개월 수익률\", \"returns_3m\": \"3개월 수익률\", \"returns_1y\": \"1년 수익률\", \"mdd\": \"최대낙폭\", \"dividend_growth_rate\": \"배당성장률\", \"key_metrics\": [\"주요 지표\"], \"conclusion\": \"핵심 결론\"}}}}\n"
    )

    # ==================== Part 1 생성 ====================
    if session.get('p1'):
        p1 = session['p1']
        facts = session['p1_facts']
        print("✅ Part 1 재사용: 이전 실행에서 존재하는 생성 결과를 사용합니다.")
    else:
        p1_raw, p1_quality = _generate_part_with_check(part1, 1, "Part1(도입/기초)", confirmed_text_so_far="", session_key=current_session_key, label=session_label)
        if not p1_raw:
            print("❌ Part1 생성 실패")
            _save_generation_state(gen_state)
            return None, None
        p1 = p1_raw
        # [신규] 사람이 저장된 raw_responses/*.json 파일을 직접 열어 html/facts를
        # 고쳤을 수 있으므로, 방금 받은 메모리 값 대신 디스크에 저장된 최신본을
        # 먼저 확인한다. 파일이 없거나 손상됐으면 메모리 값(p1_raw)을 그대로 쓴다.
        response_data = _load_raw_part_response(current_session_key, 1, label=session_label)
        if response_data is None:
            try:
                response_data = json.loads(p1)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}, _extract_facts_from_response 시도...")
                parsed = _extract_facts_from_response(p1, 1)
                response_data = parsed if isinstance(parsed, dict) else {"html": p1, "facts": {}}
        else:
            print("📝 Part1: 저장된 파일(raw_responses/)의 내용을 사용합니다 (사람이 직접 수정했을 수 있음).")
        p1 = response_data.get('html', '')
        facts = response_data.get('facts', {})
        # [수정] recommended_url을 예전엔 "추천 URL: ..."라는 텍스트로 본문에 그대로
        # 노출시켰으나(독자에게 아무 의미 없는 흔적이었음), 이제는 발행 단계에서
        # 워드프레스 API의 실제 slug 파라미터로 전달해 진짜 게시물 URL로 사용한다.
        # 본문에는 더 이상 아무것도 삽입하지 않는다 - facts는 아래에서 그대로 유지.
        session['p1'] = p1
        session['p1_facts'] = facts
        _save_generation_state(gen_state)

    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    print(f"✅ Part 1 팩트 시트:\n{facts_json_str}")
    
    # ==================== Part 2 생성 ====================
    part2_template = f"""[Part 2/5 - 수익/시뮬레이션: 수익률+배당, 시나리오 분석]
{shared_base}
{no_greeting_rule}

[주의] 제목/메타 설명/서론/목차/작가 프로필/기초정보는 이미 Part1에서 생성되었으므로 절대 다시 작성하지 마세요.
오직 다음 섹션들만 <h3> 제목과 함께 작성하세요:
1) 수익률+배당: 1,000만 원 시뮬레이션 + 세후 실질 수익 계산. [필수] 직접 계산하지 말고, 위쪽 [핵심 데이터]의 "[1,000만 원 투자 시뮬레이션]" 항목에 있는 값을 그대로 사용해 설명하세요. (아래 두 표는 반드시 이 섹션에서 먼저 작성하세요 - 이후 파트들이 이 수치를 팩트로 참고합니다.)
   **[수익률 표 강제 템플릿 - 반드시 아래 HTML 코드를 그대로 복사해 데이터만 채우세요]**
   [필수] 이 표에 새로운 숫자를 계산하거나 지어내면 안 됩니다. 위쪽 [핵심 데이터]의 "[수익률 데이터(필수사용)]" 항목에 있는 1개월/3개월/1년 수익률 값을 그대로 옮겨 적으세요.
   [중요] color:[[COLOR]] 부분은 그 칸의 수익률이 양수(+)면 #c0392b(빨강), 음수(-)면 #2166ac(파랑)로 직접 바꿔 넣으세요. 세 칸 모두 같은 색을 쓰면 안 되고, 각 칸의 실제 부호에 맞게 개별적으로 판단하세요. (국내 증시 관행: 상승/양수=빨강, 하락/음수=파랑)
   <div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; text-align:center; font-size:14px; margin-bottom:20px;"><tr style="background:#f1f5f9;"><th style="border:1px solid #ddd; padding:10px;">구분</th><th style="border:1px solid #ddd; padding:10px;">수익률 (%)</th></tr><tr><td style="border:1px solid #ddd; padding:10px;">최근 1개월</td><td style="border:1px solid #ddd; padding:10px; font-weight:bold; color:[[COLOR]];">...</td></tr><tr><td style="border:1px solid #ddd; padding:10px;">최근 3개월</td><td style="border:1px solid #ddd; padding:10px; font-weight:bold; color:[[COLOR]];">...</td></tr><tr><td style="border:1px solid #ddd; padding:10px;">최근 1년</td><td style="border:1px solid #ddd; padding:10px; font-weight:bold; color:[[COLOR]];">...</td></tr></table></div>
   **[배당 내역 표 강제 템플릿 - 반드시 아래 HTML 코드를 그대로 복사해 데이터만 채우세요]**
   [필수] 이 표는 절대 새로운 숫자를 만들어내면 안 됩니다. 위쪽 [핵심 데이터]의 "[최근 배당내역(필수사용)]" 항목에 있는 실제 지급일·지급액·증감률 값만 그대로 옮겨 적으세요. 그 항목에 없는 지급일은 표에 추가하지 말고, 그 항목에 있는 값과 다른 숫자를 쓰면 절대 안 됩니다. 이후 파트들도 이 표의 숫자를 그대로 참고하므로, 여기서 만든 숫자가 사실상 최종 확정 데이터가 됩니다.
   [중요] color:[[COLOR]] 부분도 마찬가지로 "직전 배당 대비 증감"이 증가(+)면 #c0392b(빨강), 감소(-)면 #2166ac(파랑)로 바꿔 넣으세요.
   <div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; text-align:center; font-size:14px; margin-bottom:20px;"><tr style="background:#f1f5f9;"><th style="border:1px solid #ddd; padding:10px;">지급 기준일</th><th style="border:1px solid #ddd; padding:10px;">지급액</th><th style="border:1px solid #ddd; padding:10px;">직전 배당 대비 증감</th></tr><tr><td style="border:1px solid #ddd; padding:10px;">...</td><td style="border:1px solid #ddd; padding:10px;">...</td><td style="border:1px solid #ddd; padding:10px; font-weight:bold; color:[[COLOR]];">...</td></tr></table></div>

이후 아래 두 섹션은 이 ETF에서 어느 쪽이 더 중요한 이야깃거리인지 스스로 판단해서, 순서와 분량을 다르게 배치하세요(항상 같은 순서·같은 분량으로 기계적으로 나열하지 마세요):
- 시나리오 분석: 계좌별 세금 비교 + 3개 페르소나 구체화. [필수] 세금 비교 수치는 위쪽 [핵심 데이터]의 "[세금 시뮬레이션(배당 1억 기준)]" 항목에 있는 값과 "(기준: ...)"에 적힌 세율 설명을 그대로 사용하세요. 새로운 세율이나 절세액을 직접 계산하거나, 거기 없는 세율(예: "ISA 전액 비과세")을 쓰지 마세요.
  [필수] [핵심 데이터]의 "[계좌 안내(필수 반영)]"를 반드시 따르세요. 해외 상장 ETF라면 "ISA·연금저축·IRP로 이 ETF를 산다"는 문장을 절대 쓰지 말고, 이 계좌를 쓰려면 같은 지수를 추종하는 국내 상장 ETF를 사야 한다고 설명하세요. 페르소나별 조언도 이 사실과 어긋나면 안 됩니다. 국내 상장 대체 ETF의 구체적인 상품명은 데이터에 없으므로 지어내지 마세요.
- 최근 뉴스/실제 사례: 최근 2~3건의 뉴스 또는 공시 간략 정리. 특별히 주목할 뉴스가 없다면 짧게 넘어가거나 생략하세요.
[블록 참고]
시나리오 분석: {section_htmls.get('시나리오 분석', '')}
[최소 1000자 이상 작성 필수]
{_build_previous_content_block(p1)}
[지켜야 할 절대 수치 (Part 1 팩트 시트)]
{facts_json_str}

[중요 지시사항]
- 위 JSON의 수치와 모순되는 내용을 작성하면 안 됩니다.
- 위 원문의 논리와 자연스럽게 연결되도록 작성하세요.
- Part 1에서 이미 언급한 내용은 반복하지 마세요.
- [경험담 금지] "제가 투자해봤더니", "제 계좌에서" 등 필자가 실제로 해당 금액을 투자한 것처럼 1인칭 경험담으로 서술하지 마세요. "1,000만 원을 투자했다고 가정하면", "과거 데이터를 기준으로 시뮬레이션하면"처럼 명시적인 가정/시뮬레이션 어법을 사용하세요.
"""
    
    if session.get('p2'):
        p2 = session['p2']
        facts_p2 = session['p2_facts']
        print("✅ Part 2 재사용: 이전 실행에서 존재하는 생성 결과를 사용합니다.")
    else:
        part2_prompt = part2_template + "\n[JSON Mode 지시사항]\n응답을 JSON 형식으로 출력하세요: {\"html\": \"생성된 HTML 콘텐츠\", \"facts\": {\"yields\": \"배당률\", \"expense_ratio\": \"운용보수\", \"returns_1m\": \"1개월 수익률\", \"returns_3m\": \"3개월 수익률\", \"returns_1y\": \"1년 수익률\", \"mdd\": \"최대낙폭\", \"dividend_growth_rate\": \"배당성장률\", \"key_metrics\": [\"주요 지표\"], \"conclusion\": \"핵심 결론\"}}"
        # [중요] p1은 이 시점에 이미 확정된 상태(검수 통과 또는 최대 재시도 후 확정)이므로
        # 안전하게 이전 컨텍스트로 넘길 수 있음
        p2_raw, p2_quality = _generate_part_with_check(part2_prompt, 2, "Part2(수익/시뮬레이션)", confirmed_text_so_far=p1, session_key=current_session_key, label=session_label)
        if not p2_raw:
            print("❌ Part2 생성 실패")
            _save_generation_state(gen_state)
            return None, None
        p2 = p2_raw
        response_data = _load_raw_part_response(current_session_key, 2, label=session_label)
        if response_data is None:
            try:
                response_data = json.loads(p2)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}, _extract_facts_from_response 시도...")
                parsed = _extract_facts_from_response(p2, 2)
                response_data = parsed if isinstance(parsed, dict) else {"html": p2, "facts": {}}
        else:
            print("📝 Part2: 저장된 파일(raw_responses/)의 내용을 사용합니다 (사람이 직접 수정했을 수 있음).")
        p2 = response_data.get('html', '')
        facts_p2 = response_data.get('facts', {})
        session['p2'] = p2
        session['p2_facts'] = facts_p2
        _save_generation_state(gen_state)
    
    # 정보없음이 아닌 값만 업데이트 (기존 유효 데이터 보호)
    for key, value in facts_p2.items():
        if value and value != "정보없음" and value != "null" and value is not None:
            if isinstance(value, list) and not value:  # 빈 리스트 제외
                continue
            facts[key] = value
    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    print(f"✅ 누적 팩트 시트:\n{facts_json_str}")
    
    # ==================== Part 3 생성 ====================
    _prev_p1p2 = p1 + "\n" + p2
    part3_template = f"""[Part 3/5 - 전략/리스크: 리스크 분석, 위험 시나리오, 경쟁분석, 실수료 비교]
{shared_base}
{no_greeting_rule}

[주의] 제목/메타 설명/서론/목차/작가 프로필은 이미 Part1에서 생성되었으므로 절대 다시 작성하지 마세요. 이전 파트에서 다룬 내용도 반복하지 마세요.
아래 4가지 주제를 다루되, 이 ETF에서 실제로 중요한 주제에 분량과 깊이를 더 쓰고,
상대적으로 덜 중요하거나 특별할 것 없는 주제는 짧게 짚고 넘어가세요.
모든 항목을 기계적으로 똑같은 비중으로 채우지 마세요 — 이 ETF만의 특징이 드러나는 게 우선입니다.
또한 아래 번호는 우선순위가 아니라 참고용 목록일 뿐입니다 - 이 ETF에서 가장 먼저 짚어야
할 주제가 무엇인지에 따라 등장 순서를 자유롭게 바꾸세요(예: 리스크가 특히 부각되는 ETF라면
리스크 분석을 맨 앞에, 경쟁이 치열한 ETF라면 경쟁분석을 맨 앞에 배치해도 됩니다).
각 항목은 <h3> 제목과 함께 작성하세요:
1) 리스크 분석: MDD, 변동성, 추적오차, 레버리지/커버드콜 위험 등 이 ETF에 실제로 해당하는 리스크 위주로. 해당 없는 리스크 유형은 언급하지 마세요.
2) 위험 시나리오: 과거 위기(2000/2008/2020) 기반 낙폭 시뮬레이션. 이 ETF의 실제 역사적 성과 데이터가 있는 경우에만 구체적으로 다루고, 없다면 짧게 언급하세요. 최근 뉴스/시장 반응 사례가 실제로 있다면 포함하세요.
3) 경쟁분석: 이 ETF와 비교할 가치가 있는 다른 ETF들을 언급하되, [지켜야 할 절대 수치] JSON에 없는 수치(경쟁 ETF의 정확한 수익률, MDD, 보수율 등)는 절대 지어내지 마세요. 실제 확보된 수치가 없다면 "운용사, 상장 시기, 기초자산이 어떻게 다른지"처럼 정성적으로만 비교하고, 구체적 숫자가 나열된 비교표는 만들지 마세요. 확인되지 않은 숫자를 표로 만들면 사실처럼 보이는 허위 정보가 되어 심각한 신뢰성 문제가 됩니다.
4) 실수료 비교: HTML `<table>` 표로 1억원 10년 투자 시 운용보수 차이로 인한 누적 손실 계산. [필수] 직접 계산하지 말고, 위쪽 [핵심 데이터]의 "[운용보수 1억 10년 영향]" 항목에 있는 값을 그대로 사용하세요. 그 항목이 "정보 없음"이면 이 표를 만들지 말고 이 항목 자체를 생략하세요.
[위기 데이터 가이드]
{crisis_guidance}
[블록 참고]
경쟁분석: {section_htmls.get('경쟁분석', '')}
위험시나리오: {section_htmls.get('위험시나리오', '')}
실수료비교: {section_htmls.get('실수료비교', '')}
[분량 가이드] 최소 900자. 상한은 없습니다 - 이 ETF에 실제로 중요한 내용이 많다면 그만큼 길어져도 됩니다. 억지로 채운 문장보다 짧더라도 알맹이 있는 내용이 우선입니다.

[작성 원칙]
- 이 ETF 고유의 특징, 실제 수치, 실제 사례를 근거로 서술하세요. 다른 ETF에도 그대로 적용될 법한 일반론적 문장은 피하세요.
- 뻔한 말이나 반복적인 상투구 대신, 이 종목을 분석하면서 실제로 발견한 특징을 쓰세요.
{_build_previous_content_block(_prev_p1p2)}
[지켜야 할 절대 수치 (누적 팩트 시트)]
{facts_json_str}

[중요 지시사항]
- 위 JSON의 수치와 모순되는 내용을 작성하면 안 됩니다.
- 위 원문들의 논리와 자연스럽게 연결되도록 작성하세요.
- Part 1~2에서 이미 언급한 내용은 반복하지 마세요.
"""
    
    if session.get('p3'):
        p3 = session['p3']
        facts_p3 = session.get('p3_facts', {})
        # 이전 실행에서 JSON 문자열이 저장된 경우를 대비해 HTML/팩트로 정규화
        if isinstance(p3, str) and p3.strip().startswith('{') and '"html"' in p3:
            try:
                parsed = json.loads(p3)
                p3 = parsed.get('html', p3)
                facts_p3 = parsed.get('facts', facts_p3)
                session['p3'] = p3
                session['p3_facts'] = facts_p3
                _save_generation_state(gen_state)
            except json.JSONDecodeError:
                pass
        print("✅ Part 3 재사용: 이전 실행에서 존재하는 생성 결과를 사용합니다.")
    else:
        print("🤖 Part 3 생성 중 (전략/리스크)...")
        part3_prompt = part3_template + "\n[JSON Mode 지시사항]\n응답을 JSON 형식으로 출력하세요: {\"html\": \"생성된 HTML 콘텐츠\", \"facts\": {\"yields\": \"배당률\", \"expense_ratio\": \"운용보수\", \"returns_1m\": \"1개월 수익률\", \"returns_3m\": \"3개월 수익률\", \"returns_1y\": \"1년 수익률\", \"mdd\": \"최대낙폭\", \"dividend_growth_rate\": \"배당성장률\", \"key_metrics\": [\"주요 지표\"], \"conclusion\": \"핵심 결론\"}}"
        p3_raw, p3_quality = _generate_part_with_check(part3_prompt, 3, "Part3(전략/리스크)", confirmed_text_so_far=p1 + "\n" + p2, session_key=current_session_key, label=session_label)
        if not p3_raw:
            print("❌ Part3 생성 실패")
            _save_generation_state(gen_state)
            return None, None
        p3 = p3_raw
        response_data = _load_raw_part_response(current_session_key, 3, label=session_label)
        if response_data is None:
            try:
                response_data = json.loads(p3)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}, _extract_facts_from_response 시도...")
                parsed = _extract_facts_from_response(p3, 3)
                response_data = parsed if isinstance(parsed, dict) else {"html": p3, "facts": {}}
        else:
            print("📝 Part3: 저장된 파일(raw_responses/)의 내용을 사용합니다 (사람이 직접 수정했을 수 있음).")
        p3 = response_data.get('html', p3)
        facts_p3 = response_data.get('facts', {})
        session['p3'] = p3
        session['p3_facts'] = facts_p3
        _save_generation_state(gen_state)
    
    print("📊 Part 3 팩트 시트 추출 중...")
    # 정보없음이 아닌 값만 업데이트 (기존 유효 데이터 보호)
    for key, value in facts_p3.items():
        if value and value != "정보없음" and value != "null" and value is not None:
            if isinstance(value, list) and not value:  # 빈 리스트 제외
                continue
            facts[key] = value
    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    print(f"✅ 누적 팩트 시트:\n{facts_json_str}")
    
    # ==================== Part 4 생성 ====================
    _prev_p1p2p3 = p1 + "\n" + p2 + "\n" + p3
    part4_template = f"""[Part 4/5 - 포트폴리오/심화]
{shared_base}
{no_greeting_rule}

[주의] 제목/메타 설명/서론/목차/작가 프로필은 이미 Part1에서 생성되었으므로 절대 다시 작성하지 마세요. 이전 파트에서 다룬 내용도 반복하지 마세요.
아래는 다룰 수 있는 주제 목록입니다. 이 중 이 ETF에 실제로 의미 있고 독자에게 도움이 되는 주제를
3~4개만 골라서 깊이 있게 쓰세요. 모든 항목을 다 채울 필요는 없습니다 — 해당사항이 적은 주제를
억지로 채우면 오히려 글이 뻔해집니다.

- 연령별 포트폴리오: 20대/30대/40대/50대 배치 전략. 이 ETF의 변동성/배당 특성상 실제로 차등을 둘 이유가 있을 때만 다루세요.
- 매매 타이밍: 거치식 vs DCA, 진입 포인트. 현재 거시경제 상황과 실제로 연결지어 설명할 수 있을 때 다루세요.
- 가상 포트폴리오 백테스트: 실제 데이터에 기반한 백테스트 결과가 있을 때만 다루세요. 가짜 수치를 만들지 마세요.
- 섹터 분석: 이 ETF가 특정 섹터에 대한 노출이 뚜렷할 때만 다루세요. 일반 시장 추종 ETF라면 생략하거나 짧게.
- 과거 경제위기와 비교: 크라이시스 가이드에 실제 데이터가 있는 경우에만 구체적으로 다루세요.

[블록 참고 - 선택한 주제에 해당하는 것만 참고]
연령별포트폴리오: {section_htmls.get('연령별포트폴리오', '')}
매매타이밍: {section_htmls.get('매매타이밍', '')}
가상포트폴리오: {section_htmls.get('가상포트폴리오', '')}
섹터심화: {section_htmls.get('섹터심화', '')}
시간대마커: {section_htmls.get('시간대마커', '')}
[분량 가이드] 최소 900자. 상한은 없습니다 - 선택한 주제를 깊이 다루다 보면 자연스럽게 길어져도 됩니다.

[작성 원칙]
- 항목 수보다 밀도가 중요합니다. 3~4개를 골라 이 ETF만의 이야기로 채우세요.
- 다른 ETF 글에도 그대로 쓸 수 있는 일반론적 문장은 피하세요.
{_build_previous_content_block(_prev_p1p2p3)}
[지켜야 할 절대 수치 (누적 팩트 시트)]
{facts_json_str}

[중요 지시사항]
- 위 JSON의 수치와 모순되는 내용을 작성하면 안 됩니다.
- Part 1~3의 전체 논리와 자연스럽게 연결되도록 작성하세요.
- 이미 언급한 내용은 반복하지 마세요.
"""
    
    if session.get('p4'):
        p4 = session['p4']
        facts_p4 = session.get('p4_facts', {})
        if isinstance(p4, str) and p4.strip().startswith('{') and '"html"' in p4:
            try:
                parsed = json.loads(p4)
                p4 = parsed.get('html', p4)
                facts_p4 = parsed.get('facts', facts_p4)
                session['p4'] = p4
                session['p4_facts'] = facts_p4
                _save_generation_state(gen_state)
            except json.JSONDecodeError:
                pass
        print("✅ Part 4 재사용: 이전 실행에서 존재하는 생성 결과를 사용합니다.")
    else:
        print("🤖 Part 4 생성 중 (포트폴리오/심화)...")
        part4_prompt = part4_template + "\n[JSON Mode 지시사항]\n응답을 JSON 형식으로 출력하세요: {\"html\": \"생성된 HTML 콘텐츠\", \"facts\": {\"yields\": \"배당률\", \"expense_ratio\": \"운용보수\", \"returns_1m\": \"1개월 수익률\", \"returns_3m\": \"3개월 수익률\", \"returns_1y\": \"1년 수익률\", \"mdd\": \"최대낙폭\", \"dividend_growth_rate\": \"배당성장률\", \"key_metrics\": [\"주요 지표\"], \"conclusion\": \"핵심 결론\"}}"
        # [수정] 예전엔 p2+p3만 넘겨서 Part1(도입/기초 - 환율·금리·공포지수 등 거시 지표를
        # 처음 설명하는 곳)이 통째로 빠졌음. 그래서 Part4가 같은 거시 지표를 "처음 보는
        # 내용"처럼 반복 설명해도 검수가 못 잡았음. 이제 전체 누적 히스토리(p1~p3)를 넘김.
        p4_raw, p4_quality = _generate_part_with_check(part4_prompt, 4, "Part4(포트폴리오/심화)", confirmed_text_so_far=p1 + "\n" + p2 + "\n" + p3, session_key=current_session_key, label=session_label)
        if not p4_raw:
            print("❌ Part4 생성 실패")
            _save_generation_state(gen_state)
            return None, None
        p4 = p4_raw
        response_data = _load_raw_part_response(current_session_key, 4, label=session_label)
        if response_data is None:
            try:
                response_data = json.loads(p4)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}, _extract_facts_from_response 시도...")
                parsed = _extract_facts_from_response(p4, 4)
                response_data = parsed if isinstance(parsed, dict) else {"html": p4, "facts": {}}
        else:
            print("📝 Part4: 저장된 파일(raw_responses/)의 내용을 사용합니다 (사람이 직접 수정했을 수 있음).")
        p4 = response_data.get('html', p4)
        facts_p4 = response_data.get('facts', {})
        session['p4'] = p4
        session['p4_facts'] = facts_p4
        _save_generation_state(gen_state)
    
    print("📊 Part 4 팩트 시트 추출 중...")
    # 정보없음이 아닌 값만 업데이트 (기존 유효 데이터 보호)
    for key, value in facts_p4.items():
        if value and value != "정보없음" and value != "null" and value is not None:
            if isinstance(value, list) and not value:  # 빈 리스트 제외
                continue
            facts[key] = value
    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    print(f"✅ 누적 팩트 시트:\n{facts_json_str}")
    
    # ==================== Part 5 생성 ====================
    related_link_cmd = "5) 관련 콘텐츠: 기존 블로그 글 2-3개와 실제 URL 매칭 (절대 AI 임의 URL 금지)." if "내 블로그 기존 글 목록" in collected_context else ""

    _prev_p1p2p3p4 = p1 + "\n" + p2 + "\n" + p3 + "\n" + p4
    part5_template = f"""[Part 5/5 - 반박/결론/마무리: 반박 섹션, 경제 사이클, 제언, 요약, 관련 콘텐츠, FAQ, 스키마, 면책]
{shared_base}
{part5_only_block}
{no_greeting_rule}
{collected_context}

[주의] 제목/메타 설명/서론/목차/작가 프로필은 이미 Part1에서 생성되었으므로 절대 다시 작성하지 마세요. 이전 파트에서 다룬 내용도 반복하지 마세요.
오직 다음만 작성하세요:
아래 세 섹션(반박/경제사이클/결론)은 이 ETF에 대해 가장 먼저 짚어야 할 게 무엇인지에 따라 순서를 자유롭게 정하세요(예: 지금 이 ETF의 리스크가 시급하면 결론성 경고를 먼저 던지고 반박은 뒤에 배치해도 됩니다). 다만 세 섹션 모두 반드시 작성해야 합니다:
- 반박 섹션: 이 ETF에 대해 실제로 흔한 오해나 장점만 강조된 착각이 있다면 1~2개 짚으세요. 억지로 만들어내지 말고, 없다면 짧게 넘어가세요.
- 경제 사이클: 현재 경제 위치(회복/과열/침체/완화) + 투자 전략 제시. 공포/탐욕 지수({fear_greed}) 반영. (현 시점 경제 상황과 연결)
- 제언(결론): <h3>제언(결론)</h3> + 250자 이상. 보수적/중립/공격적 프레임 중 이 ETF 상황에 맞는 1개 선택. 공포/탐욕 지수({fear_greed}) 눈에 띄게 삽입. 결론을 맺는 방식은 매번 다르게 하세요 - "~한 접근이 필요합니다" 같은 뻔한 문장으로만 끝내지 말고, 이번엔 구체적인 행동 지침으로 끝내거나, 이번엔 앞으로 지켜봐야 할 지표를 짚으며 끝내거나, 이번엔 이 ETF의 핵심 트레이드오프를 한 문장으로 요약하며 끝내는 식으로 매번 다른 마무리 방식을 쓰세요. "당신의 자산은 안전한가" 같은 클리셰 수사 의문문은 쓰지 마세요.

이후 아래는 정해진 순서/형식대로 작성하세요 (번호는 위 세 섹션 다음부터 이어짐):
4) 3줄 핵심 요약: <div style=...>으로 배경색 지정, <ol><li>3개 핵심 포인트</li>...</ol> 형식.
4-1) 손익 캘린더 자리 표시: 3줄 핵심 요약 바로 다음, FAQ 바로 전에 정확히 [[CALENDAR_PLACEHOLDER]] 문구만 삽입하세요. 이 문구를 그대로 두면 시스템이 실제 손익 캘린더로 자동 치환합니다. 직접 HTML이나 표를 만들지 마세요.
4-2) 정정 이력 자리 표시: 손익 캘린더 표시 바로 다음, FAQ 바로 전에 정확히 [[REVISION_HISTORY_PLACEHOLDER]] 문구만 삽입하세요. 이 문구를 그대로 두면 시스템이 실제 정정 이력으로 자동 치환합니다. 직접 HTML이나 표를 만들지 마세요.
{related_link_cmd}
6) FAQ: 본문에서 실제로 다룬 내용 기반으로 2~4개. 개수보다 질문이 실제 독자가 궁금해할 만한지가 중요합니다.
7) JSON-LD 스키마: 
   - Article 스키마: headline(제목), description(Part1 서두의 HTML 주석에 작성했던 메타 설명 문장을 그대로 재사용하세요 - 이게 검색엔진에 실제로 전달되는 유일한 경로입니다), datePublished({today_str}), author(온도).
   - FAQ 스키마: 본문 FAQ 섹션과 100% 일치하는 Q&A.
   (근거 없는 자체 평점을 노출하는 Review/별점 스키마는 작성하지 마세요. 실제 사용자 리뷰가 없는 상태에서 별점을 구조화 데이터로 넣는 것은 검색 정책 위반 소지가 있습니다.)
8) 업데이트 정보: 최종 업데이트 {today_str}.
9) 면책조항: 해당 섹션은 이 스크립트에서 고정 HTML 블록으로 자동 삽입되므로, AI는 이 부분을 생성하지 않아도 됩니다.
10) 태그: 본문 맨 마지막에 반드시 아래 형식으로 딱 5개의 태그만 띄어쓰기로 구분하여 작성하세요. 부가 설명 절대 금지.
형식: 태그: #{today_str[:4]}년 #[현재분석중인ETF] #[비슷한해외ETF1] #[비슷한해외ETF2] #[유사한한국ETF1개]
예시: 태그: #2026년 #QQQ #SPY #VOO #TIGER미국나스닥100
[블록 참고]
반박섹션: {section_htmls.get('반박섹션', '')}
경제사이클: {section_htmls.get('경제사이클', '')}
용어사전: {section_htmls.get('용어사전', '')}
관련 콘텐츠: {section_htmls.get('관련 콘텐츠', '')}
FAQ 스키마: {section_htmls.get('FAQ 스키마', '')}
Article 스키마: {section_htmls.get('Article 스키마', '')}
업데이트 정보: {section_htmls.get('업데이트 정보', '')}
[분량 가이드] 최소 1000자. 상한은 없습니다.

[작성 원칙]
- 이 ETF를 실제로 분석하면서 나온 결론을 쓰세요. 다른 종목에도 그대로 붙여 쓸 수 있는 문장은 피하세요.
- 반박 섹션이나 FAQ를 억지로 채우지 말고, 실제로 의미 있는 것만 남기세요.
{_build_previous_content_block(_prev_p1p2p3p4)}
[지켜야 할 절대 수치 (최종 팩트 시트)]
{facts_json_str}

[중요 지시사항]
- 위 JSON의 수치와 모순되는 내용을 작성하면 안 됩니다.
- 전체 5개 Part의 논리를 종합적으로 정리하며 마무리하세요.
- 새로운 정보를 추가하기보다는 Part 1~4를 집약하는 결론을 작성하세요.
- [숫자 재작성 절대 금지] 배당액·수익률·증감률처럼 위 [이전까지 실제로 작성된 본문]에 이미 구체적인 숫자로 나온 값은, 절대 기억에 의존해 다시 계산하거나 새로 쓰지 말고 그 문단을 그대로 다시 찾아 옮겨 적으세요. 특히 배당 지급액과 증감률은 반드시 Part2의 배당 내역 표에 나온 값과 정확히 일치해야 합니다(예: 표에 0.60 USD로 나왔다면 결론에서도 반드시 0.60 USD여야 하며, 0.8130 USD처럼 다른 값을 새로 지어내면 안 됩니다).
"""
    
    if session.get('p5'):
        p5 = session['p5']
        facts_p5 = session.get('p5_facts', {})
        if isinstance(p5, str) and p5.strip().startswith('{') and '"html"' in p5:
            try:
                parsed = json.loads(p5)
                p5 = parsed.get('html', p5)
                facts_p5 = parsed.get('facts', facts_p5)
                session['p5'] = p5
                session['p5_facts'] = facts_p5
                _save_generation_state(gen_state)
            except json.JSONDecodeError:
                pass
        print("✅ Part 5 재사용: 이전 실행에서 존재하는 생성 결과를 사용합니다.")
    else:
        print("🤖 Part 5 생성 중 (반박/결론/마무리)...")
        part5_prompt = part5_template + "\n[JSON Mode 지시사항]\n응답을 JSON 형식으로 출력하세요: {\"html\": \"생성된 HTML 콘텐츠\", \"facts\": {\"yields\": \"배당률\", \"expense_ratio\": \"운용보수\", \"returns_1m\": \"1개월 수익률\", \"returns_3m\": \"3개월 수익률\", \"returns_1y\": \"1년 수익률\", \"mdd\": \"최대낙폭\", \"dividend_growth_rate\": \"배당성장률\", \"key_metrics\": [\"주요 지표\"], \"conclusion\": \"핵심 결론\"}}"
        # [수정] 예전엔 p3+p4만 넘겨서 Part1(도입/기초), Part2(수익/시뮬레이션)이 둘 다
        # 빠졌음. Part5(결론/FAQ)가 이 두 파트 내용을 몰랐던 채로 검수됐다는 뜻이라,
        # 정확히 이 결론부에서 관찰된 거시 지표 반복이 왜 안 걸렸는지를 설명하는 원인.
        p5_raw, p5_quality = _generate_part_with_check(part5_prompt, 5, "Part5(반박/결론/마무리)", confirmed_text_so_far=p1 + "\n" + p2 + "\n" + p3 + "\n" + p4, session_key=current_session_key, label=session_label)
        if not p5_raw:
            print("❌ Part5 생성 실패")
            _save_generation_state(gen_state)
            return None, None
        p5 = p5_raw
        response_data = _load_raw_part_response(current_session_key, 5, label=session_label)
        if response_data is None:
            try:
                response_data = json.loads(p5)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}, _extract_facts_from_response 시도...")
                parsed = _extract_facts_from_response(p5, 5)
                response_data = parsed if isinstance(parsed, dict) else {"html": p5, "facts": {}}
        else:
            print("📝 Part5: 저장된 파일(raw_responses/)의 내용을 사용합니다 (사람이 직접 수정했을 수 있음).")
        p5 = response_data.get('html', p5)
        facts_p5 = response_data.get('facts', {})
        session['p5'] = p5
        session['p5_facts'] = facts_p5
        _save_generation_state(gen_state)
    
    print("📊 Part 5 팩트 시트 추출 중...")
    # 정보없음이 아닌 값만 업데이트 (기존 유효 데이터 보호)
    for key, value in facts_p5.items():
        if value and value != "정보없음" and value != "null" and value is not None:
            if isinstance(value, list) and not value:  # 빈 리스트 제외
                continue
            facts[key] = value
    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    print(f"✅ 최종 팩트 시트:\n{facts_json_str}")
    
    # AI 내용에서 온도계 중복 제거
    temp_pattern = r'<div[^>]*>[\s\n]*<(?:h3|div)[^>]*>🔥\s*투자\s*온도계.*?</div>[\s\n]*</div>'
    p1 = re.sub(temp_pattern, '', p1, flags=re.DOTALL)
    p2 = re.sub(temp_pattern, '', p2, flags=re.DOTALL)
    p3 = re.sub(temp_pattern, '', p3, flags=re.DOTALL)
    p4 = re.sub(temp_pattern, '', p4, flags=re.DOTALL)
    p5 = re.sub(temp_pattern, '', p5, flags=re.DOTALL)
    
    print("\n✅ 5단 분할 기사 생성 완료 (온도계 중복 제거)")
    # [신규] 4대 거시 온도계+종합 온도계는 맨 위 단일 온도계와 달리 글 맨 아래(결론부
    # 바로 뒤)에 배치한다 - 원래 계획이 "결론 역할"이었으므로 상단에 합치지 않는다.
    bottom_block = f"\n\n{macro_thermo_html}" if macro_thermo_html else ""
    final_blog_content = f"{investment_temperature_html}\n\n" + "\n\n".join([p1, p2, p3, p4, p5]) + bottom_block
    # [추가] 사후 교정(targeted fix)이 "특정 파트의 원문만" 골라 고칠 수 있도록,
    # 합쳐지기 전의 개별 파트 텍스트도 함께 반환한다. 기존 호출부(반환값 2개만
    # 받는 곳)와의 호환을 위해 3번째 반환값으로 추가하되 선택적으로 쓰도록 한다.
    parts_dict = {1: p1, 2: p2, 3: p3, 4: p4, 5: p5}
    return final_blog_content, facts_json_str, parts_dict


def _parse_inception_year(inception_date):
    if not inception_date or inception_date == '정보 없음':
        return None
    try:
        if isinstance(inception_date, (int, float)):
            return int(inception_date)
        date_str = str(inception_date)
        if date_str.isdigit():
            from datetime import datetime
            return datetime.fromtimestamp(int(date_str)).year
        for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%Y']:
            try:
                from datetime import datetime
                parsed = datetime.strptime(date_str.split()[0], fmt)
                return parsed.year
            except ValueError:
                continue
        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if year_match:
            return int(year_match.group())
    except (ValueError, TypeError) as e:
        print(f"⚠️ inception_date 파싱 실패: {type(e).__name__}: {e}")
        pass
    return None

def _get_available_crisis_periods(inception_year):
    if not inception_year:
        return []
    crisis_periods = [
        ("2000년 닷컴버블", 2000),
        ("2008년 금융위기", 2008),
        ("2020년 코로나", 2020),
        ("2022년 금리 인상/테크 조정", 2022),
    ]
    return [name for name, year in crisis_periods if inception_year <= year]


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


def _build_investment_temperature(etf_data_cache):
    values = []
    for d in etf_data_cache.values():
        score = d.get('custom_attractiveness_score')
        if isinstance(score, (int, float)):
            values.append(score)
        elif isinstance(score, str):
            try:
                values.append(float(score))
            except (ValueError, TypeError):
                continue

    if not values:
        return {
            'temp': 50,
            'desc': '중립',
            'color': '#f1c40f',
            'message': '현재 투자 매력도가 명확하지 않아 신중한 접근이 필요합니다.'
        }

    avg_score = sum(values) / len(values)
    temp = int(max(0, min(100, round((avg_score - 1) / 9 * 100))))

    if temp >= 80:
        desc = '매수 적절'
        color = '#27ae60'
        message = '보수적 투자자에게도 매수 매력이 높습니다.'
    elif temp >= 60:
        desc = '매수 우호'
        color = '#2ecc71'
        message = '현재 매수하기에 비교적 좋은 시점입니다.'
    elif temp >= 40:
        desc = '중립'
        color = '#f1c40f'
        message = '투자 타이밍이 중립적입니다. 신중히 접근하세요.'
    elif temp >= 20:
        desc = '관망'
        color = '#e67e22'
        message = '지금은 추가 자료 확인 후 매수를 결정하는 것이 좋습니다.'
    else:
        desc = '매수 위험'
        color = '#e74c3c'
        message = '현 시점에서 매수는 위험할 수 있으며 보수적인 관점이 필요합니다.'

    return {
        'temp': temp,
        'desc': desc,
        'color': color,
        'message': message
    }


def _build_temperature_banner_html(temperature_meta):
    return (
        f'<div style="margin:20px auto;padding:18px;border-radius:18px;background:#fcfcfc;border:1px solid #e0e0e0;max-width:760px;">'
        f'<div style="margin:0 0 10px 0;font-size:18px;font-weight:bold;color:#333;">🔥 투자 온도계: {temperature_meta["temp"]}° ({temperature_meta["desc"]})</div>'
        f'<div style="position:relative;height:18px;border-radius:9px;background:#ececec;overflow:hidden;margin:10px 0;">'
        f'<div style="width:{temperature_meta["temp"]}%;height:100%;background:{temperature_meta["color"]};transition:width 0.4s ease;"></div>'
        f'</div>'
        f'<p style="margin:0;font-size:13px;color:#555;">{temperature_meta["message"]}</p>'
        f'</div>'
    )


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










def _estimate_wp_url(final_facts_json_str):
    """[신규] 워드프레스 반자동(수동 붙여넣기) 발행 시, 실제 발행 URL을
    코드가 알 방법이 없으므로 recommended_url(팩트시트의 URL 슬러그 추천값)로
    예상 URL을 구성한다. 정확한 URL은 아니지만 저장 안 하는 것보다는 낫다."""
    estimated_wp_url = ''
    try:
        if WP_SITE_URL and final_facts_json_str:
            parsed_facts = json.loads(final_facts_json_str)
            slug = parsed_facts.get('recommended_url', '')
            if slug:
                estimated_wp_url = f"{WP_SITE_URL.rstrip('/')}/{slug}/"
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return estimated_wp_url






def _last_written_dates():
    """
    article_state.json을 읽어, 알려진 티커별 "가장 최근에 쓴 날짜"를 돌려준다.
    매칭 방식은 기존 _get_previous_analysis와 동일하게 "ticker_clean in title"
    부분일치를 쓴다 (제목에 티커가 그대로 들어가는 기존 관례를 그대로 따름).
    반환: { "QQQ": datetime(...), "SPY": datetime(...), ... }
    """
    state = _load_state()
    last_dates = {}
    for article in state.get('articles', []):
        ts = article.get('timestamp', '')
        if not ts:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        for ticker in _article_tickers(article):
            if ticker not in last_dates or ts_dt > last_dates[ticker]:
                last_dates[ticker] = ts_dt
    return last_dates


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

def plan_article(ticker, series_context="", selection_reason=""):
    """
    [3번 부서: 기획] 승인된 티커에 대해 실제 글쓰기(Part1~5) 전에, 이번 글의
    핵심 메시지/강조점/차별화 지점을 한 번 정리한다. series_context(지난
    분석과 뭐가 달라졌는지 - 기존 코드에 이미 있는 정보)를 재료로 쓴다.

    실패하면 None을 돌려주고, 호출한 쪽은 이 기획 없이(지금까지 해오던
    방식 그대로) 진행한다 - 있으면 좋고 없어도 파이프라인이 안 죽는 설계.
    """
    prompt = f"""당신은 ETF 분석 블로그의 콘텐츠 기획자입니다.
아래 정보를 보고, 이번 글을 어떻게 풀어갈지 간단히 기획해주세요.

티커: {ticker}
이 주제가 선정된 이유: {selection_reason or "(자동 선정)"}

[시리즈 맥락 - 과거에 이 티커를 다룬 적 있다면 그 내용]
{series_context.strip() or "(이 티커를 처음 다룹니다 - 과거 시리즈 없음)"}

반드시 JSON 형식으로만 답하세요:
{{"key_message": "이번 글에서 가장 강조할 핵심 메시지 1문장",
  "emphasis_points": ["강조할 포인트1", "강조할 포인트2", "강조할 포인트3"],
  "differentiation": "지난 글과 다르게 다룰 지점 (처음 다루는 티커면 '해당 없음'이라고 답)"}}
"""
    raw = get_gemini_response(prompt, thinking_budget=0)
    if raw is None:
        print("⚠️ 기획 단계 생성 실패(API 소진 등) - 기획 없이 기존 방식대로 글쓰기를 진행합니다.")
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        print("⚠️ 기획 결과 JSON 파싱 실패 - 기획 없이 기존 방식대로 글쓰기를 진행합니다.")
        return None


def _plan_to_context_block(plan):
    """plan_article()의 결과를 collected_context에 붙일 수 있는 텍스트 블록으로 변환."""
    if not plan:
        return ""
    points = "\n".join(f"  - {p}" for p in plan.get("emphasis_points", []))
    return (
        f"\n[기획 방향 - 3번 부서가 미리 정한 이번 글의 방향]\n"
        f"- 핵심 메시지: {plan.get('key_message', '')}\n"
        f"- 강조할 포인트:\n{points}\n"
        f"- 지난 글과 차별화: {plan.get('differentiation', '')}\n"
        f"-> [지시] 위 기획 방향을 본문 전개에 실제로 반영하세요.\n\n"
    )


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

    total = len(recent)
    fallback_count = sum(1 for a in recent if 'selenium' in a.get('notes', '') or 'manual paste' in a.get('notes', ''))
    low_quality_count = sum(1 for a in recent if 'low quality override' in a.get('notes', ''))

    lines = [f"📊 이번 주 발행 현황 ({week_ago.date()} ~ {now.date()})", ""]
    lines.append(f"총 발행: {total}편")
    if total > 0:
        lines.append(f"API 완전자동 발행: {total - fallback_count}편")
        lines.append(f"반자동(Selenium/수동 붙여넣기) 폴백: {fallback_count}편")
        if low_quality_count:
            lines.append(f"⚠️ 품질 낮음에도 강제 발행된 글: {low_quality_count}편 - 한 번 확인해보시는 걸 추천해요")
    else:
        lines.append("이번 주 발행된 글이 없습니다 - 워크플로우가 정상 실행되고 있는지 확인해보세요.")

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

    message = "\n".join(lines)
    _telegram_send_message(message)
    print("✅ 주간 상태 점검 리포트 전송 완료")
    print(message)


# ============================================================
# [신규] 홍보팀 - 발행 완료 시 Threads에 카드형 요약 자동 게시
# ============================================================

# 발굴 대상 12개 티커에 대한 한 줄 소개. 매번 API로 새로 만들지 않고
# 고정 문구를 재사용해서 완전 무료로 유지한다 (일반적으로 알려진 사실이라
# 자주 바뀌지 않음 - 상품 구조가 바뀌면 이 표만 수정하면 됨).
ETF_INTRO_MAP = {
    "QQQ": "나스닥100 지수를 추종하는 대형 기술주 중심 ETF",
    "QQQM": "QQQ와 같은 지수를 추종하지만 보수가 더 낮은 저비용 버전",
    "TQQQ": "나스닥100을 3배 레버리지로 추종하는 고위험·고변동 ETF",
    "SPY": "S&P500 지수를 추종하는 미국 대표 대형주 ETF",
    "IVV": "SPY와 같은 S&P500을 추종하는 초저보수 ETF",
    "VOO": "뱅가드가 운용하는 S&P500 추종 ETF, 낮은 보수로 인기",
    "VTI": "미국 대형~소형주 전체 시장에 투자하는 ETF",
    "IWM": "러셀2000 지수를 추종하는 미국 중소형주 ETF",
    "EFA": "미국을 제외한 선진국(유럽·일본 등) 주식에 투자하는 ETF",
    "EEM": "중국·인도 등 신흥국 주식에 투자하는 ETF",
    "GLD": "실물 금 가격을 추종하는 대표적인 금 ETF",
    "SLV": "실물 은 가격을 추종하는 대표적인 은 ETF",
}


# 카드 이미지 크기. 1080x1350은 인스타/스레드에서 가장 무난하게 쓰이는
# 4:5 세로 비율 - 스레드 피드에서 화면을 많이 차지해 눈에 잘 띈다.




def build_card_cover_html(ticker):
    """1번 카드: 표지 - 티커를 크게 보여줘서 눈에 띄게."""
    body = f"""
    <div style="font-size:38px; color:#38bdf8; letter-spacing:4px; margin-bottom:24px;">TODAY'S ETF BRIEFING</div>
    <div style="font-size:180px; font-weight:800; color:#ffffff; letter-spacing:2px;">{ticker}</div>
    <div style="font-size:44px; color:#cbd5e1; margin-top:32px;">지금 어떤 상황일까요?</div>
    """
    return _card_html_shell(body)


def build_card_data_html(ticker, intro, signal):
    """2번 카드: 핵심 데이터 - 등락률과 ETF 소개."""
    pct = signal["pct_change"] if signal else None
    if pct is not None:
        color = "#f87171" if pct >= 0 else "#60a5fa"  # 빨강=상승, 파랑=하락 (국내 표기 관행)
        sign = "+" if pct >= 0 else ""
        price_html = f'<div style="font-size:120px; font-weight:800; color:{color};">{sign}{pct}%</div><div style="font-size:32px; color:#94a3b8; margin-bottom:56px;">전일 대비</div>'
    else:
        price_html = ""
    body = f"""
    {price_html}
    <div style="font-size:34px; color:#38bdf8; margin-bottom:16px;">📌 뭐하는 ETF?</div>
    <div style="font-size:42px; color:#f1f5f9; text-align:center; line-height:1.5;">{intro}</div>
    """
    return _card_html_shell(body)


def build_card_cta_html(key_message):
    """3번 카드: 핵심 메시지 + CTA. URL은 이미지가 아니라 게시물 텍스트에 넣는다
    (이미지 안의 링크는 클릭이 안 되므로)."""
    body = f"""
    <div style="font-size:34px; color:#38bdf8; margin-bottom:32px;">💡 오늘의 핵심</div>
    <div style="font-size:46px; color:#f1f5f9; text-align:center; line-height:1.6; margin-bottom:64px;">{key_message}</div>
    <div style="font-size:36px; color:#94a3b8;">👉 전체 분석은 게시글 링크에서</div>
    """
    return _card_html_shell(body)




def build_card_news_images(driver, ticker, plan, output_dir="."):
    """
    [홍보팀 - 카드뉴스 제작] 3장짜리 카드뉴스(표지/데이터/핵심메시지)를
    이미지 파일로 렌더링한다. 반환: 성공한 이미지 경로 리스트(실패한 카드는
    건너뛰고 나머지만 반환 - 최소 2장은 있어야 캐러셀로 게시 가능).
    """
    intro = ETF_INTRO_MAP.get(ticker, f"{ticker} ETF")
    signal = _get_price_volume_signal(ticker)
    key_message = (plan or {}).get("key_message", "") or f"{ticker}, 지금 확인해볼 타이밍일 수 있어요."

    cards = [
        ("cover", build_card_cover_html(ticker)),
        ("data", build_card_data_html(ticker, intro, signal)),
        ("cta", build_card_cta_html(key_message)),
    ]

    image_paths = []
    for name, html_str in cards:
        out_path = os.path.join(output_dir, f"threads_card_{name}_{int(time.time())}.png")
        if _render_html_to_image(driver, html_str, out_path):
            image_paths.append(out_path)
    return image_paths






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











def build_threads_promo_post(ticker, plan, article_url):
    """
    [텍스트 폴백용] 카드뉴스 이미지 업로드가 실패했을 때(예: 워드프레스
    API가 요금제상 막혀있는 경우) 쓰는 기존 텍스트 카드형 게시물.
    """
    intro = ETF_INTRO_MAP.get(ticker, f"{ticker} ETF")
    key_message = (plan or {}).get("key_message", "")

    price_line = ""
    signal = _get_price_volume_signal(ticker)
    if signal:
        sign = "+" if signal["pct_change"] >= 0 else ""
        price_line = f"전일 대비 {sign}{signal['pct_change']}%\n"

    def _compose(message):
        return (
            f"📊 {ticker}, 지금 어떤 상황일까요?\n\n"
            f"📌 뭐하는 ETF?\n{intro}\n\n"
            f"📈 최근 동향\n{price_line}{message}\n\n"
            f"👉 전체 분석: {article_url}"
        )

    text = _compose(key_message)
    if len(text) > 500:
        overflow = len(text) - 500
        trimmed = key_message[:max(0, len(key_message) - overflow - 3)] + "..." if key_message else ""
        text = _compose(trimmed)
    return text[:500]




def promote_published_article(driver, etf_list, plan, article_url):
    """
    [홍보팀 진입점] 발행이 실제로 확정된 직후 호출한다.

    시도 순서:
    1) 카드뉴스 3장 렌더링 (Selenium 스크린샷, 완전 무료)
    2) 워드프레스 미디어 라이브러리에 업로드해서 공개 URL 확보
    3) Threads에 캐러셀로 게시
    4) 위 중 어느 하나라도 실패하면 -> 기존 텍스트 카드형 게시물로 폴백
    5) (사람 대상 홍보와 별개로) 검색엔진 알림 - IndexNow로 Bing/Yandex/네이버에 즉시 통보

    전체가 실패해도 예외를 던지지 않는다 - 홍보는 부가 기능이라 이것 때문에
    발행 자체가 실패로 취급되면 안 된다.
    """
    if not etf_list:
        return
    primary_ticker = etf_list[0].replace(".KS", "")

    # 검색엔진 알림은 사람 대상 홍보(Threads)와 완전히 독립적이라 따로 시도한다.
    ping_indexnow(article_url)

    try:
        image_paths = build_card_news_images(driver, primary_ticker, plan)
        image_urls = []
        for path in image_paths:
            url = _upload_image_to_wordpress(path)
            if url:
                image_urls.append(url)
            try:
                os.remove(path)
            except OSError:
                pass

        if len(image_urls) >= 2:
            caption = f"오늘의 ETF 브리핑: {primary_ticker}\n\n전체 분석: {article_url}"
            if _threads_post_carousel(image_urls, caption[:500]):
                return
            print("⚠️ 카드뉴스 캐러셀 게시 실패 - 텍스트 홍보로 폴백합니다.")
        else:
            print("ℹ️ 카드뉴스 이미지 업로드가 부족해(요금제 제한 등) 텍스트 홍보로 폴백합니다.")

        text = build_threads_promo_post(primary_ticker, plan, article_url)
        _threads_post(text)
    except Exception as e:
        print(f"⚠️ 홍보 게시 중 예상치 못한 오류(무시하고 계속 진행): {type(e).__name__}: {e}")





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


def _pause(prompt):
    """무인 실행 모드에서는 마지막 '엔터 누르면 종료' 대기를 건너뛴다."""
    if os.environ.get("NONINTERACTIVE"):
        return
    input(prompt)


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

    # [수정] RSS 조회를 시리즈 추적보다 먼저 실행하도록 순서를 옮김 -
    # 시리즈 추적(_get_previous_analysis)이 이 실제 RSS 데이터로 저장된
    # "추정 URL"을 실제 확인된 URL로 보정할 수 있게 하기 위함.
    # 이전에는 PLATFORM과 무관하게 항상 BLOG_NAME(티스토리 전용 변수)을
    # 보고 있어서, 워드프레스로 발행할 때는 관련 콘텐츠(다른 종목 글끼리
    # 서로 링크)를 위한 기존 글 목록 조회가 항상 실패하고 있었음.
    # PLATFORM에 맞는 실제 사이트 주소를 쓰도록 수정.
    rss_target_site = WP_SITE_URL if PLATFORM == "wordpress" else BLOG_NAME
    rss_posts = get_tistory_rss_links(rss_target_site) if rss_target_site else []
    rss_context = ""
    if rss_posts:
        rss_context = "[내 블로그 기존 글 목록(내부 링크용)]\n" + "\n".join([f"- 제목: {p['title']} (URL: {p['url']})" for p in rss_posts]) + "\n\n"
        print(f"✅ 기존 글 {len(rss_posts)}개 링크 확보 완료!")
    else:
        print("ℹ️ 기존 글 목록이 없습니다. 관련 콘텐츠(가상 링크) 생성을 생략합니다.")

    # 시리즈 추적: 이전 분석 정보 수집 (rss_posts로 URL 정확도 보정)
    previous_analyses = _get_previous_analysis(etf_list, today_str, rss_posts=rss_posts)
    series_context = ""
    for ticker_clean, analysis in previous_analyses.items():
        if analysis['previous']:
            prev = analysis['previous']
            series_context += f"[{ticker_clean} 시리즈 이전(v{prev['version']}) 분석 데이터]\n"
            prev_day = prev['date_display']
            series_context += f"- 이전 분석일: {prev_day} (오늘은 {today_str}. 두 날짜를 혼동하지 마세요)\n"
            
            # 이전 팩트 데이터 추출
            past_data = None
            for key, val in prev.get('etf_data', {}).items():
                if ticker_clean in key:
                    past_data = val
                    break
            
            if past_data:
                past_yield = past_data.get('yield', '기록 없음')
                past_mdd = past_data.get('mdd', '기록 없음')
                past_1y_ret = past_data.get('returns', {}).get('1년', '기록 없음')
                if isinstance(past_1y_ret, float):
                    past_1y_ret = f"{past_1y_ret:.2f}%"
                series_context += f"- [과거 지표] 배당률: {past_yield} / MDD: {past_mdd} / 1년 수익률: {past_1y_ret}\n"
                series_context += "-> [필수 지시]: 서론 및 본문 작성 시, 현재 데이터와 위의 과거 데이터를 반드시 대조하십시오. 수익성(수익률/배당)과 리스크(MDD)가 지난 분석 대비 어떻게 변했는지 팩트 기반으로 비교 서술해야 합니다.\n\n"
            else:
                series_context += f"- 이전 글 URL: {prev['url']}\n\n"

            # [개선] 같은 티커를 재작성할 때, 지난번과 똑같은 섹션 구성/비중으로
            # 글이 나오면 "재탕 콘텐츠"로 보일 위험이 있음. 이전 글에서 실제로
            # 다룬 섹션 제목을 추출해, 이번에는 다른 섹션에 무게를 싣도록 명시적으로 지시.
            prev_content = prev.get('content', '')
            if prev_content:
                prev_sections = _extract_section_titles(prev_content)
                if prev_sections:
                    series_context += (
                        f"- [이전 글에서 다룬 섹션들]: {', '.join(prev_sections)}\n"
                        "-> [구성 차별화 필수 지시]: 이번 글이 위 섹션들과 똑같은 비중, 똑같은 순서, "
                        "똑같은 관점으로 구성되면 '재탕 콘텐츠'로 취급됩니다. 위에서 이미 깊게 다룬 "
                        "주제는 이번엔 수치 업데이트 정도로 짧게만 언급하고, 대신 지난번에 상대적으로 "
                        "덜 다뤘던 각도(예: 경쟁 ETF 변화, 거시경제 국면 변화, 새로운 리스크 요인 등)를 "
                        "이번 글의 중심으로 삼아 실질적으로 다른 글이 되도록 작성하십시오.\n\n"
                    )
    
    print(f"✅ 시리즈 추적 완료 - {'업데이트' if any(a['previous'] for a in previous_analyses.values()) else '첫 분석'}")
    
    macro_data = get_macro_data()
    print(f"✅ 수집 완료 - 환율: {macro_data['usd_krw']} / 금리: {macro_data['us_10y']} / 공포탐욕지수: {macro_data['fear_greed']}")

    driver = _create_chrome_driver()
    
    quote_data = get_unique_quote()
    print(f"✅ 선택된 명언: {quote_data['kor']} - {quote_data['author']}")

    tooltip_style = """
<style>
.finq-tip { position: relative; display: inline; border-bottom: 1px dashed #4A90E2; color: #1f3c88; cursor: help; font-weight: bold; }
.finq-tip .finq-tip-text { visibility: hidden; width: 260px; background-color: #1f3c88; color: #fff; text-align: left; border-radius: 8px; padding: 10px 14px; position: absolute; z-index: 999; bottom: 130%; left: 50%; transform: translateX(-50%); opacity: 0; transition: opacity 0.2s ease-in-out; font-size: 13px; font-weight: normal; line-height: 1.6; box-shadow: 0 6px 16px rgba(0,0,0,0.18); word-break: keep-all; }
.finq-tip .finq-tip-text::after { content: ""; position: absolute; top: 100%; left: 50%; margin-left: -6px; border-width: 6px; border-style: solid; border-color: #1f3c88 transparent transparent transparent; }
.finq-tip:hover .finq-tip-text,
.finq-tip:focus .finq-tip-text {
    visibility: visible;
    opacity: 1;
}
.finq-tip:focus { outline: none; }
</style>
"""

    recent_issues = _get_recent_economic_issues(macro_data)

    fx_text = ""
    if macro_data.get('is_fx_volatile'):
        diff_pct = macro_data.get('usd_krw_diff_pct', 0)
        direction = macro_data.get('usd_krw_direction', '')
        fx_text = (
            f"- 원/달러 환율: {macro_data['usd_krw']} (전일 대비 {diff_pct:.2f}% {direction} 급변동 발생. "
            f"반드시 본문에서 '전일 대비 {diff_pct:.2f}% {direction}했다'는 수치를 명시하고 환율 리스크를 분석할 것)\n"
        )

    collected_context = rss_context + (
        f"[오늘의 거시경제 지표]\n"
        f"{fx_text}"
        f"- 미국 10년물 국채 금리: {macro_data['us_10y']}\n"
        f"- 공포/탐욕 지수(Fear & Greed): {macro_data['fear_greed']}\n"
        f"\n[거시 원시 신호 - 그대로 복사 금지, 이 ETF 특성과 연결해 직접 해석할 것]\n- {recent_issues}\n\n"
    )
    widget_items = []
    is_multi = len(etf_list) >= 2
    wrapper_style = "flex: 1 1 45%; max-width: 48%; min-width: 320px; margin: 10px; box-sizing: border-box;" if is_multi else "width: 100%; max-width: 700px; margin: 30px auto;"
    
    us_etf_tickers = [t for t in etf_list if not t.endswith(".KS")]
    has_us_etf = bool(us_etf_tickers)
    title_tickers = ", ".join(t.replace(".KS", "").replace(".US", "") for t in etf_list)

    # [신규] raw_responses/ 폴더에 저장될 파일명을 사람이 알아보기 쉽게 구성.
    # 예: "2026-07-06_IBIT" - 세션키(해시)만으로는 어떤 글인지 파일명만 보고
    # 알 수 없었던 문제를 해결하기 위함.
    file_date_str = now.strftime("%Y-%m-%d")
    ticker_label = "_".join(t.replace(".KS", "").replace(".US", "") for t in etf_list) or "unknown"
    session_label = f"{file_date_str}_{ticker_label}"

    etf_crisis_info = {}
    etf_data_cache = {}

    # 환율 정보 추출 (기본값: 1300원) - 루프마다 반복 계산할 필요 없어 미리 계산
    usd_krw_str = macro_data.get('usd_krw', '1300')
    try:
        usd_krw_rate = float(usd_krw_str.replace('원', '').replace(',', ''))
    except (ValueError, AttributeError):
        usd_krw_rate = 1300.0

    for ticker in etf_list:
        d = get_etf_real_data(ticker, driver, macro_data)
        if d:
            etf_data_cache[ticker] = d
            ret_str = "".join(f"{k}: {v:.2f}%\n" for k, v in d['returns'].items())
            div_str = "\n".join(f"- {i['date']}: {i['val']} (이전 대비: {i.get('change', '-')})" for i in d['div_history'])

            # [수정] 코드가 이미 정확히 계산해둔 "배당 안정성 요약 결론"
            # (dividend_stability_desc, 예: "최근 4회 중 1회는 감소")이 지금까지
            # AI에게 전혀 전달되지 않고 있었다. AI는 개별 배당 내역 나열(div_str)만
            # 보고 스스로 "전부 증가했다" 등으로 요약을 시도했는데, 이 자체
            # 요약 과정에서 실수가 나서 파트마다 다른 결론(Part2는 "전부 증가",
            # Part4는 "1회 감소")을 내리는 모순이 실제로 발생했다. 이제 코드가
            # 이미 정확히 계산해둔 결론 문장을 명시적으로 같이 주고, "이 결론을
            # 그대로 인용하고 스스로 다시 요약/계산하지 말라"고 못박는다.
            div_stability_line = ""
            if d.get('dividend_stability_desc'):
                div_stability_line = (
                    f"- [배당 안정성 결론(반드시 이 문장을 그대로 인용, 스스로 다시 판단하지 마세요)]: "
                    f"{d['dividend_stability_desc']}\n"
                )

            widget_items.append(_create_widget_html(ticker, d, wrapper_style, usd_krw_rate))
            
            inception_year = _parse_inception_year(d.get('inception_date'))
            available_crises = _get_available_crisis_periods(inception_year)
            etf_crisis_info[ticker] = {
                'inception_year': inception_year,
                'inception_date_raw': d.get('inception_date', '정보 없음'),
                'available_crises': available_crises,
                'is_recent': inception_year and inception_year >= 2008 if inception_year else None
            }
            
            tax_m = _estimate_account_tax_impact(d.get('yield'), overseas=_is_overseas_listed(d))
            collected_context += (
                f"[{ticker} 핵심 데이터]\n"
                f"- 종목명: {d['name']} / 운용사: {d['issuer']} / 지수: {d['index']}\n"
                f"- 분류: {d['sector']} (산업: {d['industry']})\n"
                f"- 보수: {d['expense_ratio']} / 배당: 수익률({d['yield']}), 주기({d['div_cycle']})\n"
                f"- 상장일: {d.get('inception_date', '정보 없음')}\n"
                f"- [수익률 데이터(필수사용)]:\n{ret_str}"
                f"- [최근 배당내역(필수사용)]:\n{div_str}\n"
                f"{div_stability_line}"
                f"- [최대 낙폭(MDD, 5년 기준)]: {d['mdd']}\n"
                f"- [배당성장률]: {d.get('dividend_growth_rate', '정보 없음')} / [환노출 여부]: {d.get('fx_exposure', 'N/A')} "
                f"(주의: 이 ETF가 실제로 환헤지 상품인지는 별도로 확인된 사실이 아니므로, '환헤지 비용'이라는 표현은 쓰지 말고 '환노출 리스크'로만 서술하세요)\n"
                f"- [투자 매력도 점수]: {d.get('custom_attractiveness_score', '정보 없음')} (사유: {', '.join(d.get('custom_attractiveness_notes', []))})\n"
                f"- [세금 시뮬레이션(배당 1억 기준)]: 과세계좌 {tax_m.get('taxable_dividend_tax', 'N/A')}, "
                f"ISA 절세 {tax_m.get('isa_tax_saving', 'N/A')}, "
                f"IRP/연금저축 절세 {tax_m.get('irp_tax_saving', 'N/A')} "
                f"(기준: {tax_m.get('notes', '')})\n"
                f"- [계좌 안내(필수 반영)]: {OVERSEAS_ACCOUNT_NOTE if _is_overseas_listed(d) else '국내 상장 ETF라 ISA·연금저축·IRP로 매수 가능'}\n"
                f"- [운용보수 1억 10년 영향]: {d.get('fee_impact_100m_10y', '정보 없음')}\n"
                f"- [1,000만 원 투자 시뮬레이션]: {d['simulated_result']}\n"
                f"- 공식 홈페이지 URL: {d['website']}\n"
                f"- 인베스팅닷컴 실시간 데이터 URL: {d['investing_url']}\n"
                f"- 통화: {d['currency']} / 요약: {d['description']}\n"
            )
    
    recent_news = _get_recent_news_for_etfs(etf_data_cache, macro_data)
    if recent_news:
        collected_context += "[최근 주요 뉴스]\n" + "\n".join([f"- {item['title']} ({item['source']}) {item['url']}" for item in recent_news]) + "\n\n"
        print(f"✅ 최근 뉴스 {len(recent_news)}건 수집 완료")
    else:
        collected_context += "[최근 주요 뉴스]\n- 뉴스 데이터를 수집하지 못했습니다.\n\n"
        print("⚠️ 최근 뉴스 수집 실패")

    # [신규] "정정 이력" 섹션 - etf_data_cache가 완전히 채워진 이 시점에서
    # 안전하게 생성. previous_analyses는 위쪽(series_context 조립부)에서 이미
    # 계산되어 있음.
    revision_history_html = _build_revision_history_section(previous_analyses, etf_data_cache, today_str)

    if has_us_etf:
        collected_context += (
            f"[미국 ETF 감지]\n- 미국 ETF 티커: {', '.join(us_etf_tickers)}\n- 한국 투자자 관점 필수 포함: 환율 변동 영향, 국내 상장 동일 지수 ETF와 비교(수수료·세금 등)\n"
            f"- [상장 위치(사실)]: {', '.join(us_etf_tickers)}는 미국 거래소에 상장된 ETF입니다. 한국 투자자 입장에서는 '해외 상장 ETF'라고만 쓰고, "
            f"'미국 외 국가에 상장' 같은 표현이나 이중 부정 문장('~가 아닌 해외 상장')은 쓰지 마세요.\n"
        )

    widgets_html_block = f'<div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; width: 100%; margin: 30px auto;">{"".join(widget_items)}</div>' if is_multi else "".join(widget_items) + "<br>"

    # [교체] 이전에는 Portfolio Visualizer를 셀레니움으로 조작해 스크린샷을 찍으려 했으나,
    # 외부 사이트 UI가 바뀌며 계속 실패했고(엉뚱한 샘플 포트폴리오 화면이 찍힘), 애초에
    # 본문에 자동 삽입되지도 않는 죽은 코드였음. 이미 갖고 있는 가격 데이터로 직접
    # "거치식 vs 적립식" 시뮬레이션 그래프를 그려 외부 의존성 없이 안정적으로 대체함.
    backtest_sim_charts = []
    backtest_results_by_ticker = {}  # [신규] 티커별 백테스트 계산 결과 보관 - 다른 섹션에서 재사용
    for ticker in etf_list:
        d = etf_data_cache.get(ticker)
        if d:
            chart_html, backtest_result = _create_backtest_simulation_chart(ticker, d, wrapper_style, usd_krw_rate)
            if chart_html:
                backtest_sim_charts.append(chart_html)
            if backtest_result:
                backtest_results_by_ticker[ticker] = backtest_result
    backtest_sim_html = "".join(backtest_sim_charts)

    # [신규] 손익 캘린더 - 접힌 상태로 제공되는 심화 시각자료 (기본은 <details> 닫힘)
    calendar_charts = []
    for ticker in etf_list:
        d = etf_data_cache.get(ticker)
        if d:
            cal_html = _create_return_calendar_heatmap(ticker, d, wrapper_style, usd_krw_rate)
            if cal_html:
                calendar_charts.append(cal_html)
    calendar_html = "".join(calendar_charts)

    # [정리] table_style/th_style/td_style/blockquote_style/toc_box_style는
    # 어디서도 실제로 참조되지 않는 죽은 변수였음(과거 버전의 잔재로 추정).
    # 값 개수와 순서는 그대로 유지하되(다른 실제 사용 변수들과의 매핑이
    # 깨지지 않도록), 미사용임을 명시적으로 표시.
    (
        _table_style_unused,
        _th_style_unused,
        _td_style_unused,
        _blockquote_style_unused,
        quote_box_style,
        glossary_box_style,
        bio_box_style,
        _toc_box_style_unused,
        disclaimer_box_style,
    ) = (
        'style="border-collapse: collapse; width: 100%; max-width: 650px; margin: 20px auto; border: 1px solid #eee; font-size: 16px;"',
        'style="border: 1px solid #ddd; padding: 12px; text-align: center; background-color: #f9f9f9; font-weight: bold; color: #333;"',
        'style="border: 1px solid #ddd; padding: 10px; text-align: center; color: #555;"',
        'style="font-size: 1.0em; color: #555; background-color: #fcfcfc; border-left: 5px solid #4A90E2; padding: 18px; margin: 25px 0; line-height: 1.7;"',
        'style="position: relative; text-align: center; padding: 30px 30px 26px; margin: 32px 0; background: #fbfbfa; border-top: 1px solid #e5e5e5; border-bottom: 1px solid #e5e5e5;"',
        'style="margin-top: 55px !important; padding-top: 25px !important; border-top: 1px solid #eaeaea !important; font-size: 12px !important; color: #888 !important; line-height: 1.5 !important;"',
        'style="margin-top: 45px; padding: 25px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e9ecef; display: flex; align-items: center; gap: 18px;"',
        'style="background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px; padding: 25px; margin: 35px 0;"',
        'style="margin: 30px 0; padding: 20px; background-color: #fff8e6; border: 1px solid #ffd966; border-radius: 10px; font-size: 14px; color: #5c4a00; line-height: 1.7;"',
    )

    title_prefix = "[ETF 비교]" if len(etf_list) > 1 else "[ETF 분석]"
    
    # 시리즈 버전 반영
    for ticker_clean, analysis in previous_analyses.items():
        if analysis['previous']:
            title_prefix = f"[ETF 분석 v{analysis['current_version']}]"
            break  # 첫 번째 ETF의 버전 사용
    title_candidates = [
        [
            f"{current_year}년 {title_tickers} 비교 — 수익률·배당·보수 한 번에 정리",
            f"{title_tickers}, 지금 담기 전 꼭 체크할 3가지(수익률·배당·리스크)",
            f"{title_tickers} 장단점 정리 — 같은 지수인데 결과가 다른 이유",
            f"{title_tickers} ETF, 장기 투자 전 알아두면 좋은 핵심 포인트",
            f"{title_tickers} 비교 분석: 수익률 vs 배당 vs 리스크 균형점 찾기",
            f"{current_year}년 {title_tickers} 투자 가이드: 데이터로 보는 장단기 전망",
            f"{title_tickers} 선택의 기준: 보수와 성과의 상관관계",
            f"{title_tickers} ETF 포트폴리오 구축: 다각화의 핵심"
        ],
        [
            f"{current_year}년 {title_tickers} — 환율·세금까지 고려한 현실적인 수익률 점검",
            f"{title_tickers}, 미국 ETF에 처음 들어가려는 분이 꼭 확인할 부분",
            f"{title_tickers} 수익률이 예전 같지 않게 느껴진다면(환율·금리·밸류에이션 점검)",
            f"{title_tickers} — 달러 기준 vs 원화 기준 성과, 어디까지 봐야 할까?",
            f"{title_tickers} 투자, 지금이 적기일까? 수익률과 리스크 분석",
            f"{current_year}년 {title_tickers} 성과 리뷰: 배당과 환율의 영향",
            f"{title_tickers} ETF의 숨겨진 매력: 보수와 세금을 넘어선 가치",
            f"{title_tickers} — 미국 주식 시장의 거울, 현재 상태는?"
        ],
        [
            f"{current_year}년 {title_tickers} — 배당률·보수·변동성까지 함께 보는 현실적인 분석",
            f"{title_tickers}, 배당률만 보고 선택하기 전에 생각해 볼 점들",
            f"{title_tickers} — 과거 조정 구간과 비교해 본 리스크와 기회",
            f"{title_tickers} 한 번에 정리: 수익률·배당·보수·리스크 핵심 요약",
            f"{title_tickers} 배당 투자 전략: 안정성과 성장성의 균형",
            f"{current_year}년 {title_tickers} 변동성 분석: 리스크 관리의 핵심",
            f"{title_tickers} ETF의 진정한 가치: 보수율이 말해주는 것",
            f"{title_tickers} 투자 포인트: 배당과 성과의 상호작용"
        ]
    ]
    chosen_hint = random.choice(title_candidates[0 if is_multi else 1 if has_us_etf else 2])
    title_pattern_hint = f"{title_prefix} {chosen_hint}"

    # [신규] 서론 시작 방식을 매번 다르게 선택.
    # 이전에는 모든 글이 예외 없이 "안녕하세요, 온도(ondo)입니다."로 시작해서,
    # 개별 글의 내용은 달라도 여러 글에 걸쳐 서사 뼈대가 완전히 동일하다는
    # 구조적 반복 신호가 됐음(다른 실패 사례 블로그의 "지인 에피소드가 매번
    # 반복되는" 패턴과 근본적으로 같은 문제). 아래 스타일 중 매번 다른 것을
    # 골라 다양성을 준다. 단, 거짓 경험담(지인 에피소드 등)은 여기에 포함하지
    # 않는다 - 그건 별도로 이미 금지되어 있고, 다양화 대상이 아니라 아예
    # 없어야 할 항목이기 때문.
    intro_styles = [
        "인사말 없이 바로 현재 거시경제 상황(환율/금리/공포탐욕지수)을 한두 문장으로 요약하며 시작하세요.",
        "이 ETF와 관련해 최근 실제로 일어난 뉴스나 시장 반응을 언급하며 시작하세요 (지어내지 말고, 제공된 [최근 경제 이슈]나 뉴스 데이터에 실제로 있는 내용만 사용).",
        "독자가 이 ETF에 대해 가질 법한 자연스러운 질문(예: '지금 들어가도 될까?')을 던지며 시작하세요. 특정 인물이나 지인의 질문으로 꾸미지 말고, 일반적인 궁금증으로 제시하세요.",
        "이 ETF의 가장 눈에 띄는 실제 수치(수익률, MDD, 배당률 중 하나) 하나를 먼저 던지고, 그 숫자가 의미하는 바를 풀어가며 시작하세요.",
        "이 ETF에 대한 흔한 오해나 인식(예: '고배당이니 안전하다')을 먼저 언급한 뒤, 실제 데이터가 그와 어떻게 다른지 대비시키며 시작하세요. 오해의 출처를 지어내지 말고 일반적인 통념으로만 제시하세요.",
    ]
    chosen_intro_style = random.choice(intro_styles)

    # -----------------------------------------------------------------
    # [통제된 완전 랜덤 (Controlled Randomness) 로직 적용]
    # -----------------------------------------------------------------
    # 1. 무한 셔플 블록 (본문 순서 랜덤)
    body_sections = ["기초정보+차트", "수익률+배당", "리스크"]
    if has_us_etf:
        body_sections.append("미국 ETF 특화 분석")
    random.shuffle(body_sections)
    body_order_str = " → ".join(body_sections)

    # 2. 선택적 요소 (On/Off 랜덤)
    # [수정] 목차는 이전에 다른 요소들과 똑같이 50% 확률로 랜덤 On/Off였는데,
    # 이건 과했음 - 목차는 긴 글(이 코드가 만드는 글은 보통 6천자 이상)의
    # 가독성과 SEO(검색결과 요약 노출 등)에 실질적으로 기여하는 요소라, 매번
    # 동전 던지듯 통째로 빠지면 안 됨. 목차는 항상 켜고, 나머지 순수 장식성
    # 요소만 다양성을 위해 계속 랜덤으로 둔다. 용어사전은 실제 유익한 정보라
    # 아예 끄기보다 등장 확률을 더 높인다(75%).
    include_toc = True
    include_quote = random.choice([True, False])
    # [정리] include_bio는 제거함 - 작가 프로필은 후처리 단계(_inject_static_sections)가
    # 이미 항상 강제로 삽입하고 있어서, 랜덤으로 껐다 켰다 하는 게 의미가 없었음
    # (AI에게 "넣지 마라" 지시해도 결국 코드가 강제로 붙이는 모순된 구조였음).
    include_glossary = random.random() < 0.75

    # 3. 디자인 요소 랜덤 (요약 박스 색상 랜덤 변경)
    summary_styles = [
        {"bg": "#f0f7ff", "border": "#4A90E2"}, # 블루
        {"bg": "#f9f9f9", "border": "#888888"}, # 그레이
        {"bg": "#fffbf0", "border": "#f39c12"}, # 오렌지
        {"bg": "#f4fcf8", "border": "#2ecc71"}  # 그린
    ]
    chosen_summary_style = random.choice(summary_styles)

    # 4. 전체 구조 조립 (머리와 꼬리는 고정, 중간은 무작위 조립)
    structure_list = ["제목", "메타 설명", "서론", "작가 프로필"]
    if include_toc: structure_list.append("목차")
    if include_quote: structure_list.append("명언")
    structure_list.append(f"본문 (내부 소제목 작성 순서: {body_order_str})")
    structure_list.append("제언(결론)")
    structure_list.append("3줄 핵심 요약")
    structure_list.append("관련 콘텐츠")
    if include_glossary: structure_list.append("용어사전")
    structure_list.extend(["FAQ", "업데이트 정보", "면책조항", "스키마(FAQ, Article, Review)", "태그"])

    template_structure_str = "\n".join([f"{i+1}. {item}" for i, item in enumerate(structure_list)])
    print(f"🎲 [통제된 완전 랜덤] 생성된 문서 구조:\n{template_structure_str}\n")
    # -----------------------------------------------------------------

    section_htmls = {
        "면책조항": f'<div {disclaimer_box_style}><strong>⚠️ 면책 조항</strong> 본 글은 개인 연구 및 정보 공유 목적이며, 투자 권유·추천·청약이 아닙니다. 글 작성 과정에는 AI 도구를 활용해 공개된 시장 데이터를 분석·정리했으며, 본문의 투자금 시뮬레이션(예: 1,000만 원 투자 시나리오)은 실제 투자 경험이 아니라 과거 시세·배당 데이터를 기준으로 한 가정적 계산 결과입니다. 실제 수익률은 시장 상황에 따라 달라질 수 있으며, 모든 투자 결정과 손익은 단독 책임이며, 필요 시 공인 자격을 가진 전문가와 상담하시기 바랍니다.</div>',
        "명언": f'<div {quote_box_style}><div style="font-size: 2.6em; color: #d8dce3; line-height: 1; font-family: Georgia, serif; margin-bottom: 8px;">&ldquo;</div><p style="font-size: 1.3em; font-weight: 600; color: #222; margin: 0 0 14px; line-height: 1.55; letter-spacing: -0.2px;">{quote_data["kor"]}</p><p style="font-size: 0.85em; color: #999; font-style: italic; margin: 0 0 16px;">{quote_data["eng"]}</p><p style="font-size: 0.85em; color: #555; margin: 0; letter-spacing: 0.5px;">— {quote_data["author"]}</p></div>',
        "FAQ 스키마": (
            "HTML 본문에서 실제로 작성한 FAQ 3~5개의 질문/답변과 100% 일치하는 "
            "FAQPage JSON-LD를 <script type=\"application/ld+json\">...</script> 형식으로 생성하세요. "
            "\"질문1\"/\"답변1\" 같은 플레이스홀더나 예시 텍스트를 쓰지 말고, FAQ 섹션에 등장한 실제 문장을 사용해야 합니다."
        ),
        "Article 스키마": (
            "이 글 전체를 대표하는 Article JSON-LD를 <script type=\"application/ld+json\">...</script> 형식으로 생성하세요. "
            "\"headline\"에는 실제 <h1> 제목, \"description\"에는 메타 설명(150자 요약), "
            "\"datePublished\"/\"dateModified\"에는 오늘 날짜({today_str}), "
            "\"author\"와 \"publisher\"는 온도(ondo)로 설정합니다. "
            "제목/요약과 무관한 가짜 문구를 넣지 말고, 본문 내용과 일치하도록 작성하세요."
        ),
        "작가 프로필": (lambda _hist=_get_operating_history(): (
            f'<div {bio_box_style}><div style="flex-shrink: 0; width: 60px; height: 60px; border-radius: 50%; background-color: #4A90E2; color: white; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold;">O</div>'
            f'<div><h4 style="margin: 0 0 5px 0; color: #333;">온도(ondo)</h4>'
            f'<p style="margin: 0; font-size: 13px; color: #666; line-height: 1.5;">공개된 시장 데이터를 리서치·정리해 투자 관점을 제공하는 콘텐츠 채널입니다. 원고 작성에는 AI 도구를 보조 도구로 활용하며, \'현상 제시 - 원인 분석 - 향후 전망\'의 구조로 데이터 기반 인사이트를 정리합니다.'
            + (f' {_hist["first_date"]}부터 운영하며, 현재까지 {_hist["count"]}건의 분석을 발행했습니다.' if _hist['count'] > 0 and _hist['first_date'] else '')
            + '</p></div></div>'
        ))(),
        "용어사전": (lambda _glossary=_technical_term_glossary(): (
            f'<div {glossary_box_style}><p style="font-weight: bold; margin-bottom: 10px; color: #555; font-size: 13px;">💡 온도(ondo)의 용어 사전</p>'
            f'<ul style="padding-left: 15px; margin: 0; font-size: 12px; line-height: 1.8; color: #666;">'
            + "".join(f'<li style="margin-bottom: 4px;"><b>{term}</b>: {desc}</li>' for term, desc in list(_glossary.items())[:7])
            + '</ul></div>'
        ))(),
        "관련 콘텐츠": (
            "전달된 '[내 블로그 기존 글 목록(내부 링크용)]'을 분석하십시오. "
            "현재 분석 중인 ETF의 특성(추종 지수, 주요 섹터, 경쟁 ETF, 세금/계좌 전략 등)을 바탕으로, "
            "독자가 비교하거나 연계해서 읽기 좋은 기존 글을 스스로 판단해 최대 3개 선정하십시오. "
            "**[중요 경고]** 제공된 목록에서 실제 제목과 URL만 정확히 매칭해야 하며, 임의로 주소를 생성해선 안 됩니다. 적합한 글이 없다면 섹션 자체를 생성하지 마십시오. "
            '형식: <div style="margin-top: 40px; padding: 20px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #4A90E2;">'
            '<h4 style="margin-top: 0; color: #333;">📚 관련 글</h4><ul style="line-height: 1.8; padding-left: 20px;">'
            '<li><a href="[실제 URL]" style="color: #0056b3; text-decoration: none;">[실제 제목]</a></li>'
            '</ul></div>'
        ) if rss_posts else "",

        "업데이트 정보": f'<p style="font-size: 0.85em; color: #888; margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee;">최종 업데이트: {today_str}</p>',
    }

    # 로컬 계산 커스텀 메트릭 섹션 (AI 템플릿에 삽입용)
    # [수정] "환헤지" 열이 실제로 계산한 적 없는 hedge_cost(내부 채점용 이진 신호를
    # 그대로 숫자로 노출한 것)를 보여줘서, 운용보수와 우연히 같은 값(0.25%)이 찍히고
    # "환헤지를 하고 있다"는 오해를 주던 문제가 있었음(IBIT은 환헤지 상품이 아님).
    # "환노출" 열로 바꾸고 사실 그대로의 값(있음/없음)을 표시한다.
    custom_metric_html = '<div style="margin:20px 0;padding:15px;border:1px solid #e2e2e2;border-radius:8px;background:#fafafa;"><h3>커스텀 ETF 투자 매력도 점수(1~10)</h3><table style="width:100%;border-collapse:collapse;"><thead><tr><th style="border:1px solid #ddd;padding:8px;">티커</th><th style="border:1px solid #ddd;padding:8px;">스코어</th><th style="border:1px solid #ddd;padding:8px;">MDD</th><th style="border:1px solid #ddd;padding:8px;">배당 성장</th><th style="border:1px solid #ddd;padding:8px;">보수</th><th style="border:1px solid #ddd;padding:8px;">환노출</th></tr></thead><tbody>'
    for ticker, d in etf_data_cache.items():
        custom_metric_html += f"<tr><td style='border:1px solid #ddd;padding:8px;'>{ticker}</td><td style='border:1px solid #ddd;padding:8px;font-weight:bold;'>{d.get('custom_attractiveness_score','N/A')}</td><td style='border:1px solid #ddd;padding:8px;'>{d.get('mdd','N/A')}</td><td style='border:1px solid #ddd;padding:8px;'>{d.get('dividend_growth_rate','N/A')}</td><td style='border:1px solid #ddd;padding:8px;'>{d.get('expense_ratio','N/A')}</td><td style='border:1px solid #ddd;padding:8px;'>{d.get('fx_exposure','N/A')}</td></tr>"
    custom_metric_html += '</tbody></table><p style="margin-top:10px;font-size:0.9em;color:#555;">(점수 산정 기준: MDD/배당성장/운용보수/환노출 여부 기반 로컬 계산)</p></div>'

    section_htmls["커스텀 지표"] = custom_metric_html

    # 데이터 출처 명시
    data_citation_html = _add_data_citation(today_str, etf_list, etf_data_cache)
    section_htmls["데이터 출처"] = data_citation_html

    # [신규] 정정 이력 (이전 분석 대비 실제 데이터 변화) - 첫 분석 글에는 표시할
    # 게 없어 자동으로 빈 문자열이 되고, 시리즈 재분석 글에만 표시된다.
    section_htmls["정정 이력"] = revision_history_html

    # 투자 시나리오 분석 (텍스트 표) + 백테스트 시뮬레이션 그래프(거치식 vs 적립식)를 함께 배치
    scenario_html = _add_scenario_analysis(etf_data_cache, title_tickers)
    section_htmls["시나리오 분석"] = scenario_html + backtest_sim_html

    # 경쟁상품 비교
    comparison_html = _add_competitive_comparison(etf_data_cache)
    section_htmls["경쟁분석"] = comparison_html

    # 연령별 포트폴리오 가이드 (이 글이 다루는 실제 ETF 기준으로 동적 생성)
    # [순서 변경] 연령별 포트폴리오 가이드가 아래 세 계산 결과(백테스트, 위험
    # 시나리오, 실수료 비교)를 실제로 인용해서 "이 ETF만의 숫자"로 서술하도록
    # 하려면, 이 계산들이 먼저 끝나 있어야 한다. 위험 시나리오와 실수료 비교표를
    # 연령별 가이드보다 앞으로 옮긴다(백테스트 결과는 이미 위쪽에서
    # backtest_results_by_ticker로 계산되어 있음).

    # 위험 시나리오 분석
    risk_scenario_html, risk_results_by_ticker = _add_risk_scenarios(etf_data_cache)
    section_htmls["위험시나리오"] = risk_scenario_html

    # 실수료 비교표
    fee_comparison_html, tax_comparison_result = _add_fee_comparison_table(etf_data_cache)
    section_htmls["실수료비교"] = fee_comparison_html

    # 연령별 포트폴리오 가이드 (이 글이 다루는 실제 ETF의 백테스트/위험시나리오/
    # 세금비교 계산값을 직접 인용해 "이 ETF만의 숫자"로 서술하도록 전달)
    age_portfolio_html = _add_age_based_portfolio_guide(
        etf_list, etf_data_cache,
        backtest_results_by_ticker=backtest_results_by_ticker,
        risk_results_by_ticker=risk_results_by_ticker,
        tax_comparison_result=tax_comparison_result,
    )
    section_htmls["연령별포트폴리오"] = age_portfolio_html

    # 매매 타이밍 프레임
    if macro_data.get('is_fx_volatile'):
        timing_frame_html = _add_trading_timing_framework(macro_data, today_str, etf_list)
        section_htmls["매매타이밍"] = timing_frame_html
    else:
        section_htmls["매매타이밍"] = ""

    # 가상 포트폴리오 공개
    virtual_portfolio_html = _add_virtual_portfolio_showcase(etf_list, driver)
    section_htmls["가상포트폴리오"] = virtual_portfolio_html

    # [신규] 손익 캘린더 - 3줄 요약과 FAQ 사이에 접힌 상태로 삽입 (Part5에서 참조)
    section_htmls["손익캘린더"] = calendar_html
    # [수정] 이전 코드에서 셀레니움 스크린샷 기능을 자체 데이터 기반 그래프로
    # 교체하면서 'backtest_img_path' 변수 자체를 없앴는데, 이 줄이 그 변수를
    # 참조하고 있어서 NameError로 프로그램이 즉시 중단됐음.
    # 백테스트 시뮬레이션 그래프(backtest_sim_html)는 이미 "시나리오 분석" 섹션에
    # 삽입해뒀으므로, 여기서 또 추가하면 같은 그래프가 중복 노출되어 제거함.

    # [수정] 계산기는 ETF마다 달라지는 내용이 없는 범용 도구라서, 매 글마다
    # 반복 삽입하지 않고 워드프레스 사이드바에 1회만 수동으로 넣는 것으로 변경.
    # 본문 자동 삽입은 제거함 (_add_calculator_widget 함수 자체는 사이드바용
    # HTML을 뽑을 때 참고용으로 남겨둠 - 더 이상 section_htmls에 채워지지 않음).

    # 심화 섹터 분석
    sector_analysis_html = _add_sector_deep_analysis(etf_data_cache, macro_data)
    section_htmls["섹터심화"] = sector_analysis_html

    # 시간대 마커
    temporal_markers_html = _add_temporal_markers(today_str)
    section_htmls["시간대마커"] = temporal_markers_html

    # 반박 섹션
    counter_args_html = _add_counter_arguments(etf_data_cache, macro_data)
    section_htmls["반박섹션"] = counter_args_html

    # 경제 사이클별 분석
    economic_cycle_html = _add_economic_cycle_analysis(macro_data, etf_list, etf_data_cache)
    section_htmls["경제사이클"] = economic_cycle_html

    crisis_guidance = ""
    for ticker, crisis_data in etf_crisis_info.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        inception_year = crisis_data['inception_year']
        available_crises = crisis_data['available_crises']
        
        if inception_year:
            if available_crises:
                crisis_list = ", ".join(available_crises)
                crisis_guidance += f"\n- [{ticker_clean}] 상장 연도: {inception_year}년. **이 ETF는 {inception_year}년에 상장되었으므로, 다음 위기 시점의 실제 데이터가 있습니다: {crisis_list}. 이 ETF의 리스크 분석 시 위 언급된 위기 시점의 실제 성과 데이터만 사용할 수 있습니다. {inception_year}년 이전의 위기(예: 2000년 닷컴버블, 2008년 금융위기 등)는 이 ETF의 직접적인 데이터가 없으므로, 절대로 \"{ticker_clean}이 2000년에 -X% 하락했다\" 같은 거짓 정보를 만들지 마세요. 대신 \"상장 기간이 짧아({inception_year}년 상장) 과거 경제 위기(2000년 닷컴버블, 2008년 금융위기 등) 당시의 직접적인 데이터는 없으나, 동일 지수를 추종하는 다른 ETF나 지수 자체의 과거 흐름을 유추해 볼 때...\"와 같은 방어적 문구를 사용하세요."
            else:
                crisis_guidance += f"\n- [{ticker_clean}] 상장 연도: {inception_year}년. **이 ETF는 {inception_year}년에 상장되어 주요 경제 위기 시점(2000년 닷컴버블, 2008년 금융위기, 2020년 코로나, 2022년 금리 인상)의 직접적인 데이터가 없습니다. 절대로 \"{ticker_clean}이 2000년/2008년에 -X% 하락했다\" 같은 거짓 정보를 만들지 마세요. 대신 \"상장 기간이 짧아({inception_year}년 상장) 과거 경제 위기 당시의 직접적인 데이터는 없으나, 동일 지수를 추종하는 다른 ETF나 지수 자체의 과거 흐름을 유추해 볼 때...\"와 같은 방어적 문구를 사용하세요."
        else:
            crisis_guidance += f"\n- [{ticker_clean}] 상장 연도 정보 없음. **상장 연도가 확인되지 않았으므로, 과거 위기 시점 언급 시 신중하게 접근하세요. 확실하지 않은 정보는 \"상장 기간이 짧아 과거 경제 위기 당시의 직접적인 데이터는 없으나, 동일 지수의 과거 흐름을 유추해 볼 때...\"와 같은 방어적 문구를 사용하세요."

    usd_krw = macro_data.get('usd_krw', '정보 없음')
    us_10y = macro_data.get('us_10y', '정보 없음')
    fear_greed = macro_data.get('fear_greed', '정보 없음')

    temperature_meta = _build_investment_temperature(etf_data_cache)
    temperature_html = _build_temperature_banner_html(temperature_meta)
    collected_context += (
        f"[투자 온도계]\n- 현재 투자 온도: {temperature_meta['temp']}도 ({temperature_meta['desc']})\n"
        f"- 해석: {temperature_meta['message']}\n"
    )

    # [신규] 4대 거시 온도계(변동성/밸류에이션/환율/인플레이션) + 종합 온도계.
    # 맨 위 단일 투자 온도계와는 별도로 관리해, 글 맨 아래(결론부 뒤)에 배치한다.
    macro_thermo_indicators = get_macro_thermometer_indicators()
    macro_thermo_html = _build_macro_thermometers_chart(macro_thermo_indicators)
    if macro_thermo_html:
        thermo_context_lines = []
        for key, name in [('volatility', '변동성'), ('valuation', '밸류에이션'), ('fx', '환율'), ('inflation', '인플레이션')]:
            v = macro_thermo_indicators.get(key)
            if isinstance(v, (int, float)):
                thermo_context_lines.append(f"  - {name} 온도: {v}°")
        if thermo_context_lines:
            collected_context += "[시장환경 4대 온도계]\n" + "\n".join(thermo_context_lines) + "\n"

    # ============================================================
    # [신규] 3번 부서: 기획 - Part1~5 생성 직전에 한 번 실행
    # ============================================================
    confirmed_context = _load_json_file("confirmed_topic_context.json", None)
    selection_reason = ""
    operator_memo = ""
    if confirmed_context:
        confirmed_set = {_normalize_ticker(x) for x in str(confirmed_context.get("ticker", "")).split(",") if x.strip()}
        if confirmed_set == {_normalize_ticker(x) for x in etf_list}:
            selection_reason = confirmed_context.get("reason", "")
            operator_memo = (confirmed_context.get("memo") or "").strip()

    plan = plan_article(", ".join(etf_list), series_context=series_context, selection_reason=selection_reason)
    if plan:
        collected_context += _plan_to_context_block(plan)
        print(f"📋 기획 완료 - 핵심 메시지: {plan.get('key_message', '')}")

    # 기획에 썼으면 다음 실행에 잘못 재사용되지 않도록 정리
    if confirmed_context and os.path.exists("confirmed_topic_context.json"):
        os.remove("confirmed_topic_context.json")

    # ============================================================
    # [신규] SEO/제목 최적화 부서 - Part1 실행 직전에 제목 확정
    # ============================================================
    title_optimization = generate_optimized_title(", ".join(etf_list), title_pattern_hint, collected_context)
    forced_title = title_optimization.get("selected") if title_optimization else None
    if forced_title:
        print(f"🏷️ 제목 최적화 완료 - 확정된 제목: {forced_title}")
        print(f"   선정 이유: {title_optimization.get('reason', '')}")

    print("🤖 AI 원고 생성 중... (5단 분할 생성 방식 적용)")
    policy_issues_overall = []
    generated_body = None
    final_quality_score = None
    final_quality_issues = []
    max_attempts = 3
    consecutive_total_api_failures = 0  # get_gemini_response가 완전히 실패(None)한 연속 횟수
    previous_quality_result = None  # 직전 시도의 최종 검수 결과 (problem_parts 참고용)
    blog_parts_dict = None  # [추가] 사후 교정용 개별 파트 원문 (part_num -> html)

    for attempt in range(max_attempts):
        # [수정] 예전에는 재시도할 때 무조건 Part5(마지막 파트)부터만 다시 썼습니다.
        # 하지만 최종 검수는 글 전체를 보고 판단하므로, 실제 문제 원인이 Part2나
        # Part3에 있어도 Part5만 고치면 원인이 그대로 남아 다음 재시도도 같은 이유로
        # 또 실패할 수 있었습니다(그때마다 API 호출만 추가로 소모). 이제 직전
        # 검수 결과의 problem_parts(문제 원인 파트 번호)를 참고해, 그중 가장 이른
        # 번호부터 다시 생성합니다. problem_parts가 비어 있거나 검수 자체가
        # 실패했다면(정보 없음) 안전하게 기존처럼 Part5부터 다시 생성합니다.
        if attempt == 0:
            force_from = None
        elif previous_quality_result and previous_quality_result.get('problem_parts'):
            problem_parts = previous_quality_result['problem_parts']
            # [추가] AI가 "안전하게" 문제 파트를 전부(또는 거의 전부) 지목해버리면
            # min()이 사실상 1이 되어 "부분 재생성"이라는 취지가 무의미해지고 지금까지와
            # 똑같이 매번 전체를 다시 쓰게 된다(실제로 발생했던 사례: [1,2,3,4,5] 전부
            # 반환). problem_parts가 4개 이상(5개 중 대부분)이면 "사실상 특정 안 함"으로
            # 보고, 대신 issues(final_review_issues로 이미 프롬프트에 반영됨)에 기대어
            # Part5부터 재생성하는 기존 안전한 방식으로 되돌린다.
            if len(problem_parts) >= 4:
                print(f"⚠️ 직전 검수가 문제 파트로 {problem_parts}(사실상 전체)를 지목해 "
                      f"특정 파트로 좁히는 의미가 없습니다. 대신 지적사항(issues)을 프롬프트에 "
                      f"반영한 채 Part5부터 다시 생성합니다.")
                force_from = 5
            else:
                force_from = min(problem_parts)
                print(f"🎯 직전 검수에서 지목된 문제 파트({problem_parts}) 중 "
                      f"Part{force_from}부터 다시 생성합니다.")
        else:
            force_from = 5
        blog_content, final_facts_json_str, blog_parts_dict = _generate_chained_article(
            today_str=today_str,
            collected_context=collected_context,
            series_context=series_context,
            widgets_html_block=widgets_html_block,
            recent_issues=recent_issues,
            section_htmls=section_htmls,
            usd_krw=usd_krw,
            us_10y=us_10y,
            fear_greed=fear_greed,
            crisis_guidance=crisis_guidance,
            title_pattern_hint=title_pattern_hint,
            investment_temperature_html=temperature_html,
            include_toc=include_toc,
            include_quote=include_quote,
            include_glossary=include_glossary,
            chosen_summary_style=chosen_summary_style,
            intro_style=chosen_intro_style,
            force_regenerate_from=force_from,
            session_label=session_label,
            final_review_issues=previous_quality_result.get('issues') if previous_quality_result else None,
            macro_thermo_html=macro_thermo_html,
            forced_title=forced_title,
        )
        if not blog_content:
            print(f"❌ AI 원고 생성 실패 (시도 {attempt + 1}/{max_attempts})")
            continue

        # AI가 출력한 플레이스홀더를 실제 차트 HTML(Base64 이미지)로 치환
        blog_content = blog_content.replace("[[CHART_WIDGET_PLACEHOLDER]]", widgets_html_block)

        # [수정] 이전에는 손익캘린더/정정이력을 "AI가 프롬프트로 받아 그대로
        # 베끼도록" 지시했는데, 실제 발행 결과물을 확인해보니 <details>/<div>
        # 껍데기는 남아있고 정작 <script>로 그래프를 그리는 부분이 통째로
        # 사라지는 버그가 있었음(AI가 복잡한 JS 구문을 텍스트로 재생성하는
        # 과정에서 누락시킨 것으로 추정). 이제 플레이스홀더 문구만 AI가
        # 삽입하게 하고, 실제 완성된 HTML(스크립트 포함)은 코드가 100%
        # 확정적으로 치환한다 - AI가 재생성할 여지 자체를 없앰.
        #
        # [추가 수정] 그런데 실제로는 AI가 "[[CALENDAR_PLACEHOLDER]]" 문구
        # 자체를 무시하고, 대신 코드가 만드는 것과 비슷한 구조
        # (<details id="details_calendar_TICKER">...)를 스스로 상상해서
        # 직접 만들어버리는 경우가 확인됨. 이 경우 실제 데이터가 담긴
        # <script>가 없는 빈 껍데기라 캘린더가 전혀 렌더링되지 않는데,
        # 플레이스홀더 문구 자체는 없으니 아래 "빼먹은 경우" 안전장치도
        # 발동하지 않아 진짜 캘린더가 영영 삽입되지 못했다. AI가 만든 가짜
        # 껍데기를 정규식으로 찾아 제거한 뒤, 플레이스홀더가 있는 것처럼
        # 취급해 진짜로 교체한다.
        fake_calendar_pattern = re.compile(r'<details[^>]*id=["\']details_calendar_[^"\']*["\'][^>]*>.*?</details>', re.DOTALL)
        if fake_calendar_pattern.search(blog_content) and "[[CALENDAR_PLACEHOLDER]]" not in blog_content:
            print("⚠️ AI가 플레이스홀더 대신 손익 캘린더의 가짜 껍데기 구조를 직접 만든 것을 감지했습니다 - 제거 후 실제 캘린더로 교체합니다.")
            blog_content = fake_calendar_pattern.sub("[[CALENDAR_PLACEHOLDER]]", blog_content, count=1)

        if "[[CALENDAR_PLACEHOLDER]]" in blog_content:
            blog_content = blog_content.replace("[[CALENDAR_PLACEHOLDER]]", calendar_html)
        elif calendar_html:
            # [안전장치] AI가 플레이스홀더 문구 자체를 빼먹은 경우까지 대비해,
            # FAQ 섹션 시작 직전에 강제로 삽입한다(찾지 못하면 본문 맨 끝에라도 추가).
            faq_match = re.search(r'<h3[^>]*>[^<]*FAQ', blog_content, flags=re.IGNORECASE)
            if faq_match:
                insert_at = faq_match.start()
                blog_content = blog_content[:insert_at] + calendar_html + blog_content[insert_at:]
            else:
                blog_content += calendar_html

        # [추가 수정] 정정 이력도 동일한 위험이 있어 같은 방식으로 방어.
        fake_revision_pattern = re.compile(r'<div[^>]*>\s*<p[^>]*>\s*📋\s*이전 분석 대비.*?</div>\s*</div>', re.DOTALL)
        if fake_revision_pattern.search(blog_content) and "[[REVISION_HISTORY_PLACEHOLDER]]" not in blog_content:
            print("⚠️ AI가 플레이스홀더 대신 정정 이력의 가짜 구조를 직접 만든 것을 감지했습니다 - 제거 후 실제 데이터로 교체합니다.")
            blog_content = fake_revision_pattern.sub("[[REVISION_HISTORY_PLACEHOLDER]]", blog_content, count=1)

        if "[[REVISION_HISTORY_PLACEHOLDER]]" in blog_content:
            blog_content = blog_content.replace("[[REVISION_HISTORY_PLACEHOLDER]]", revision_history_html)
        elif revision_history_html:
            faq_match2 = re.search(r'<h3[^>]*>[^<]*FAQ', blog_content, flags=re.IGNORECASE)
            if faq_match2:
                insert_at2 = faq_match2.start()
                blog_content = blog_content[:insert_at2] + revision_history_html + blog_content[insert_at2:]
            else:
                blog_content += revision_history_html

        blog_content = blog_content.replace("```html", "").replace("```", "")
        blog_content = _post_process_blog_content(blog_content)
        blog_content, policy_issues = _safe_html_filter(blog_content)
        if policy_issues:
            policy_issues_overall.extend(policy_issues)

        validation_messages = _validate_blog_content(blog_content, macro_data, etf_data_cache)
        if validation_messages:
            print("⚠️ AI 원고 검증 경고:")
            for message in validation_messages:
                print(f"   - {message}")
            # [수정] "[문법 이상 감지]" 항목은 정규식 기반이라 오탐지를 완전히
            # 피할 수 없다(정상적인 한국어 문장에서 같은 글자가 우연히 반복되는
            # 경우를 "버그"로 잘못 판단하는 경우가 실제로 확인됨). 이걸로 매번
            # 전체 재생성을 강제하면, 재생성마다 파트 생성+검수가 또 반복되며
            # 한 편에 100회 이상의 API 요청이 발생하는 심각한 문제가 있었음.
            # 문법 이상 감지는 경고만 출력하고, 재생성은 그보다 신뢰도가 높은
            # 다른 검증(수치 미반영 등)에서만 강제한다.
            non_grammar_warnings = [m for m in validation_messages if not m.startswith("[문법 이상 감지]")]
            if non_grammar_warnings and attempt < max_attempts - 1:
                print("   → (문법 이상 감지 제외) 다른 검증 경고가 있으므로 재생성을 시도합니다.")
                continue
            elif not non_grammar_warnings:
                print("   ℹ️ 위 경고는 문법 이상 감지뿐이라 재생성을 강제하지 않습니다 - 발행 전 직접 확인하세요.")

        title_match = re.search(r"<h1>(.*?)</h1>", blog_content)
        generated_title = title_match.group(1).strip() if title_match else title_pattern_hint

        length_ok = len(blog_content) >= 3500
        duplicate_state = _load_state()
        is_duplicate = _check_duplicate(generated_title, blog_content, duplicate_state)

        print(f"🤖 AI 원고에 대한 실제 품질 검수를 진행합니다 (시도 {attempt + 1})...")
        # [수정] 개별 호출 간격을 60초→20초로 줄인 것과 비례해 여기도 30초로
        # 줄였다. 5단 생성이 다 끝난 직후, 지금까지 누적된 호출 수가 가장 많은
        # 시점이라 완전히 없애지는 않고 다른 지점보다 조금 더 여유를 둔다.
        print("⏳ 5단 생성 완료 - 최종 검수 전 API 부하 완화를 위해 30초 추가 대기합니다...")
        time.sleep(30)
        # [조정] 각 Part 검수를 이미 통과한 뒤의 마지막 관문이라, 여기서 실패하면
        # 손해가 크다(전체 5개 파트를 다시 만들어야 함). 기본 재시도 2회로는
        # 60초 대기 사이 일시적 429/오류에도 취약했으므로 재시도를 넉넉히 늘림.
        quality_result = _llm_quality_check(blog_content, facts_json_str=final_facts_json_str, max_retries=4)

        if quality_result is None:
            # 검수 자체가 실패한 경우 '통과'로 간주하지 않고, 재시도 여지가 있으면 재시도.
            # 마지막 시도라면 사람이 반드시 확인하도록 명확히 표시하고 넘어감.
            print("⚠️ LLM 품질 검수 실패(응답 없음/파싱 오류) - 자동 판정 불가")
            quality_ok = False
            quality_score = None
            quality_issues = ["자동 품질 검수 실패 - 발행 전 반드시 직접 읽어보세요."]

            consecutive_total_api_failures += 1
            # [중요] 60초씩 대기하며 재시도했는데도 API가 연속으로 완전히 실패했다면,
            # 이건 일시적 혼잡이 아니라 무료 티어 "일일 요청 한도(RPD)" 자체가
            # 소진됐을 가능성이 높다. 이 경우 몇 분을 더 기다려도 절대 풀리지 않고
            # (태평양 시간 자정까지 리셋 안 됨), 계속 재시도하면 사용자가 겪으신 것처럼
            # 수십 분간 429만 반복하다 강제 종료하게 되는 상황이 벌어진다.
            # 2회 연속 완전 실패 시 자동 재시도를 멈추고 명확히 알린다.
            if consecutive_total_api_failures >= 2:
                print("\n" + "=" * 50)
                print("🛑 API 호출이 연속으로 완전히 실패했습니다.")
                print("   무료 티어의 '일일 요청 한도(RPD)'가 소진되었을 가능성이 높습니다.")
                print("   이 경우 몇 분을 더 기다려도 풀리지 않으며, 태평양 시간 자정에 리셋됩니다.")
                print("   지금까지 생성된 원고는 검수 없이 클립보드에 복사되니, 직접 검토 후 판단하세요.")
                print("=" * 50 + "\n")
                pyperclip.copy(blog_content)
                generated_body = _inject_static_sections(blog_content, section_htmls)
                if include_toc:
                    generated_body = _inject_table_of_contents(generated_body)
                generated_body = _highlight_technical_terms(generated_body)
                final_title = generated_title
                final_quality_score = None
                final_quality_issues = ["API 한도 소진으로 자동 검수를 완료하지 못했습니다 - 반드시 직접 검토하세요."]
                break
        else:
            consecutive_total_api_failures = 0  # API가 응답을 줬으니 연속 실패 카운터 리셋
            quality_score = quality_result['quality_score']
            quality_issues = quality_result['issues']
            quality_ok = quality_result['publish_recommended'] and quality_score >= 0.6
            # [추가] 다음 루프 반복(재시도)에서 force_from을 정할 때 참고할 수 있도록 저장.
            previous_quality_result = quality_result

        print(
            f"🔍 후처리 상태 - 시도 {attempt + 1}: "
            f"품질점수={'N/A' if quality_score is None else f'{quality_score:.2f}'}, "
            f"길이={len(blog_content)}, 중복={is_duplicate}"
        )
        if quality_issues:
            print("   품질 검수 지적 사항:")
            for issue in quality_issues:
                print(f"   - {issue}")

        if not length_ok or not quality_ok or is_duplicate:
            # [추가] 예전에는 품질 미달이면 곧바로 "Part 전체 재생성"으로 넘어갔다.
            # 문제는 재생성이 "처음부터 다시 쓰기"라서, 이미 잘 쓴 부분까지 통째로
            # 바뀌면서 (a) 매번 새로운 종류의 실수가 생길 여지가 있고 (b) 검수가
            # 정확히 찾아낸 문제(예: "Part2와 Part4의 배당 정보가 모순됨")를 고치는
            # 데 비효율적이었다(운 좋게 다르게 써지길 바라는 것에 가까움). 이제
            # 재생성 전에 먼저 "사후 교정"을 시도한다: 문제로 지목된 파트의 원문만
            # 골라, 검수가 지적한 문제만 정확히 고치도록 요청한다. 이미 잘 쓰인
            # 나머지 90% 이상은 건드리지 않으므로 새로운 실수가 생길 여지가 적고,
            # API 호출도 훨씬 적게 든다(파트 전체 재생성 대신 파트 1~2개 교정).
            can_try_targeted_fix = (
                quality_result is not None
                and quality_result.get('issues')
                and quality_result.get('problem_parts')
                and len(quality_result['problem_parts']) <= 3  # 너무 많으면(사실상 전체) 교정보다 재생성이 나음
                and blog_parts_dict
                and not is_duplicate  # 중복 문제는 텍스트 교정으로 해결 안 되므로 제외
            )
            if can_try_targeted_fix:
                print(f"🔧 전체 재생성 대신, 지목된 문제 파트({quality_result['problem_parts']})만 "
                      f"사후 교정을 먼저 시도합니다...")
                fixed_parts = dict(blog_parts_dict)
                any_fix_succeeded = False
                for part_num in quality_result['problem_parts']:
                    part_label_map = {
                        1: "Part1(도입/기초)", 2: "Part2(수익/시뮬레이션)", 3: "Part3(전략/리스크)",
                        4: "Part4(포트폴리오/심화)", 5: "Part5(반박/결론/마무리)",
                    }
                    part_label = part_label_map.get(part_num, f"Part{part_num}")
                    original_part_text = blog_parts_dict.get(part_num)
                    if not original_part_text:
                        continue
                    fixed_text = _llm_targeted_fix(
                        original_part_text, part_label, quality_result['issues'],
                        facts_json_str=final_facts_json_str,
                    )
                    if fixed_text:
                        fixed_parts[part_num] = fixed_text
                        any_fix_succeeded = True
                        print(f"   ✅ {part_label} 사후 교정 완료")
                    else:
                        print(f"   ⚠️ {part_label} 사후 교정 실패 - 원본 유지")

                if any_fix_succeeded:
                    # 교정된 파트들로 전체 글을 다시 조립해 재검수한다.
                    # [신규] 4대 온도계+종합 온도계는 여기서도 동일하게 맨 아래에 배치한다.
                    _bottom_block = f"\n\n{macro_thermo_html}" if macro_thermo_html else ""
                    candidate_content = f"{temperature_html}\n\n" + "\n\n".join(
                        fixed_parts[i] for i in range(1, 6)
                    ) + _bottom_block
                    print("🔎 사후 교정 결과를 재검수합니다...")
                    recheck_result = _llm_quality_check(candidate_content, facts_json_str=final_facts_json_str)
                    if recheck_result and recheck_result['publish_recommended'] and recheck_result['quality_score'] >= 0.6:
                        print(f"✅ 사후 교정으로 검수 통과했습니다 (점수 {recheck_result['quality_score']:.2f}). "
                              f"전체 재생성을 건너뜁니다.")
                        blog_content = candidate_content
                        blog_parts_dict = fixed_parts
                        quality_score = recheck_result['quality_score']
                        quality_issues = recheck_result['issues']
                        length_ok = len(blog_content) >= 3500
                        quality_ok = True
                    else:
                        recheck_score = recheck_result['quality_score'] if recheck_result else None
                        print(f"⚠️ 사후 교정 후에도 검수 기준 미달입니다"
                              f"({'N/A' if recheck_score is None else f'점수 {recheck_score:.2f}'}). "
                              f"기존 방식(전체 재생성)으로 넘어갑니다.")

        if not length_ok or not quality_ok or is_duplicate:
            if attempt < max_attempts - 1:
                print("🔁 재생성 트리거: 조건 미충족(길이/품질검수/중복)")
                continue
            else:
                print("⚠️ 최대 재시도 도달 후에도 조건 미충족 - 아래 발행 전 확인 단계에서 반드시 직접 검토하세요.")

        generated_body = _inject_static_sections(blog_content, section_htmls)
        if include_toc:
            generated_body = _inject_table_of_contents(generated_body)
        generated_body = _highlight_technical_terms(generated_body)
        final_title = generated_title
        final_quality_score = quality_score
        final_quality_issues = quality_issues
        break

    if not generated_body:
        print("❌ AI 원고 생성 최종 실패 - 나중에 다시 시도하세요")
        driver.quit()
        return

    if _check_duplicate(final_title, generated_body, _load_state()):
        print("⚠️ 이미 비슷한 내용을 게시한 글이 발견되었습니다. 중복 등록을 생략합니다.")
        _telegram_send_message(
            f"⚠️ 발행 중단: '{final_title}'이(가) 이미 올린 글과 너무 비슷해서 올리지 않았어요.\n"
            f"같은 내용 반복은 애드센스 심사에 불리해서 자동으로 막았습니다. 다음 추천을 기다려주세요."
        )
        driver.quit()
        return

    if operator_memo:
        generated_body = _insert_operator_memo(generated_body, operator_memo)
        print("📝 운영자 메모를 본문에 넣었습니다.")

    # 등록 시 버전 정보 포함
    current_version = 1
    for analysis in previous_analyses.values():
        if analysis['previous']:
            current_version = analysis['current_version']
            break
    
    blog_content = generated_body

    # 줄바꿈이나 HTML 태그(<)가 나오기 전까지만 명확하게 추출
    tag_match = re.search(r"태그:\s*([^\n<]+)", blog_content)
    if tag_match:
        raw_tags = tag_match.group(1)
        # 쉼표 등 불필요한 구두점 제거 후 5개만 추출
        tags = [re.sub(r'[,.]', '', t.strip().replace("#", "")) for t in raw_tags.split() if t.strip()]
        tags = tags[:5]
    else:
        tags = []
    
    # 본문에서 태그 라인만 확실하게 삭제 (HTML 구조 훼손 방지)
    blog_content = re.sub(r"(?:\d+\)\s*)?태그:\s*[^\n<]+", "", blog_content).strip()

    # 차트를 그리기 위한 Plotly 라이브러리 및 툴팁 스타일 최상단 주입
    # ... 앞부분 생략 ...
    plotly_cdn = '<script src="https://cdn.plot.ly/plotly-2.34.0.min.js"></script>\n'
    blog_content = tooltip_style + "\n" + plotly_cdn + blog_content

    # [신규] 이 시점에서 blog_content는 완전히 완성된 최종 본문이다(태그 정제,
    # 스타일/스크립트 삽입까지 끝남). 이후 어떤 발행 경로(API/Selenium/반자동)로
    # 가든 이미 파일로 안전하게 보존된 상태이므로, 발행이 실패하거나 클립보드
    # 내용이 덮어써져도 이 글 자체는 사라지지 않는다.
    _save_published_article_file(final_title, blog_content, etf_list, version=current_version)

    try:
        if PLATFORM == "wordpress":
            # 품질 점수가 기준(PUBLISH_MIN_QUALITY, 기본 0.7) 미만이거나 검수 자체가
            # 실패하면 공개 발행하지 않고 워드프레스 "임시글"로만 올린 뒤 텔레그램으로
            # 알린다. 예전에는 0.3만 넘으면 자동 공개 발행돼서, 검수가 "위험 신호"라고
            # 판단한 글(0.3~0.6)도 그대로 사이트에 올라갔다.
            publish_min_quality = float(os.environ.get("PUBLISH_MIN_QUALITY", "0.7"))
            # 대표 이미지(썸네일) 카드 - 허브·카테고리 페이지 글 카드에 보인다. 실패하면 없이 발행.
            import media_engine
            featured_id = media_engine.featured_card_id(final_title, "etf")
            if final_quality_score is None or final_quality_score < publish_min_quality:
                score_text = "검수 실패" if final_quality_score is None else f"{final_quality_score:.2f}"
                print(f"🛑 품질 점수({score_text})가 기준({publish_min_quality}) 미만이라 임시글로만 올립니다.")
                _print_final_quality_summary(final_quality_score, final_quality_issues, policy_issues_overall)
                draft_ok, draft_result = publish_to_wordpress(final_title, blog_content, tags=tags, status="draft",
                                                               featured_image=featured_id)
                issues_text = "\n".join(f"- {i}" for i in (final_quality_issues or [])[:6]) or "- (지적 내용 없음)"
                if draft_ok:
                    _register_article(final_title, generated_body, status='draft',
                                      notes=f'below quality threshold ({score_text})', version=current_version,
                                      extra_data=etf_data_cache, url=draft_result)
                    _clear_generation_state(session_label=session_label)
                    _telegram_send_message(
                        f"📝 임시글로만 올렸어요 (공개 안 됨)\n\n제목: {final_title}\n"
                        f"품질 점수: {score_text} (기준 {publish_min_quality})\n지적된 문제:\n{issues_text}\n\n"
                        f"워드프레스 '글 → 임시글'에서 확인한 뒤, 고쳐서 발행하거나 삭제해주세요."
                    )
                else:
                    _telegram_send_message(
                        f"⚠️ 품질 점수 {score_text}(기준 {publish_min_quality}) 미달이라 임시글로 올리려 했는데 그것도 실패했어요.\n"
                        f"제목: {final_title}\n오류: {str(draft_result)[:200]}"
                    )
                return

            # [신규] 워드프레스는 API로 직접 발행하므로 브라우저 조작이 전혀
            # 필요 없다. 로그인, 알림창 처리, 태그 하나씩 입력하는 절차가
            # 모두 사라지고 API 호출 한 번으로 끝난다. 발행 성공/실패도
            # API 응답으로 즉시 명확하게 알 수 있어, 티스토리처럼 "실제로
            # 발행하셨나요?"를 사람에게 물어볼 필요가 없다.
            # [신규] Part1 팩트시트의 recommended_url을 실제 워드프레스 slug로 사용한다.
            # 파싱 실패나 값 부재 시 None이 되어, publish_to_wordpress가 기존처럼
            # 제목 기반 자동 슬러그 생성으로 자연스럽게 폴백한다.
            publish_slug = None
            if final_facts_json_str:
                try:
                    _facts_for_slug = json.loads(final_facts_json_str)
                    _raw_slug = _facts_for_slug.get('recommended_url') or ''
                    # [안전장치] AI가 형식을 안 지키고 한글/공백/특수문자를 섞어
                    # 넣는 경우를 대비해, 영문 소문자/숫자/하이픈만 남기고 나머지는
                    # 제거한다. 정제 후 남는 게 없으면 슬러그를 아예 쓰지 않고
                    # 워드프레스의 제목 기반 자동 생성에 맡긴다.
                    _cleaned_slug = re.sub(r'[^a-z0-9-]', '', _raw_slug.strip().lower().replace(' ', '-'))
                    _cleaned_slug = re.sub(r'-{2,}', '-', _cleaned_slug).strip('-')
                    publish_slug = _cleaned_slug or None
                except (json.JSONDecodeError, AttributeError):
                    publish_slug = None

            print("\n" + "="*50)
            print("🚀 워드프레스로 발행을 시도합니다...")
            if publish_slug:
                print(f"   슬러그(URL): {publish_slug}")
            wp_success, wp_result = publish_to_wordpress(final_title, blog_content, tags=tags, status="publish", slug=publish_slug,
                                                         featured_image=featured_id)

            print("\n📋 발행 전 최종 품질 검수 요약")
            if final_quality_score is None:
                print("   ⚠️ 자동 품질 검수가 완료되지 못했습니다. 반드시 본문을 직접 읽고 판단하세요.")
            else:
                print(f"   품질 점수: {final_quality_score:.2f} / 1.00 (0.6 미만이면 위험 신호)")
            if final_quality_issues:
                print("   지적된 문제점:")
                for issue in final_quality_issues:
                    print(f"   - {issue}")
            else:
                print("   지적된 문제점 없음")
            if policy_issues_overall:
                unique_policy_issues = list(dict.fromkeys(policy_issues_overall))
                print("   자동 순화된 표현 (애드센스 정책 대응):")
                for issue in unique_policy_issues:
                    print(f"   - {issue}")
            print("="*50)

            if wp_success:
                print(f"✅ 워드프레스 발행 성공! URL: {wp_result}")
                _register_article(final_title, generated_body, status='published', notes='autosaved with AI risk filter', version=current_version, extra_data=etf_data_cache, url=wp_result)
                promote_published_article(driver, etf_list, plan, wp_result)
                print("✅ 글 정보 및 팩트 데이터가 저장되었습니다. 다음 실행 시 과거 수치 비교가 작동합니다.")
                _clear_generation_state(session_label=session_label)
                # 썸네일용 ComfyUI 프롬프트를 텔레그램으로 (사용자가 그림을 답장하면 썸네일 교체)
                import blog_engine
                media_engine.send_image_prompt(blog_engine.LAST_PUBLISHED_POST_ID, final_title, "etf", wp_result)
            elif WP_EMAIL and WP_PASSWORD:
                # [신규] API가 실패했지만(무료/개인/프리미엄 요금제는 항상
                # 이 경로) 로그인 정보(WP_EMAIL/WP_PASSWORD)가 있으면, API 대신
                # Selenium으로 로그인부터 발행까지 완전 자동화를 시도한다.
                # 이것도 실패하면 최종적으로 반자동(클립보드+수동확인)으로 폴백한다.
                print(f"ℹ️ 워드프레스 API 발행 실패({wp_result}) - Selenium 자동 발행을 시도합니다...")
                sel_success, sel_result = publish_to_wordpress_selenium(driver, final_title, blog_content, WP_EMAIL, WP_PASSWORD, WP_SITE_URL)
                if sel_success:
                    print(f"✅ Selenium 자동 발행 성공! URL: {sel_result}")
                    _register_article(final_title, generated_body, status='published', notes='autosaved with AI risk filter (selenium)', version=current_version, extra_data=etf_data_cache, url=sel_result)
                    promote_published_article(driver, etf_list, plan, sel_result)
                    print("✅ 글 정보 및 팩트 데이터가 저장되었습니다. 다음 실행 시 과거 수치 비교가 작동합니다.")
                    _clear_generation_state(session_label=session_label)
                else:
                    print(f"⚠️ Selenium 자동 발행도 실패: {sel_result}")
                    print("ℹ️ 화면 구조가 예상과 달라서 실패했을 수 있습니다. 아래 반자동 방식으로 계속 진행합니다.")
                    pyperclip.copy(blog_content)
                    print("\n" + "="*50)
                    print("✅ 원고 생성 완료!")
                    print("👉 워드프레스 에디터에서 '코드 편집기'(HTML 모드)로 전환한 뒤 붙여넣기(Ctrl+V) 하세요.")
                    print("="*50)
                    _print_final_quality_summary(final_quality_score, final_quality_issues, policy_issues_overall)
                    publish_confirm = _ask_yn("\n❓ 워드프레스에 실제로 발행하셨나요? (y/n): ")
                    if publish_confirm in ['y', 'yes', '네', 'ㅇ']:
                        estimated_wp_url = _estimate_wp_url(final_facts_json_str)
                        _register_article(final_title, generated_body, status='published', notes='autosaved with AI risk filter (manual paste)', version=current_version, extra_data=etf_data_cache, url=estimated_wp_url)
                        promote_published_article(driver, etf_list, plan, estimated_wp_url)
                        print("✅ 글 정보 및 팩트 데이터가 저장되었습니다. 다음 실행 시 과거 수치 비교가 작동합니다.")
                        _clear_generation_state(session_label=session_label)
                    else:
                        print("ℹ️ 발행하지 않으셨으므로 버전 정보가 저장되지 않았습니다. 다음 실행 시 동일한 버전으로 유지됩니다.")
            else:
                # [수정] 이전에는 API 실패 시 클립보드 복사만 하고 끝나서,
                # 무료 요금제(API 자체가 막혀있어 항상 실패)에서는 시리즈
                # 추적(이전 글 비교)에 필요한 _register_article이 전혀
                # 호출되지 않는 문제가 있었음. 티스토리와 동일하게 "실제로
                # 발행하셨나요?" 확인 절차를 거쳐 저장하도록 보강. 나중에
                # 비즈니스 요금제로 올려 API가 열리면 이 블록 자체를
                # 안 타게 되므로(위 wp_success가 True가 되므로) 코드를
                # 다시 고칠 필요 없이 자동으로 API 경로로 전환된다.
                print(f"⚠️ 워드프레스 API 발행 실패: {wp_result}")
                print("ℹ️ .env에 WP_OAUTH_TOKEN/WP_SITE_ID가 없거나 잘못되었을 수 있습니다 (요금제와는 무관합니다).")
                print("ℹ️ .env에 WP_EMAIL/WP_PASSWORD를 추가하면 Selenium 완전자동 발행을 시도할 수 있습니다.")
                pyperclip.copy(blog_content)
                print("\n" + "="*50)
                print("✅ 원고 생성 완료!")
                print("👉 워드프레스 에디터에서 '코드 편집기'(HTML 모드)로 전환한 뒤 붙여넣기(Ctrl+V) 하세요.")
                print("="*50)
                _print_final_quality_summary(final_quality_score, final_quality_issues, policy_issues_overall)
                publish_confirm = _ask_yn("\n❓ 워드프레스에 실제로 발행하셨나요? (y/n): ")
                if publish_confirm in ['y', 'yes', '네', 'ㅇ']:
                    # 실제 발행 URL을 코드가 알 방법이 없으므로(사람이 직접
                    # 붙여넣는 방식), WP_SITE_URL 기준 추정 URL을 남긴다.
                    # 정확한 URL은 아니지만 저장 안 하는 것보다는 낫다.
                    estimated_wp_url = _estimate_wp_url(final_facts_json_str)
                    _register_article(final_title, generated_body, status='published', notes='autosaved with AI risk filter (manual paste)', version=current_version, extra_data=etf_data_cache, url=estimated_wp_url)
                    promote_published_article(driver, etf_list, plan, estimated_wp_url)
                    print("✅ 글 정보 및 팩트 데이터가 저장되었습니다. 다음 실행 시 과거 수치 비교가 작동합니다.")
                    _clear_generation_state(session_label=session_label)
                else:
                    print("ℹ️ 발행하지 않으셨으므로 버전 정보가 저장되지 않았습니다. 다음 실행 시 동일한 버전으로 유지됩니다.")
                    print("ℹ️ 발행하지 않으셨으므로 버전 정보가 저장되지 않았습니다. 다음 실행 시 동일한 버전으로 유지됩니다.")

        else:
            # 기존 로직 (크롬 브라우저 실행 ~ 글 등록 로직 전체) - 티스토리
            driver.get("https://www.tistory.com/auth/login")
            time.sleep(2)
            driver.find_element(By.CLASS_NAME, "link_kakao_id").click()
            time.sleep(2)

            def paste_val(name, text):
                el = driver.find_element(By.NAME, name)
                el.click()
                pyperclip.copy(text)
                el.send_keys(Keys.CONTROL, 'v')
                time.sleep(0.5)

            paste_val("loginId", TISTORY_ID); paste_val("password", TISTORY_PW)
            driver.find_element(By.CSS_SELECTOR, ".btn_g.highlight.submit").click()

            print("⏳ 로그인 대기 (20초)...")
            time.sleep(20)

            driver.get(f"{BLOG_NAME}/manage/newpost")
            print("📝 글 티스토리 에디터 진입 및 알림창 처리 중...")

            try:
                WebDriverWait(driver, 5).until(EC.alert_is_present())
                alert = driver.switch_to.alert
                alert.dismiss()
                print("✅ 알림창 제거 완료.")
            except TimeoutException: pass

            time.sleep(3)

            if tags:
                for tag in tags:
                    try:
                        # 태그를 입력할 때마다 DOM이 갱신되므로 매번 요소를 새로 찾음
                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "tagText")))
                        tag_input = driver.find_element(By.ID, "tagText")
                        pyperclip.copy(tag)
                        tag_input.send_keys(Keys.CONTROL, 'v')
                        tag_input.send_keys(Keys.ENTER)
                        time.sleep(0.8) # 티스토리 태그 생성 애니메이션 대기
                    except Exception as e:
                        print(f"⚠️ '{tag}' 태그 입력 실패: {type(e).__name__}: {e} - 무시하고 계속 진행")
                        continue

            pyperclip.copy(blog_content)
            print("\n" + "="*50)
            print("✅ 원고 생성 완료!")
            print("👉 티스토리 에디터 [HTML 모드]에서 붙여넣기(Ctrl+V) 하세요.")
            print("="*50)

            # 발행 여부를 사람이 판단할 수 있도록, 자동 품질 검수 결과를 다시 한번 요약해서 보여줌.
            # (재생성 루프 중에는 로그가 여러 번 지나가서 놓치기 쉬우므로 여기서 최종 요약을 반드시 노출)
            print("\n📋 발행 전 최종 품질 검수 요약")
            if final_quality_score is None:
                print("   ⚠️ 자동 품질 검수가 완료되지 못했습니다. 반드시 본문을 직접 읽고 판단하세요.")
            else:
                print(f"   품질 점수: {final_quality_score:.2f} / 1.00 (0.6 미만이면 위험 신호)")
            if final_quality_issues:
                print("   지적된 문제점:")
                for issue in final_quality_issues:
                    print(f"   - {issue}")
            else:
                print("   지적된 문제점 없음")

            # [추가] 정책 필터(_policy_filter)가 실제로 자동 치환한 표현이 있다면
            # 여기서 함께 보여줌. 지금까지는 이 정보가 수집만 되고 화면에 전혀
            # 노출되지 않아, 어떤 문구가 왜 바뀌었는지 확인할 방법이 없었음.
            if policy_issues_overall:
                unique_policy_issues = list(dict.fromkeys(policy_issues_overall))  # 중복 제거, 순서 유지
                print("   자동 순화된 표현 (애드센스 정책 대응):")
                for issue in unique_policy_issues:
                    print(f"   - {issue}")

            print("="*50)

            # 티스토리 발행 성공 시에만 등록
            publish_confirm = _ask_yn("\n❓ 티스토리에 실제로 발행하셨나요? (y/n): ")
            if publish_confirm in ['y', 'yes', '네', 'ㅇ']:
                # [추가] recommended_url(사람이 티스토리 URL 슬러그로 실제 입력하도록
                # 안내되는 값)로 예상 발행 URL을 구성해 저장. 정확한 URL은 사람이
                # 슬러그를 그대로 썼을 때만 맞지만, 저장 안 하는 것보다는 "이전 글
                # 링크" 기능이 작동할 확률이 훨씬 높아짐. 사람이 슬러그를 다르게
                # 입력했다면 다음 실행 때 이 URL이 틀릴 수 있으니 참고용으로만 사용.
                estimated_url = ''
                try:
                    if final_facts_json_str:
                        parsed_facts = json.loads(final_facts_json_str)
                        slug = parsed_facts.get('recommended_url', '')
                        if slug and BLOG_NAME:
                            estimated_url = f"{BLOG_NAME.rstrip('/')}/entry/{slug}"
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
                _register_article(final_title, generated_body, status='published', notes='autosaved with AI risk filter', version=current_version, extra_data=etf_data_cache, url=estimated_url)
                promote_published_article(driver, etf_list, plan, estimated_url)
                print("✅ 글 정보 및 팩트 데이터가 저장되었습니다. 다음 실행 시 과거 수치 비교가 작동합니다.")
                _clear_generation_state(session_label=session_label)
            else:
                print("ℹ️ 발행하지 않으셨으므로 버전 정보가 저장되지 않았습니다. 다음 실행 시 동일한 버전으로 유지됩니다.")

    except Exception as e:
        print(f"❌ 오류 발생: {type(e).__name__}: {e}")
    finally:
        # 에러 발생 여부와 상관없이 무조건 실행되어 프로세스 종료
        try:
            driver.quit()
        except Exception:
            pass
    
    _pause("\n엔터를 누르면 종료됩니다...")

if __name__ == "__main__":
    run_automation()