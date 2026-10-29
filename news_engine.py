"""news_engine.py — 테크/바이오/특허 3개 카테고리가 공유하는 뉴스 블로그 엔진.

기존 tech.py/bio.py/patent.py는 카테고리 이름 몇 개만 빼고 거의 100% 동일한
코드가 3번 복붙되어 있었고, 발행도 Gmail로 HTML을 보내 사람이 직접
복사-붙여넣기 하는 반자동 방식이었다(당시 티스토리가 API/Selenium을 모두
막아서 어쩔 수 없이 택한 우회로였음).

이제 워드프레스로 옮기면서 blog_engine.py의 발행/품질검수 파이프라인을 그대로
쓸 수 있게 됐으므로, 이 파일 하나에 "발굴 -> 기획 -> 5단 분할 글쓰기 -> 검수 ->
발행 -> 홍보" 전체를 구현하고, tech_auto.py/bio_auto.py/patent_auto.py는 각자
RSS 주소와 카테고리 이름 같은 설정값만 채워서 run_news_pipeline()을 호출하는
아주 얇은 파일로 남긴다.

[ETF 파이프라인과의 차이]
- 텔레그램 승인 대기 없음: 뉴스는 3일 지나면 낡아버리는 시의성 문제가 있어서,
  ETF처럼 사람 확인을 기다리지 않고 발굴부터 발행까지 한 번에 완료한다.
  대신 발행 후 텔레그램으로 "발행 완료" 알림만 보낸다(승인이 아니라 보고).
- 팩트시트 숫자 검증 없음: ETF는 배당률/보수율 같은 수치가 틀리면 안 되므로
  facts_json_str로 교차검증하지만, 뉴스 콘텐츠는 그런 고정 수치가 핵심이
  아니라서 품질검수(_llm_quality_check)는 facts_json_str 없이(=수치 대조
  없이) 문체/정책위반/모순/재탕 여부만 본다.
- 두 소재를 한 편에서 다룬다(원래 스크립트 설계 그대로 유지): 뉴스 1건만으로는
  분량이 짧아 SEO에 불리하다는 원래 판단을 존중해, 관련 뉴스 2건을 골라 하나의
  글로 엮는다.
"""

import re
import json
import time
import random
import datetime
import feedparser
from bs4 import BeautifulSoup

from blog_engine import (
    _cat_path, _load_json_file, _save_json_file,
    get_gemini_response, _generate_part_with_check, _extract_facts_from_response,
    _llm_quality_check, _llm_targeted_fix, _policy_filter,
    _safe_html_filter, _reduce_repetition, _clean_redundant_parenthetical,
    _post_process_blog_content, _inject_table_of_contents,
    _check_duplicate, _register_article, _load_state, _check_publish_interval,
    _print_final_quality_summary, generate_optimized_title,
    publish_to_wordpress,
    get_wordpress_recent_posts,
    _telegram_send_message, ping_indexnow,
    WP_EMAIL, WP_PASSWORD,
)

import os
import requests

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")

# [신규] 소재 발굴 이력. article_state.json(전체 본문 저장)과는 별도로,
# "이 RSS 항목을 이미 다뤘는지"만 가볍게 기록한다 (id/title/date만 저장,
# 30일 지나면 자동 정리) - 원래 tech/bio/patent 스크립트의 history.json과
# 같은 역할이며, blog_engine의 카테고리별 경로 규칙을 그대로 따른다.
TOPIC_HISTORY_FILE = _cat_path('topic_history.json')


# ============================================================
# 1) 소재 발굴 (RSS 수집 -> 스크래핑 -> 중복 제외 -> AI가 2건 선정)
# ============================================================

def _load_topic_history():
    return _load_json_file(TOPIC_HISTORY_FILE, [])


def _save_topic_history(history, new_items):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
    cleaned = []
    for item in history:
        try:
            d = datetime.datetime.strptime(item.get('date', '2000-01-01'), "%Y-%m-%d")
            if d >= cutoff:
                cleaned.append(item)
        except (ValueError, TypeError):
            continue
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    for item in new_items:
        cleaned.append({"id": item['id'], "title": item['title'], "date": today})
    _save_json_file(TOPIC_HISTORY_FILE, cleaned)


def _scrape_article_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=8)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        return text[:3000] if len(text) > 100 else None
    except requests.exceptions.RequestException:
        return None


def _fetch_rss_candidates(rss_urls, category_code, max_age_days=3):
    items = []
    cutoff = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"⚠️ RSS 조회 실패({url}): {type(e).__name__}: {e}")
            continue
        for entry in feed.entries:
            if 'published_parsed' in entry and entry.published_parsed:
                pub_date = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                if pub_date < cutoff:
                    continue
            raw_text = _scrape_article_text(entry.link)
            if not raw_text:
                raw_text = (entry.summary if 'summary' in entry else entry.title)[:2000]
            items.append({"id": entry.link, "title": entry.title, "type": category_code, "raw": raw_text})
    return items


# ============================================================
# 토론 부서 - ETF의 debate_and_select()와 같은 원칙: 후보마다 "왜 오늘 이걸
# 다뤄야 하는지" 논거를 서로 독립적으로(다른 후보 논거를 못 보게) 만들게 한
# 뒤, 마지막에 한 번 더 호출해서 전체 논거를 심사하고 최종 2개를 뽑는다.
# 순서효과(먼저 나온 논거에 끌려가는 것) 방지를 위해 논거 생성 단계에서는
# 후보들이 서로를 보지 못하게 한다.
#
# [비용 안내] 후보 하나당 API 호출이 1번씩 추가되므로, 심사 대상은
# 최대 MAX_DEBATE_CANDIDATES개로 제한한다(원문 스크래핑까지 마친 신선한
# 후보 위주로 앞에서부터 자른다).
# ============================================================

MAX_DEBATE_CANDIDATES = 6


def _build_news_advocate_prompt(candidate, category_label):
    return (
        f"역할: {category_label} 담당 기자.\n"
        "아래 뉴스를 '오늘' 우리 블로그에서 다뤄야 하는 이유를 2~3문장으로 논거를 제시하세요. "
        "단순히 흥미롭다는 말이 아니라, 왜 지금 시의성이 있는지, 독자에게 어떤 실질적 가치가 "
        "있는지 구체적으로 서술하세요. 논거만 출력하세요(다른 텍스트 없이).\n\n"
        f"[뉴스 제목] {candidate['title']}\n"
        f"[내용 요약] {candidate['raw'][:800]}\n"
    )


def _build_news_judge_prompt(candidates_with_arguments, category_label):
    listing = "\n\n".join(
        f"{i}. {c['title']}\n   논거: {arg or '(논거 생성 실패)'}"
        for i, (c, arg) in enumerate(candidates_with_arguments)
    )
    return f"""당신은 {category_label} 블로그의 편집장입니다.
아래는 오늘의 후보 뉴스들과, 각 후보를 담당한 기자가 독립적으로 제시한 "왜 다뤄야 하는지" 논거입니다.
이 중 서로 연결지어 하나의 글로 엮었을 때 가장 좋은 조합이 되는 2개를 선정하세요.
논거가 그럴싸한지가 아니라, 실제로 오늘 다룰 만한 가치가 있는지 비판적으로 심사하세요.

[후보 목록]
{listing}

응답은 아래 JSON 형식으로만 출력하세요:
{{"selected": [번호1, 번호2], "reason": "이 조합을 선택한 이유를 2~3문장으로"}}
"""


def debate_and_select_news(candidates, history, category_label):
    """반환: (선정된 topic 2개 리스트, 선정 이유) - 후보가 2개 미만이면 이유는 빈 문자열."""
    history_ids = [h['id'] for h in history]
    filtered = [c for c in candidates if c['id'] not in history_ids]
    if len(filtered) < 2:
        return filtered[:2], ""

    pool = filtered[:MAX_DEBATE_CANDIDATES]

    arguments = []
    for c in pool:
        arg = get_gemini_response(_build_news_advocate_prompt(c, category_label))
        arguments.append((c, (arg or "").strip()))

    try:
        res = get_gemini_response(_build_news_judge_prompt(arguments, category_label))
        json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip()
        data = json.loads(json_str)
        idxs = [int(i) for i in data.get("selected", [])]
        if len(idxs) >= 2 and all(0 <= i < len(arguments) for i in idxs[:2]):
            reason = data.get("reason", "")
            return [arguments[idxs[0]][0], arguments[idxs[1]][0]], reason
        raise ValueError(f"invalid selected indices: {idxs}")
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        print(f"⚠️ 토론 심사 실패({type(e).__name__}) - 후보 순서 상위 2개로 대체합니다.")
        return [c for c, _ in arguments[:2]], "심사 실패로 상위 후보 자동 선택"


def _get_catchy_korean_title(english_title, category_label):
    prompt = (
        f"다음 영문 {category_label} 뉴스 제목을 100% 한국어로 30자 이내 간결한 "
        f"블로그 소제목(H2)으로 번역해. 오직 제목 1개만 출력.\n영문: {english_title}"
    )
    res = get_gemini_response(prompt)
    return res.strip() if res else english_title


def discover_news_topics(rss_urls, category_code, category_label):
    """RSS에서 최근 소재를 모아 중복 제외 후, 토론 부서(debate_and_select_news)로
    최종 2건을 선정해 돌려준다.
    반환: (topic1, topic2, selection_reason) 또는 부족하면 None (호출부는 이번 실행을 건너뛰어야 함)"""
    history = _load_topic_history()
    candidates = _fetch_rss_candidates(rss_urls, category_code)
    selected, selection_reason = debate_and_select_news(candidates, history, category_label)
    if len(selected) < 2:
        print(f"ℹ️ [{category_label}] 다룰 만한 새 소재가 2건 미만이라 이번 실행을 건너뜁니다.")
        return None

    print(f"🗣️ [{category_label}] 토론 완료 - 선정 이유: {selection_reason or '(없음)'}")

    selected[0]['title_en'] = selected[0]['title']
    selected[1]['title_en'] = selected[1]['title']
    selected[0]['title'] = _get_catchy_korean_title(selected[0]['title'], category_label)
    selected[1]['title'] = _get_catchy_korean_title(selected[1]['title'], category_label)

    _save_topic_history(history, selected)
    return selected[0], selected[1], selection_reason


# ============================================================
# 2) 5단 분할 글쓰기 (ETF의 _generate_chained_article과 동일한 방식:
#    Part 하나씩 생성 -> 즉시 검수 -> 실패시 그 Part만 재생성 -> 확정 후 다음 Part)
# ============================================================

_READABILITY_RULES = (
    "- AI 기계어투를 피하고 사람 냄새 나는 문체로 작성하세요.\n"
    "- [가독성 절대 원칙] 글이 빽빽하고 어지럽지 않도록 문단을 2~3문장 단위로 짧게 나누세요.\n"
    "- [가독성 절대 원칙] 1-1, 1-2 같은 딱딱한 숫자 넘버링은 절대 금지합니다.\n"
    "- [가독성 절대 원칙] 대제목은 `<h3>` 태그로, 세부 소제목은 `<h4>🔸 소제목 내용</h4>` 형식 그대로 "
    "작성하세요(태그 안에 다른 속성/단어를 추가하지 마세요).\n"
    "- [가독성 절대 원칙] 대주제가 바뀔 때는 `<hr style='border:0;height:1px;background:#ddd;margin:35px 0;'>` "
    "태그로 시각적으로 분리하세요.\n"
    "- [가독성 절대 원칙] 핵심 내용은 `<div style='background:#f8f9fa;padding:15px;border-left:4px solid "
    "#1f3c88;margin:15px 0;border-radius:4px;'>` 박스로 강조하세요.\n"
    "- 결과는 반드시 HTML로 출력하세요. 표는 `<table><tr><th><td>` HTML 태그로만 작성하고 텍스트/마크다운 "
    "표는 금지합니다.\n"
    "- 상장사가 언급되면 뒤에 `<a href=\"https://kr.investing.com/search/?q=회사명\" target=\"_blank\">"
    "[📈주가확인]</a>`을 붙이세요.\n"
)


# ============================================================
# 기획 부서 - 매번 똑같은 틀로 찍어내는 것을 막기 위해, 글쓰기 전에 이번
# 소재 조합에 가장 잘 맞는 "글 형식"을 먼저 정한다.
#
# [ETF의 plan_article()과 다른 점] ETF는 "지난 글과 뭐가 다른지"(series_context,
# 같은 티커를 다시 다룰 때의 차별화)를 기준으로 기획하지만, 뉴스는 매번 소재
# 자체가 다르므로 "지난 글과 비교"가 의미가 없다. 대신 "이번 소재 조합에 어떤
# 형식이 가장 잘 맞는지"를 매번 새로 판단하게 해서, 글마다 구성 자체가
# 달라지도록 한다 - ETF로 치면 성장주 ETF와 배당 ETF가 다른 형식으로 쓰이는
# 것과 같은 효과를 뉴스 카테고리에서도 내기 위함이다.
# ============================================================

# ============================================================
# 기획 부서 (진짜 버전) - 5가지 형식 중 하나를 고르는 게 아니라, 이번 소재
# 조합만을 위한 목차를 AI가 직접 설계한다. 서로 다른 관점을 준 여러 개의
# 초안을 독립적으로 만들게 한 뒤, 편집장 역할이 그중 가장 탄탄한 걸 고르거나
# 좋은 부분들을 합쳐서 최종 목차를 확정한다 - 토론 부서(소재 선정)와 같은
# 원칙(독립생성 -> 심사)을 목차 기획에도 적용한 것.
#
# Part1(인사말+도입)과 Part5(반론/전망/FAQ/마무리)의 "역할"만 고정이고,
# 그 안에서 구체적으로 뭘 다룰지는 매번 새로 설계된다. Part2~4는 완전히 자유.
# ============================================================

NUM_OUTLINE_DRAFTS = 3

_OUTLINE_DRAFT_ANGLES = [
    "두 소재 중 더 비중 있는 쪽을 중심에 놓고, 나머지 소재는 이를 뒷받침하거나 대조하는 용도로 배치하는 구성을 설계하세요.",
    "두 소재를 계속 나란히 놓고 비교/대조하면서, 그 안에서 공통된 시사점을 끌어내는 구성을 설계하세요.",
    "독자가 가장 궁금해할 실질적인 질문(왜 중요한지, 나에게 어떤 영향이 있는지, 앞으로 어떻게 될지)에 답하는 흐름으로 구성을 설계하세요.",
]


def _build_outline_draft_prompt(topic1, topic2, category_label, selection_reason, angle_hint):
    reason_block = f"\n[토론 부서가 이 조합을 선정한 이유]\n{selection_reason}\n" if selection_reason else ""
    return f"""당신은 {category_label} 블로그의 콘텐츠 기획자입니다.
아래 두 소재로 한 편의 글을 쓰려고 합니다. 정해진 형식에 끼워맞추지 말고, 이 소재들의 실제 성격에 맞는
5단계 구성(목차)을 처음부터 직접 설계하세요.

소재1: {topic1['title']}
원문 요약: {topic1['raw'][:600]}

소재2: {topic2['title']}
원문 요약: {topic2['raw'][:600]}
{reason_block}
[이번 기획안에서 시도할 관점] {angle_hint}

[필수 제약 - 이 두 가지만 지키고 나머지는 자유]
- Part1의 역할은 인사말+도입부여야 합니다(구체적으로 뭘 도입부에서 다룰지는 자유).
- Part5의 역할은 반론/리스크, 향후 전망, FAQ, 마무리여야 합니다(구체적 내용은 자유).
- Part2~4는 완전히 자유롭게 설계하세요. 한 소재가 압도적으로 중요하면 3개 파트를 몰아줘도 되고,
  두 소재가 팽팽하면 계속 교차시켜도 됩니다.

각 파트마다 "이 파트에서 구체적으로 뭘 다룰지"(heading, 15자 내외)와 "그 안에서 실제로 서술할 내용"
(focus, 1~2문장)을 정하세요. 뻔하고 일반적인 목차(예: 그냥 "소재1 소개", "소재2 소개")가 아니라,
이 소재 조합만을 위한 구체적인 목차를 만드세요.

응답은 아래 JSON 형식으로만 출력하세요:
{{"outline": [
  {{"part": 1, "heading": "...", "focus": "..."}},
  {{"part": 2, "heading": "...", "focus": "..."}},
  {{"part": 3, "heading": "...", "focus": "..."}},
  {{"part": 4, "heading": "...", "focus": "..."}},
  {{"part": 5, "heading": "...", "focus": "..."}}
], "key_message": "이 구성으로 쓸 때 이번 글의 핵심 메시지 한 문장", "emphasis": "topic1 또는 topic2 또는 balanced"}}
"""


def _build_outline_judge_prompt(drafts, topic1, topic2, category_label):
    listing = "\n\n".join(
        f"[기획안 {i + 1}]\n"
        + "\n".join(f"  Part{p['part']}: {p['heading']} - {p['focus']}" for p in d['outline'])
        + f"\n  핵심메시지: {d.get('key_message', '')} / 비중: {d.get('emphasis', 'balanced')}"
        for i, d in enumerate(drafts)
    )
    return f"""당신은 {category_label} 블로그의 편집장입니다.
아래는 오늘 소재({topic1['title']} / {topic2['title']})를 위해 기획자들이 서로 다른 관점으로 독립적으로
제안한 {len(drafts)}개의 목차 기획안입니다. 이 중 가장 탄탄하고 독자에게 유익한 기획안 하나를 그대로
고르거나, 여러 기획안의 좋은 부분들을 조합해서 최종 목차를 확정하세요. 뻔하거나 파트 간 내용이 겹치는
기획안은 피하세요.

{listing}

응답은 아래 JSON 형식으로만 출력하세요 (기획안 번호가 아니라 최종 확정된 목차 내용을 그대로 다시 쓰세요):
{{"outline": [
  {{"part": 1, "heading": "...", "focus": "..."}},
  {{"part": 2, "heading": "...", "focus": "..."}},
  {{"part": 3, "heading": "...", "focus": "..."}},
  {{"part": 4, "heading": "...", "focus": "..."}},
  {{"part": 5, "heading": "...", "focus": "..."}}
], "key_message": "...", "emphasis": "topic1 또는 topic2 또는 balanced", "reason": "이 목차를 확정한 이유 1~2문장"}}
"""


def _parse_outline_response(res):
    json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip()
    data = json.loads(json_str)
    outline = data.get("outline")
    if not isinstance(outline, list) or len(outline) != 5:
        raise ValueError(f"outline must have exactly 5 parts, got: {outline}")
    part_nums = sorted(int(p.get("part")) for p in outline)
    if part_nums != [1, 2, 3, 4, 5]:
        raise ValueError(f"outline parts must be exactly 1..5, got {part_nums}")
    for p in outline:
        if not p.get("heading") or not p.get("focus"):
            raise ValueError("outline entries need non-empty heading and focus")
    outline.sort(key=lambda p: int(p["part"]))
    data["outline"] = outline
    return data


def _fallback_outline(topic1, topic2):
    """초안/심사가 전부 실패했을 때만 쓰는 최소한의 안전망 목차."""
    return {
        "outline": [
            {"part": 1, "heading": f"{topic1['title']} 소개", "focus": "인사말과 함께 오늘 다룰 소식을 소개"},
            {"part": 2, "heading": f"{topic1['title']} 심층분석", "focus": "배경과 파급력을 자세히 서술"},
            {"part": 3, "heading": f"{topic2['title']} 소개와 분석", "focus": "두 번째 소식을 소개하고 분석"},
            {"part": 4, "heading": "경쟁구도와 업계반응", "focus": "관련 기업/업계 동향을 비교"},
            {"part": 5, "heading": "전망과 마무리", "focus": "반론, 전망, FAQ로 마무리"},
        ],
        "key_message": "",
        "emphasis": "balanced",
        "reason": "초안/심사 실패로 기본 목차 사용",
    }


def plan_news_article(topic1, topic2, category_label, selection_reason=""):
    """목차 초안 여러 개를 독립적으로 만들고, 심사로 최종 목차를 확정한다.
    반환: {"outline": [{"part","heading","focus"} x5], "key_message", "emphasis", "reason"}"""
    drafts = []
    for angle in _OUTLINE_DRAFT_ANGLES[:NUM_OUTLINE_DRAFTS]:
        prompt = _build_outline_draft_prompt(topic1, topic2, category_label, selection_reason, angle)
        try:
            res = get_gemini_response(prompt, thinking_budget=0)
            drafts.append(_parse_outline_response(res))
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
            print(f"⚠️ 목차 초안 생성 실패({type(e).__name__}) - 이 초안은 건너뜁니다.")

    if not drafts:
        print("⚠️ 목차 초안이 전부 실패했습니다 - 기본 목차로 대체합니다.")
        return _fallback_outline(topic1, topic2)

    if len(drafts) == 1:
        drafts[0].setdefault("reason", "유일하게 성공한 초안을 그대로 사용")
        return drafts[0]

    try:
        res = get_gemini_response(_build_outline_judge_prompt(drafts, topic1, topic2, category_label), thinking_budget=24576)
        return _parse_outline_response(res)
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        print(f"⚠️ 목차 심사 실패({type(e).__name__}) - 초안 중 첫 번째를 그대로 사용합니다.")
        drafts[0].setdefault("reason", "심사 실패로 첫 번째 초안 사용")
        return drafts[0]


def _news_shared_base(today_str, category_label, topic1, topic2, chosen_style, plan):
    key_message_line = f"- [이번 글의 핵심 메시지] {plan['key_message']}\n" if plan.get('key_message') else ""
    outline_lines = "\n".join(f"  Part{p['part']}: {p['heading']} - {p['focus']}" for p in plan['outline'])
    return (
        f"당신은 {category_label} 소식을 공개 자료로 정리해 전달하는 블로그 'ondo'의 작성자입니다. "
        "전문가인 척하거나 가짜 경험담을 쓰지 마세요.\n"
        f"{_READABILITY_RULES}"
        f"- 이 글은 {today_str} 기준입니다.\n"
        f"- 다루는 두 소재: (1) {topic1['title']} (2) {topic2['title']}\n"
        f"- [이번 글 전체 목차 - 기획 부서가 이 소재 조합만을 위해 직접 설계함. 반드시 이 구성을 따르세요]\n"
        f"{outline_lines}\n"
        f"{key_message_line}"
        "- [자기소개 금지] 'ondo의 시선' 같은 자기소개 박스를 본문 중간에 스스로 만들지 마세요. "
        "작가 소개는 시스템이 별도로 삽입합니다. 실제로 존재하지 않는 블로그 글 링크를 지어내 삽입하지 "
        "마세요 - 내부 링크는 오직 지정된 파트에서 실제 확인된 URL로만 넣습니다.\n"
        "- [중복 금지] 앞선 Part에서 이미 설명한 내용(같은 소재의 같은 사실관계, 같은 문장 구조)을 "
        "이번 Part에서 다시 반복하지 마세요.\n"
        "- [목차/3줄요약/면책조항/용어정리/출처 금지] 이 요소들은 이미 처리되었거나 시스템이 자동으로 "
        "삽입하므로 어떤 Part에서도 직접 만들지 마세요.\n"
    )


def _build_news_part_prompt(shared_base, part_num, plan, topic1, topic2, extra_instruction=""):
    """기획 부서가 정한 목차(plan['outline'])의 해당 파트 지시를 그대로 프롬프트에 반영한다.
    어느 파트가 어느 소재를 다룰지는 목차가 자유롭게 정하므로, 두 소재의 원문을 항상 함께 넘긴다."""
    p = next(item for item in plan['outline'] if item['part'] == part_num)
    return f"""{shared_base}
[Part {part_num}/5 - {p['heading']}]
지금 작성할 내용: {p['focus']}
{extra_instruction}

[소재1 원문] {topic1['title']}
{topic1['raw']}

[소재2 원문] {topic2['title']}
{topic2['raw']}

[출력 지침] 아래 JSON 형식으로만 답하세요:
{{"html": "생성된 HTML", "facts": {{"companies_mentioned": ["언급된 기업명들"], "recommended_url": "이-글에-어울리는-영문-소문자-하이픈-슬러그"}}}}
"""


NEWS_PART_DESCRIPTIONS_TEMPLATE = (
    "이 글은 5개 파트를 이어붙여 만들어졌고, 이번 글의 목차는 다음과 같습니다(기획 부서가 이 소재 "
    "조합만을 위해 설계한 목차이므로 매 글마다 다릅니다):\n{outline_lines}"
)


def _news_part_descriptions(plan):
    outline_lines = "\n".join(f"- Part{p['part']}: {p['heading']} - {p['focus']}" for p in plan['outline'])
    return NEWS_PART_DESCRIPTIONS_TEMPLATE.format(outline_lines=outline_lines)


def generate_news_article(topic1, topic2, category_code, category_label, session_label=None, selection_reason=""):
    """토론(이미 완료) -> 기획(목차 초안+심사) -> 5단 분할 글쓰기(Part1~5) 순으로 진행한다.
    반환: (완성된 HTML, 태그 리스트, facts 누적 dict, plan, parts_dict) 또는 실패 시 (None, [], {}, plan, {})
    parts_dict는 {part_num: html} 형태로, 최종검수에서 특정 파트만 사후교정할 때 재사용한다."""
    today_str = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    session_key = session_label or f"{category_code}_{datetime.datetime.now().strftime('%Y%m%d')}"

    chosen_style = random.choice([
        "최근 흐름에 대한 솔직한 놀라움이나 기대감을 담은 도입부",
        "새로운 소식을 보며 느끼는 '설렘'과 호기심을 담은 긍정적인 도입부",
        "감정을 배제하고 팩트와 수치, 업계 논리에만 집중하는 냉철한 도입부",
        "친밀한 지인과 커피 한잔하며 '요즘 이런 일이 있었는데' 하고 썰을 푸는 위트 있는 말투",
    ])

    published_posts = get_wordpress_recent_posts()
    if published_posts:
        history_titles = "\n".join([f"- {p['title']}" for p in published_posts])
        link_rule = (
            "[필수 - 내부 링크] 아래 [이전 발행 글 목록] 중 가장 잘 맞는 글 1개를 골라 본문 문장 속에 "
            "자연스럽게 언급하세요. 언급할 때는 반드시 `[링크: 선택한 이전 글 제목]` 형태로 목록에 있는 "
            f"제목 그대로 정확히 적으세요.\n[이전 발행 글 목록]\n{history_titles}\n"
        )
    else:
        link_rule = "[내부 링크] 이전 발행 글이 없으므로 생략합니다.\n"

    faq_hint = {
        "bio": "특히 '이게 실제로 시중에 언제 나오나요?' 같은 독자가 가장 궁금해할 현실적인 질문을 포함하세요.",
        "patent": "특히 '이 특허가 실제 제품으로 이어지나요?' 같은 질문을 포함하세요.",
    }.get(category_code, "개수보다 독자가 실제로 궁금해할 만한 질문인지가 중요합니다.")

    # ============================================================
    # 기획 부서: 글쓰기 전에 이번 소재 조합만을 위한 목차를 확정한다.
    # ============================================================
    plan = plan_news_article(topic1, topic2, category_label, selection_reason=selection_reason)
    outline_summary = " / ".join(f"P{p['part']}:{p['heading']}" for p in plan['outline'])
    print(f"📋 [{category_label}] 기획 완료 - {outline_summary}")
    print(f"   핵심메시지: {plan.get('key_message') or '(없음)'} / 확정 이유: {plan.get('reason', '(없음)')}")

    emphasis_line = {
        "topic1": f"- [비중 지시] {topic1['title']} 쪽에 더 무게를 실어 깊이 있게 다루세요.\n",
        "topic2": f"- [비중 지시] {topic2['title']} 쪽에 더 무게를 실어 깊이 있게 다루세요.\n",
    }.get(plan.get('emphasis'), "")

    shared_base = _news_shared_base(today_str, category_label, topic1, topic2, chosen_style, plan) + emphasis_line

    # [필수 요소] 목차 내용과 무관하게 항상 강제로 들어가야 하는 것들. 자유 목차가
    # 아무리 창의적으로 짜여도 이미지/표/내부링크/FAQ/태그는 빠지면 안 되므로,
    # 특정 파트에 고정으로 붙인다.
    part_extras = {
        1: (
            f'인사말이나 자기소개 없이 [{chosen_style}]을 적용해 위 "지금 작성할 내용"으로 바로 시작하세요.'
        ),
        2: "[필수] 이 파트 어딘가에 [IMAGE_PLACEHOLDER_1]을 정확히 1번 삽입하세요.",
        3: "[필수] 이 파트에 <table> 비교표를 반드시 1개 포함하세요(수치/경쟁구도/타임라인 등 이 파트 내용에 맞는 것으로).",
        4: "[필수] 이 파트 어딘가에 [IMAGE_PLACEHOLDER_2]를 정확히 1번 삽입하세요.",
        5: (
            f"[필수] {link_rule}"
            f"[필수] FAQ: 본문에서 실제로 다룬 내용 기반으로 2~4개. {faq_hint}\n"
            "[필수] 태그: 본문 맨 마지막에 정확히 5개, 띄어쓰기로 구분해서만 작성하세요(부가 설명 금지)."
        ),
    }
    part_labels = {p['part']: f"Part{p['part']}({p['heading']})" for p in plan['outline']}

    confirmed_parts = []
    parts_dict = {}
    all_facts = {}
    for part_num in range(1, 6):
        prompt = _build_news_part_prompt(shared_base, part_num, plan, topic1, topic2, part_extras[part_num])
        part_label = part_labels[part_num]
        confirmed_text_so_far = "\n".join(confirmed_parts)
        response_text, quality_info = _generate_part_with_check(
            prompt, part_num, part_label, confirmed_text_so_far,
            session_key=session_key, label=category_code, category_label=category_label,
        )
        if not response_text:
            print(f"❌ {part_label} 생성 완전 실패 - 이번 글 작성을 중단합니다.")
            return None, [], {}, plan, {}
        extracted = _extract_facts_from_response(response_text, part_num)
        confirmed_parts.append(extracted['html'])
        parts_dict[part_num] = extracted['html']
        all_facts.update(extracted.get('facts', {}) or {})

    full_html = _assemble_news_html(parts_dict)
    tags = all_facts.get('tags', [])
    return full_html, tags, all_facts, plan, parts_dict


def _assemble_news_html(parts_dict):
    """parts_dict({part_num: html})를 순서대로 이어붙이고 공통 후처리를 적용한다.
    사후교정(targeted-fix)으로 특정 파트만 교체한 뒤 재조립할 때도 이 함수를 재사용한다."""
    full_html = "\n".join(parts_dict[i] for i in range(1, 6))
    full_html = re.sub(r"```[a-zA-Z]*\n?|```", "", full_html).strip()
    full_html = _post_process_blog_content(full_html)
    full_html, _redundant_issues = _clean_redundant_parenthetical(full_html)
    full_html = _reduce_repetition(full_html)
    return full_html


# ============================================================
# 3) 이미지 삽입 (Unsplash - ETF와 무관한 독립 기능, 원래 스크립트 그대로 유지)
# ============================================================

def _get_image_tag(keyword, used_urls, alt_text=""):
    if not UNSPLASH_ACCESS_KEY:
        return ""
    url = f"https://api.unsplash.com/search/photos?query={keyword}&per_page=5&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
    try:
        data = requests.get(url, timeout=8).json()
        if not data.get('results'):
            return ""
        img_url = ""
        for res in data['results']:
            if res['urls']['regular'] not in used_urls:
                img_url = res['urls']['regular']
                used_urls.add(img_url)
                break
        if not img_url:
            img_url = data['results'][0]['urls']['regular']
            used_urls.add(img_url)
        return f'<figure style="margin:30px 0;">\n<img src="{img_url}" alt="{alt_text}" style="width:100%;border-radius:12px;" />\n</figure>'
    except (requests.exceptions.RequestException, KeyError, ValueError):
        return ""


def inject_news_images(html_text, topic1, topic2, category_label, fallback_keywords):
    fb1, fb2 = fallback_keywords
    try:
        prompt = (
            f"주제1({topic1['title']})과 주제2({topic2['title']})에 어울리는 Unsplash 영문 검색 키워드 2개와, "
            "구글 SEO에 최적화된 구체적인 한국어 이미지 설명(alt 태그용) 2개를 추출해.\n"
            '출력 형식(JSON): {"k1": "영문키워드1", "alt1": "한국어 설명1", "k2": "영문키워드2", "alt2": "한국어 설명2"}'
        )
        res = get_gemini_response(prompt)
        json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip()
        keywords = json.loads(json_str)
        k1 = keywords.get("k1", fb1)
        alt1 = keywords.get("alt1", f"{topic1['title']} 관련 이미지")
        k2 = keywords.get("k2", fb2)
        alt2 = keywords.get("alt2", f"{topic2['title']} 관련 이미지")
    except (json.JSONDecodeError, AttributeError, TypeError):
        k1, k2 = fb1, fb2
        alt1, alt2 = f"{topic1['title']} 참고 이미지", f"{topic2['title']} 참고 이미지"

    used_urls = set()
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_1]", _get_image_tag(k1, used_urls, alt1))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_2]", _get_image_tag(k2, used_urls, alt2))
    return html_text


# ============================================================
# 4) 발행 전 컴플라이언스 고정 블록 (AI가 아니라 코드가 삽입 - ETF의
#    면책조항 처리 방식과 동일한 원칙: 법적으로 민감한 문구는 AI 자유생성에
#    맡기지 않고 고정 텍스트로 강제한다)
# ============================================================

_DISCLAIMER_BY_CATEGORY = {
    "tech": (
        "* 본 포스팅은 정보 제공을 목적으로 하며, 특정 종목에 대한 매수/매도 권유나 "
        "투자자문을 의미하지 않습니다.<br>투자의 최종 책임은 본인에게 있으며, 언급된 "
        "기업/기술의 사업 전망은 확정된 사실이 아닌 시장 전망에 기반한 서술입니다."
    ),
    "bio": (
        "* 본 포스팅은 정보 제공을 목적으로 하며, 특정 종목에 대한 매수/매도 권유나 "
        "의학적 진단·치료를 의미하지 않습니다.<br>임상시험/승인 관련 내용은 보도 시점의 "
        "예비적 정보이며, 실제 상용화까지 추가 검증 절차가 필요할 수 있습니다. 건강 관련"
        "결정은 반드시 의료 전문가와 상담하세요."
    ),
    "patent": (
        "* 본 포스팅은 정보 제공을 목적으로 하며, 특정 종목에 대한 매수/매도 권유를 "
        "의미하지 않습니다.<br>특허 출원/등록 사실이 해당 기술의 실제 상용화나 사업적 "
        "성공을 보장하지 않으며, 관련 서술은 보도 시점의 전망에 기반합니다."
    ),
}


def build_source_and_disclaimer_block(topic1, topic2, category_code):
    disclaimer = _DISCLAIMER_BY_CATEGORY.get(category_code, _DISCLAIMER_BY_CATEGORY["tech"])
    return f"""
<div style="margin-top:40px;padding:15px;background-color:#f8f9fa;border-radius:5px;font-size:0.9em;">
<strong style="color:#2c3e50;">🔗 참고 자료 (원본 출처)</strong>
<ul style="margin-top:10px;padding-left:20px;line-height:1.6;">
<li><a href="{topic1['id']}" target="_blank" style="color:#7f8c8d;text-decoration:underline;">{topic1.get('title_en', topic1['title'])}</a></li>
<li><a href="{topic2['id']}" target="_blank" style="color:#7f8c8d;text-decoration:underline;">{topic2.get('title_en', topic2['title'])}</a></li>
</ul>
</div>
<hr style="border:0;border-top:1px solid #eee;margin:30px 0;">
<p style="color:#95a5a6;font-size:0.85em;text-align:center;line-height:1.5;">
{disclaimer}<br>
<strong>Editor: ondo</strong>
</p>
"""


# ============================================================
# 5) 전체 파이프라인 오케스트레이션
# ============================================================

def run_news_pipeline(category_code, category_label, rss_urls, fallback_image_keywords,
                       min_publish_interval_hours=20):
    """tech_auto.py/bio_auto.py/patent_auto.py가 호출하는 진입점.
    발굴 -> 글쓰기(5단분할) -> 이미지삽입 -> 검수 -> 발행 -> 홍보까지 한 번에 진행한다.
    (ETF와 달리 텔레그램 승인 대기 없음 - 뉴스는 시의성 때문에 완전자동으로 진행)
    """
    print("=" * 50)
    print(f"[{category_label}] 뉴스 블로그 자동 발행 시작")
    print("=" * 50)

    can_proceed, interval_msg = _check_publish_interval(min_publish_interval_hours)
    print(interval_msg)
    if not can_proceed:
        print(f"ℹ️ [{category_label}] 발행 간격 확보를 위해 이번 실행을 건너뜁니다.")
        return

    topics = discover_news_topics(rss_urls, category_code, category_label)
    if not topics:
        return
    topic1, topic2, selection_reason = topics
    print(f"✅ [{category_label}] 소재 선정 완료: {topic1['title']} / {topic2['title']}")

    session_label = f"{category_code}_{datetime.datetime.now().strftime('%Y%m%d')}"
    html_content, tags, facts, plan, parts_dict = generate_news_article(
        topic1, topic2, category_code, category_label, session_label, selection_reason=selection_reason,
    )
    if not html_content:
        print(f"❌ [{category_label}] 글 생성 실패로 발행을 중단합니다.")
        return

    context_snippet = plan.get('key_message') or f"{topic1['title']} / {topic2['title']}"
    title_optimization = generate_optimized_title(
        f"{topic1['title']} · {topic2['title']}", "", context_snippet, category_label=category_label,
    )
    final_title = (title_optimization or {}).get("selected") or f"[{category_label} 이슈] {topic1['title']}"

    # ============================================================
    # 최종검수 -> 문제 파트만 사후교정(targeted-fix) -> 그래도 안되면 그대로 진행/중단.
    # ETF 원본의 "전체 재생성 대신 문제 파트만 먼저 교정" 로직과 동일한 원칙.
    # 사후교정은 parts_dict(이미지/면책조항 삽입 전 순수 Part1~5 텍스트) 기준으로
    # 하고, 통과/개선 확인 후에야 이미지·면책조항을 붙인다 - 그래야 이미지
    # placeholder가 사후교정 중에 유실될 걱정이 없다.
    # ============================================================
    QUALITY_FIX_THRESHOLD = 0.6
    CRITICAL_QUALITY_THRESHOLD = 0.3
    part_descriptions = _news_part_descriptions(plan)
    part_label_map = {p['part']: f"Part{p['part']}({p['heading']})" for p in plan['outline']}

    quality_info = _llm_quality_check(
        html_content, facts_json_str=None, category_label=category_label, part_descriptions=part_descriptions,
    )
    final_score = quality_info.get('quality_score') if quality_info else None
    final_issues = quality_info.get('issues', []) if quality_info else []
    problem_parts = quality_info.get('problem_parts', []) if quality_info else []

    if quality_info and final_score < QUALITY_FIX_THRESHOLD and problem_parts and len(problem_parts) <= 3:
        print(f"🔧 [{category_label}] 품질 점수({final_score:.2f})가 낮아, 전체 재생성 대신 "
              f"문제 파트({problem_parts})만 사후교정을 먼저 시도합니다...")
        fixed_parts = dict(parts_dict)
        any_fix_succeeded = False
        for part_num in problem_parts:
            original = parts_dict.get(part_num)
            if not original:
                continue
            fixed_text = _llm_targeted_fix(
                original, part_label_map.get(part_num, f"Part{part_num}"), final_issues,
                facts_json_str=None, category_label=category_label,
            )
            if fixed_text:
                fixed_parts[part_num] = fixed_text
                any_fix_succeeded = True
                print(f"   ✅ {part_label_map.get(part_num, f'Part{part_num}')} 사후교정 완료")
            else:
                print(f"   ⚠️ {part_label_map.get(part_num, f'Part{part_num}')} 사후교정 실패 - 원본 유지")

        if any_fix_succeeded:
            candidate_html = _assemble_news_html(fixed_parts)
            print(f"🔎 [{category_label}] 사후교정 결과를 재검수합니다...")
            recheck = _llm_quality_check(
                candidate_html, facts_json_str=None, category_label=category_label, part_descriptions=part_descriptions,
            )
            if recheck and recheck.get('quality_score', 0) > final_score:
                print(f"✅ [{category_label}] 사후교정으로 품질이 개선됐습니다 "
                      f"({final_score:.2f} -> {recheck['quality_score']:.2f}). 전체 재생성은 건너뜁니다.")
                parts_dict = fixed_parts
                html_content = candidate_html
                final_score = recheck['quality_score']
                final_issues = recheck.get('issues', [])
            else:
                print(f"ℹ️ [{category_label}] 사후교정으로 개선되지 않아 원본을 유지합니다.")

    html_content = inject_news_images(html_content, topic1, topic2, category_label, fallback_image_keywords)
    html_content += build_source_and_disclaimer_block(topic1, topic2, category_code)

    html_content, policy_issues = _policy_filter(html_content)
    html_content, safe_html_issues = _safe_html_filter(html_content)
    policy_issues = policy_issues + safe_html_issues
    html_content = _inject_table_of_contents(html_content)

    _print_final_quality_summary(final_score, final_issues, policy_issues)

    if final_score is not None and final_score < CRITICAL_QUALITY_THRESHOLD:
        print(f"🛑 [{category_label}] 사후교정 후에도 품질 점수({final_score:.2f})가 매우 낮아 자동 발행을 건너뜁니다.")
        return

    state = _load_state()
    if _check_duplicate(final_title, html_content, state):
        print(f"ℹ️ [{category_label}] 유사/중복 글로 판단되어 발행을 건너뜁니다.")
        return

    publish_slug = None
    raw_slug = (facts or {}).get('recommended_url') or ''
    cleaned_slug = re.sub(r'[^a-z0-9-]', '', raw_slug.strip().lower().replace(' ', '-'))
    cleaned_slug = re.sub(r'-{2,}', '-', cleaned_slug).strip('-')
    publish_slug = cleaned_slug or None

    print(f"🚀 [{category_label}] 워드프레스 발행을 시도합니다...")
    wp_success, wp_result = publish_to_wordpress(final_title, html_content, tags=tags, status="publish", slug=publish_slug)

    if not wp_success and WP_EMAIL and WP_PASSWORD:
        print(f"ℹ️ [{category_label}] API 발행 실패({wp_result}) - 이 카테고리는 Selenium 폴백을 지원하지 않습니다.")
        print("   (news_engine은 Chrome 드라이버를 띄우지 않으므로, OAuth 토큰/사이트ID를 다시 확인해주세요.)")

    if not wp_success:
        print(f"❌ [{category_label}] 발행 실패: {wp_result}")
        _telegram_send_message(f"❌ [{category_label}] 자동 발행 실패\n사유: {wp_result}")
        return

    print(f"✅ [{category_label}] 발행 성공! URL: {wp_result}")
    _register_article(
        final_title, html_content, status='published', notes='news_engine auto-publish',
        extra_data=facts, url=wp_result, state_file=_cat_path('article_state.json'),
    )
    ping_indexnow(wp_result)
    _telegram_send_message(f"✅ [{category_label}] 새 글이 자동 발행됐어요!\n{final_title}\n{wp_result}")
    print(f"🎉 [{category_label}] 파이프라인 완료.")
