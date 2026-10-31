"""blog_engine.py — 카테고리 무관 공용 발행 엔진.

ETF와 두 번째 슬롯(트렌드/기술·특허/바이오/에너지/인구·사회) 스크립트가 공유하는 "방식"들을 모아둔
모듈이다. 원래 tistory_auto.py(ETF 전용 8천줄 스크립트) 안에 있던 기능 중
도메인에 상관없이 재사용 가능한 부분(Gemini API 호출/키·모델 로테이션,
Part 단위 품질검수+타깃수정, 애드센스 정책 필터, 워드프레스 발행,
텔레그램 알림, IndexNow, Threads 카드뉴스, 상태/중복관리, SEO 제목 최적화)
만 뽑아서 여기로 옮겼다.

카테고리별 스크립트(etf_auto.py, topic_engine.py)는
`from blog_engine import ...`로 이 함수들을 가져다 쓰고, 자기 도메인 고유
로직(주제 발굴, Part1~5 프롬프트, 팩트시트 스키마)만 각자 파일에 둔다.

[카테고리별 상태 파일 격리] 여러 카테고리가 같은 article_state.json 등을
공유하면 한 카테고리의 중복검사/발행간격 체크가 다른 카테고리 글에 영향을
주는 문제가 생긴다. 이를 막기 위해 환경변수 BLOG_CATEGORY(예: etf/trend/tech/
bio/energy/society)로 모든 상태 파일 이름 앞에 접두어를 붙여 자동으로 격리한다.
IndexNow 인증키만 예외로 카테고리 구분 없이 사이트 전체가 공유한다(같은
사이트는 어떤 카테고리로 글을 올리든 검색엔진에 알리는 인증키는 하나면
충분하기 때문).
"""

import time
import requests
import re
import html
import os
import json
import hashlib
import uuid
import pyperclip
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv
import secrets as _secrets_module  # 이름 충돌 방지용 별칭(IndexNow 키 생성에 사용)
import atexit

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# 절대 경로 설정 (작업 디렉토리 위치와 무관하게 동작)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 카테고리 구분 (상태 파일 격리용)
# ============================================================
BLOG_CATEGORY = os.environ.get("BLOG_CATEGORY", "default").strip().lower()


def _cat_path(filename):
    """카테고리별로 격리된 상태 파일 경로를 만든다. 예: tech_article_state.json"""
    return os.path.join(BASE_DIR, f"{BLOG_CATEGORY}_{filename}")


# ============================================================
# 워드프레스 발행용 접속 정보
# ============================================================
WP_SITE_URL = os.environ.get("WP_SITE_URL")
WP_OAUTH_TOKEN = os.environ.get("WP_OAUTH_TOKEN")
WP_SITE_ID = os.environ.get("WP_SITE_ID")
WP_EMAIL = os.environ.get("WP_EMAIL")
WP_PASSWORD = os.environ.get("WP_PASSWORD")

# ============================================================
# Gemini API 키 로테이션
# ============================================================
_raw_gemini_keys = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in _raw_gemini_keys.split(",") if k.strip()]
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None  # 하위 호환용

# ============================================================
# 텔레그램 / Threads
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "")

# 카테고리별로 격리되는 상태 파일들
STATE_FILE = _cat_path('article_state.json')
GENERATION_STATE_FILE = _cat_path('generation_state.json')
DATA_CACHE_FILE = _cat_path('data_cache.json')
QUOTE_FILE = _cat_path('quotes_history.txt')
API_USAGE_LOG_FILE = _cat_path('api_usage_log.json')
RAW_RESPONSES_DIR = os.path.join(BASE_DIR, BLOG_CATEGORY, 'raw_responses')
PUBLISHED_ARTICLES_DIR = os.path.join(BASE_DIR, BLOG_CATEGORY, 'published_articles')

# [주의] IndexNow 인증키는 카테고리 구분 없이 사이트 전체가 공유한다.
INDEXNOW_KEY_STATE_FILE = os.path.join(BASE_DIR, 'indexnow_key.json')

NEWS_CACHE_TTL = 60 * 60  # 1시간 캐시

# _llm_part_check(PART_CHECK_SAFE_CAP)와 동일한 상한을 씀
PREVIOUS_CONTENT_BLOCK_CAP = 40000

# Threads 카드뉴스 이미지 크기 (인스타그램/Threads 세로형 카드 표준 비율 4:5)
CARD_WIDTH = 1080
CARD_HEIGHT = 1350


# ============================================================
# Gemini API 호출 통계 (주간 상태점검 리포트용)
# ============================================================
_api_call_stats = {"total_calls": 0, "by_model": {}, "model_switch_events": {}}

# 키 로테이션을 위한 현재 키 인덱스. 함수 호출 사이에 유지되는 전역 상태.
_current_key_index = 0

# "모든 API 키가 완전히 소진된 상태"를 전역으로 기억하는 플래그.
_all_keys_exhausted = False
_all_keys_exhausted_at = None
_EXHAUSTED_RETRY_WAIT_SECONDS = 300
_exhausted_retry_cycles = 0
_MAX_EXHAUSTED_RETRY_CYCLES = 2

# 403(PERMISSION_DENIED)을 받아 이번 실행 동안 완전히 제외된 키 목록.
_permanently_excluded_keys = set()

# 모델 로테이션을 위한 현재 모델 인덱스.
_current_model_index = 0

# 이번 프로세스 실행 동안 계산한 모델 우선순위 캐시.
_gemini_model_priority_cache = None


def _post_process_blog_content(html):
    """AI 감지 리스크를 줄이기 위한 간단한 후처리 및 버그 픽스"""
    # 1. 흉측한 리터럴 \n, \t 텍스트 화면 노출 버그 강제 제거
    html = html.replace('\\n', ' ')  # 공백으로 치환
    html = html.replace('\\t', ' ')  # 공백으로 치환
    html = html.replace('\\"', '"')
    html = re.sub(r'\s+', ' ', html)  # 다중 공백 정리
    
    # [수정] 티스토리 스킨 충돌 방지: hr 대신 div를 사용해 1px 얇은 실선을 강제로 그립니다.
    html = re.sub(r'<hr[^>]*>', '', html)
    html = re.sub(r'(<(?:h2|h3)[^>]*>)', r'<div style="width:100%; height:1px; background-color:#ddd; margin:40px 0;"></div>\1', html, flags=re.IGNORECASE)

    replacements = {
        '하는 것이 좋습니다': '하면 좋겠습니다',
        '또한': '그리고',
        '투자자라면': '투자자분이라면',
    }
    for old, new in replacements.items():
        html = html.replace(old, new)

    # [수정] '하지만' -> '다만'을 단순 str.replace로 하면 "발생하지만"->"발생다만",
    # "제공하지만"->"제공다만", "미치지만"처럼 다른 동사 어간 뒤에 붙은 "~하지만"도
    # 전부 오염시켜 "발생다만/제공다만" 같은 비문을 만드는 버그가 실제로 있었음
    # ("영향을 미치지만"은 '하지만'이 아니라 '치지만'이라 원래 안전했지만, "발생/제공/
    # 작용/의미"처럼 '하지만'으로 끝나는 동사 어간은 전부 걸림).
    # 독립된 접속사 "하지만"(앞에 한글 동사 어간이 붙어있지 않은 경우)일 때만 치환.
    html = re.sub(r'(?<![가-힣])하지만', '다만', html)

    # [점검] '구조적으로' -> '틀을 잡아'도 부분 매치 위험을 확인해봤으나, "구조적으로"는
    # 그 자체로 독립된 4음절 부사라 다른 단어 안에 우연히 포함될 가능성이 낮아 그대로 둠.
    html = html.replace('구조적으로', '틀을 잡아')

    # 불필요한 문장 반복 간략화
    html = html.replace('이 부분을 반드시 확인해야 합니다. 이 부분을 반드시 확인해야 합니다.', '이 부분을 반드시 확인해야 합니다.')
    
    # 2. 중간에 뜬금없이 부활하는 '좀비 인사말' 강제 삭제 (첫 서론 인사만 보호)
    # 앞부분 1500자는 서론이므로 냅두고, 그 뒤(tail)에서 튀어나오는 인삿말 p태그를 싹 지움
    head = html[:1500]
    tail = html[1500:]
    tail = re.sub(r'<p>[^<]*(?:안녕하세요|반갑습니다).*?온도\(ondo\).*?</p>', '', tail, flags=re.IGNORECASE | re.DOTALL)
    html = head + tail

    # 3. [안전장치] AI가 `<h4>🔸 소제목</h4>`를 쓰려다 태그를 깨뜨려
    # `<h4 h4="" 소제목="" 단어="" 순서가="" 뒤죽박죽="" 🔸="">` 형태로 나오는 경우가 있었음.
    # 프롬프트에서 명확한 예시를 주도록 고쳐서 재발 가능성은 낮췄지만, 혹시 남아있다면
    # 단어 순서가 이미 깨진 뒤라 완벽 복원은 불가능함. 대신 최소한 유효한 HTML
    # 문법으로는 되돌리고(속성 형태 제거), 발행 전 사람이 알아채도록 콘솔에 경고를 남김.
    broken_h4_count = len(re.findall(r'<h4\s+(?:[^\s="]+=""\s*)+>', html))
    if broken_h4_count > 0:
        print(f"⚠️ 깨진 <h4> 태그 {broken_h4_count}건 발견 - 자동으로 텍스트만 추출해 복구했습니다. 발행 전 해당 소제목이 자연스러운지 꼭 확인하세요.")

    def _fix_broken_h4(match):
        attrs_str = match.group(1)
        words = re.findall(r'([^\s="]+)=""', attrs_str)
        # 'h4' 자체가 속성명으로 섞여 들어간 경우 제거하고, 남은 조각들을 이어붙임
        # (원래 단어 순서 정보는 이미 유실된 상태라 완벽 복원은 불가능 - 사람 확인 필요)
        words = [w for w in words if w.lower() != 'h4']
        text = ' '.join(words).replace('<=', '').strip()
        return f'<h4>🔸 {text}</h4>' if text else ''

    html = re.sub(r'<h4\s+((?:[^\s="]+=""\s*)+)>', _fix_broken_h4, html)

    # 4. [안전장치] 온도계 안내 문구(예: "투자 타이밍이 중립적입니다. 신중히
    # 접근하세요.")는 글 맨 앞 온도계 배너에 이미 한 번 나오는데, AI가 서론이나
    # 본문에서 이 문구를 그대로 다시 언급해 반복되는 경우가 실제로 있었음.
    # Part1 프롬프트에서 반복 금지를 명시했지만, 혹시 모를 재발에 대비해
    # 이 고정 문구들이 2회 이상 등장하면 첫 등장만 남기고 이후는 제거한다.
    temperature_messages = [
        '보수적 투자자에게도 매수 매력이 높습니다.',
        '현재 매수하기에 비교적 좋은 시점입니다.',
        '투자 타이밍이 중립적입니다. 신중히 접근하세요.',
        '지금은 추가 자료 확인 후 매수를 결정하는 것이 좋습니다.',
        '현 시점에서 매수는 위험할 수 있으며 보수적인 관점이 필요합니다.',
    ]
    for msg in temperature_messages:
        count = html.count(msg)
        if count > 1:
            # 첫 등장 위치를 찾아 보존하고, 그 뒤에 나오는 것들만 제거
            first_idx = html.find(msg)
            before = html[:first_idx + len(msg)]
            after = html[first_idx + len(msg):].replace(msg, '')
            html = before + after

    return html


def _slugify_anchor(text):
    anchor = re.sub(r'<[^>]+>', '', text)
    anchor = anchor.strip()
    anchor = re.sub(r'[^0-9a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ]+', '-', anchor)
    anchor = anchor.strip('-').lower()
    return anchor or f'section-{uuid.uuid4().hex[:8]}'


def _inject_table_of_contents(html):
    """본문 HTML에 목차 상자를 삽입하고 섹션 제목에 앵커 ID를 추가합니다."""
    headings = []
    used_ids = set()

    def replace_heading(match):
        open_tag = match.group(1)
        inner_text = match.group(2)
        close_tag = match.group(3)

        if 'id=' in open_tag:
            existing_id_match = re.search(r'id=["\']([^"\']+)["\']', open_tag)
            heading_id = existing_id_match.group(1) if existing_id_match else _slugify_anchor(inner_text)
        else:
            heading_id = _slugify_anchor(inner_text)
            duplicate_counter = 1
            base_id = heading_id
            while heading_id in used_ids:
                duplicate_counter += 1
                heading_id = f"{base_id}-{duplicate_counter}"
            open_tag = open_tag.rstrip('>') + f' id="{heading_id}">'

        used_ids.add(heading_id)
        
        # HTML 태그 제거
        stripped_text = re.sub(r'<[^>]+>', '', inner_text).strip()
        # AI가 제목 앞에 임의로 붙인 숫자, 온점, 괄호 등 제거 (예: "1. ", "2) ")
        clean_text = re.sub(r'^\d+[\.\-\)]?\s*', '', stripped_text)
        clean_text = re.sub(r'^part\s*\d+\s*[:.\-)]?\s*', '', clean_text, flags=re.IGNORECASE)
        
        headings.append((heading_id, clean_text))
        return open_tag + inner_text + close_tag

    # h3 태그를 목차로 수집
    html_with_ids = re.sub(r'(<h3[^>]*>)(.*?)(</h3>)', replace_heading, html, flags=re.DOTALL | re.IGNORECASE)

    if len(headings) < 3:
        return html_with_ids

    priority_keywords = ['수익', '배당', '리스크', '위험', '포트폴리오', '시나리오', '타이밍', '전략', '결론']
    selected_headings = []
    
    # 1. 우선순위 키워드가 포함된 항목 먼저 추출
    for hid, text in headings:
        if any(kw in text for kw in priority_keywords):
            selected_headings.append((hid, text))
            
    # 2. 5개가 안 되면 나머지 항목으로 채움
    if len(selected_headings) < 5:
        for hid, text in headings:
            if (hid, text) not in selected_headings:
                selected_headings.append((hid, text))
                if len(selected_headings) >= 5:
                    break
                    
    # 3. 최종적으로 최대 5개까지만 자르고, 목차는 글에 나오는 순서대로 보여준다
    #    (예전엔 '배당'·'수익' 같은 단어가 든 제목을 앞으로 당겨서 목차 순서가 뒤죽박죽이 됐다)
    order = {hid: i for i, (hid, _) in enumerate(headings)}
    selected_headings = sorted(selected_headings[:5], key=lambda h: order[h[0]])

    # 목차 아이템 생성 시 코드상의 숫자({idx}) 제거
    toc_items = ''
    for hid, text in selected_headings:
        toc_items += f'<li><a href="#{hid}">{text}</a></li>'

    # 간결한 목차 HTML
    toc_html = (
        '<div style="margin:20px 0; padding:18px 22px; border-radius:8px; '
        'background:#f8fafb; border-left:3px solid #1f3c88; '
        'box-shadow:0 1px 4px rgba(0,0,0,0.08);">'
        '<h2 style="margin:0 0 12px 0; font-size:16px; color:#1f3c88; font-weight:700;">📑 핵심 목차</h2>'
        f'<ul style="margin:0; padding-left:20px; list-style-type:decimal;">'
        f'{toc_items}'
        '</ul></div>'
    )

    if '<h1' in html_with_ids.lower():
        html_with_toc = re.sub(r'(<h1[^>]*>.*?</h1>)', r'\1' + toc_html, html_with_ids, count=1, flags=re.DOTALL | re.IGNORECASE)
    else:
        html_with_toc = toc_html + html_with_ids

    return html_with_toc


def _load_state(state_file=None):
    path = state_file or STATE_FILE
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ 상태 파일 로드 실패: {type(e).__name__}: {e}")
    return {'articles': []}


def _save_state(state, state_file=None):
    path = state_file or STATE_FILE
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ 상태 파일 저장 실패: {type(e).__name__}: {e}")


def _load_json_file(file_path, default=None):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ JSON 파일 로드 실패 ({file_path}): {type(e).__name__}: {e}")
    return default


def _save_json_file(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ JSON 파일 저장 실패 ({file_path}): {type(e).__name__}: {e}")


# ------------------------------------------------------------
# 예약 실행 보충 - 깃허브 예약 실행은 몇 시간씩 밀리거나 아예 빠지는 일이 잦다
# (실제로 2026-10-29~30에 10분마다 돌아야 할 잡이 11시간 동안 3번만 돌았고,
# 아침 7:30 추천은 아예 안 돌았다). 그래서 "오늘 이미 보냈는지"를 파일에 남기고,
# 10분 점검 잡이 돌 때마다 놓친 추천이 있으면 대신 보낸다.
# ------------------------------------------------------------
SCHEDULE_STATE_FILE = "schedule_state.json"
CATCHUP_LAST_HOUR_KST = 22   # 이 시각(KST) 이후엔 늦은 밤이라 보충하지 않고 다음 날로 넘김


def _kst_now():
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)


def _discover_due(kind, hour, minute):
    """kind(etf/topic)의 오늘 추천이 아직이고, 정해진 시각(KST)이 지났으면 True."""
    now = _kst_now()
    state = _load_json_file(SCHEDULE_STATE_FILE, {}) or {}
    if state.get(kind) == now.strftime("%Y-%m-%d"):
        return False
    return (now.hour, now.minute) >= (hour, minute) and now.hour < CATCHUP_LAST_HOUR_KST


def _mark_discovered(kind):
    state = _load_json_file(SCHEDULE_STATE_FILE, {}) or {}
    state[kind] = _kst_now().strftime("%Y-%m-%d")
    _save_json_file(SCHEDULE_STATE_FILE, state)


def _load_generation_state():
    return _load_json_file(GENERATION_STATE_FILE, default={'sessions': {}})


def _save_generation_state(state):
    _save_json_file(GENERATION_STATE_FILE, state)


def _get_raw_response_path(session_key, part_num, label=None):
    """[신규] Part별 원본 JSON 저장 경로를 결정.
    session_key(해시)는 캐시 매칭에 쓰이던 값 그대로 유지해 기존 로직과의
    호환성을 지키되, 실제 파일명에는 label(예: "2026-07-06_IBIT")을 붙여서
    파일명만 보고도 어떤 날짜의 어떤 티커인지 바로 알아볼 수 있게 한다.
    label이 없으면 세션키만으로 구성(하위 호환).
    같은 세션 안에서는 파트번호로 구분되고, 재생성되면 같은 경로에 덮어써진다
    (가장 최근/최종 확정된 버전만 유지하는 게 검토 목적에 맞음)."""
    os.makedirs(RAW_RESPONSES_DIR, exist_ok=True)
    if label:
        # 파일명에 부적합한 문자(경로 구분자 등) 제거
        safe_label = re.sub(r'[\\/:*?"<>|]+', '_', label)
        filename = f"{safe_label}_part{part_num}_{session_key[:8]}.json"
    else:
        filename = f"{session_key}_part{part_num}.json"
    return os.path.join(RAW_RESPONSES_DIR, filename)


def _save_raw_part_response(session_key, part_num, response_text, label=None):
    """Part 생성이 성공(검수 통과 또는 최대 재시도 후 확정)했을 때, AI가 준
    원본 JSON 그대로(html+facts)를 파일로 저장. 사람이 이 파일을 직접 열어
    html이나 facts 필드를 고칠 수 있고, 그 수정은 _load_raw_part_response로
    다시 읽을 때 그대로 반영된다."""
    path = _get_raw_response_path(session_key, part_num, label=label)
    try:
        # response_text 자체가 이미 JSON 문자열이므로, 파싱해서 보기 좋게
        # indent를 넣어 저장한다 (사람이 직접 열어 읽고 고치기 쉽도록).
        parsed = json.loads(response_text)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        print(f"💾 Part{part_num} 원본 응답 저장: {path}")
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Part{part_num} 원본 응답 저장 실패 (검토용 파일만 실패, 진행에는 영향 없음): {type(e).__name__}: {e}")


def _load_raw_part_response(session_key, part_num, label=None):
    """저장된 Part 원본 JSON을 다시 읽어온다. 사람이 파일을 직접 고쳤다면
    그 수정된 내용 그대로 반환된다. 파일이 없거나 손상됐으면 None을 반환하고,
    호출부는 이 경우 메모리에 있던 원래 값을 그대로 쓰면 된다(안전한 폴백)."""
    path = _get_raw_response_path(session_key, part_num, label=label)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Part{part_num} 저장된 응답 읽기 실패 - 메모리 값을 대신 사용합니다: {type(e).__name__}: {e}")
        return None


def _clear_generation_state(session_label=None):
    """발행이 완전히 끝난 시점에 호출된다. generation_state.json을 지워
    "재개할 세션이 없음" 상태로 만드는 기존 동작에 더해, session_label이
    주어지면 raw_responses/ 폴더에서 이번 세션이 만든 Part1~5 원본 JSON
    파일도 함께 지운다.

    [신규] 발행이 끝난 raw_responses/ 파일은 더 이상 아무도 읽지 않는다
    (_load_raw_part_response는 "재시도/재생성 진행 중"일 때만 쓰이고, 세션이
    끝나면 다시 열릴 일이 없음 - 사람이 검토용으로 열어보는 것도 발행 *전에*
    하는 것이지 발행 후엔 의미가 없음). GitHub Actions처럼 무인으로 도는
    환경에서는 애초에 이 파일을 열어 손으로 고칠 사람도 없으므로, 발행 완료와
    동시에 지워서 디스크(혹은 git 저장소) 용량이 계속 쌓이는 걸 막는다.
    로컬에서 사람이 검토 목적으로 계속 남겨두고 싶다면 KEEP_RAW_RESPONSES=1을
    .env에 넣어 이 정리 동작을 끌 수 있다."""
    try:
        if os.path.exists(GENERATION_STATE_FILE):
            os.remove(GENERATION_STATE_FILE)
    except OSError as e:
        print(f"⚠️ 생성 상태 파일 삭제 실패: {type(e).__name__}: {e}")

    if not session_label:
        return
    if os.environ.get("KEEP_RAW_RESPONSES", "").strip() == "1":
        print("ℹ️ KEEP_RAW_RESPONSES=1 설정으로 raw_responses/ 파일을 지우지 않고 남겨둡니다.")
        return
    if not os.path.isdir(RAW_RESPONSES_DIR):
        return

    safe_label = re.sub(r'[\\/:*?"<>|]+', '_', session_label)
    removed = 0
    try:
        for filename in os.listdir(RAW_RESPONSES_DIR):
            # 파일명 형식: "{safe_label}_part{번호}_{세션키8자리}.json"
            if filename.startswith(f"{safe_label}_part") and filename.endswith(".json"):
                try:
                    os.remove(os.path.join(RAW_RESPONSES_DIR, filename))
                    removed += 1
                except OSError as e:
                    print(f"⚠️ raw_responses 파일 삭제 실패({filename}): {type(e).__name__}: {e}")
        if removed:
            print(f"🧹 발행 완료 - 이번 세션의 raw_responses 파일 {removed}개를 정리했습니다.")
    except OSError as e:
        print(f"⚠️ raw_responses 폴더 조회 실패: {type(e).__name__}: {e}")


def _load_cache():
    return _load_json_file(DATA_CACHE_FILE, default={})


def _save_cache(cache):
    _save_json_file(DATA_CACHE_FILE, cache)


def _get_cached_record(cache, key, max_age):
    record = cache.get(key)
    if not record:
        return None
    try:
        if time.time() - float(record.get('timestamp', 0)) <= max_age:
            return record.get('data')
    except (TypeError, ValueError):
        return None
    return None


def _set_cached_record(cache, key, data):
    cache[key] = {'timestamp': time.time(), 'data': data}
    _save_cache(cache)


def _get_text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _is_similar_text(a, b):
    a_words = set(re.findall(r"\w+", a.lower()))
    b_words = set(re.findall(r"\w+", b.lower()))
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words)
    ratio = overlap / max(len(a_words), len(b_words))
    return ratio > 0.75


def _extract_section_titles(html_content, max_titles=15):
    """저장된 이전 글의 HTML에서 <h3> 제목들을 뽑아, 그 글이 어떤 섹션을
    중점적으로 다뤘는지 파악합니다. 같은 티커를 재작성할 때 이전 글과
    다른 앵글을 잡도록 지시하는 데 사용합니다."""
    titles = re.findall(r'<h3[^>]*>(.*?)</h3>', html_content, flags=re.DOTALL | re.IGNORECASE)
    cleaned = []
    for t in titles:
        clean = re.sub(r'<[^>]+>', '', t).strip()
        # 이모지 및 변형 선택자(variation selector) 등 앞머리 장식 문자 제거
        clean = re.sub(r'^[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\s]+', '', clean).strip()
        if clean and clean not in cleaned:
            cleaned.append(clean)
    return cleaned[:max_titles]


def _normalize_title_for_compare(title):
    t = re.sub(r"\[[^\]]*\]", " ", title or "")      # [ETF 비교] 같은 머리말
    t = re.sub(r"(19|20)\d{2}\s*년?", " ", t)          # 연도
    t = re.sub(r"[^\w가-힣]+", "", t.lower())
    return t


def _is_similar_title(a, b, threshold=0.85):
    """제목에서 머리말·연도·문장부호를 뺀 뒤 비교한다. "2026년"만 붙은 사실상 같은
    제목(티스토리에서 실제로 같은 글이 3일 간격으로 두 번 나간 사례)을 잡기 위함."""
    import difflib
    na, nb = _normalize_title_for_compare(a), _normalize_title_for_compare(b)
    if not na or not nb:
        return False
    return na == nb or difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def _check_duplicate(title, content, state):
    h = _get_text_hash(content)
    for item in state.get('articles', []):
        # 임시글(품질 미달로 공개 안 된 글)은 독자에게 안 보이므로 중복 비교에서 뺀다.
        # 안 그러면 같은 주제를 고친 코드로 다시 쓸 때 자기 임시글 때문에 막힌다.
        if item.get('status') == 'draft':
            continue
        if item.get('hash') == h or item.get('title') == title:
            return True
        if _is_similar_title(item.get('title', ''), title):
            return True
        if _is_similar_text(item.get('content', ''), content):
            return True
    return False


def _prune_old_article_content(state, keep_full_count=20, truncate_to=1000):
    """
    [신규] article_state.json이 전체 본문(수만 자)을 계속 누적 저장하다 보니,
    글이 쌓일수록 파일이 무한정 커지는 문제가 있었음. 중복 검사(_is_similar_text)와
    "이전 글과 다른 앵글 잡기"(_extract_section_titles)는 최근 글에서 특히
    의미가 크므로, 최근 keep_full_count개는 전체 본문을 그대로 유지하고
    그보다 오래된 글은 본문을 앞부분 일부(truncate_to자)로 축소한다.
    해시(hash)는 항상 그대로 보존하므로 "완전히 동일한 글 재발행" 탐지는
    오래된 글에 대해서도 계속 정상 작동한다.
    """
    articles = state.get('articles', [])
    if len(articles) <= keep_full_count:
        return state

    # 최신 글이 리스트 뒤쪽에 append되므로, 뒤에서 keep_full_count개를 제외한
    # 나머지(오래된 글)만 축소 대상
    cutoff = len(articles) - keep_full_count
    pruned_count = 0
    for article in articles[:cutoff]:
        content = article.get('content', '')
        if len(content) > truncate_to:
            article['content'] = content[:truncate_to]
            article['content_truncated'] = True  # 축소됐음을 표시해 혼동 방지
            pruned_count += 1

    if pruned_count > 0:
        print(f"🧹 오래된 글 {pruned_count}건의 본문을 축소해 상태 파일 용량을 관리했습니다.")

    return state


def _save_published_article_file(title, html_content, topic_keys, version=1):
    """완성된 최종 글(제목/목차/태그까지 다 합쳐진 상태)을 주제 키별
    폴더에 사람이 읽기 좋은 형태로 저장한다. (ETF는 티커, 테크/바이오/특허는
    슬러그 등 카테고리별로 다른 값을 topic_keys에 넘기면 된다.)

    구조: published_articles/{키}/{날짜}_{키}[_v{버전}].html
    예:   published_articles/QQQ/2026-07-09_QQQ.html
          published_articles/QQQ/2026-08-15_QQQ_v2.html (같은 키 재분석 시)

    여러 키를 한 글에서 같이 다뤘다면 각 키 폴더에 전부 저장한다 - 어느
    폴더에서 찾아도 그 글을 볼 수 있게.

    실패해도(디스크 문제 등) 전체 발행 흐름을 막지 않도록 조용히 로그만
    남기고 넘어간다 - 이건 편의 기능이지 발행 자체의 필수 조건이 아니다."""
    if not html_content:
        return

    date_str = datetime.now().strftime('%Y-%m-%d')
    keys = topic_keys or ['UNKNOWN']

    # 파일 안에 제목을 맨 위에 명시해서, 메모장으로 열었을 때 바로 무슨
    # 글인지 알아볼 수 있게 한다(HTML 주석이라 실제 렌더링에는 영향 없음).
    file_content = f"<!-- 제목: {title} -->\n<!-- 저장일: {date_str} -->\n\n{html_content}"

    for key in keys:
        key_clean = key.replace(".KS", "").replace(".US", "")
        try:
            key_dir = os.path.join(PUBLISHED_ARTICLES_DIR, key_clean)
            os.makedirs(key_dir, exist_ok=True)
            version_suffix = f"_v{version}" if version and version > 1 else ""
            filename = f"{date_str}_{key_clean}{version_suffix}.html"
            filepath = os.path.join(key_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(file_content)
            print(f"💾 완성본 저장: {filepath}")
        except OSError as e:
            print(f"⚠️ {key_clean} 완성본 파일 저장 실패(발행 자체엔 영향 없음): {type(e).__name__}: {e}")


def _register_article(title, content, status='draft', notes='', version=1, extra_data=None, url='', state_file=None):
    state = _load_state(state_file)
    state['articles'].append({
        'title': title,
        'hash': _get_text_hash(content),
        # [중요] 이전 버전은 content[:500]만 저장해서, 글 중후반부(연령별 포트폴리오,
        # 경제 사이클 표 등 반복되기 쉬운 섹션)에 있는 중복은 _is_similar_text가 아예
        # 비교하지 못했음. 전체 본문을 저장해 실제 유사도 비교가 가능하도록 함.
        # 파일 용량 관리는 _prune_old_article_content가 오래된 글에 한해 담당함.
        'content': content,
        'status': status,
        'notes': notes,
        'timestamp': datetime.now().isoformat(),
        'version': version,
        'topic_data': extra_data or {},  # 과거 팩트 데이터 저장용 필드
        # [추가] 이전에는 url을 아예 저장하지 않아서, _get_previous_analysis가
        # 같은 티커 재분석 시 "이전 글 URL"을 언급하려 해도 항상 빈 값이었음.
        # 실제 발행 URL은 이 코드가 알 수 없지만(사람이 직접 붙여넣는 방식),
        # 팩트시트의 recommended_url(사람이 티스토리 URL 슬러그로 실제 사용하도록
        # 안내되는 값)로 예상 URL을 구성해 저장한다.
        'url': url,
    })
    state = _prune_old_article_content(state)
    _save_state(state, state_file)


def _llm_part_check(part_html, part_label, previous_parts_summary, max_retries=2, category_label="ETF"):
    """
    완성본 전체를 보는 _llm_quality_check와 달리, Part 하나가 생성되는 즉시
    그 Part만 빠르게 검수합니다. 목적은 두 가지:
    1) 방금 생성된 Part가 이전 Part들과 내용이 겹치지 않는지 (목차/메타/서론 중복,
       같은 조언 반복 등)
    2) 이 Part 자체가 다른 ETF 글에도 그대로 쓸 수 있는 뻔한 문장으로 채워지지 않았는지

    [중요] 이 함수는 반드시 "이전 Part는 이미 확정된 상태"에서만 호출해야 합니다.
    즉 Part n을 검수할 때는 Part 1~(n-1)이 이미 통과되어 session에 저장된 뒤여야
    하며, 절대로 나중에 이전 Part로 거슬러 올라가 재검수/재생성해서는 안 됩니다.
    그렇게 하면 이후 Part들이 이미 옛날 버전을 참고해 쓰여진 상태라 중복/모순이
    생길 수 있습니다. 순서: Part 생성 -> 이 함수로 검수 -> 실패시 그 자리에서
    Part만 재생성 -> 통과하면 확정 -> 다음 Part로 진행.

    실패 시(응답 없음/파싱 실패) None을 반환하며, 호출부는 이를 "검수 불가"로
    처리해 통과로 간주하지 않아야 합니다.
    """
    # [수정] 예전엔 뒤 3000자만 잘라서 넘겼는데, 호출부도 이제 전체 누적 히스토리
    # (p1~p_(n-1))를 넘기도록 고쳤으므로 여기서 다시 뒤쪽만 잘라버리면 그 수정이
    # 무의미해진다. HTML 태그(script/style 포함)는 벗겨서 텍스트만 남기고,
    # 전체를 그대로 넘긴다 - 최종 검수(_llm_quality_check)와 동일한 방식.
    summary_excerpt = _extract_text_for_review(previous_parts_summary) if previous_parts_summary else ""
    PART_CHECK_SAFE_CAP = 40000
    if len(summary_excerpt) > PART_CHECK_SAFE_CAP:
        print(f"⚠️ {part_label} 검수: 이전 파트 누적 텍스트가 {len(summary_excerpt)}자로 예상보다 깁니다. "
              f"뒤 {PART_CHECK_SAFE_CAP}자만 검수에 사용합니다.")
        summary_excerpt = summary_excerpt[-PART_CHECK_SAFE_CAP:]

    prompt = (
        f"당신은 한국어 원어민 편집자입니다. 5개 파트로 나눠 순차 생성 중인 {category_label} 블로그 글에서 "
        f"방금 '{part_label}' 파트가 생성되었습니다. 이 파트만 아래 기준으로 빠르게 검수하세요.\n\n"
        "체크리스트:\n"
        "1. duplicate_with_previous: 아래 [이전까지 생성된 내용 요약]과 실질적으로 같은 내용(같은 조언, "
        "같은 문장 구조, 이미 나온 섹션 재작성)이 이 파트에 또 나오는가?\n"
        "2. thin_content: 이 파트의 문단을 소재명만 바꿔 다른 글에 그대로 붙여도 말이 되는 "
        "뻔한 일반론 문장이 있는가?\n"
        "3. broken_html: h3/table 등 HTML 태그가 깨지거나 지시받은 형식(표 등)을 안 지킨 부분이 있는가?\n\n"
        "아래 JSON 형식으로만 답하세요 (다른 텍스트 없이):\n"
        "{\n"
        '  "quality_score": 0.0에서 1.0 사이 숫자 (1.0 = 문제 없음),\n'
        '  "issues": ["구체적 문제점을 한국어로 짧게 나열, 없으면 빈 배열"],\n'
        '  "pass": true 또는 false\n'
        "}\n\n"
        "[이전까지 생성된 내용 전체 (HTML 태그 제거, 텍스트만)]\n"
        f"{summary_excerpt}\n\n"
        f"[방금 생성된 '{part_label}' 파트 본문]\n"
        f"{part_html}\n"
    )

    for attempt in range(max_retries):
        try:
            # [신규] 이 검수가 여기서 문제를 놓치면, 나중에 훨씬 비싼 최종 통합검수
            # 단계에서야 발견되어 5파트 전체 재생성이 트리거될 수 있다(실제 로그에서
            # 반복 관측됨). 출력 자체는 짧은 JSON이라 사고를 켜도 비용 증가가 작으므로,
            # 여기서 조기에 정확히 잡아내는 쪽이 총 비용/호출 수 관점에서 더 이득이다.
            raw = get_gemini_response(prompt, thinking_budget=24576)
            if not raw:
                print(f"⚠️ {part_label} 검수: API 응답 없음 (시도 {attempt + 1}/{max_retries})")
                continue
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1 or end <= start:
                print(f"⚠️ {part_label} 검수 응답 파싱 실패 (시도 {attempt + 1}/{max_retries})")
                continue
            data = json.loads(text[start:end + 1])
            score = max(0.0, min(1.0, float(data.get('quality_score', 0.0))))
            issues = data.get('issues', []) or []
            passed = bool(data.get('pass', score >= 0.6))
            return {'quality_score': score, 'issues': issues, 'pass': passed}
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"⚠️ {part_label} 검수 파싱 오류 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
        except Exception as e:
            print(f"⚠️ {part_label} 검수 오류 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")

    return None


def _extract_text_for_review(html_content):
    """LLM 검수용으로만 쓸 '텍스트 사본'을 만든다.

    [중요] 이 함수는 실제 발행 콘텐츠(blog_content)를 전혀 건드리지 않는다.
    BeautifulSoup으로 원본을 파싱해 script/style 태그(플로틀리 차트 JSON,
    CSS 등 - AI가 쓴 문장이 아니라 코드가 계산한 값이라 정책/품질 검수 대상이
    아님)만 제거한 '읽기 전용 사본'을 만들어 반환한다. 원본 html_content는
    이 함수 호출 전/후로 전혀 수정되지 않으며, 실제 발행은 항상 원본으로 이루어진다.

    태그 단위로 파싱 후 제거하기 때문에, 예전의 문자열 앞/뒤 N자 자르기 방식과
    달리 태그 중간이 잘리는 일이 없다(<table> 등이 통째로 파싱되어 다뤄짐).

    BeautifulSoup이 없으면 원본을 그대로 반환한다(안전한 폴백 - 검수 품질은
    떨어지지만 프로그램이 죽지는 않음).
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup(['script', 'style']):
            tag.decompose()
        text_only = soup.get_text(separator=' ', strip=True)
        text_only = re.sub(r'\s+', ' ', text_only).strip()
        return text_only
    except ImportError:
        print("⚠️ BeautifulSoup 미설치 - 검수용 텍스트를 원본 그대로 사용합니다(차트 데이터 포함, 토큰 소모 증가).")
        return html_content
    except Exception as e:
        print(f"⚠️ 검수용 텍스트 추출 실패({type(e).__name__}: {e}) - 원본을 그대로 사용합니다.")
        return html_content


def _build_previous_content_block(confirmed_text_so_far):
    """[신규] Part2~5 생성 프롬프트에 이전 파트의 '실제 문장'을 직접 넣어주기 위한 블록.

    [중요] 예전에는 생성 프롬프트에 facts_json_str(숫자 요약)만 들어가고, 이전 파트가
    실제로 어떤 문장/조언으로 그 숫자를 풀어썼는지는 전혀 안 들어갔다. 그래서 "이미
    언급한 내용은 반복하지 마세요"라고 지시해봤자 AI 입장에선 뭘 반복하면 안 되는지
    구체적으로 알 방법이 없었고, 그 결과 절세 계좌 설명 같은 문단이 파트마다 처음
    쓰는 것처럼 반복 생성되는 문제가 있었음(_llm_part_check가 사후에 이걸 잡아내
    재생성을 트리거하긴 했지만, 애초에 안 겹치게 예방하는 것보다 비효율적).

    HTML 태그/스타일/스크립트는 _extract_text_for_review로 벗겨서 토큰을 아끼되,
    실제 문장 내용은 그대로 전달한다. 글이 길어질 것을 대비해 뒤쪽(가장 최근에
    쓰인 파트 = 지금 이어 쓸 파트와 가장 가까운 맥락)을 우선 보존한다.
    """
    if not confirmed_text_so_far:
        return ""
    text = _extract_text_for_review(confirmed_text_so_far)
    if len(text) > PREVIOUS_CONTENT_BLOCK_CAP:
        text = "...(앞부분 생략)... " + text[-PREVIOUS_CONTENT_BLOCK_CAP:]
    return (
        "\n[이전까지 실제로 작성된 본문 전체 (HTML 태그 제거, 텍스트만 - 참고용)]\n"
        f"{text}\n"
        "[위 내용을 반드시 확인하고, 같은 조언·같은 문장 구조·같은 설명(예: 절세 계좌 활용법, "
        "거시경제 지표 해석 등)을 다시 쓰지 마세요. 위에 없는 새로운 이야기만 작성하세요.]\n"
    )


# ETF 파이프라인의 기본 Part 구성 설명. category_label이 ETF가 아닌 다른 카테고리
# (테크/바이오/특허 등)에서 _llm_quality_check를 호출할 때는 반드시 그 카테고리의
# 실제 Part 구성에 맞는 part_descriptions를 넘겨야 한다 - 안 넘기면 이 ETF용
# 설명이 기본값으로 쓰여서, 검수가 엉뚱한 기준으로 problem_parts를 판단하게 된다.
DEFAULT_ETF_PART_DESCRIPTIONS = (
    "- Part1: 도입/기초 (제목, 서론, 기초정보, 수익률·배당 기초 지표)\n"
    "- Part2: 수익/시뮬레이션 (수익률+배당 표, 1000만원 시뮬레이션, 세금 시나리오)\n"
    "- Part3: 전략/리스크 (리스크 분석, 위험 시나리오, 경쟁분석, 실수료 비교)\n"
    "- Part4: 포트폴리오/심화 (연령별 포트폴리오, 매매 타이밍, 섹터 심화)\n"
    "- Part5: 반박/결론/마무리 (반박, 경제 사이클, 제언, 요약, FAQ, 태그)"
)


def _extra_quality_items(category_label):
    """실제 발행 글에서 놓쳤던 오류 유형을 검수 항목에 명시한다(2026-07 QQQ 글 점검 결과)."""
    items = (
        "6. repeated_blocks: 같은 표(예: 수익률표, 배당내역표)나 같은 문단이 글 안에서 두 번 이상 나오는가?\n"
        "7. unsupported_claims: 링크나 구체적 출처 없이 '외신 보도', '업계에 따르면', '운용사 팩트시트' 같은 "
        "뭉뚱그린 출처를 단 주장, 또는 위 데이터에 없는 사실(다른 회사의 신상품 출시, 특정 기업 실적 등)을 "
        "단정적으로 쓴 문장이 있는가?\n"
        "8. date_confusion: '지난 분석(날짜) 대비'처럼 비교 기준 날짜가 글 작성일과 같거나 뒤섞인 문장이 있는가?\n"
    )
    if "ETF" in (category_label or ""):
        items += (
            "9. korea_account_rules: 한국 계좌 규칙 오류가 있는가? 해외(미국 등) 상장 ETF는 ISA·연금저축·IRP로 "
            "직접 살 수 없는데 그 계좌로 이 ETF를 사라고 안내하거나, 'ISA 전액 비과세'처럼 한도 없이 비과세라고 "
            "쓴 경우를 반드시 지적하세요.\n"
        )
    return items + "\n"


def _llm_quality_check(content, facts_json_str=None, max_retries=2, category_label="ETF/투자", part_descriptions=None):
    """
    단순 단어 카운트가 아니라, Gemini에게 실제로 글을 읽고 채점하게 합니다.
    애드센스 통과 관점에서 자연스러움, 정책 위반 소지, 논리적 모순,
    실질적 정보 부족(thin content) 여부를 봅니다.

    [강화] 이전에는 팩트시트를 받지 않아서, 본문 안의 서술(예: 투자 매력도 평가,
    "안정적", "위험함" 같은 정성적 판단)이 실제 수치와 모순되는지 전혀 검증하지
    못했음(예: MDD -53%인데 "안정적"이라고 서술해도 이 검수가 못 잡는 구조).
    facts_json_str이 주어지면 이 대조 검증도 체크리스트에 포함시킨다.

    [신규] 이 함수는 최종 발행 여부를 좌우하는 마지막 관문이므로, 다른 호출과
    달리 get_gemini_response에 thinking_budget=24576(gemini-2.5-flash 최댓값 =
    "추론강도 high")을 넘겨 실제로 깊게 사고한 뒤 채점하게 한다. 원고 생성
    호출(Part1~5)은 여전히 thinking_budget=0(기본값)을 그대로 쓰므로 이 변경은
    검수 정확도만 높이고 생성 속도/토큰 비용에는 영향을 주지 않는다.

    실패 시(네트워크 오류, 파싱 실패 등) None을 반환합니다.
    호출부는 None일 경우 반드시 "검수 불가 - 사람이 직접 확인 필요"로 처리해야 하며,
    실패를 '통과'로 간주해서는 안 됩니다.
    """
    # [변경] 예전에는 앞 4000자+뒤 3000자만 잘라서 넘겼는데, 이러면 중간 섹션
    # (연령별 포트폴리오, 매매 타이밍, 경제 사이클 등)에서 발생하는 반복/중복은
    # 애초에 비교 대상이 서로 안 보여서 검수가 절대 못 잡는 구조였음
    # (조각을 몇 개로 나누든 "따로 보기"만으로는 조각 간 비교가 저절로 생기지 않음).
    #
    # Gemini 2.5 계열은 무료 티어도 100만 토큰 컨텍스트 윈도우를 그대로 쓰므로,
    # ETF 글 한 편(보통 수만 자 수준)을 통째로 넣는 건 용량 문제가 아니다.
    # 대신 Plotly 차트용 원본 JSON 배열(script 태그)과 style은 AI가 쓴 문장이
    # 아니라 코드가 계산한 값이라 애초에 검수 대상이 아니므로, 이를 제거한
    # '검수용 텍스트 사본'을 만들어 전체를 한 번에 넘긴다(원본 blog_content는
    # 건드리지 않음 - 실제 발행은 항상 원본 그대로 나간다).
    review_text = _extract_text_for_review(content)

    # 혹시 모를 극단적 케이스(섹션이 크게 늘어나는 등)에 대비한 안전장치.
    # 평소 분량(수천~1만자 수준)에서는 절대 걸리지 않는 매우 넉넉한 상한이며,
    # 걸리더라도 조용히 자르지 않고 경고를 남겨 사람이 알아채도록 한다.
    SAFE_CHAR_CAP = 60000
    if len(review_text) > SAFE_CHAR_CAP:
        print(f"⚠️ 검수용 텍스트가 {len(review_text)}자로 예상보다 훨씬 깁니다. "
              f"앞 {SAFE_CHAR_CAP}자만 검수합니다 - 섹션이 비정상적으로 늘어나지 않았는지 확인하세요.")
        excerpt = review_text[:SAFE_CHAR_CAP]
    else:
        excerpt = review_text

    facts_block = ""
    fact_check_item = ""
    if facts_json_str:
        facts_block = f"\n[이 글이 근거해야 할 실제 수치 데이터(팩트 시트)]\n{facts_json_str}\n"
        fact_check_item = (
            "5. fact_mismatch: 본문의 서술(예: '안정적', '낮은 변동성', '고성장' 같은 정성적 평가나 "
            "요약 문구)이 위 팩트 시트의 실제 수치와 모순되지 않는가? 예를 들어 MDD가 -40% 이상인데 "
            "'안정적'이라고 서술하거나, 수익률이 마이너스인데 '견조한 성과'라고 서술하는 경우를 지적하세요. "
            "본문에 등장하는 숫자 자체가 팩트 시트와 다르게 왜곡되어 있는지도 확인하세요. "
            "다만 주의: '최근 1년 수익률'과 '연평균성장률(CAGR, 상장 이후 전체 기간 기준)'은 서로 다른 "
            "기간을 기준으로 하므로 값이 크게 다를 수 있습니다(예: 최근 1년은 -40%인데 CAGR은 +13%인 것이 "
            "실제로 가능함 - 장기 누적과 최근 1년의 방향이 다를 수 있기 때문). 본문이 이 두 지표의 기준 기간이 "
            "다르다는 점을 이미 설명하고 있다면 이를 모순으로 지적하지 마세요. 오직 같은 기간을 가리키는데도 "
            "서로 다른 숫자가 나오는 경우만 지적하세요.\n\n"
        )

    prompt = (
        "당신은 애드센스 심사 담당자이자 한국어 원어민 편집자입니다.\n"
        f"아래는 자동 생성된 {category_label} 블로그 글의 전체 본문(HTML 태그와 차트 스크립트는 제거된 텍스트)입니다.\n"
        "글 전체가 빠짐없이 제공되므로, 서로 다른 섹션 사이의 반복이나 모순도 함께 판단할 수 있습니다.\n"
        "이 글이 애드센스 심사와 실제 독자 관점에서 문제가 없는지 엄격하게 평가하세요.\n"
        f"[오늘 날짜] {_kst_now():%Y년 %m월 %d일}. 오늘이나 그 이전 날짜는 미래가 아니므로 날짜 오류로 지적하지 마세요"
        "(당신이 아는 최신 시점보다 뒤라도 실제 오늘 날짜가 기준입니다).\n"
        "[내부 링크] 같은 블로그의 다른 글을 소개하는 링크(함께 보면 좋은 글)는 정상이니 문제로 보지 마세요. "
        "다만 문장 중간에 다른 글 제목이 어색하게 끼어 있으면 unnatural_language로 지적하세요.\n"
        f"{facts_block}\n"
        "체크리스트:\n"
        "1. unnatural_language: 어색하거나 기계적으로 치환된 흔적이 있는 문장, 반복되는 표현이 있는가?\n"
        "2. policy_risk: 무조건적 수익 보장, 100% 확정 표현, 과장된 표현, 오해를 유발할 수 있는 금융 조언이 있는가?\n"
        "3. logical_issues: 문맥상 모순되거나 앞뒤가 안 맞는 문장, 뜬금없는 문장이 있는가?\n"
        "4. thin_content: 다음 기준으로 엄격하게 판단하세요 - 이 문단을 소재명만 바꿔서 다른 글에 "
        "그대로 붙여넣어도 말이 되는가? 그렇다면 그건 이 글만의 고유 정보가 아니라 뻔한 일반론이므로 문제로 지적하세요. "
        "특히 연령별 포트폴리오, 매매 타이밍, 경제 사이클, 결론/제언 섹션에 이런 일반론적 문장이 없는지 확인하세요.\n\n"
        f"{fact_check_item}"
        f"{_extra_quality_items(category_label)}"
        "[본문 구성 안내] 이 글은 다음 5개 파트를 이어붙여 만들어졌습니다. 문제를 발견하면 그 문제가 "
        "실제로 어느 파트에서 비롯됐는지 함께 판단하세요:\n"
        f"{part_descriptions or DEFAULT_ETF_PART_DESCRIPTIONS}\n\n"
        "아래 JSON 형식으로만 답하세요 (다른 텍스트 없이):\n"
        "{\n"
        '  "quality_score": 0.0에서 1.0 사이 숫자 (1.0 = 문제 전혀 없음, 0.0 = 심각한 문제),\n'
        '  "issues": ["구체적 문제점을 한국어로 짧게 나열, 없으면 빈 배열"],\n'
        '  "problem_parts": [문제의 원인이 되는 파트 번호만 정수 배열로, 예: [2, 3]. 문제가 없거나 '
        '어느 파트 때문인지 특정하기 어려우면 빈 배열 []. 단순히 "여러 곳에서 언급된 정보"라는 이유로 '
        '전체 파트를 다 넣지 말고, 실제로 그 문제 문장/수치가 처음 등장하거나 원인이 된 파트만 지목하세요.\n'
        '  "publish_recommended": true 또는 false\n'
        "}\n\n"
        "--- 본문 시작 ---\n"
        f"{excerpt}\n"
        "--- 본문 끝 ---\n"
    )

    for attempt in range(max_retries):
        try:
            raw = get_gemini_response(prompt, thinking_budget=24576)
            if not raw:
                print(f"⚠️ LLM 품질 체크: API 응답 없음 (시도 {attempt + 1}/{max_retries})")
                continue
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1 or end <= start:
                print(f"⚠️ LLM 품질 체크 응답 파싱 실패 (시도 {attempt + 1}/{max_retries})")
                continue
            data = json.loads(text[start:end + 1])
            score = float(data.get('quality_score', 0.0))
            score = max(0.0, min(1.0, score))
            issues = data.get('issues', []) or []
            publish_recommended = bool(data.get('publish_recommended', score >= 0.6))
            # [추가] 어느 파트(1~5)가 문제의 원인인지. 형식이 어긋나거나 범위를
            # 벗어난 값이 섞여 있어도 죽지 않도록 안전하게 정수 1~5만 걸러낸다.
            raw_problem_parts = data.get('problem_parts', []) or []
            problem_parts = []
            for p in raw_problem_parts:
                try:
                    p_int = int(p)
                    if 1 <= p_int <= 5:
                        problem_parts.append(p_int)
                except (ValueError, TypeError):
                    continue
            problem_parts = sorted(set(problem_parts))
            return {
                'quality_score': score,
                'issues': issues,
                'publish_recommended': publish_recommended,
                'problem_parts': problem_parts,
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"⚠️ LLM 품질 체크 파싱 오류 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
        except Exception as e:
            print(f"⚠️ LLM 품질 체크 오류 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")

    return None


def _llm_targeted_fix(part_html, part_label, issues, facts_json_str=None, max_retries=2, category_label="ETF"):
    """
    [신규] 최종 검수(_llm_quality_check)가 지적한 문제를, 처음부터 다시 쓰는 대신
    "문제가 된 그 파트의 텍스트만" 넘겨서 직접 고치게 하는 사후 교정 함수.

    기존 방식(재생성)의 문제: 검수가 "Part2와 Part4의 배당 정보가 모순된다"처럼
    정확한 문제를 찾아내도, 그 파트를 통째로 다시 "새로 쓰게" 시키면 AI가 완전히
    다른 문장으로 재작성하면서 (a) 잘 써졌던 다른 부분까지 같이 바뀌어버리고
    (b) 운이 나쁘면 새로운 종류의 실수가 또 생길 수 있음. 그래서 재시도를 거듭해도
    같은 유형의 문제가 계속 반복되는 경우가 많았음(3번을 다 써도 해결 안 됨).

    이 함수는 다르게 접근한다: "이 텍스트에서 지적된 문제만 고치고, 나머지는 최대한
    원래 표현을 유지하라"고 명시적으로 요청한다. 즉 재작성이 아니라 "교정"이다.
    이러면 (a) 이미 잘 쓴 부분이 불필요하게 또 바뀔 위험이 줄고 (b) 무엇을 고쳐야
    하는지 매우 구체적으로 알려주므로 같은 실수가 반복될 확률도 낮아진다.

    반환값: 성공 시 교정된 HTML 문자열, 실패 시 None (호출부는 None이면 원본을
    그대로 쓰거나 기존 재생성 방식으로 폴백해야 함).
    """
    if not part_html or not issues:
        return None

    issues_text = "\n".join(f"- {issue}" for issue in issues)
    fact_check_item = ""
    if facts_json_str:
        fact_check_item = (
            f"\n[반드시 지켜야 할 실제 데이터]\n{facts_json_str}\n"
            "위 데이터와 다른 숫자가 본문에 있다면 반드시 위 데이터에 맞게 고치세요.\n"
        )

    prompt = (
        f"아래는 {category_label} 분석 블로그 글의 '{part_label}' 부분입니다. "
        "이 텍스트를 검수한 결과 아래와 같은 구체적 문제가 발견되었습니다:\n"
        f"{issues_text}\n"
        f"{fact_check_item}\n"
        "[매우 중요한 작업 방식]\n"
        "- 이 텍스트를 처음부터 새로 쓰지 마세요. 지적된 문제가 있는 부분만 정확히 찾아 "
        "고치고, 문제와 무관한 나머지 문장/구조/HTML은 최대한 원래 그대로 유지하세요.\n"
        "- 특히 수치나 사실관계가 지적됐다면, 위쪽 [반드시 지켜야 할 실제 데이터]와 "
        "정확히 일치하도록 그 숫자만 바로잡으세요.\n"
        "- 반복/중복이 지적됐다면, 중복되는 문장을 삭제하거나 다른 파트를 참조하는 짧은 "
        "언급으로 줄이세요. 전체 문단을 다른 말로 풀어써서 '재작성'하지 마세요.\n"
        "- HTML 태그 구조는 원본과 동일하게 유지하세요.\n"
        "- 출력은 고쳐진 전체 HTML만 출력하세요. 설명이나 안내 문구를 앞뒤에 붙이지 마세요.\n\n"
        "--- 원본 텍스트 시작 ---\n"
        f"{part_html}\n"
        "--- 원본 텍스트 끝 ---\n"
    )

    for attempt in range(max_retries):
        try:
            raw = get_gemini_response(prompt, thinking_budget=24576)
            if not raw:
                print(f"⚠️ 사후 교정: API 응답 없음 (시도 {attempt + 1}/{max_retries})")
                continue
            fixed = raw.strip()
            if fixed.startswith("```"):
                fixed = re.sub(r'^```(?:html)?\s*', '', fixed)
                fixed = re.sub(r'\s*```$', '', fixed)
            if len(fixed) < len(part_html) * 0.5:
                # [안전장치] 교정 결과가 원본의 절반도 안 되면, AI가 요약해버렸거나
                # 뭔가 크게 잘못 잘렸을 가능성이 높다. 이 경우 교정 실패로 간주해
                # 호출부가 원본을 그대로 쓰도록 한다(내용이 통째로 사라지는 것보다
                # 안전).
                print(f"⚠️ 사후 교정 결과가 원본보다 지나치게 짧습니다({len(fixed)}자 vs 원본 {len(part_html)}자) - 교정 실패로 간주합니다.")
                continue
            return fixed
        except Exception as e:
            print(f"⚠️ 사후 교정 오류 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")

    return None


def _policy_filter(content):
    """애드센스 정책 위반 단어 필터링"""
    blacklist = {
        '무조건': '항상',
        '100%': '대략',
        '절대': '사실상',
        '한 방에': '단기간에',
        '완벽한': '완전한',
        '무조건 수익': '안정성 확보',
    }
    issues = []
    for bad, replacement in blacklist.items():
        if bad in content:
            content = content.replace(bad, replacement)
            issues.append(f"'{bad}' -> '{replacement}'")

    # [수정] 이전에는 '보장' -> '보장할 수는 없지만'으로 무차별 치환했는데,
    # AI가 이미 "보장하지 않습니다"처럼 부정문을 쓴 경우에도 똑같이 적용되어
    # "보장할 수는 없지만하지 않습니다" 같은 이중부정 문장이 실제로 여러 번
    # 생성됐음(1,000만원 시뮬레이션 안내문 등에서 3회 반복 확인됨).
    # "보장한다/보장합니다"류 확정 서술어일 때만 자연스러운 완결 문장으로
    # 바꾸고, 이미 부정형인 경우는 건드리지 않는다.
    guarantee_confirm_pattern = re.compile(r'보장(?:합니다|한다|해요|드립니다)')
    if guarantee_confirm_pattern.search(content):
        content = guarantee_confirm_pattern.sub('보장할 수는 없지만 기대할 수 있습니다', content)
        issues.append("'보장(확정형 서술어)' -> '보장할 수는 없지만 기대할 수 있습니다'")

    return content, issues


def _ai_recovery(content):
    """AI 감지 우회 단어 치환.
    [수정] 이전에는 단순 str.replace()로 'AI'를 찾아 무조건 치환했는데,
    이게 "FAIR"->"F인공지능R", "MAIN"->"M인공지능N"처럼 완전히 무관한
    영단어 안에 우연히 포함된 "AI"까지 오염시키는 버그가 있었음(실제
    재현 확인됨). 정규식 단어 경계(\\b)를 사용해 'AI'가 독립된 단어로
    등장할 때만 치환하도록 수정."""
    simple_replacements = {
        '자동 생성': '자동 생성(참고)',
        '매우 중요': '중요',
        '이것은': '여기서',
        '결론적으로': '요약하면',
        '요약하자면': '정리하면',
        '정리하자면': '간단히 말하면',
        '무조건': '가능성이 높다',
        '100%': '대체로',
        '완벽한': '충분히 검토된'
    }
    for old, new in simple_replacements.items():
        content = content.replace(old, new)

    # 'AI'만 별도로 단어 경계를 지켜서 치환 (앞뒤가 영문자가 아닐 때만)
    # [수정] 기존 정규식은 "AI(인공지능)"처럼 AI 본인이 이미 "AI"를 풀어서
    # 설명해둔 경우에도 앞의 "AI"까지 똑같이 "인공지능"으로 바꿔버려서
    # "인공지능(인공지능)"이라는 중복이 실제로 여러 번 발생했음(이건 AI가 만든
    # 실수가 아니라 이 치환 로직 자체가 만들어낸 결과물이었음). 바로 뒤에
    # "(인공지능"이 이어지는 경우는 이미 풀어 쓴 것으로 보고 건드리지 않는다.
    content = re.sub(r'(?<![A-Za-z])AI(?![A-Za-z])(?!\s*\(인공지능)', '인공지능', content)

    return content


def _reduce_repetition(content):
    """텍스트 반복도 감소"""
    sentences = re.split(r'(?<=[.!?])\s+', content)
    uniq = []
    for sent in sentences:
        if not sent.strip():
            continue
        is_dup = any(_is_similar_text(sent, prev) for prev in uniq)
        if is_dup:
            sent = sent.replace('투자자라면', '투자자분이시라면')
        uniq.append(sent)
    return ' '.join(uniq)


def _clean_redundant_parenthetical(content):
    """
    [신규] "인공지능(인공지능)"처럼 '단어(같은 단어)' 형태로 괄호 안에
    직전 단어가 그대로 반복되는 패턴을 정리하는 로컬(비-API) 후처리 필터.

    이런 패턴은 대부분 여러 단계의 텍스트 치환(_ai_recovery 등)이 겹치면서
    우연히 생기는 기계적 실수라서, AI에게 "이거 고쳐줘"라고 API를 또 호출할
    필요가 없다. 정규식으로 즉시, 무료로, 100% 정확하게 잡아낼 수 있는
    문제라서 API 사후 교정(_llm_targeted_fix)과는 역할을 분리했다:
    - 의미 판단이 필요한 문제(파트 간 모순, 실질적 중복) -> API 사후 교정
    - 순수 기계적 패턴(단어(같은 단어) 등) -> 이 로컬 필터

    실행 위치: Part1~5를 합친 직후, 발행 직전 한 번만 실행되며 네트워크
    호출이 전혀 없어 몇 밀리초 안에 끝난다.
    """
    issues = []

    # 패턴 1: "인공지능(인공지능)", "ETF(ETF)"처럼 한글/영문 단어가 그대로
    # 괄호 안에 반복되는 경우 -> 괄호 부분 삭제
    pattern = re.compile(r'([가-힣A-Za-z0-9]+)\(\1\)')
    matches = pattern.findall(content)
    if matches:
        content = pattern.sub(r'\1', content)
        for m in set(matches):
            issues.append(f"중복 괄호 정리: '{m}({m})' -> '{m}'")

    # 패턴 2: "인공지능(AI)"처럼 이미 풀어 쓴 한글 단어 뒤에 원어 약어가
    # 불필요하게 다시 붙는 경우는 굳이 건드리지 않음(오히려 원어 병기가
    # 독자에게 도움이 될 수 있어 패턴 1보다 훨씬 보수적으로 접근).

    return content, issues


def _safe_html_filter(html_content):
    """HTML 구조를 파괴하지 않도록 텍스트 노드만 필터링.
    [중요] 이전에는 _policy_filter가 반환하는 issues(실제로 어떤 정책 위반
    표현이 어떻게 자동 치환됐는지)를 전부 버리고 있어서, 발행 전 요약에서
    "이 글에서 무엇이 순화됐는지"를 사람이 전혀 알 수 없었음. 이제 issues를
    모아서 반환하고, 호출부(run_automation)가 policy_issues_overall에
    누적해 발행 전 요약에 보여줄 수 있게 한다."""
    all_issues = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # 텍스트 노드만 필터링 (태그 속성은 건드리지 않음)
        for text_node in soup.find_all(string=True):
            if text_node.parent.name not in ['script', 'style']:  # 코드/스타일 제외
                filtered_text, issues = _policy_filter(text_node.string)
                filtered_text = _ai_recovery(filtered_text)
                filtered_text = _reduce_repetition(filtered_text)
                filtered_text, redundant_issues = _clean_redundant_parenthetical(filtered_text)
                text_node.string.replace_with(filtered_text)
                all_issues.extend(issues)
                all_issues.extend(redundant_issues)

        return str(soup), all_issues
    except ImportError:
        # BeautifulSoup 없으면 기존 방식 (리스크 있음)
        print("⚠️ BeautifulSoup 설치 필요: pip install beautifulsoup4")
        filtered, issues = _policy_filter(html_content)
        filtered = _ai_recovery(filtered)
        filtered = _reduce_repetition(filtered)
        filtered, redundant_issues = _clean_redundant_parenthetical(filtered)
        return filtered, issues + redundant_issues
    except (ValueError, TypeError, AttributeError, RuntimeError) as e:
        print(f"⚠️ HTML 필터링 실패: {type(e).__name__}: {e}")
        return html_content, []


def _record_api_call(model_name):
    _api_call_stats["total_calls"] += 1
    _api_call_stats["by_model"][model_name] = _api_call_stats["by_model"].get(model_name, 0) + 1


def _record_model_switch(exhausted_model):
    """어떤 모델의 키를 다 써서 다음 모델로 넘어갔는지 기록 - 자주 소진되는
    모델을 나중에 사람이 우선순위에서 내리는 판단에 참고할 수 있게."""
    _api_call_stats["model_switch_events"][exhausted_model] = (
        _api_call_stats["model_switch_events"].get(exhausted_model, 0) + 1
    )


def _flush_api_usage_stats():
    """프로세스 종료 시(atexit) 이번 실행의 통계를 로그 파일에 한 줄 추가한다."""
    if _api_call_stats["total_calls"] == 0:
        return  # 이번 실행에서 API를 아예 안 썼으면 기록할 것도 없음
    log = _load_json_file(API_USAGE_LOG_FILE, [])
    log.append({"timestamp": datetime.now().isoformat(), **_api_call_stats})
    log = log[-90:]  # 최근 90회 실행 기록만 유지(무한정 쌓이지 않게)
    _save_json_file(API_USAGE_LOG_FILE, log)


def _build_gemini_model_priority():
    """시도할 Gemini 모델의 우선순위 리스트를 만든다.

    적용 순서:
    1. .env의 GEMINI_MODEL_PRIORITY (쉼표로 구분) - 있으면 이 순서를 그대로 씀.
    2. 없으면 아래 기본값 사용. 2026년 8월 AI Studio 대시보드 기준으로
       Flash-Lite 계열의 무료 등급 일일 한도(RPD)가 500회로, 일반 Flash
       계열(20회 안팎)보다 훨씬 넉넉해서 Lite를 먼저 시도하도록 순서를 잡았다.
       Google 정책은 예고 없이 바뀔 수 있으므로, 주기적으로
       aistudio.google.com/rate-limit에서 직접 확인 후 .env의
       GEMINI_MODEL_PRIORITY로 덮어써서 갱신하는 걸 권장한다.
    3. 기존 GEMINI_MODEL(단일 모델 지정용, 하위 호환)이 남아있다면 최우선
       순위로 맨 앞에 끼워 넣는다 - 이미 이 값을 넣어두신 분들의 설정을 존중.
    """
    global _gemini_model_priority_cache
    if _gemini_model_priority_cache is not None:
        return _gemini_model_priority_cache

    env_priority = os.environ.get("GEMINI_MODEL_PRIORITY", "").strip()
    if env_priority:
        priority = [m.strip() for m in env_priority.split(",") if m.strip()]
    else:
        priority = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
        ]

    legacy_model = os.environ.get("GEMINI_MODEL", "").strip()
    if legacy_model:
        if legacy_model in priority:
            priority.remove(legacy_model)
        priority = [legacy_model] + priority

    # 혹시 모를 중복 제거 (순서는 그대로 유지)
    seen = set()
    deduped = []
    for m in priority:
        if m not in seen:
            seen.add(m)
            deduped.append(m)

    _gemini_model_priority_cache = deduped
    print(f"🧭 Gemini 모델 우선순위: {' → '.join(deduped)}")
    return deduped


def _classify_quota_error(text):
    """429 응답 본문에서 일일 한도(RPD)인지 분당 한도(RPM)인지 추정한다.
    확실하지 않으면 '알 수 없음'을 반환 - 판단 실패가 로직을 막지는 않고
    로그에만 참고용으로 찍힌다."""
    lowered = (text or "").lower().replace("_", "").replace(" ", "")
    if "perday" in lowered:
        return "일일 한도(RPD로 추정 - 자정까지 회복 안 될 수 있음)"
    if "perminute" in lowered:
        return "분당 한도(RPM으로 추정 - 짧으면 1분 내 회복)"
    return "알 수 없음"


def get_gemini_response(prompt, thinking_budget=0):
    # [수정] 이전에는 "모든 키가 다 소진됐다"가 한 번 확인되면 이번 실행이 끝날
    # 때까지 영원히 재시도하지 않았다. 하지만 429는 두 종류가 있다: 분당 한도
    # (RPM, 1분이면 회복)와 일일 한도(RPD, 자정까지 회복 안 됨). 여러 키가 서로
    # 다른 계정에서 나온 경우, 짧은 시간에 요청이 몰려 RPM에 걸렸을 가능성이 커서
    # 무조건 포기하기보다 일정 시간(_EXHAUSTED_RETRY_WAIT_SECONDS) 후 한 번 더
    # 전체 키를 시도해본다. 그마저 실패하면 그때는 진짜 RPD 소진으로 보고 포기한다.
    global _all_keys_exhausted, _all_keys_exhausted_at, _exhausted_retry_cycles, _current_key_index
    if _all_keys_exhausted:
        elapsed = time.time() - _all_keys_exhausted_at if _all_keys_exhausted_at else 999999
        if elapsed < _EXHAUSTED_RETRY_WAIT_SECONDS:
            # [수정] 예전엔 여기서 즉시 None을 반환하고 "건너뛰었다"고만 했다.
            # 문제는 이 함수를 호출하는 바깥쪽에 "전체 원고를 몇 번 다시
            # 시도할지"를 세는 별도의 한도(예: max_attempts=3)가 있는데, 그
            # 바깥쪽 재시도는 몇 초~몇십 초 만에 한 바퀴 돌기 때문에, 5분을
            # 다 채우기도 전에 "건너뛰었다"만 반복하다가 바깥쪽 재시도 횟수를
            # 전부 소진해버렸다(실제 있었던 문제: Part4가 "재도전까지 299초
            # 남음"을 반복하는 사이 상위의 "전체 재생성 시도 1/3, 2/3, 3/3"이
            # 순식간에 다 끝나버림). 이제 그냥 건너뛰지 않고, 이 자리에서
            # 남은 시간만큼 실제로 잠들었다가 다시 시도한다. 이렇게 하면 이
            # 함수를 호출한 쪽은 "느리지만 결국 응답이 온다"고 인식하므로,
            # 상위의 재시도 횟수가 대기 시간 때문에 낭비되지 않는다.
            remaining = int(_EXHAUSTED_RETRY_WAIT_SECONDS - elapsed)
            print(f"⏳ 이전에 모든 API 키가 소진되어 남은 {remaining}초를 여기서 그대로 기다립니다 "
                  f"(다른 재시도 카운터를 낭비하지 않기 위함)...")
            time.sleep(remaining)
            elapsed = _EXHAUSTED_RETRY_WAIT_SECONDS  # 대기를 마쳤으므로 아래 분기로 넘어가게 함

        if elapsed >= _EXHAUSTED_RETRY_WAIT_SECONDS:
            if _exhausted_retry_cycles >= _MAX_EXHAUSTED_RETRY_CYCLES:
                print(f"🛑 {_MAX_EXHAUSTED_RETRY_CYCLES}번의 재도전 기회를 모두 써도 계속 소진 상태입니다. "
                      f"일일 한도(RPD) 소진으로 판단해 이후 재시도를 완전히 중단합니다 "
                      f"(태평양 시간 자정에 리셋됩니다).")
                return None
            else:
                _exhausted_retry_cycles += 1
                print(f"🔄 소진 확인 후 {_EXHAUSTED_RETRY_WAIT_SECONDS}초가 지났습니다. "
                      f"분당 한도(RPM)라면 이미 회복됐을 시간이므로 전체 키로 한 번 더 시도합니다. "
                      f"(재도전 {_exhausted_retry_cycles}/{_MAX_EXHAUSTED_RETRY_CYCLES}회)")
                _all_keys_exhausted = False
                _all_keys_exhausted_at = None

    # [수정] 이전에는 GEMINI_MODEL 환경변수로 모델을 하나만 고정해서 썼다.
    # 문제는 무료 등급 할당량이 모델마다 다르고(대체로 신규 모델일수록
    # 넉넉한 경향), 그 배분이 언제 바뀔지 예측할 수 없다는 점이다. 이제
    # _build_gemini_model_priority()가 만든 우선순위 리스트를 위에서부터
    # 시도하고, 특정 모델에서 (이번 실행 동안 쓸 수 있는) 키를 모두
    # 소진하면 자동으로 다음 순위 모델로 넘어간다. 실제 시도할 모델은
    # 아래 재시도 루프 안에서 _current_model_index를 기준으로 매번 다시
    # 계산한다(모델 로테이션이 루프 도중 일어날 수 있으므로). 실제 재할당은
    # 안쪽의 중첩 함수가 자체 global 선언으로 처리하므로 여기서는 읽기만 한다.
    model_priority = _build_gemini_model_priority()
    num_models = len(model_priority)
    # [수정] generationConfig에 maxOutputTokens를 지정하지 않으면 API가 기본값
    # 8,192 토큰으로 출력을 제한한다. gemini-2.5-flash는 "thinking"(내부 추론)이
    # 기본으로 켜져 있고, 이 추론 토큰도 같은 예산을 함께 소모하기 때문에 복잡한
    # 지시사항이 많은 프롬프트(Part2~5)일수록 실제 본문에 쓸 수 있는 토큰이
    # 8,192보다 훨씬 적게 남을 수 있다. 실제로 로그에 남은
    # "JSONDecodeError: ... line 2 column 8131" 같은 파싱 실패가 정확히 이
    # 지점(8,192 근방)에서 응답이 잘렸음을 시사한다. 모델이 실제로 지원하는
    # 65536까지 올리고, 이 파이프라인은 순수 추론보다 완성된 HTML 출력 분량이
    # 더 중요하므로 원고 생성 호출은 기본적으로 thinkingBudget을 0으로 꺼서
    # 예산을 전부 출력에 쓰게 한다.
    # [신규] 다만 호출부에 따라 정확성(사고)이 분량보다 더 중요한 경우가 있다
    # (예: 최종 품질검수 - 팩트시트 대조, 파트 간 중복/모순 판단은 실제로 model이
    # "생각"을 거칠수록 더 잘 잡아낸다). 이런 호출은 thinking_budget 인자를
    # 직접 넘겨서 이 함수 하나로 원고 생성/검수 양쪽을 다 커버한다.
    # gemini-2.5-flash의 thinkingBudget 유효 범위는 0~24576(또는 -1=동적)이며,
    # "추론강도 high"에 해당하는 고정값으로 최댓값인 24576을 사용한다.
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 65536,
            "thinkingConfig": {"thinkingBudget": thinking_budget},
        },
    }

    # [추가] 403으로 영구 제외된 키를 뺀 "지금 실제로 쓸 수 있는 키 목록".
    # 이 목록을 기준으로 순환해야 이미 죽은 키에 다시 걸려 시간을 낭비하지 않는다.
    available_keys = [k for k in GEMINI_API_KEYS if k not in _permanently_excluded_keys]
    num_keys = len(available_keys)

    if num_keys == 0:
        print("🛑 사용 가능한 API 키가 남아있지 않습니다 (모든 키가 403으로 제외됨). 이후 재시도를 중단합니다.")
        _all_keys_exhausted = True
        return None

    def _sleep_backoff(attempt, base_seconds):
        wait_time = (attempt + 1) * base_seconds
        print(f"⏳ API 서버 한도 초과 방지를 위해 {wait_time}초간 대기합니다...")
        time.sleep(wait_time)

    # [수정] 기존 _rotate_key를 "키 + 모델" 두 축을 함께 순환하는 _advance로
    # 확장했다. 동작 순서:
    #   1순위: 지금 모델에서 다음 키가 남아있으면 키만 전환 (기존 동작 그대로).
    #   2순위: 지금 모델의 키를 한 바퀴 다 돌았고, 다른 모델이 남아있으면
    #          모델을 다음 순위로 전환하고 키 인덱스는 처음(0)부터 다시 시작.
    #          예: gemini-3.5-flash-lite의 키 3개를 다 써봤는데도 안 되면,
    #          gemini-3.1-flash-lite로 넘어가서 다시 키 1번부터 시도.
    #   둘 다 불가능(키도 1개, 모델도 1개)하면 False를 반환해 제자리에서
    #   대기하게 함 - 이전과 동일한 동작.
    def _advance(reason):
        global _current_key_index, _current_model_index
        if num_keys > 1:
            next_key_index = (_current_key_index + 1) % num_keys
            if next_key_index != 0:
                _current_key_index = next_key_index
                print(f"🔁 {reason} - API 키를 다음 것으로 전환합니다 ({_current_key_index + 1}/{num_keys}번째 키).")
                return True
            # next_key_index == 0 이면 이 모델의 키를 한 바퀴 다 돈 것 -> 아래에서 모델 전환 시도
        if num_models > 1:
            exhausted_model = model_priority[_current_model_index % num_models]
            _record_model_switch(exhausted_model)
            _current_model_index = (_current_model_index + 1) % num_models
            _current_key_index = 0
            new_model = model_priority[_current_model_index]
            print(f"🔀 {reason} - 지금 모델의 키를 모두 소진해 모델을 '{new_model}'(으)로 전환합니다 "
                  f"({_current_model_index + 1}/{num_models}번째 모델, 키는 1번부터 다시 시작).")
            return True
        if num_keys > 1:
            # 모델은 1개뿐이지만 키는 여러 개인 경우 - 그냥 다음 키로 순환
            _current_key_index = (_current_key_index + 1) % num_keys
            print(f"🔁 {reason} - API 키를 다음 것으로 전환합니다 ({_current_key_index + 1}/{num_keys}번째 키).")
            return True
        return False

    total_combos = max(1, num_keys * num_models)  # 키 x 모델 전체 조합 수
    max_attempts = max(4, total_combos * 2)  # 조합이 많으면 그만큼 순회할 여유를 둠
    consecutive_failures = 0  # [신규] 키/모델을 바꿔가며 연속으로 실패한 횟수
    for attempt in range(max_attempts):
        # [수정] 키 x 모델 전체 조합을 한 바퀴 다 돌았는데도 전부 실패했다면,
        # 남은 시도를 다 채울 필요 없이 조기에 포기한다. "가진 조합을 한
        # 바퀴 돌았는데도 하나도 안 되면 더 돌아봐야 소용없다"는 현실적인
        # 판단. 이 상태를 전역 플래그로도 남겨서, 이후 다른 함수(Part 생성/
        # 검수 등)의 호출도 이미 소진된 걸 알고 즉시 포기하게 한다.
        if consecutive_failures >= total_combos and attempt >= total_combos:
            print(f"🛑 보유한 {num_keys}개 키 x {num_models}개 모델(총 {total_combos}개 조합)을 "
                  f"모두 순회했지만 전부 실패했습니다. "
                  f"{_EXHAUSTED_RETRY_WAIT_SECONDS}초 후 한 번 더 시도합니다 (그 사이의 호출은 즉시 건너뜁니다).")
            _all_keys_exhausted = True
            _all_keys_exhausted_at = time.time()
            return None

        current_key = available_keys[_current_key_index % num_keys]
        current_model = model_priority[_current_model_index % num_models]
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={current_key}"
        try:
            print(f"🔄 Gemini API 호출 시도 {attempt + 1}/{max_attempts} "
                  f"(모델 '{current_model}' {_current_model_index + 1}/{num_models}, "
                  f"키 {_current_key_index + 1}/{num_keys})...")
            response = requests.post(gemini_url, json=payload, timeout=120)

            if response.status_code == 429:
                quota_type = _classify_quota_error(response.text)
                print(f"⚠️ HTTP 429 오류: API 호출 한도 초과. (추정: {quota_type})")
                if not _advance("한도 초과"):
                    _sleep_backoff(attempt, 30)
                consecutive_failures += 1  # [수정] continue 전에 직접 증가 - 아래 참고
                continue

            if response.status_code != 200:
                # [수정] 이전에는 429/5xx만 로테이션하고, 403(권한/키 문제) 같은
                # 그 외 오류 코드는 로테이션 없이 같은 키로 계속 대기만 했음.
                # 200이 아닌 모든 경우를 "이 조합으로는 지금 안 된다"는 신호로
                # 보고 예외 없이 로테이션을 시도한다.
                print(f"⚠️ HTTP 오류: {response.status_code} - {response.text[:200]}")
                # [추가] 403(PERMISSION_DENIED, 프로젝트 자체가 차단된 상태)은
                # 429(한도초과)와 성격이 완전히 다르다. 429는 시간이 지나면
                # 풀리지만, 403은 그 키/프로젝트가 아예 접근을 거부당한 상태라
                # 몇 번을 더 순번대로 돌아와도 절대 성공하지 않는다. 그런데도
                # 예전 로직은 403 키를 계속 순환 목록에 남겨둬서, 키가 5개면
                # 그중 403인 것들에 매번 다시 걸려 헛되이 재시도가 낭비됐다.
                # 이제 403을 만난 키는 이번 실행 동안 완전히 제외한다.
                # [참고] 404(모델 이름이 틀렸거나 이 키/지역에서 아직 그
                # 모델을 못 쓰는 경우)는 키가 아니라 모델 쪽 문제일 가능성이
                # 높지만, 다른 키에서는 될 수도 있으므로 일단은 기존과 동일하게
                # 다음 조합으로 넘어가는 것으로 처리한다(별도 영구 제외 없음).
                if response.status_code == 403:
                    global _permanently_excluded_keys
                    _permanently_excluded_keys.add(current_key)
                    remaining = len([k for k in GEMINI_API_KEYS if k not in _permanently_excluded_keys])
                    print(f"🚫 이 키는 403(권한 거부)으로 이번 실행 동안 완전히 제외합니다. "
                          f"(남은 사용 가능 키: {remaining}개)")
                # 400(요청 형식 오류)은 키가 아니라 그 모델이 이 요청 설정을 안 받는 경우라
                # 다른 키로 돌려봐도 똑같이 실패한다 → 이 모델의 남은 키는 건너뛰고 바로 다음 모델로.
                if response.status_code == 400 and num_models > 1:
                    _current_key_index = num_keys - 1
                if not _advance(f"HTTP 오류({response.status_code})"):
                    _sleep_backoff(attempt, 15)
                consecutive_failures += 1
                continue

            try:
                res_data = response.json()
            except requests.exceptions.JSONDecodeError:
                print("⚠️ API 응답 파싱 실패 (JSON 형태가 아님)")
                if not _advance("응답 파싱 실패"):
                    _sleep_backoff(attempt, 15)
                consecutive_failures += 1
                continue

            if 'error' in res_data:
                print(f"⚠️ API 오류: {res_data['error'].get('message', '알 수 없는 오류')}")
                if not _advance("API 오류"):
                    _sleep_backoff(attempt, 15)
                consecutive_failures += 1
                continue

            if 'candidates' in res_data and len(res_data['candidates']) > 0:
                # [수정] 예전엔 매 성공마다 60초씩 대기했는데, 이게 한 편당 실행
                # 시간을 지나치게 늘렸다(정상 경로만 12회 호출 x 60초 = 12분,
                # 재시도가 겹치면 30분 이상). 20초 간격이면 분당 최대 3회 호출이라
                # 무료 티어 RPM 한도(분당 10회 안팎)에 여유 있게 들어간다. 대신
                # 혹시 이 정도로도 429가 반복되면, 모든 키가 소진된 것으로 판단해
                # 5분을 쉬었다가 한 번 더 시도하는 별도 안전장치(아래
                # _all_keys_exhausted 로직)가 이미 있으므로 이중으로 보호된다.
                print(f"✅ 응답 성공! (모델: {current_model}) 서버 과부하 방지를 위해 20초 대기합니다...")
                _record_api_call(current_model)
                time.sleep(20)
                return res_data['candidates'][0]['content']['parts'][0]['text']
            else:
                print("⚠️ 응답에 candidates가 없습니다")
                if not _advance("candidates 없음"):
                    _sleep_backoff(attempt, 15)
                # [수정] 이 경로는 continue가 없어 원래도 아래 카운터 증가에
                # 도달했지만, 명확성을 위해 여기서도 명시적으로 증가시킨 뒤
                # 아래 공통 증가 라인과 중복되지 않도록 continue로 통일한다.
                consecutive_failures += 1
                continue

        except requests.exceptions.Timeout as e:
            print(f"⚠️ 타임아웃 오류 (시도 {attempt + 1}/{max_attempts}): {e}")
            if not _advance("타임아웃"):
                _sleep_backoff(attempt, 20)
            consecutive_failures += 1
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 네트워크 오류 (시도 {attempt + 1}/{max_attempts}): {e}")
            if not _advance("네트워크 오류"):
                _sleep_backoff(attempt, 15)
            consecutive_failures += 1
        except Exception as e:
            print(f"⚠️ 예상치 못한 오류 (시도 {attempt + 1}/{max_attempts}): {type(e).__name__}: {e}")
            if not _advance("예상치 못한 오류"):
                _sleep_backoff(attempt, 15)
            consecutive_failures += 1

    print("❌ 모든 재시도 실패. 한 번에 요청하는 데이터가 너무 커서 무료 계정에서 차단되었을 수 있습니다.")
    return None


def _extract_facts_from_response(response_text, part_num):
    """JSON 응답에서 주요 수치 및 HTML을 안전하게 추출합니다."""
    try:
        import json
        response_data = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                import json
                response_data = json.loads(response_text[start:end+1])
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 오류 (Part {part_num}): {e}")
                return {"html": response_text, "facts": {}}
        else:
            print(f"⚠️ JSON 파싱 오류 (Part {part_num}): 유효한 JSON 블록을 찾을 수 없음")
            return {"html": response_text, "facts": {}}
    except Exception as e:
        print(f"⚠️ 팩트 추출 오류 (Part {part_num}): {e}")
        return {"html": response_text, "facts": {}}

    facts = response_data.get('facts', {})
    html = response_data.get('html', response_data.get('content', response_text))
    print(f"✅ Part {part_num} 팩트 추출 완료")
    return {"html": html, "facts": facts}


def _generate_part_with_check(prompt, part_num, part_label, confirmed_text_so_far, max_part_retries=2, session_key=None, label=None, category_label="ETF"):
    """
    Part 하나를 생성하고, 생성 직후 그 자리에서 검수 -> 실패시 재생성을 반복합니다.
    반드시 이전 Part들이 이미 확정된 상태(confirmed_text_so_far)에서만 호출해야 하며,
    이 함수가 반환한 뒤에는 그 결과를 확정으로 간주하고 다음 Part로 넘어갑니다.
    (거슬러 올라가 다시 부르면 안 됩니다 - 이후 Part들이 이미 이 결과를 참고해 쓰여집니다)

    session_key가 주어지면, 확정된 원본 JSON 응답을 raw_responses/ 폴더에
    저장해 사람이 나중에 직접 열어 검토하거나 html/facts 필드를 수정할 수
    있게 한다. 없으면 저장을 건너뛴다(기존 동작과 동일, 하위 호환).

    반환값: (raw_response_text, quality_info) - quality_info는 None일 수 있음(검수 불가 상태)
    raw_response_text는 항상 최선의 결과(마지막 시도)를 반환합니다 (완전 실패해도 재생성을 포기하고
    사람이 최종 검토하게 함 - 자동화가 멈춰버리는 것보다 낫습니다).
    """
    last_response = None
    last_quality = None
    previous_issues = None
    last_failed_html = None  # [신규] 직전 시도에서 실제로 생성됐던 HTML(검수 실패분) - 재시도 프롬프트에 원문으로 첨부

    RETRY_ATTEMPT_EXCERPT_CAP = 8000  # 재시도 프롬프트에 원문을 통째로 넣진 않고 텍스트 추출 후 상한을 둠

    for attempt in range(max_part_retries):
        print(f"🤖 {part_label} 생성 중 (시도 {attempt + 1}/{max_part_retries})...")

        # [수정] 이전 시도에서 검수가 지적한 문제가 있다면, 프롬프트에 명시적으로
        # 추가해서 AI가 같은 실수를 반복하지 않도록 합니다. 첫 시도(previous_issues
        # 없음)에는 원래 prompt를 그대로 사용합니다.
        # [추가 수정] 예전에는 "지적사항 요약 문구"만 다시 넣어줬는데, 이러면 AI가
        # 실제로 뭘 어떻게 썼길래 겹쳤는지 원문 대조 없이 "말로만" 고치게 되어
        # 형태만 바뀐 비슷한 문제가 재발하기 쉬웠음. 직전 시도의 실제 텍스트(HTML
        # 제거)를 함께 보여줘서, 그 원문을 보고 실제로 다른 문장으로 고치도록 한다.
        if previous_issues:
            issues_text = "\n".join(f"- {issue}" for issue in previous_issues)
            previous_attempt_block = ""
            if last_failed_html:
                prev_text = _extract_text_for_review(last_failed_html)
                if len(prev_text) > RETRY_ATTEMPT_EXCERPT_CAP:
                    prev_text = prev_text[:RETRY_ATTEMPT_EXCERPT_CAP] + " ...(중략)"
                previous_attempt_block = (
                    "\n\n[직전 시도에서 실제로 작성했던 원문 (텍스트만 추출 - 이걸 그대로 다시 쓰지 말 것)]\n"
                    f"{prev_text}\n"
                )
            current_prompt = (
                prompt
                + "\n\n[중요 - 직전 시도 검수 결과 반영 필수]\n"
                + "바로 이전 시도에서 아래 문제들이 지적되어 재생성하는 것입니다. "
                + "같은 문제를 절대 반복하지 말고, 아래 각 지적사항을 실제로 고친 새로운 내용을 작성하세요:\n"
                + issues_text
                + previous_attempt_block
            )
        else:
            current_prompt = prompt

        # [신규] 첫 시도는 사고 없이 빠르게 뽑는다(대부분 통과하거나, 실패해도
        # 재시도 프롬프트가 문제를 구체적으로 짚어주므로 굳이 비쌀 필요 없음).
        # 반면 재시도(previous_issues가 있는 경우)는 "지적된 문제를 실제로
        # 피해서 다시 써야" 하는, 사고가 실제로 값어치를 하는 상황이므로
        # 사고를 켠다 - 같은 문제를 반복해서 재시도 횟수를 낭비하는 것보다
        # 한 번에 제대로 고치는 쪽이 총 호출 수/토큰 관점에서 더 싸다.
        gen_thinking_budget = 24576 if previous_issues else 0
        response_text = get_gemini_response(current_prompt, thinking_budget=gen_thinking_budget)
        if not response_text:
            print(f"⚠️ {part_label} 생성 자체가 실패했습니다 (API 응답 없음).")
            continue
        last_response = response_text

        # 검수용으로 HTML만 대략 추출 (완전 파싱은 호출부에서 다시 함 - 여기선 검수 목적만)
        try:
            parsed_for_check = json.loads(response_text)
            html_for_check = parsed_for_check.get('html', response_text)
        except (json.JSONDecodeError, AttributeError):
            html_for_check = response_text

        print(f"🔎 {part_label} 즉시 검수 중...")
        check_result = _llm_part_check(html_for_check, part_label, confirmed_text_so_far, category_label=category_label)
        last_quality = check_result

        if check_result is None:
            print(f"⚠️ {part_label} 검수 불가(응답 실패) - 통과로 간주하지 않고 재시도합니다.")
            continue

        if check_result['pass'] and check_result['quality_score'] >= 0.6:
            print(f"✅ {part_label} 검수 통과 (점수 {check_result['quality_score']:.2f})")
            if session_key:
                _save_raw_part_response(session_key, part_num, last_response, label=label)
            return last_response, last_quality
        else:
            print(f"🔁 {part_label} 검수 미통과 (점수 {check_result['quality_score']:.2f}) - 이 파트만 재생성합니다.")
            if check_result['issues']:
                for issue in check_result['issues']:
                    print(f"   - {issue}")
            # [수정] 다음 재시도에서 사용할 수 있도록 지적사항을 저장해둡니다.
            previous_issues = check_result['issues']
            # [신규] 지적사항 요약뿐 아니라 실제로 뭐라고 썼는지도 다음 시도에 보여주기 위해 원문을 저장.
            last_failed_html = html_for_check

    print(f"⚠️ {part_label}: 최대 재시도 도달 - 마지막 생성 결과를 그대로 사용합니다. 발행 전 직접 확인하세요.")
    if session_key and last_response:
        _save_raw_part_response(session_key, part_num, last_response, label=label)
    return last_response, last_quality


def get_unique_quote():
    used_quotes = []
    if os.path.exists(QUOTE_FILE):
        with open(QUOTE_FILE, "r", encoding="utf-8") as f:
            used_quotes = f.read().splitlines()
    
    print("📜 중복되지 않는 새로운 금융 명언을 찾는 중...")
    prompt = f"금융 데이터베이스. 사용된 명언: {used_quotes}\n위 리스트에 없는 새로운 금융/투자 명언 1개(워렌 버핏, 피터 린치, 앙드레 코스톨라니, 벤저민 그레이엄 등 실존 투자가).\n응답을 JSON 형식으로 출력하세요: {{\"kor\": \"한글명언\", \"eng\": \"영어원문\", \"author\": \"인물이름\"}}"
    
    res = get_gemini_response(prompt)
    default_quote = {"kor": "투자는 IQ 게임이 아니다.", "eng": "Investing is not a game where the guy with the 160 IQ beats the guy with 130 IQ.", "author": "워렌 버핏"}
    
    if not res:
        return default_quote

    try:
        quote_data = json.loads(res)
        with open(QUOTE_FILE, "a", encoding="utf-8") as f:
            f.write(quote_data.get("kor", "") + "\n")
        return quote_data
    except Exception as e:
        print(f"⚠️ 명언 파싱 오류: {type(e).__name__}: {e}")
        return default_quote


def _check_publish_interval(min_hours=20):
    """[신규] 최근 발행글과의 시간 간격을 확인.
    완전자동화 파이프라인은 발행 속도를 스스로 제어하지 않으면, 짧은 기간에
    구조가 비슷한 글을 몰아서 발행하게 되기 쉽고 이는 구글이 스팸/저품질 신호로
    보는 대표적인 패턴(scaled content abuse)이다. 최소 간격을 두어 이를 방지한다.
    반환값: (진행 가능 여부(bool), 안내 메시지(str))"""
    state = _load_state()
    published = [a for a in state.get('articles', []) if a.get('status') == 'published']
    if not published:
        return True, "✅ 첫 발행 글입니다."

    try:
        last = max(published, key=lambda a: a.get('timestamp', ''))
        last_time = datetime.fromisoformat(last['timestamp'])
    except (ValueError, KeyError):
        return True, "⚠️ 이전 발행 시각 파싱 실패 - 간격 체크를 건너뜁니다."

    elapsed_hours = (datetime.now() - last_time).total_seconds() / 3600
    if elapsed_hours < min_hours:
        remaining = min_hours - elapsed_hours
        return False, (
            f"⏱️ 마지막 발행({last_time.strftime('%Y-%m-%d %H:%M')})으로부터 {elapsed_hours:.1f}시간밖에 지나지 않았습니다.\n"
            f"   최소 권장 간격은 {min_hours}시간이며, {remaining:.1f}시간 더 기다리는 것을 권장합니다.\n"
            f"   (짧은 간격으로 유사한 구조의 글을 몰아서 발행하면 애드센스/검색 스팸 정책상 불리할 수 있습니다)"
        )
    return True, f"✅ 마지막 발행으로부터 {elapsed_hours:.1f}시간 경과 - 발행 간격 조건을 충족합니다."


def _clean_stale_sessions(max_age_hours=6):
    """
    [중요] Part1~5 생성 세션은 API 비용을 아끼려고 파일에 캐싱되는데, 실행이
    Ctrl+C나 에러로 중간에 끊기면 그 세션이 disk에 그대로 남는다. 문제는 이후
    다시 실행했을 때, 코드가 그 사이 수정됐거나(예: "목차 금지" 지시 추가 전/후)
    여러 번의 서로 다른 시도에서 부분적으로만 채워진 Part 조각들이 뒤섞여
    재사용될 수 있다는 것 - 실제로 목차가 6번 나오는 등 뒤죽박죽 결과물이
    이 문제로 발생했다. 일정 시간(기본 6시간)이 지난 세션은 자동으로 정리해,
    "당일 재시도"는 살리면서 "며칠에 걸친 오염된 캐시 재사용"은 막는다.
    """
    gen_state = _load_generation_state()
    sessions = gen_state.get('sessions', {})
    if not sessions:
        return
    now_ts = time.time()
    stale_keys = [
        key for key, sess in sessions.items()
        if now_ts - sess.get('created_at', 0) > max_age_hours * 3600
    ]
    if stale_keys:
        for key in stale_keys:
            sessions.pop(key, None)
        _save_generation_state(gen_state)
        print(f"🧹 {len(stale_keys)}개의 오래된 생성 세션 캐시를 정리했습니다 (뒤섞임 방지).")


def _wp_tags_param(tag_names):
    """[수정] 예전 코어 REST API(wp-json/wp/v2/tags)는 태그를 ID로 요구해서
    검색→없으면 생성→ID 수집이라는 별도 왕복이 필요했다. 하지만
    WordPress.com 자체 API(v1.1)는 posts/new 호출 시 "tags" 파라미터에
    태그 "이름"을 콤마로 구분한 문자열로 그냥 넘기면 되고, 없는 태그는
    워드프레스가 알아서 만들어준다. 그래서 별도 API 왕복 자체가 필요 없어져
    이 함수로 단순화한다(기존 _wp_get_or_create_tags는 더 이상 쓰지 않음)."""
    cleaned = [name.strip() for name in (tag_names or []) if name and name.strip()]
    return ",".join(cleaned)


def _print_final_quality_summary(final_quality_score, final_quality_issues, policy_issues_overall):
    """[신규] 발행 직전 품질 검수 요약을 출력하는 헬퍼. 반자동 발행 경로
    여러 곳(워드프레스 API 실패, Selenium 실패)에서 동일한 로직이 중복되던
    것을 하나로 추출."""
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


def publish_to_wordpress_selenium(driver, title, html_content, wp_email, wp_password, site_url):
    """[신규] wordpress.com에 Selenium으로 로그인부터 발행까지 완전 자동화한다.
    API(애플리케이션 비밀번호)가 막혀있는 무료/개인/프리미엄 요금제에서
    사용하기 위한 방식. wordpress.com 로그인은 보통 "이메일 입력 -> 계속 ->
    비밀번호 입력 -> 로그인"의 2단계 구조를 쓴다.

    [중요] wordpress.com의 실제 화면 구조(버튼 클래스명, ID)는 시점에 따라
    조금씩 바뀔 수 있다. 아래 셀렉터가 정확히 안 맞으면(예: "요소를 찾을 수
    없음" 오류), 실제로 로그인 화면을 열어 개발자 도구(F12)로 정확한
    선택자를 확인해서 조정이 필요할 수 있다 - 이건 Selenium 방식 자체의
    근본적인 한계(화면이 바뀌면 깨짐)로, 티스토리에서 겪은 것과 동일한
    종류의 문제이며 API 방식만이 이 문제에서 완전히 자유롭다.

    반환값: (성공 여부(bool), 발행된 글의 실제 URL(str) 또는 오류 메시지)
    """
    try:
        # --- 1단계: 로그인 ---
        driver.get("https://wordpress.com/log-in")
        time.sleep(3)

        try:
            email_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "usernameOrEmail"))
            )
            email_field.click()
            pyperclip.copy(wp_email)
            email_field.send_keys(Keys.CONTROL, 'v')
            time.sleep(0.5)
            email_field.send_keys(Keys.ENTER)
            time.sleep(2)
        except TimeoutException:
            return False, "로그인 화면의 이메일 입력란(#usernameOrEmail)을 찾지 못했습니다. wordpress.com 화면 구조가 바뀌었을 수 있습니다."

        try:
            password_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "password"))
            )
            password_field.click()
            pyperclip.copy(wp_password)
            password_field.send_keys(Keys.CONTROL, 'v')
            time.sleep(0.5)
            password_field.send_keys(Keys.ENTER)
        except TimeoutException:
            return False, "로그인 화면의 비밀번호 입력란(#password)을 찾지 못했습니다. wordpress.com 화면 구조가 바뀌었을 수 있습니다."

        print("⏳ 워드프레스 로그인 대기 (10초)...")
        time.sleep(10)

        # --- 2단계: 새 글쓰기 화면 진입 ---
        base = site_url.rstrip('/')
        driver.get(f"{base}/wp-admin/post-new.php")
        time.sleep(5)

        # 구텐베르크 에디터의 초기 안내 팝업(사용법 소개 등)이 뜨면 닫기
        try:
            close_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Close']"))
            )
            close_btn.click()
            time.sleep(1)
        except TimeoutException:
            pass  # 팝업이 없으면 그냥 진행

        # --- 3단계: 제목 입력 ---
        try:
            title_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1[aria-label='Add title'], textarea[aria-label='Add title']"))
            )
            title_field.click()
            pyperclip.copy(title)
            title_field.send_keys(Keys.CONTROL, 'v')
            time.sleep(1)
        except TimeoutException:
            return False, "제목 입력란을 찾지 못했습니다. 에디터 화면 구조가 바뀌었을 수 있습니다."

        # --- 4단계: 본문을 코드 편집기(HTML 모드)로 전환해 붙여넣기 ---
        # 구텐베르크는 블록 단위 편집이 기본이라, 완성된 HTML을 그대로
        # 붙여넣으려면 "코드 편집기" 모드로 전환해야 한다(우측 상단 옵션
        # 메뉴(⋮) -> Code editor). 이 전환 없이 본문에 바로 붙여넣으면
        # HTML 태그가 텍스트 그대로 노출되어 깨진다.
        try:
            options_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Options']"))
            )
            options_btn.click()
            time.sleep(1)
            code_editor_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Code editor')]"))
            )
            code_editor_btn.click()
            time.sleep(1)
        except TimeoutException:
            return False, "코드 편집기(HTML 모드) 전환 버튼을 찾지 못했습니다. 에디터 화면 구조가 바뀌었을 수 있습니다."

        try:
            content_area = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea.editor-post-text-editor"))
            )
            content_area.click()
            pyperclip.copy(html_content)
            content_area.send_keys(Keys.CONTROL, 'v')
            time.sleep(2)
        except TimeoutException:
            return False, "본문 코드 편집기 영역을 찾지 못했습니다."

        # --- 5단계: 발행 ---
        try:
            publish_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Publish')]"))
            )
            publish_btn.click()
            time.sleep(2)
            # 발행 확인 패널에서 다시 한번 "Publish" 버튼이 뜨는 2단계 확인 구조
            confirm_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.editor-post-publish-panel button.editor-post-publish-button"))
            )
            confirm_btn.click()
            time.sleep(5)
        except TimeoutException:
            return False, "발행 버튼을 찾지 못했습니다. 초안으로 저장되었을 수 있으니 워드프레스 관리자 화면에서 직접 확인해주세요."

        # --- 6단계: 발행된 글의 실제 URL 확인 ---
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'View Post')]"))
            )
            view_post_link = driver.find_element(By.XPATH, "//a[contains(text(), 'View Post')]")
            published_url = view_post_link.get_attribute("href")
            return True, published_url or f"{base} (발행됐지만 정확한 URL 확인 실패 - 관리자 화면에서 확인하세요)"
        except TimeoutException:
            return True, f"{base} (발행은 된 것으로 보이나 정확한 URL 확인 실패 - 관리자 화면에서 확인하세요)"

    except Exception as e:
        return False, f"예상치 못한 오류: {type(e).__name__}: {e}"


# 자동화 카테고리(BLOG_CATEGORY) → 워드프레스 카테고리 주소(slug).
# 기존 주소(etf/patents/biotech/trend)는 이미 걸린 링크가 깨지지 않게 그대로 두고,
# 화면에 보이는 이름만 워드프레스 관리자에서 바꾼다.
WP_CATEGORY_SLUGS = {
    "etf": "etf", "trend": "trend", "tech": "patents", "patent": "patents",
    "bio": "biotech", "energy": "energy", "society": "society",
}
_wp_category_id_cache = {}


def _wp_category_id(category_slug):
    """워드프레스 카테고리 주소로 ID를 찾는다. 없으면 None(그 카테고리를 관리자에서 먼저 만들어야 함)."""
    if category_slug in _wp_category_id_cache:
        return _wp_category_id_cache[category_slug]
    cat_id = None
    try:
        r = requests.get(
            f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/categories/slug:{category_slug}",
            headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"}, timeout=20)
        if r.status_code == 200:
            cat_id = r.json().get("ID")
        else:
            print(f"⚠️ 워드프레스 카테고리 '{category_slug}'를 찾지 못했습니다(HTTP {r.status_code}). "
                  f"관리자 화면에서 이 주소(slug)로 카테고리를 만들어주세요. 이번 글은 카테고리 없이 올라갑니다.")
    except Exception as e:
        print(f"⚠️ 워드프레스 카테고리 조회 실패: {type(e).__name__}: {e}")
    _wp_category_id_cache[category_slug] = cat_id
    return cat_id


def publish_to_wordpress(title, html_content, tags=None, status="publish", slug=None, category_slug=None,
                         featured_image=None):
    """[수정] 워드프레스 발행 함수.

    [중요/버그수정 이력] 예전 버전은 자체호스팅용 코어 REST API
    (wp-json/wp/v2/posts)를 "애플리케이션 비밀번호"(WP_USERNAME/
    WP_APP_PASSWORD) Basic Auth로 호출했다. 이 경로는 WordPress.com에서는
    요금제(무료/개인/프리미엄/비즈니스 등)와 무관하게 서버 자체에서 항상
    막혀 있어서, 토큰을 아무리 새로 발급해도 rest_cannot_create 401이
    반복될 수밖에 없었다(원인은 요금제가 아니라 이 인증 방식/엔드포인트
    자체였음). 그래서 WordPress.com이 자체 제공하는 OAuth2 기반 API
    (public-api.wordpress.com/rest/v1.1)를 Bearer 토큰으로 호출하는 방식으로
    교체했다 - 요금제 무관, Free 요금제에서도 작동한다.

    필요한 .env 값: WP_OAUTH_TOKEN(OAuth2 access token), WP_SITE_ID(숫자형
    사이트 ID). 발급 방법은 PROJECT_STATUS.txt 3-1절 참고.

    [신규] slug 파라미터: AI가 Part1 팩트시트에서 만든 recommended_url(영문
    소문자-하이픈 슬러그)을 여기로 넘기면, 워드프레스가 제목 기반으로 자동
    생성하는 슬러그 대신 이 값을 실제 게시물 URL로 사용한다(예:
    ondo99.com/이-슬러그/). WordPress.com REST API의 posts/new 엔드포인트는
    slug 파라미터를 정식 지원한다. 값이 없거나 비어 있으면 기존처럼 제목
    기반 자동 생성에 맡긴다.

    반환값: (성공 여부(bool), 발행된 글의 실제 URL(str) 또는 오류 메시지)
    """
    if not (WP_OAUTH_TOKEN and WP_SITE_ID):
        return False, "WP_OAUTH_TOKEN/WP_SITE_ID가 .env에 설정되지 않았습니다."

    headers = {"Authorization": f"Bearer {WP_OAUTH_TOKEN}"}

    payload = {
        "title": title,
        "content": html_content,
        "status": status,  # "publish"(즉시 발행) 또는 "draft"(임시저장)
    }
    if slug:
        payload["slug"] = slug
    if featured_image:
        # 대표 이미지(썸네일) - 미디어 라이브러리 첨부파일 ID. 허브·카테고리 페이지 카드에 보인다.
        payload["featured_image"] = str(featured_image)
    # 예전엔 카테고리를 지정하지 않아 모든 글이 "미분류"로 올라갔고, 허브/카테고리
    # 페이지(카테고리 주소로 글을 불러옴)에 글이 하나도 안 보이는 문제가 있었다.
    category_slug = category_slug or WP_CATEGORY_SLUGS.get(BLOG_CATEGORY)
    if category_slug:
        cat_id = _wp_category_id(category_slug)
        if cat_id:
            payload["categories"] = str(cat_id)
    tags_param = _wp_tags_param(tags)
    if tags_param:
        payload["tags"] = tags_param  # v1.1 API는 태그 "이름"의 콤마구분 문자열을 받고, 없는 태그는 자동 생성함

    try:
        response = requests.post(
            f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/new/",
            data=payload,
            headers=headers,
            timeout=60,
        )
    except requests.exceptions.RequestException as e:
        return False, f"네트워크 오류: {type(e).__name__}: {e}"

    if response.status_code not in (200, 201):
        return False, f"HTTP {response.status_code}: {response.text[:500]}"

    try:
        data = response.json()
        published_url = data.get("URL", "") or data.get("link", "")
        # 발행한 글 번호 - 나중에 텔레그램으로 받은 이미지로 썸네일을 바꿀 때 쓴다.
        global LAST_PUBLISHED_POST_ID
        LAST_PUBLISHED_POST_ID = data.get("ID")
        return True, published_url
    except (ValueError, KeyError) as e:
        return False, f"응답 파싱 실패: {type(e).__name__}: {e}"


LAST_PUBLISHED_POST_ID = None


def wp_set_featured_image(post_id, media_id):
    """이미 올라간 글의 대표 이미지(썸네일)를 바꾼다. 성공하면 True."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID and post_id and media_id):
        return False
    try:
        r = requests.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/{post_id}",
                          headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                          data={"featured_image": str(media_id)}, timeout=30)
        if r.status_code in (200, 201):
            return True
        print(f"⚠️ 대표 이미지 바꾸기 실패: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 대표 이미지 바꾸기 중 오류: {type(e).__name__}")
    return False


def wp_get_post_content(post_id):
    """글 본문(저장된 원본 HTML)을 가져온다. 실패하면 None."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID and post_id):
        return None
    try:
        r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/{post_id}",
                         headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                         params={"context": "edit", "fields": "content"}, timeout=30)
        return r.json().get("content") if r.status_code == 200 else None
    except Exception as e:
        print(f"⚠️ 글 본문 가져오기 실패: {type(e).__name__}")
        return None


def wp_update_post_content(post_id, content):
    """글 본문을 바꾼다(본문 그림을 나중에 넣을 때). 성공하면 True."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID and post_id):
        return False
    try:
        r = requests.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/{post_id}",
                          headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                          data={"content": content}, timeout=60)
        if r.status_code in (200, 201):
            return True
        print(f"⚠️ 글 본문 바꾸기 실패: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 글 본문 바꾸기 중 오류: {type(e).__name__}")
    return False


def wp_find_post_by_url(url):
    """글 주소로 (글 번호, 제목, 분야 코드)를 찾는다. 못 찾으면 None.
    텔레그램으로 그림을 보낼 때 설명에 글 주소를 붙이면 아무 글이나 썸네일을 바꿀 수 있게 하는 용도."""
    import urllib.parse as _up
    if not (WP_OAUTH_TOKEN and WP_SITE_ID and url):
        return None
    parsed = _up.urlparse(url.strip())
    q = _up.parse_qs(parsed.query)
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/"
    if q.get("p"):
        target = base + q["p"][0]
    else:
        slug = _up.unquote([seg for seg in parsed.path.split("/") if seg][-1]) if parsed.path.strip("/") else ""
        if not slug:
            return None
        target = base + "slug:" + _up.quote(slug)
    try:
        r = requests.get(target, headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                         params={"fields": "ID,title,categories"}, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        cat_slugs = [c.get("slug") for c in (data.get("categories") or {}).values()]
        code_by_slug = {"etf": "etf", "trend": "trend", "patents": "tech", "biotech": "bio",
                        "energy": "energy", "society": "society"}
        code = next((code_by_slug[c] for c in cat_slugs if c in code_by_slug), "etf")
        title = html.unescape(data.get("title", ""))
        return data.get("ID"), title, code
    except Exception as e:
        print(f"ℹ️ 글 주소로 글 찾기 실패: {type(e).__name__}")
        return None


def get_wordpress_recent_posts(count=15):
    """[신규] 워드프레스에 이미 발행된 글 목록(제목/URL)을 최신순으로 가져온다.
    내부 링크(다른 카테고리 글도 포함해서 서로 연결) 재료로 쓰인다.

    예전 tech/bio/patent 스크립트는 티스토리 RSS(get_tistory_published_posts)로
    이 목록을 가져왔지만, 이제 워드프레스로 옮겼으므로 워드프레스 공개 REST API
    (인증 불필요 - 공개 글이라 누구나 조회 가능)로 대체한다.
    실패해도(네트워크 오류 등) 빈 리스트를 반환해 내부 링크 없이 계속 진행한다.
    """
    if not (WP_SITE_URL and WP_SITE_ID):
        return []
    try:
        response = requests.get(
            f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/",
            params={"number": count, "status": "publish"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {"title": p.get("title", ""), "link": p.get("URL", "")}
            for p in data.get("posts", [])
            if p.get("title") and p.get("URL")
        ]
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"⚠️ 워드프레스 최근 글 목록 조회 실패(내부 링크 없이 진행): {type(e).__name__}: {e}")
        return []


def generate_optimized_title(topic, title_pattern_hint, context_snippet="", category_label="ETF"):
    """
    [SEO/제목 최적화 부서] Part1이 제목을 자유생성하기 전에, 서로 다른
    앵글(데이터 강조/질문형/호기심 유발/이득 강조/시의성 강조)로 후보
    제목 5개를 만들고, 그중 가장 클릭할 만한(그러면서 과장/낚시성은 아닌)
    제목 하나를 스스로 골라 확정한다.

    확정된 제목은 이후 Part1 프롬프트에 "이 제목을 그대로 써라"로 전달되어,
    기존의 "패턴을 참고해서 새로 만들어라" 방식을 대체한다.

    실패하면 None을 돌려주고, 호출한 쪽은 기존 방식(title_pattern_hint를
    참고해서 Part1이 자유생성)으로 그대로 진행한다.
    """
    prompt = f"""당신은 {category_label} 분석 블로그의 SEO 담당자입니다.
주제: {topic}
참고할 제목 스타일(그대로 베끼지 말고 영감만 얻으세요): {title_pattern_hint}
글의 대략적인 맥락: {context_snippet[:500] if context_snippet else "(정보 없음)"}

서로 다른 5가지 앵글로 제목 후보를 만들고, 그중 가장 클릭률이 높을 것 같으면서도
과장·낚시성이 없는 제목 하나를 선택하세요.
앵글: ① 데이터/수치 강조 ② 질문형 ③ 호기심 유발 ④ 독자 이득 강조 ⑤ 시의성 강조

[SEO 체크리스트 - 워드프레스 Rank Math 플러그인의 채점 기준에 맞춰서 작성]
- 제목 길이: 50~60자 권장 (너무 길면 검색결과에서 잘리고, 너무 짧으면 정보가 부족함)
- 포커스 키워드("{topic}")를 제목 앞쪽 절반 안에 배치
- 능동태, 읽기 쉬운 문장 구조 사용

반드시 JSON 형식으로만 답하세요:
{{"candidates": ["후보1", "후보2", "후보3", "후보4", "후보5"],
  "selected": "최종 선택된 제목",
  "reason": "이 제목을 고른 이유(1~2문장)"}}
"""
    raw = get_gemini_response(prompt, thinking_budget=0)
    if raw is None:
        print("⚠️ 제목 최적화 생성 실패(API 소진 등) - 기존 방식(자유생성)으로 진행합니다.")
        return None
    try:
        parsed = json.loads(raw)
        if parsed.get("selected"):
            return parsed
        return None
    except (json.JSONDecodeError, TypeError):
        print("⚠️ 제목 최적화 결과 JSON 파싱 실패 - 기존 방식(자유생성)으로 진행합니다.")
        return None


def _card_html_shell(body_html):
    """3개 카드가 공통으로 쓰는 배경/폰트/레이아웃 뼈대."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {CARD_WIDTH}px; height: {CARD_HEIGHT}px;
    background: linear-gradient(160deg, #0f172a 0%, #1e293b 100%);
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    display: flex; flex-direction: column; justify-content: center; align-items: center;
    padding: 80px; color: #f1f5f9;
  }}
</style></head>
<body>{body_html}</body></html>"""


def _render_html_to_image(driver, html_str, output_path):
    """
    이미 실행 중인 Selenium 드라이버(driver)를 재사용해서 HTML을 그대로
    스크린샷으로 저장한다. 새로 브라우저를 띄우지 않고 발행 파이프라인이
    이미 켜둔 드라이버를 공유하는 방식이라 리소스가 추가로 들지 않는다.
    """
    tmp_path = os.path.abspath(f"_card_tmp_{int(time.time()*1000)}.html")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    try:
        driver.set_window_size(CARD_WIDTH, CARD_HEIGHT)
        driver.get(f"file://{tmp_path}")
        time.sleep(0.5)  # 렌더링 안정화 대기
        driver.save_screenshot(output_path)
        return True
    except Exception as e:
        print(f"⚠️ 카드 이미지 렌더링 실패: {type(e).__name__}: {e}")
        return False
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _upload_media(file_path, mime_type):
    """미디어 라이브러리에 올리고 (첨부파일 ID, 공개 URL)을 돌려준다. 실패하면 (None, None).
    ID는 글의 대표 이미지(featured_image) 지정에 쓴다."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID):
        return None, None
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/media/new",
                headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                files={"media[]": (os.path.basename(file_path), f, mime_type)},
                timeout=60,
            )
        media_list = resp.json().get("media", [])
        if media_list:
            return media_list[0].get("ID"), media_list[0].get("URL")
        print(f"⚠️ 워드프레스 파일 업로드 실패: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"⚠️ 워드프레스 파일 업로드 중 오류: {type(e).__name__}: {e}")
    return None, None


def _upload_file_to_wordpress(file_path, mime_type):
    """파일을 워드프레스 미디어 라이브러리에 올리고 공개 URL을 돌려준다(카드뉴스 이미지, IndexNow
    키 파일 등). 실패하면(요금제 제한 등으로 API가 막혀 있을 수 있음) None."""
    return _upload_media(file_path, mime_type)[1]


def _upload_image_to_wordpress(image_path):
    """[하위 호환용 별칭] 카드뉴스 이미지 업로드는 이 이름 그대로 계속 쓴다."""
    return _upload_file_to_wordpress(image_path, "image/png")


def _get_or_create_indexnow_key():
    """
    IndexNow 인증키를 (최초 1회만) 자동으로 만들고, 워드프레스 미디어
    라이브러리에 키 파일을 올려서 공개 URL을 확보한다. 이후로는 저장해둔
    값을 계속 재사용한다 - 사람이 직접 키를 발급받거나 파일을 올릴 필요가
    전혀 없이, 첫 실행 때 코드가 알아서 다 처리한다.
    """
    state = _load_json_file(INDEXNOW_KEY_STATE_FILE, None)
    if state and state.get("key") and state.get("key_url"):
        return state["key"], state["key_url"]

    key = _secrets_module.token_hex(16)  # 32자리 16진수 - IndexNow 규격에 맞음
    key_file_path = os.path.abspath(f"{key}.txt")
    with open(key_file_path, "w", encoding="utf-8") as f:
        f.write(key)

    key_url = _upload_file_to_wordpress(key_file_path, "text/plain")
    try:
        os.remove(key_file_path)
    except OSError:
        pass

    if not key_url:
        print("⚠️ IndexNow 키 파일 업로드 실패 - 이번엔 검색엔진 알림을 건너뜁니다.")
        return key, None

    _save_json_file(INDEXNOW_KEY_STATE_FILE, {"key": key, "key_url": key_url})
    print(f"✅ IndexNow 키 최초 생성 및 업로드 완료: {key_url}")
    return key, key_url


def ping_indexnow(article_url):
    """
    발행된 글 URL을 IndexNow에 제출해서 Bing/Yandex/네이버 등에 즉시
    알린다. 실패해도 예외를 던지지 않는다 - 발행 자체와는 무관한 부가
    기능이라, 이것 때문에 파이프라인이 멈추면 안 된다.
    """
    try:
        key, key_url = _get_or_create_indexnow_key()
        if not key_url:
            return False
        resp = requests.get(
            "https://api.indexnow.org/indexnow",
            params={"url": article_url, "key": key, "keyLocation": key_url},
            timeout=10,
        )
        if resp.status_code in (200, 202):
            print("✅ IndexNow(Bing/Yandex/네이버 등) 색인 알림 전송 완료")
            return True
        print(f"⚠️ IndexNow 알림 실패: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ IndexNow 알림 중 오류(무시하고 계속 진행): {type(e).__name__}: {e}")
        return False


def _threads_create_carousel_item(image_url):
    """캐러셀에 들어갈 이미지 하나를 위한 컨테이너를 만들고 id를 돌려준다."""
    try:
        resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            data={
                "media_type": "IMAGE",
                "image_url": image_url,
                "is_carousel_item": "true",
                "access_token": THREADS_ACCESS_TOKEN,
            },
            timeout=20,
        )
        return resp.json().get("id")
    except Exception as e:
        print(f"⚠️ Threads 캐러셀 아이템 생성 실패: {type(e).__name__}: {e}")
        return None


def _threads_post_carousel(image_urls, caption):
    """
    이미지 URL 목록을 캐러셀(옆으로 넘기는 여러 장) 게시물로 발행한다.
    최소 2장이 있어야 캐러셀로 취급된다(1장이면 그냥 단일 이미지 게시물이 됨).
    """
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("ℹ️ THREADS_ACCESS_TOKEN/THREADS_USER_ID 미설정 - Threads 게시를 건너뜁니다.")
        return False
    if len(image_urls) < 2:
        print("⚠️ 캐러셀에 쓸 이미지가 2장 미만이라 게시를 건너뜁니다.")
        return False
    try:
        item_ids = [i for i in (_threads_create_carousel_item(u) for u in image_urls) if i]
        if len(item_ids) < 2:
            print("⚠️ 캐러셀 아이템 생성에 실패한 이미지가 있어 게시를 건너뜁니다.")
            return False

        carousel_resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(item_ids),
                "text": caption,
                "access_token": THREADS_ACCESS_TOKEN,
            },
            timeout=20,
        )
        carousel_id = carousel_resp.json().get("id")
        if not carousel_id:
            print(f"⚠️ Threads 캐러셀 컨테이너 생성 실패: {carousel_resp.status_code} {carousel_resp.text[:200]}")
            return False

        publish_resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
            data={"creation_id": carousel_id, "access_token": THREADS_ACCESS_TOKEN},
            timeout=20,
        )
        if publish_resp.status_code == 200:
            print("✅ Threads 카드뉴스(캐러셀) 게시 완료")
            return True
        print(f"⚠️ Threads 캐러셀 발행 실패: {publish_resp.status_code} {publish_resp.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ Threads 캐러셀 게시 중 오류: {type(e).__name__}: {e}")
        return False


def _threads_post(text):
    """Threads에 텍스트만 있는 게시물을 올린다 (카드뉴스 실패 시 폴백용)."""
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("ℹ️ THREADS_ACCESS_TOKEN/THREADS_USER_ID 미설정 - Threads 게시를 건너뜁니다.")
        return False
    try:
        create_resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            data={"media_type": "TEXT", "text": text, "access_token": THREADS_ACCESS_TOKEN},
            timeout=15,
        )
        creation_id = create_resp.json().get("id")
        if not creation_id:
            print(f"⚠️ Threads 게시물 생성 실패: {create_resp.status_code} {create_resp.text[:200]}")
            return False
        publish_resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
            data={"creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN},
            timeout=15,
        )
        if publish_resp.status_code == 200:
            print("✅ Threads 홍보 게시 완료 (텍스트)")
            return True
        print(f"⚠️ Threads 게시 발행 실패: {publish_resp.status_code} {publish_resp.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ Threads 게시 중 오류(무시하고 계속 진행): {type(e).__name__}: {e}")
        return False


def _telegram_send_message(text, with_approve_button=False, parse_mode=None, buttons=None, reply_to=None):
    """buttons: [[("글자", "신호"), ...], ...] 줄 단위 버튼. reply_to: 이 메시지 번호에 답장 형태로 보냄
    (예: 사용자가 보낸 그림에 답장 → 질문 위에 그 그림이 작게 같이 보인다)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 설정되지 않아 텔레그램 알림을 건너뜁니다.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode   # "HTML"이면 <pre> 상자 → 텔레그램에서 눌러서 바로 복사
    if reply_to:
        payload["reply_parameters"] = json.dumps({"message_id": int(reply_to), "allow_sending_without_reply": True})
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": [
            [{"text": t, "callback_data": d} for t, d in row] for row in buttons]})
    if with_approve_button:
        # True면 ETF 추천용 "approve", 문자열이면 그 값을 버튼 신호로 쓴다(두 번째 글은 "approve_topic").
        callback = with_approve_button if isinstance(with_approve_button, str) else "approve"
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[{"text": "✅ 승인", "callback_data": callback}]]
        })
    try:
        resp = requests.post(url, data=payload, timeout=15)
        if resp.status_code == 200:
            # 보낸 메시지 번호를 돌려준다(답장으로 어느 추천에 대한 메모인지 구분할 때 사용). 참/거짓 판단에도 그대로 쓸 수 있음.
            return (resp.json().get("result") or {}).get("message_id") or True
        print(f"⚠️ 텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 중 오류: {e}")
        return False


def _insert_operator_memo(body_html, memo):
    """운영자가 텔레그램으로 보낸 한 줄 메모를 서론 다음(첫 대제목 앞)에 넣는다.
    AI가 고쳐 쓰지 않도록 코드가 그대로 넣고, HTML로 해석되지 않게 이스케이프한다."""
    block = (
        '<div class="ondo-operator-memo" style="margin:24px 0;padding:14px 18px;'
        'border-left:3px solid #e8b944;background:#f8f9fa;border-radius:4px;">'
        '<p style="margin:0 0 6px 0;font-weight:bold;font-size:14px;">✍️ 운영자 메모</p>'
        f'<p style="margin:0;font-size:15px;line-height:1.7;">{html.escape(memo)}</p>'
        '</div>'
    )
    m = re.search(r'<h3[\s>]', body_html)
    if not m:
        return body_html + block
    return body_html[:m.start()] + block + body_html[m.start():]


def _telegram_send_photo(path=None, photo_url=None, caption="", reply_to=None):
    """사진 보내기(처리 결과를 보여줄 때). 실패해도 그냥 넘어간다."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not (path or photo_url):
        return False
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}
    if reply_to:
        data["reply_parameters"] = json.dumps({"message_id": int(reply_to), "allow_sending_without_reply": True})
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        if path:
            with open(path, "rb") as f:
                r = requests.post(url, data=data, files={"photo": f}, timeout=60)
        else:
            r = requests.post(url, data=dict(data, photo=photo_url), timeout=60)
        return r.status_code == 200
    except Exception as e:
        print(f"⚠️ 텔레그램 사진 보내기 실패: {type(e).__name__}")
        return False


def _telegram_edit_text(message_id, text):
    """보낸 메시지 글을 바꾸고 버튼을 없앤다(버튼을 이미 눌렀다는 표시). 실패해도 그냥 넘어간다."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not message_id:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                          data={"chat_id": TELEGRAM_CHAT_ID, "message_id": int(message_id), "text": text}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def _telegram_answer_callback(callback_id, text=""):
    """버튼을 누른 사람 화면의 '로딩 중' 표시를 끈다(10분 뒤라 이미 만료됐을 수 있음 - 실패해도 무시)."""
    if not TELEGRAM_BOT_TOKEN or not callback_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                      data={"callback_query_id": callback_id, "text": text[:180]}, timeout=10)
    except Exception:
        pass


def _telegram_download_file(file_id, dest_path):
    """텔레그램으로 받은 사진/파일을 내려받는다. 성공하면 dest_path, 실패하면 None.
    (봇 토큰이 들어간 주소라 절대 출력하지 않는다)"""
    if not TELEGRAM_BOT_TOKEN or not file_id:
        return None
    try:
        info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
                            params={"file_id": file_id}, timeout=15).json()
        path = (info.get("result") or {}).get("file_path")
        if not path:
            return None
        r = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}", timeout=60)
        if r.status_code != 200:
            return None
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return dest_path
    except Exception as e:
        print(f"⚠️ 텔레그램 파일 받기 실패: {type(e).__name__}")
        return None


def _telegram_update_is_authorized(update):
    """봇 이름을 아는 누구나 메시지를 보낼 수 있으므로, 운영자 채팅방(TELEGRAM_CHAT_ID)에서
    온 메시지/버튼 클릭만 인정한다. 이 확인이 없으면 남이 승인하거나 사이트에 실릴
    운영자 메모를 써넣을 수 있다."""
    if not TELEGRAM_CHAT_ID:
        return False
    callback = update.get("callback_query") or {}
    message = update.get("message") or callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    return chat_id is not None and str(chat_id) == str(TELEGRAM_CHAT_ID).strip()


def _telegram_get_updates(offset=None):
    if not TELEGRAM_BOT_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("result", [])
        # 예전엔 실패해도 조용히 "응답 없음"으로 보였다. 이유를 남긴다(토큰이 든 주소는 출력하지 않음).
        try:
            desc = resp.json().get("description", "")
        except ValueError:
            desc = ""
        print(f"⚠️ 텔레그램 응답 읽기 실패: HTTP {resp.status_code} {desc}")
        return []
    except Exception as e:
        print(f"⚠️ 텔레그램 업데이트 조회 실패: {type(e).__name__}")
        return []


def telegram_diagnose():
    """버튼을 눌러도 반응이 없을 때 원인 점검: 웹후크가 걸려 있는지, 쌓인 메시지가 몇 개인지, 최근 오류."""
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음")
        return
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        me = requests.get(f"{base}/getMe", timeout=15).json().get("result", {})
        print(f"봇 이름: @{me.get('username')}")
        info = requests.get(f"{base}/getWebhookInfo", timeout=15).json().get("result", {})
        print(f"웹후크 설정: {'있음 → ' + info['url'].split('/')[2] if info.get('url') else '없음(정상)'}")
        print(f"쌓여 있는 메시지 수: {info.get('pending_update_count')}")
        if info.get("last_error_message"):
            print(f"웹후크 최근 오류: {info.get('last_error_message')}")
        r = requests.get(f"{base}/getUpdates", params={"timeout": 0, "limit": 100}, timeout=15)
        data = r.json()
        if r.status_code != 200:
            print(f"getUpdates 실패: HTTP {r.status_code} {data.get('description')}")
            return
        ups = data.get("result", [])
        print(f"getUpdates로 읽힌 메시지: {len(ups)}개 (가장 최근 번호: {ups[-1]['update_id'] if ups else '-'})")
        for u in ups[-8:]:
            kind = "버튼" if u.get("callback_query") else ("사진" if (u.get("message") or {}).get("photo") else "글")
            src = u.get("callback_query") or u.get("message") or {}
            chat = ((src.get("message") or src).get("chat") or {}).get("id")
            print(f"  #{u['update_id']} {kind} / 운영자 채팅방: {str(chat) == str(TELEGRAM_CHAT_ID).strip()}")
    except Exception as e:
        print(f"텔레그램 점검 실패: {type(e).__name__}")


atexit.register(_flush_api_usage_stats)
