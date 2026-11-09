"""ETF 부서 공용 설정: 환경값·상수·종목 목록·blog_engine 공용 함수.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
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
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))  # 저장소 맨 위의 .env

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
CONFIRMED_TOPIC2_FILE = "confirmed_topic2_context.json"

__all__ = [k for k in dir() if not k.startswith('__')]
