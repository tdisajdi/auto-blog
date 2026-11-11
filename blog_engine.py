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
from datetime import datetime
from dotenv import load_dotenv
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

# ============================================================
# Gemini API 키 로테이션
# ============================================================
# 키 앞에 "이름표:"를 붙일 수 있다(예: aa@gmail.com:AIza...) - 문제 생기면 텔레그램에 이름표로 알림. ondo/keys.py
from ondo import keys as _ondo_keys
GEMINI_API_KEYS = [k for _no, _label, k in _ondo_keys.parse(os.environ.get("GEMINI_API_KEY", ""))]

# ============================================================
# 텔레그램 / Threads
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 카테고리별로 격리되는 상태 파일들
STATE_FILE = _cat_path('article_state.json')
GENERATION_STATE_FILE = _cat_path('generation_state.json')
DATA_CACHE_FILE = _cat_path('data_cache.json')
API_USAGE_LOG_FILE = _cat_path('api_usage_log.json')


NEWS_CACHE_TTL = 60 * 60  # 1시간 캐시




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


def _post_process_blog_content(html, rewrite_words=True):
    """AI 감지 리스크를 줄이기 위한 간단한 후처리 및 버그 픽스.
    rewrite_words=False: 단어 바꾸기("또한"→"그리고" 등)를 하지 않는다. 새 편집국은 검토를 통과한 문장을
    검토 뒤에 기계적으로 바꾸면 안 되므로(예: "이 또한"→"이 그리고") 끈다(2026-10-31)."""
    # 1. 흉측한 리터럴 \n, \t 텍스트 화면 노출 버그 강제 제거
    html = html.replace('\\n', ' ')  # 공백으로 치환
    html = html.replace('\\t', ' ')  # 공백으로 치환
    html = html.replace('\\"', '"')
    html = re.sub(r'\s+', ' ', html)  # 다중 공백 정리
    
    # [수정] 티스토리 스킨 충돌 방지: hr 대신 div를 사용해 1px 얇은 실선을 강제로 그립니다.
    html = re.sub(r'<hr[^>]*>', '', html)
    html = re.sub(r'(<(?:h2|h3)[^>]*>)', r'<div style="width:100%; height:1px; background-color:#ddd; margin:40px 0;"></div>\1', html, flags=re.IGNORECASE)

    if not rewrite_words:
        return _post_process_structure(html)
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

    return _post_process_structure(html)


def _post_process_structure(html):
    """단어는 건드리지 않고 깨진 태그·반복된 고정 문구만 정리한다."""
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
        # 2026-11-11: 구분 기호(. ) -)가 있을 때만 지움 - 예전엔 '1년 범위'의 1까지 지워 목차가 '년 범위'가 됨
        clean_text = re.sub(r'^\d+(?:[\.\)]|\s*-)\s*', '', stripped_text)
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
    from ondo.config import kst_now
    return kst_now()


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
                key_problem = _ondo_keys.classify_error(response.status_code, response.text)
                if key_problem:
                    _ondo_keys.alert_key_problem(current_key, key_problem, response.text[:150])
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






# 자동화 카테고리(BLOG_CATEGORY) → 워드프레스 카테고리 주소(slug).
# 기존 주소(etf/patents/biotech/trend)는 이미 걸린 링크가 깨지지 않게 그대로 두고,
# 화면에 보이는 이름만 워드프레스 관리자에서 바꾼다.
from ondo.config import CATEGORY_SLUGS as WP_CATEGORY_SLUGS  # noqa: E402  (분야 → 카테고리 주소, 설정 한 곳에서)
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

    # 품질이 안정될 때까지 모든 글은 임시글로(2026-10-31 결정). 공개 발행은 .env에 AUTO_PUBLISH=1을 넣었을 때만.
    global LAST_FORCED_DRAFT
    LAST_FORCED_DRAFT = status == "publish" and not auto_publish_enabled()
    if LAST_FORCED_DRAFT:
        print("ℹ️ 자동 발행이 꺼져 있어(AUTO_PUBLISH) 임시글로 올립니다.")
        status = "draft"

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
LAST_FORCED_DRAFT = False


def auto_publish_enabled():
    return os.environ.get("AUTO_PUBLISH", "").strip() == "1"


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


def wp_update_post(post_id, **fields):
    """이미 올라간 글의 제목·본문·태그·대표 이미지 등을 한꺼번에 바꾼다(글 다시 쓰기용). 성공하면 True."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID and post_id):
        return False
    data = {k: (",".join(v) if isinstance(v, (list, tuple)) else str(v)) for k, v in fields.items() if v is not None}
    try:
        r = requests.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/{post_id}",
                          headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"}, data=data, timeout=60)
        if r.status_code in (200, 201):
            return True
        print(f"⚠️ 글 바꾸기 실패: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 글 바꾸기 중 오류: {type(e).__name__}")
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
        targets = [base + q["p"][0]]
    else:
        raw = [seg for seg in parsed.path.split("/") if seg][-1] if parsed.path.strip("/") else ""
        if not raw:
            return None
        # 한글 제목 글은 워드프레스가 주소를 '%eb%82…' 문자열 그대로 저장한다(2026-11-09: 한글로 풀어 다시 대문자로 바꿔 보냈더니
        # 7월 QQQ 글을 못 찾음) → 푼 이름과 저장된 그대로의 이름을 차례로 시도
        targets = [base + "slug:" + _up.quote(_up.unquote(raw))]
        if "%" in raw:
            targets.append(base + "slug:" + _up.quote(raw.lower(), safe=""))
    try:
        for target in targets:
            r = requests.get(target, headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                             params={"fields": "ID,title,categories"}, timeout=20)
            if r.status_code == 200:
                break
        if r.status_code != 200:
            # 2026-11-09: 못 찾은 이유(404 = 글 없음/삭제됨, 403 = 권한)가 안 보여서 비공개 처리 확인이 안 됐다
            print(f"ℹ️ 글 주소로 글 찾기: 응답 {r.status_code} ({target.rsplit('/', 1)[-1][:60]})")
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


def wp_list_public_posts(limit=100):
    """사이트에 지금 '공개'된 글 전체(번호·날짜·제목·주소). 2026-11-09: 7월 QQQ 글이 실제로 공개돼 있었는데 기록만 보고는
    알 수 없었다 → 공개 글을 직접 세어 보는 점검용(애드센스 심사관 관점 점검 파①, 정기 점검 차)."""
    if not (WP_OAUTH_TOKEN and WP_SITE_ID):
        return None
    out, page = [], 1
    while len(out) < limit:
        r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{WP_SITE_ID}/posts/",
                         headers={"Authorization": f"Bearer {WP_OAUTH_TOKEN}"},
                         params={"status": "publish", "number": 50, "page": page, "fields": "ID,date,title,URL"}, timeout=20)
        if r.status_code != 200:
            print(f"ℹ️ 공개 글 목록: 응답 {r.status_code}")
            return None
        posts = r.json().get("posts", [])
        out += [{"id": p.get("ID"), "date": str(p.get("date", ""))[:10], "title": html.unescape(p.get("title", "")),
                 "url": p.get("URL", "")} for p in posts]
        if len(posts) < 50:
            break
        page += 1
    return out[:limit]


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
            {"title": p.get("title", ""), "link": p.get("URL", ""), "date": str(p.get("date", ""))[:10]}
            for p in data.get("posts", [])
            if p.get("title") and p.get("URL")
        ]
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"⚠️ 워드프레스 최근 글 목록 조회 실패(내부 링크 없이 진행): {type(e).__name__}: {e}")
        return []








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
