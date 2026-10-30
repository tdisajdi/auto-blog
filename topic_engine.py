"""
ETF 외 분야(트렌드 / 신기술·특허 / 바이오·신약 / 에너지·자원·기후 / 인구·사회) 공용 엔진.

하루 두 번째 글(ETF 1 + 다른 분야 1)을 담당한다. 분야를 순서대로 돌리지 않고, 그날
실제로 소식이 있는 분야를 고른다(소식 강도 + 오래 안 쓴 분야 가산점 + 약간의 무작위).
마땅한 소식이 없으면 그날은 건너뛴다.

흐름:
  --discover : 분야별 발굴기 → 분야 고르기 → 텔레그램 추천(승인 버튼). pending_topic.json 저장
  (승인 확인은 etf_auto.run_check_approval이 ETF 추천과 함께 처리 → APPROVED_TOPIC:<분야>)
  --run      : 승인된 후보로 글쓰기 → 품질 검사 → 발행 또는 임시글 (BLOG_CATEGORY=<분야>로 실행)

글쓰기 핵심부(produce_article)는 ETF 기초 가이드/이슈 해설(explainer_engine.py)도 같이 쓴다.
"""
import argparse
import html
import json
import os
import random
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from blog_engine import (
    get_gemini_response, _generate_part_with_check, _extract_facts_from_response,
    _post_process_blog_content, _inject_table_of_contents, _llm_quality_check,
    _check_duplicate, _load_state, _register_article, publish_to_wordpress,
    _telegram_send_message, _load_json_file, _save_json_file, get_wordpress_recent_posts,
    _insert_operator_memo, _discover_due, _mark_discovered,
)

PENDING_TOPIC_FILE = "pending_topic.json"
CONFIRMED_TOPIC_FILE = "confirmed_topic2_context.json"
REMINDER_MAX_DAYS = 3
MIN_PICK_SCORE = 1.0          # 소식 강도+가산점 합이 이보다 낮으면 그날은 건너뜀
STALENESS_FULL_DAYS = 14      # 이 일수만큼 비면 가산점 최대
STALENESS_MAX_BONUS = 0.8

CATEGORIES = {
    "trend": {"label": "트렌드", "kind": "트렌드 해설", "repeat_days": 60, "rules": (
        "- [트렌드 원칙] 사람들이 왜 이것에 관심을 갖는지(배경, 계기, 숫자)를 중심으로 쓰세요. 특정 개인의 "
        "사생활·사건사고·정치적 주장은 다루지 마세요.\n"
        "- 마지막에 이 흐름과 연결되는 산업이나 생활 변화를 한두 문장으로 짚되, 특정 종목 매수 권유는 하지 마세요.\n")},
    "tech": {"label": "신기술·특허", "kind": "신기술 해설", "repeat_days": 45, "rules": (
        "- [기술 원칙] 기술이 무엇이고 무엇이 새로운지, 아직 확인되지 않은 것은 무엇인지 구분해 쓰세요. "
        "회사 발표를 사실처럼 단정하지 말고 '발표에 따르면'으로 출처를 밝히세요.\n"
        "- 특허를 언급할 때는 자료에 있는 출원인·번호·내용만 쓰세요.\n")},
    "bio": {"label": "바이오·신약", "kind": "바이오 소식 해설", "repeat_days": 45, "rules": (
        "- [의학 정보 원칙] 승인·임상 결과처럼 자료에 있는 사실만 쓰세요. '완치', '부작용 없음' 같은 단정, "
        "복용·치료 권유, 개인 의료 조언은 절대 금지합니다. 임상 단계(1·2·3상)와 승인 여부를 정확히 구분하세요.\n"
        "- 글 안에 '치료 결정은 반드시 의료진과 상의하세요'라는 취지의 안내를 한 번 넣으세요.\n")},
    "energy": {"label": "에너지·자원·기후", "kind": "에너지·자원 해설", "repeat_days": 21, "rules": (
        "- [자원 원칙] 가격 변화는 사실 자료의 숫자로만 쓰고, 원인은 뉴스에 나온 설명을 출처와 함께 소개하세요. "
        "앞으로의 가격을 단정해서 예측하지 마세요.\n")},
    "society": {"label": "인구·사회", "kind": "통계로 보는 사회", "repeat_days": 30, "rules": (
        "- [사회 원칙] 통계 숫자와 발표 기관을 정확히 쓰세요. 특정 정당·정책에 대한 찬반 의견은 쓰지 마세요.\n")},
}

BASE_RULES = (
    "- 글쓴이는 블로그 'ondo'입니다. 전문가인 척하지 말고, 공개 자료를 정리해 알기 쉽게 전달하는 사람의 "
    "목소리로 쓰세요. 인사말·자기소개·가짜 경험담은 금지합니다.\n"
    "- 문단은 2~3문장 단위로 짧게. 대제목은 `<h3>`, 소제목은 `<h4>🔸 소제목</h4>` 형식만 쓰세요.\n"
    "- 표는 `<table><tr><th><td>` HTML로만 작성하세요(마크다운 표 금지).\n"
    "- [숫자 원칙] [사실 자료]에 있는 숫자만 쓰세요. 자료에 없는 수치·날짜·인용을 만들어내지 마세요.\n"
    "- [출처 원칙] 뉴스는 [사실 자료]·[관련 뉴스]·[최근 뉴스]에 있는 기사만, 매체명에 `<a href=\"주소\" target=\"_blank\" rel=\"noopener\">` "
    "링크를 달아 인용하세요. '외신 보도', '전문가들은' 같은 확인할 수 없는 출처는 금지합니다.\n"
    "- [중복 금지] 앞 파트에서 쓴 사실·문장을 반복하지 마세요. 목차·3줄 요약·면책 문구·출처 목록은 "
    "시스템이 넣으므로 만들지 마세요.\n"
)

OUTLINE_ANGLES = [
    "독자가 가장 먼저 궁금해할 질문 하나에서 출발해, 자료의 사실로 답을 쌓아가는 구성",
    "흔한 오해나 단편적인 반응을 먼저 짚고, 자료로 더 정확한 그림을 보여주는 구성",
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}


# ============================================================
# 공용 도우미
# ============================================================

def google_news(query, max_results=5):
    """구글 뉴스 RSS 검색(한국어). 링크는 구글 뉴스 주소라 본문 수집은 안 되고 제목·매체만 쓴다."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        return [{"title": i.findtext("title", "").strip(), "url": i.findtext("link", "").strip(),
                 "source": i.findtext("source", "Google News").strip(), "date": i.findtext("pubDate", "").strip()}
                for i in root.findall(".//item")[:max_results]]
    except Exception as e:
        print(f"ℹ️ 뉴스 검색 실패({query}): {type(e).__name__}")
        return []


def fetch_feed(url, max_age_days=3):
    """RSS를 읽어 최근 글 목록을 돌려준다 [{title, url, summary, source}]."""
    import feedparser
    out = []
    try:
        feed = feedparser.parse(requests.get(url, headers=UA, timeout=15).content)
        cutoff = time.time() - max_age_days * 86400
        source = (feed.feed.get("title") or urllib.parse.urlparse(url).netloc).strip()
        for e in feed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and time.mktime(ts) < cutoff:
                continue
            summary = re.sub(r"<[^>]+>", " ", e.get("summary", "") or "")
            out.append({"title": e.get("title", "").strip(), "url": e.get("link", ""), "summary": re.sub(r"\s+", " ", summary)[:600],
                        "source": source})
    except Exception as e:
        print(f"ℹ️ RSS 읽기 실패({url}): {type(e).__name__}")
    return out


def scrape_text(url, limit=3000):
    try:
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        text = " ".join(p.get_text(" ", strip=True) for p in BeautifulSoup(r.text, "html.parser").find_all("p"))
        return text[:limit] if len(text) > 200 else ""
    except Exception:
        return ""


def _ask_json(prompt, thinking_budget=0):
    try:
        res = get_gemini_response(prompt, thinking_budget=thinking_budget)
        return json.loads(re.sub(r"```[a-zA-Z]*\n?|```", "", res or "").strip())
    except Exception as e:
        print(f"ℹ️ AI 판단 실패: {type(e).__name__}")
        return None


def _news_block(items):
    return "\n".join(f"- {n['title']} ({n['source']}) {n['url']}" for n in items) or "- 수집된 뉴스 없음"


def _slug(text):
    return re.sub(r"[^0-9a-z가-힣]+", "-", str(text).lower()).strip("-")[:60]


# ============================================================
# 글쓰기 핵심부 (ETF 가이드/이슈도 사용)
# ============================================================

def _parse_outline(res_obj):
    outline = (res_obj or {}).get("outline")
    if not isinstance(outline, list) or sorted(int(p.get("part")) for p in outline) != [1, 2, 3, 4, 5]:
        raise ValueError("outline must have parts 1..5")
    if any(not p.get("heading") or not p.get("focus") for p in outline):
        raise ValueError("empty heading/focus")
    outline.sort(key=lambda p: int(p["part"]))
    return {"outline": outline, "key_message": res_obj.get("key_message", "")}


def plan_outline(kind_label, title_seed, facts_text):
    base = (f"당신은 정보 블로그의 기획자입니다. 오늘 쓸 글은 [{kind_label}]이고, 주제는 '{title_seed}'입니다.\n"
            f"아래 사실 자료를 바탕으로 이 주제만을 위한 5단계 목차를 설계하세요.\n\n{facts_text}\n"
            "[제약] Part1은 독자의 질문을 던지는 도입, Part5는 자주 묻는 질문(FAQ)과 정리여야 합니다. "
            "Part2~4는 자유롭게 설계하되, 반드시 사실 자료로 쓸 수 있는 내용이어야 합니다.\n")
    fmt = ('응답은 JSON으로만: {"outline": [{"part": 1, "heading": "15자 내외", "focus": "1~2문장"}, ... part 5까지], '
           '"key_message": "핵심 메시지 한 문장"}')
    drafts = []
    for angle in OUTLINE_ANGLES:
        try:
            drafts.append(_parse_outline(_ask_json(base + f"[이번 기획 관점] {angle}\n" + fmt)))
        except (ValueError, TypeError, AttributeError):
            pass
    if not drafts:
        return {"outline": [
            {"part": 1, "heading": "왜 지금 이 이야기일까", "focus": "독자의 질문과 오늘 다룰 범위를 소개"},
            {"part": 2, "heading": "무슨 일이 있었나", "focus": "자료에 있는 사실을 정리"},
            {"part": 3, "heading": "숫자로 보기", "focus": "자료의 숫자를 표로 정리"},
            {"part": 4, "heading": "아직 모르는 것", "focus": "확인되지 않은 점과 주의할 점"},
            {"part": 5, "heading": "자주 묻는 질문", "focus": "FAQ와 정리"},
        ], "key_message": ""}
    if len(drafts) == 1:
        return drafts[0]
    listing = "\n\n".join(f"[기획안 {i + 1}]\n" + "\n".join(f"  Part{p['part']}: {p['heading']} - {p['focus']}" for p in d["outline"])
                          for i, d in enumerate(drafts))
    try:
        return _parse_outline(_ask_json(
            f"당신은 편집장입니다. 주제 '{title_seed}'에 대한 기획안들입니다. 독자에게 가장 유익하고 파트끼리 "
            f"겹치지 않는 최종 목차를 확정하세요(조합 가능).\n\n{listing}\n\n" + fmt, thinking_budget=24576))
    except (ValueError, TypeError, AttributeError):
        return drafts[0]


def _write_parts(kind_label, title_seed, plan, facts_text, rules, session_key, category_label):
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    outline_lines = "\n".join(f"  Part{p['part']}: {p['heading']} - {p['focus']}" for p in plan["outline"])
    posts = get_wordpress_recent_posts() or []
    link_rule = ("[내부 링크] 아래 글 중 주제와 맞는 것이 있으면 1개를 골라 `<a href=\"주소\">제목</a>`로 자연스럽게 "
                 "소개하세요. 맞는 글이 없으면 생략하세요.\n"
                 + "\n".join(f"- {p['title']} ({p.get('link', '')})" for p in posts[:15])) if posts else ""
    shared = (f"[{kind_label}] 주제: {title_seed}\n이 글은 {today_str} 기준입니다.\n{BASE_RULES}{rules}"
              f"[전체 목차 - 반드시 따르세요]\n{outline_lines}\n"
              + (f"[핵심 메시지] {plan['key_message']}\n" if plan.get("key_message") else "")
              + f"\n{facts_text}\n")
    extras = {
        1: "<h1>로 제목을 쓰세요. 검색하는 사람이 이해하기 쉬운 문장으로 다듬고, 제목 뒤에 120~160자 메타 설명을 "
           "HTML 주석(<!-- -->)으로 넣으세요.",
        3: "[필수] 자료의 숫자나 사실을 정리한 <table>을 1개 넣으세요.",
        5: f"{link_rule}\n[필수] FAQ 3~4개. [필수] 맨 마지막 줄에 '태그: 태그1 태그2 태그3 태그4 태그5' 형식으로 정확히 5개.",
    }
    parts, confirmed = {}, []
    for n in range(1, 6):
        p = plan["outline"][n - 1]
        prompt = (f"{shared}\n[Part {n}/5 - {p['heading']}]\n지금 작성할 내용: {p['focus']}\n{extras.get(n, '')}\n\n"
                  '[출력] JSON으로만: {"html": "생성된 HTML", "facts": {"recommended_url": "영문-소문자-하이픈-슬러그"}}')
        text, _info = _generate_part_with_check(prompt, n, f"Part{n}({p['heading']})", "\n".join(confirmed),
                                                session_key=session_key, label=session_key.split("_")[0],
                                                category_label=category_label)
        if not text:
            return None
        ex = _extract_facts_from_response(text, n)
        parts[n] = ex["html"]
        confirmed.append(ex["html"])
        if n == 1:
            parts["_slug"] = (ex.get("facts") or {}).get("recommended_url", "")
    return parts


def _assemble(parts):
    body = re.sub(r"```[a-zA-Z]*\n?|```", "", "\n".join(parts[i] for i in range(1, 6))).strip()
    tags = []
    m = re.search(r"태그:\s*([^\n<]+)", body)
    if m:
        tags = [re.sub(r"[#,.]", "", t).strip() for t in m.group(1).split() if t.strip()][:5]
        body = body[:m.start()] + body[m.end():]
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)  # 제목은 워드프레스 제목 칸으로
    body = _inject_table_of_contents(_post_process_blog_content(body))
    return title, body, tags


def closing_block(source_note, news, extra_note=""):
    esc = html.escape
    items = "".join(f'<li><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["source"])}</a> - {esc(n["title"])}</li>'
                    for n in news if n.get("url"))
    return (
        '<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-radius:6px;font-size:13px;line-height:1.7;">'
        f"<strong>📌 자료 출처</strong><br/>{source_note}"
        + (f'<ul style="margin:8px 0 0 18px;">{items}</ul>' if items else "") + "</div>"
        '<p style="margin-top:20px;font-size:12px;color:#888;line-height:1.7;">'
        "이 글은 공개 자료를 정리한 정보 제공용 글이며, 특정 상품의 매수·매도나 의료적 판단을 권유하지 않습니다."
        f"{extra_note}</p>"
    )


def produce_article(*, kind_label, title_seed, facts_text, rules, category_label, article_type, topic_id,
                    memo="", closing_html="", meta=None):
    """목차 기획 → 5파트 → 조립 → 중복 검사 → 품질 검사 → 발행/임시글 → 기록 → 텔레그램.
    반환: (상태 "publish"/"draft"/"failed", 제목, 주소)"""
    print(f"📋 [{kind_label}] {title_seed} - 기획 중...")
    plan = plan_outline(kind_label, title_seed, facts_text)
    print("   목차: " + " / ".join(p["heading"] for p in plan["outline"]))
    session_key = f"{article_type}_{_slug(topic_id)}_{datetime.now().strftime('%Y%m%d')}"
    parts = _write_parts(kind_label, title_seed, plan, facts_text, rules, session_key, category_label)
    if not parts:
        _telegram_send_message(f"⚠️ [{kind_label}] '{title_seed}' 글 생성에 실패했어요. 다음 추천을 기다려주세요.")
        return "failed", title_seed, ""
    title, body, tags = _assemble(parts)
    title = title or title_seed
    if memo:
        body = _insert_operator_memo(body, memo)
    body += closing_html

    if _check_duplicate(title, body, _load_state()):
        _telegram_send_message(f"⚠️ 발행 중단: '{title}'이(가) 이미 올린 글과 너무 비슷해서 올리지 않았어요.")
        return "failed", title, ""

    review = _llm_quality_check(body, facts_json_str=facts_text, category_label=category_label,
                                part_descriptions="\n".join(f"- Part{p['part']}: {p['heading']} - {p['focus']}" for p in plan["outline"]))
    score = review.get("quality_score") if review else None
    issues = (review or {}).get("issues", [])
    min_q = float(os.environ.get("PUBLISH_MIN_QUALITY", "0.7"))
    status = "publish" if (score is not None and score >= min_q) else "draft"
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "", str(parts.get("_slug", "")).lower().replace(" ", "-"))).strip("-") or None
    ok, result = publish_to_wordpress(title, body, tags=tags, status=status, slug=slug)
    score_text = "검수 실패" if score is None else f"{score:.2f}"
    if not ok:
        _telegram_send_message(f"⚠️ [{kind_label}] '{title}' 업로드 실패: {str(result)[:200]}")
        return "failed", title, ""

    meta = dict(meta or {})
    meta.update({"article_type": article_type, "topic_id": topic_id})
    _register_article(title, body, status="published" if status == "publish" else "draft",
                      notes=f"{article_type} ({score_text})", version=1, extra_data={"_meta": meta}, url=result)
    if status == "publish":
        _telegram_send_message(f"✅ [{kind_label}] 발행 완료\n{title}\n{result}\n품질 점수: {score_text}")
    else:
        issues_text = "\n".join(f"- {i}" for i in issues[:6]) or "- (지적 내용 없음)"
        _telegram_send_message(f"📝 [{kind_label}] 임시글로만 올렸어요 (공개 안 됨)\n제목: {title}\n"
                               f"품질 점수: {score_text} (기준 {min_q})\n지적된 문제:\n{issues_text}")
    return status, title, result


# ============================================================
# 분야별 발굴기 - 후보: {category, topic_key, title_seed, facts_text, news, score, reason, source_note}
# ============================================================

_TREND_EXCLUDE_HINT = "사람 이름(연예인·정치인·운동선수 포함), 사건사고·범죄·재난·사망, 정치·선거, 스포츠 경기 결과, 특정 방송 회차"


def discover_trend():
    import trend_engine
    words = trend_engine.get_trending_searches("KR")[:40]
    if not words:
        return []
    picks = (_ask_json(
        "아래는 오늘 한국의 구글 급상승 검색어입니다. 블로그 '트렌드' 글로 쓸 만한 것만 최대 3개 고르세요.\n"
        f"[제외] {_TREND_EXCLUDE_HINT}\n"
        "[좋은 예] 생활·소비·음식·여행·건강 습관·신기술 제품·문화 현상처럼 '왜 사람들이 관심을 갖는지' 설명할 수 있는 주제\n"
        f"검색어: {', '.join(words)}\n"
        'JSON으로만: {"picks": [{"keyword": "검색어 그대로", "why": "쓸 만한 이유 한 문장"}]} (없으면 빈 배열)') or {}).get("picks", [])
    out = []
    for p in picks[:3]:
        kw = str(p.get("keyword", "")).strip()
        if not kw or kw not in words:
            continue
        interest = trend_engine.get_interest([kw], geo="KR", timeframe="today 3-m").get(kw)
        news = google_news(kw, 6)
        if len(news) < 3:
            continue
        momentum = interest["momentum_pct"] if interest else 0
        facts = (f"[사실 자료]\n- 구글 급상승 검색어(한국, {datetime.now():%Y-%m-%d})에 '{kw}'가 올랐습니다.\n"
                 + (f"- 구글 검색 관심도: 최근 7일 평균이 3개월 평균 대비 {momentum:+.1f}% (최근값 {interest['latest']}, 0~100 상대지수)\n" if interest else "")
                 + f"[관련 뉴스 - 제목만 확인됨, 제목에 없는 내용은 단정하지 마세요]\n{_news_block(news)}\n")
        out.append({"category": "trend", "topic_key": f"trend:{_slug(kw)}", "title_seed": f"요즘 '{kw}'에 관심이 몰리는 이유",
                    "facts_text": facts, "news": news, "score": 1.0 + min(max(momentum, 0) / 100, 1.0),
                    "reason": f"구글 급상승 검색어 '{kw}' - {p.get('why', '')}", "source_note": "구글 트렌드, 구글 뉴스"})
    return out


_TECH_FEEDS = ["https://www.technologyreview.com/feed/", "https://spectrum.ieee.org/feeds/feed.rss",
               "https://feeds.arstechnica.com/arstechnica/technology-lab", "https://techcrunch.com/feed/"]


def discover_tech():
    items = [i for f in _TECH_FEEDS for i in fetch_feed(f, 3)][:40]
    if not items:
        return []
    listing = "\n".join(f"{i}. [{it['source']}] {it['title']}" for i, it in enumerate(items))
    pick = _ask_json(
        "아래 기술 기사 중 '신기술·특허' 블로그 글로 가장 좋은 1개를 고르세요. 신제품 할인·리뷰·인사 소식보다 "
        "AI·로봇·우주·반도체·에너지 기술·바이오 기술·특허처럼 의미가 오래가는 기술 변화를 우선하세요.\n"
        f"{listing}\n"
        'JSON으로만: {"index": 번호, "title_ko": "한국어 주제 한 줄", "keywords_ko": "한국어 뉴스 검색어", "why": "이유 한 문장"}') or {}
    try:
        idx = int(pick.get("index"))
        it = items[idx] if idx >= 0 else None
    except (TypeError, ValueError, IndexError):
        it = None
    if not it:
        return []
    body = scrape_text(it["url"]) or it["summary"]
    news = [{"title": it["title"], "url": it["url"], "source": it["source"]}] + google_news(pick.get("keywords_ko") or it["title"], 4)
    facts = (f"[사실 자료 - 원문 기사]\n제목: {it['title']} ({it['source']}, {it['url']})\n본문 발췌: {body}\n\n"
             f"[관련 뉴스]\n{_news_block(news[1:])}\n")
    return [{"category": "tech", "topic_key": f"tech:{_slug(it['title'])}", "title_seed": pick.get("title_ko") or it["title"],
             "facts_text": facts, "news": news, "score": 1.0, "reason": pick.get("why", ""), "source_note": it["source"]}]


_BIO_FEEDS = ["https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
              "https://www.fiercebiotech.com/rss/xml", "https://www.biopharmadive.com/feeds/news/"]


def discover_bio():
    items = [i for f in _BIO_FEEDS for i in fetch_feed(f, 3)]
    if not items:
        return []

    def strength(it):
        t = (it["title"] + " " + it["summary"]).lower()
        if "fda" in t and re.search(r"approv|clear", t):
            return 2.0
        if re.search(r"phase 3|phase iii|topline|pivotal", t):
            return 1.5
        return 1.0
    items.sort(key=strength, reverse=True)
    listing = "\n".join(f"{i}. [{it['source']}] {it['title']}" for i, it in enumerate(items[:25]))
    pick = _ask_json(
        "아래 바이오 소식 중 일반 독자에게 의미 있는 1개를 고르세요. 신약 승인, 주요 임상 결과처럼 사실이 분명한 "
        "소식을 우선하고, 인사·투자유치·소송 소식은 피하세요.\n"
        f"{listing}\n"
        'JSON으로만: {"index": 번호, "title_ko": "한국어 주제 한 줄", "keywords_ko": "한국어 뉴스 검색어", "why": "이유 한 문장"}') or {}
    try:
        idx = int(pick.get("index"))
        it = items[:25][idx] if idx >= 0 else None
    except (TypeError, ValueError, IndexError):
        it = None
    if not it:
        return []
    body = scrape_text(it["url"]) or it["summary"]
    news = [{"title": it["title"], "url": it["url"], "source": it["source"]}] + google_news(pick.get("keywords_ko") or it["title"], 4)
    facts = (f"[사실 자료 - 원문]\n제목: {it['title']} ({it['source']}, {it['url']})\n본문 발췌: {body}\n\n"
             f"[관련 뉴스]\n{_news_block(news[1:])}\n")
    return [{"category": "bio", "topic_key": f"bio:{_slug(it['title'])}", "title_seed": pick.get("title_ko") or it["title"],
             "facts_text": facts, "news": news, "score": strength(it), "reason": pick.get("why", ""), "source_note": it["source"]}]


_COMMODITIES = {"CL=F": "WTI 원유", "BZ=F": "브렌트유", "NG=F": "천연가스", "HG=F": "구리",
                "KC=F": "커피", "CC=F": "코코아", "ZW=F": "밀", "ZC=F": "옥수수", "SB=F": "설탕"}


def _eia_crude_inventory():
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        return ""
    try:
        r = requests.get("https://api.eia.gov/v2/petroleum/stoc/wstk/data/", timeout=20, params={
            "api_key": key, "frequency": "weekly", "data[0]": "value", "facets[series][]": "WCESTUS1",
            "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 5})
        rows = r.json().get("response", {}).get("data", [])
        if rows:
            return "- 미국 상업용 원유 재고(EIA, 천 배럴): " + ", ".join(f"{x['period']} {x['value']}" for x in rows) + "\n"
    except Exception as e:
        print(f"ℹ️ EIA 조회 실패: {type(e).__name__}")
    return ""


def discover_energy():
    import yfinance as yf
    rows = []
    for t, name in _COMMODITIES.items():
        try:
            h = yf.Ticker(t).history(period="1y")["Close"].dropna()
            if len(h) < 30:
                continue
            last = float(h.iloc[-1])
            rows.append({"ticker": t, "name": name, "last": last,
                         "d1": (last / float(h.iloc[-2]) - 1) * 100, "m1": (last / float(h.iloc[-22]) - 1) * 100,
                         "y1": (last / float(h.iloc[0]) - 1) * 100})
        except Exception:
            continue
    if not rows:
        return []
    best = max(rows, key=lambda x: abs(x["m1"]) / 10 + abs(x["d1"]) / 3)
    strength = abs(best["m1"]) / 10 + abs(best["d1"]) / 3
    if strength < 0.6:
        return []
    table = "\n".join(f"- {x['name']}({x['ticker']}): 최근가 {x['last']:,.2f}, 하루 {x['d1']:+.1f}%, 한 달 {x['m1']:+.1f}%, 1년 {x['y1']:+.1f}%"
                      for x in rows)
    news = google_news(f"{best['name']} 가격", 6)
    # 한 달 변화가 작고 하루 변화가 큰 경우(급등락)는 하루 기준으로 제목을 단다.
    if abs(best["m1"]) >= 3:
        move = f"한 달 새 {abs(best['m1']):.0f}% {'오른' if best['m1'] > 0 else '내린'}"
    else:
        move = f"하루 만에 {abs(best['d1']):.1f}% {'뛴' if best['d1'] > 0 else '떨어진'}"
    facts = (f"[사실 자료 - 원자재 선물 가격, 야후 파이낸스 {datetime.now():%Y-%m-%d} 기준]\n{table}\n"
             f"{_eia_crude_inventory() if best['ticker'] in ('CL=F', 'BZ=F') else ''}\n[관련 뉴스]\n{_news_block(news)}\n")
    return [{"category": "energy", "topic_key": f"energy:{best['ticker']}", "news": news,
             "title_seed": f"{best['name']} 가격이 {move} 이유와 생활에 미치는 영향",
             "facts_text": facts, "score": 1.0 + min(strength - 0.6, 1.0),
             "reason": f"{best['name']} 한 달 {best['m1']:+.1f}%, 하루 {best['d1']:+.1f}%",
             "source_note": "원자재 가격: Yahoo Finance" + (", 원유 재고: 미국 에너지정보청(EIA)" if os.environ.get("EIA_API_KEY") else "")}]


def discover_society():
    news = []
    for q in ["통계청 발표 인구", "국가데이터처 발표", "출생아 수 통계", "1인 가구 통계", "고령인구 비율 통계"]:
        news += google_news(q + " when:3d", 4)
    seen, uniq = set(), []
    for n in news:
        if n["title"] not in seen:
            seen.add(n["title"])
            uniq.append(n)
    if len(uniq) < 3:
        return []
    listing = "\n".join(f"{i}. {n['title']} ({n['source']})" for i, n in enumerate(uniq[:25]))
    pick = _ask_json(
        "아래 뉴스 중 '통계로 보는 사회' 글로 쓸 만한 공식 통계 발표 1개를 고르세요(인구·가구·출생·고령화·이주 등). "
        "정치적 논쟁이나 정책 찬반 기사, 여론조사는 피하세요. 마땅한 게 없으면 index를 -1로.\n"
        f"{listing}\n"
        'JSON으로만: {"index": 번호, "title_ko": "주제 한 줄", "keywords_ko": "같은 통계를 찾을 검색어", "why": "이유 한 문장"}') or {}
    try:
        idx = int(pick.get("index"))
        it = uniq[:25][idx] if idx >= 0 else None
    except (TypeError, ValueError, IndexError):
        it = None
    if not it:
        return []
    related = google_news(pick.get("keywords_ko") or it["title"], 6)
    facts = (f"[사실 자료 - 관련 뉴스, 제목만 확인됨. 숫자는 제목에 나온 것만 쓰세요]\n{_news_block([it] + related)}\n")
    return [{"category": "society", "topic_key": f"society:{_slug(pick.get('keywords_ko') or it['title'])}",
             "title_seed": pick.get("title_ko") or it["title"], "facts_text": facts, "news": [it] + related,
             "score": 1.1, "reason": pick.get("why", ""), "source_note": "통계 발표 관련 보도(구글 뉴스)"}]


ADAPTERS = {"trend": discover_trend, "tech": discover_tech, "bio": discover_bio,
            "energy": discover_energy, "society": discover_society}


# ============================================================
# 분야 고르기 + 아침 추천
# ============================================================

def _category_history(code):
    """그 분야 기록 파일에서 (마지막 글 날짜, 최근 topic_key 집합)."""
    path = f"{code}_article_state.json"
    state = _load_json_file(path, {"articles": []}) or {"articles": []}
    last, keys = None, {}
    for a in state.get("articles", []):
        try:
            dt = datetime.fromisoformat(a.get("timestamp", ""))
        except (ValueError, TypeError):
            continue
        last = dt if last is None or dt > last else last
        k = ((a.get("topic_data") or {}).get("_meta") or {}).get("topic_key")
        if k:
            keys[k] = max(keys.get(k, dt), dt)
    return last, keys


def choose_topic():
    now = datetime.now()
    scored = []
    for code, fn in ADAPTERS.items():
        try:
            cands = fn()
        except Exception as e:
            print(f"⚠️ [{code}] 발굴 실패(이 분야는 오늘 건너뜀): {type(e).__name__}: {e}")
            continue
        last, keys = _category_history(code)
        repeat_days = CATEGORIES[code]["repeat_days"]
        cands = [c for c in cands if c["topic_key"] not in keys or (now - keys[c["topic_key"]]).days >= repeat_days]
        if not cands:
            print(f"ℹ️ [{code}] 오늘 쓸 만한 새 소식 없음")
            continue
        best = max(cands, key=lambda c: c["score"])
        days_idle = (now - last).days if last else STALENESS_FULL_DAYS
        bonus = STALENESS_MAX_BONUS * min(days_idle, STALENESS_FULL_DAYS) / STALENESS_FULL_DAYS
        total = best["score"] + bonus + random.uniform(0, 0.3)
        print(f"   [{code}] 후보: {best['title_seed']} | 소식 {best['score']:.2f} + 공백 {bonus:.2f} → {total:.2f}")
        scored.append((total, best))
    if not scored:
        return None
    total, best = max(scored, key=lambda x: x[0])
    if total < MIN_PICK_SCORE:
        print(f"ℹ️ 가장 높은 후보도 기준({MIN_PICK_SCORE}) 미만이라 오늘은 건너뜁니다.")
        return None
    return best


def topic_label(c):
    return f"{CATEGORIES[c['category']]['label']} - {c['title_seed']}"


def run_discover_and_notify():
    pending = _load_json_file(PENDING_TOPIC_FILE, None)
    if pending:
        age = (datetime.now() - datetime.fromisoformat(pending["created_at"])).days
        if age < REMINDER_MAX_DAYS:
            msg_id = _telegram_send_message(
                f"⏰ 아직 승인 안 하신 두 번째 글 추천이 있어요 ({age}일째)\n\n주제: {topic_label(pending)}\n이유: {pending['reason']}\n\n"
                "• 승인: [✅ 승인] 버튼\n• 메모(선택): 이 메시지에 답장으로 '메모: 내용'",
                with_approve_button="approve_topic")
            pending["message_id"], pending["sent_at"] = msg_id, datetime.now().isoformat()
            _save_json_file(PENDING_TOPIC_FILE, pending)
            return
        os.remove(PENDING_TOPIC_FILE)

    print("🔎 ETF 외 분야 발굴 중...")
    best = choose_topic()
    if not best:
        print("ℹ️ 오늘은 두 번째 글을 쉬어갑니다.")
        return
    msg_id = _telegram_send_message(
        f"📌 오늘의 두 번째 글 추천\n\n분야: {CATEGORIES[best['category']]['label']}\n주제: {best['title_seed']}\n"
        f"이유: {best['reason']}\n\n• 승인: [✅ 승인] 버튼\n• 메모(선택): 이 메시지에 답장으로 '메모: 내용'\n"
        f"({REMINDER_MAX_DAYS}일간 리마인드되고, 응답 없으면 새로 추천해드려요)",
        with_approve_button="approve_topic")
    if not msg_id:
        # 못 보낸 추천을 저장하면 다음 날 '아직 승인 안 하신…'으로 엉뚱하게 리마인드되므로 버린다.
        print("❌ 텔레그램 전송에 실패해 추천을 저장하지 않았습니다. TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 확인하세요.")
        return
    best.update({"created_at": datetime.now().isoformat(), "sent_at": datetime.now().isoformat(), "message_id": msg_id})
    _save_json_file(PENDING_TOPIC_FILE, best)
    print(f"✅ 두 번째 글 추천을 보냈습니다: {topic_label(best)}")


# ============================================================
# 발행 (승인 후, BLOG_CATEGORY=<분야>로 실행)
# ============================================================

def run_confirmed():
    ctx = _load_json_file(CONFIRMED_TOPIC_FILE, None)
    if not ctx:
        print("ℹ️ 승인된 두 번째 글이 없습니다.")
        return
    os.remove(CONFIRMED_TOPIC_FILE)
    cfg = CATEGORIES[ctx["category"]]
    produce_article(
        kind_label=cfg["kind"], title_seed=ctx["title_seed"], facts_text=ctx["facts_text"], rules=cfg["rules"],
        category_label=cfg["label"], article_type=ctx["category"], topic_id=ctx["topic_key"],
        memo=(ctx.get("memo") or "").strip(),
        closing_html=closing_block(ctx.get("source_note", ""), ctx.get("news", []),
                                   "<br/>건강·치료에 관한 결정은 반드시 의료진과 상의하세요." if ctx["category"] == "bio" else ""),
        meta={"topic_key": ctx["topic_key"]},
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--if-due", action="store_true", help="오늘 추천을 아직 안 보냈고 12:07(KST)이 지났을 때만")
    args = ap.parse_args()
    if args.discover:
        if args.if_due and not _discover_due("topic", 12, 7):
            print("ℹ️ 오늘 두 번째 글 추천은 이미 보냈거나 아직 시간이 안 됐습니다.")
        else:
            _mark_discovered("topic")
            run_discover_and_notify()
    elif args.run:
        run_confirmed()
