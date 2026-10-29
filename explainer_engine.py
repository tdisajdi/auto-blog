"""
기초 가이드 / 이슈 해설 글 엔진.

ETF 분석 글(etf_auto.py의 5단 고정 구조)과 달리, 개념 설명(가이드)과 시장 사건
해설(이슈)은 주인공이 "종목"이 아니라 "질문"이다. 그래서 뉴스 엔진처럼 목차를
매번 기획 단계에서 새로 설계한 뒤 5개 파트로 나눠 쓴다.

일반론 글이 되지 않도록, 모든 주제에 예시 ETF의 실제 데이터(수익률, 보수, 배당,
최대 낙폭 등)와 세법 상수(etf_auto.TAX_*)를 사실 자료로 붙이고, AI는 그 안의
숫자만 쓰게 한다.

진입점: run_explainer(topic) - topic은 "GUIDE:<id>" 또는 "ISSUE:<id>".
"""
import os
import re
from datetime import datetime

from blog_engine import _load_state, _load_json_file

# 실행 중인 etf_auto 모듈. `python etf_auto.py`로 실행하면 그 모듈 이름이 __main__이라
# 여기서 import etf_auto를 하면 같은 코드가 한 벌 더 올라가므로, run_explainer가 넘겨받는다.
ea = None

GUIDE_REPEAT_DAYS = 180
ISSUE_REPEAT_DAYS = 30

GUIDE_TOPICS = [
    {"id": "overseas-vs-domestic-tax", "title": "해외 상장 ETF vs 국내 상장 ETF, 세금까지 따지면 뭐가 유리할까",
     "tickers": ["SPY", "360750.KS"], "tax": True},
    {"id": "expense-ratio", "title": "ETF 총보수 0.1% 차이, 10년 뒤 얼마가 될까",
     "tickers": ["SPY", "VOO", "360750.KS"]},
    {"id": "covered-call-structure", "title": "커버드콜 ETF의 높은 분배금은 어디서 나오고, 무엇을 포기할까",
     "tickers": ["JEPI", "QYLD", "QQQ"]},
    {"id": "hedged-vs-unhedged", "title": "환헤지(H) ETF와 환노출 ETF, 같은 자산인데 수익률이 다른 이유",
     "tickers": ["GLD", "132030.KS"]},
    {"id": "tr-vs-pr", "title": "이름 끝의 'TR', 배당을 재투자하는 ETF는 정말 유리할까",
     "tickers": ["069500.KS", "278530.KS"], "tax": True},
    {"id": "dca-vs-lump", "title": "적립식 vs 거치식, 실제 가격으로 돌려보면 무엇이 달랐을까",
     "tickers": ["SPY", "QQQ"]},
    {"id": "mdd-risk", "title": "최대 낙폭(MDD)으로 내가 버틸 수 있는 ETF 고르기",
     "tickers": ["QQQ", "SCHD", "TLT"]},
    {"id": "tax-accounts", "title": "ISA·연금저축·IRP로 ETF 살 때 꼭 알아야 할 차이",
     "tickers": ["360750.KS", "SPY"], "tax": True},
    {"id": "dividend-growth", "title": "배당 ETF, 배당률보다 배당성장률을 먼저 봐야 하는 이유",
     "tickers": ["SCHD", "VYM", "DGRO"]},
    {"id": "bond-duration", "title": "채권 ETF는 왜 금리가 오르면 떨어질까: 만기와 듀레이션 기초",
     "tickers": ["TLT", "IEF", "SHY"]},
    {"id": "leverage-decay", "title": "3배 레버리지 ETF를 오래 들고 있으면 생기는 일",
     "tickers": ["QQQ", "TQQQ"]},
    {"id": "parking-etf", "title": "CD금리·머니마켓 파킹형 ETF, 예금 대신 써도 될까",
     "tickers": ["459580.KS", "488770.KS"], "tax": True},
]

ISSUE_KINDS = {
    "fx": {"label": "환율", "query": "원/달러 환율",
           "title_hint": "환율이 움직일 때 해외 ETF 투자자가 확인할 것",
           "tickers": ["SPY", "360750.KS", "GLD", "132030.KS"]},
    "rates": {"label": "금리", "query": "미국 10년물 국채 금리",
              "title_hint": "금리 변화가 채권 ETF와 성장주 ETF에 주는 영향",
              "tickers": ["TLT", "IEF", "SHY", "QQQ"]},
    "sentiment": {"label": "투자심리", "query": "미국 증시 공포 탐욕 지수",
                  "title_hint": "시장 심리가 한쪽으로 쏠릴 때 ETF 투자자가 볼 것",
                  "tickers": ["SPY", "QQQ", "SCHD", "TLT"]},
}

# 공통 글쓰기 규칙은 topic_engine.BASE_RULES에 있고, 여기에는 ETF 글 전용 규칙만 둔다.
_SECTION_RULES = (
    "- [계좌 원칙] 해외(미국 등) 상장 ETF는 ISA·연금저축·IRP로 직접 살 수 없습니다. 이 계좌를 언급할 때는 "
    "같은 지수의 국내 상장 ETF로만 설명하세요.\n"
    "- [투자 권유 금지] '지금 사세요', '확실한 수익' 같은 표현은 금지. 판단 기준을 알려주는 글로 쓰세요.\n"
)


# ------------------------------------------------------------
# 주제 고르기 (아침 추천 단계에서 etf_auto가 호출)
# ------------------------------------------------------------

def _explainer_history():
    """발행 기록에서 가이드/이슈 글의 (종류, id) → 마지막 날짜."""
    history = {}
    for a in _load_state().get('articles', []):
        meta = (a.get('topic_data') or {}).get('_meta') or {}
        kind, topic_id = meta.get('article_type'), meta.get('topic_id')
        if kind not in ("guide", "issue") or not topic_id:
            continue
        try:
            dt = datetime.fromisoformat(a.get('timestamp', ''))
        except (ValueError, TypeError):
            continue
        key = (kind, topic_id)
        if key not in history or dt > history[key]:
            history[key] = dt
    return history


def pick_guide_topic():
    history = _explainer_history()
    now = datetime.now()
    for t in GUIDE_TOPICS:
        dt = history.get(("guide", t["id"]))
        if dt is None or (now - dt).days >= GUIDE_REPEAT_DAYS:
            return t
    return None


def pick_issue_kind(macro_data):
    """최근 30일 안에 안 다룬 이슈 중, 오늘 수치가 가장 눈에 띄는 것을 고른다."""
    history = _explainer_history()
    now = datetime.now()
    available = [k for k in ISSUE_KINDS
                 if history.get(("issue", k)) is None or (now - history[("issue", k)]).days >= ISSUE_REPEAT_DAYS]
    if not available:
        return None, ""
    scores = {k: 0.0 for k in available}
    reasons = {k: "" for k in available}
    if "fx" in scores and macro_data.get("is_fx_volatile"):
        scores["fx"] += 2 + abs(float(macro_data.get("usd_krw_diff_pct") or 0))
        reasons["fx"] = f"원/달러 환율이 전일 대비 {macro_data.get('usd_krw_diff_pct')}% {macro_data.get('usd_krw_direction', '')} ({macro_data.get('usd_krw')})"
    tnx = float(macro_data.get("tnx_val") or 0)
    if "rates" in scores and (tnx >= 4.5 or 0 < tnx <= 3.5):
        scores["rates"] += 1.5
        reasons["rates"] = f"미국 10년물 금리 {macro_data.get('us_10y')}"
    fg = re.search(r"\d+", str(macro_data.get("fear_greed", "")))
    if "sentiment" in scores and fg and (int(fg.group()) <= 25 or int(fg.group()) >= 75):
        scores["sentiment"] += 1.5
        reasons["sentiment"] = f"공포/탐욕 지수 {macro_data.get('fear_greed')}"
    trending_words = {
        "fx": ("환율", "달러", "원화", "엔화"),
        "rates": ("금리", "국채", "연준", "FOMC", "파월", "한국은행", "기준금리"),
        "sentiment": ("코스피", "나스닥", "증시", "주가", "폭락", "급락", "급등", "S&P"),
    }
    try:
        import trend_engine
        trending = trend_engine.get_trending_searches("KR")
    except Exception:
        trending = []
    for k in available:
        hits = [t for t in trending if any(w.lower() in t.lower() for w in trending_words[k])]
        if hits:
            scores[k] += 1.0
            reasons[k] = (reasons[k] + " / " if reasons[k] else "") + f"구글 급상승 검색어: {', '.join(hits[:3])}"
    best = max(available, key=lambda k: scores[k])
    if scores[best] <= 0:
        return None, ""
    return best, reasons[best]


def topic_label(topic):
    kind, _, topic_id = topic.partition(":")
    if kind == "GUIDE":
        t = next((g for g in GUIDE_TOPICS if g["id"] == topic_id), None)
        return f"기초 가이드 - {t['title'] if t else topic_id}"
    if kind == "ISSUE":
        k = ISSUE_KINDS.get(topic_id)
        return f"이슈 해설 - {k['title_hint'] if k else topic_id}"
    return topic


# ------------------------------------------------------------
# 사실 자료 만들기
# ------------------------------------------------------------

def _ticker_fact_line(ticker, d):
    r = d.get("returns", {}) or {}
    one_year = r.get("1년")
    one_year = f"{one_year:.2f}%" if isinstance(one_year, (int, float)) else "정보 없음"
    cagr = d.get("cagr")
    cagr = f"{cagr * 100:.1f}%" if isinstance(cagr, (int, float)) else "정보 없음"
    return (f"- {ticker.replace('.KS', '')} ({d.get('name', '')}): 운용보수 {d.get('expense_ratio', '정보 없음')}, "
            f"배당수익률 {d.get('yield', '정보 없음')}, 배당성장률 {d.get('dividend_growth_rate', '정보 없음')}, "
            f"1년 수익률 {one_year}, 상장 이후 연평균(CAGR) {cagr}, 최대 낙폭(5년) {d.get('mdd', '정보 없음')}, "
            f"환노출 {d.get('fx_exposure', '정보 없음')}")


def _tax_fact_block():
    return (
        f"[세법 사실 자료 - {ea.TAX_RULES_BASIS}]\n"
        f"- 국내 일반계좌: 해외지수·채권형 국내 ETF의 매매차익·분배금 {ea.TAX_DOMESTIC_DIVIDEND * 100:.1f}% (국내 주식형 ETF 매매차익은 비과세)\n"
        f"- 미국 상장 ETF: 배당 미국 원천징수 {ea.TAX_US_DIVIDEND_WITHHOLDING * 100:.0f}%, 매매차익 연 {ea.OVERSEAS_CG_DEDUCTION // 10000}만 원 공제 후 "
        f"{ea.TAX_OVERSEAS_CAPITAL_GAINS * 100:.0f}% 양도소득세(다음 해 5월 직접 신고)\n"
        f"- ISA: {ea.ISA_TAX_FREE_LIMIT // 10000}만 원(서민형 400만 원)까지 비과세, 초과분 {ea.ISA_SEPARATE_TAX * 100:.1f}% 분리과세, 3년 의무가입, 연 2,000만 원 납입 한도\n"
        f"- 연금저축/IRP: 인출 전까지 과세 이연, 연금 수령 시 3.3~5.5%\n"
        f"- {ea.OVERSEAS_ACCOUNT_NOTE}\n"
    )


def _collect_facts(tickers, macro_data, news_query=None, include_tax=False):
    facts_lines, data_cache = [], {}
    driver = None
    try:
        if any(t.endswith(".KS") for t in tickers):
            driver = ea._create_chrome_driver()
        for t in tickers:
            try:
                d = ea.get_etf_real_data(t, driver, macro_data)
            except Exception as e:
                print(f"⚠️ {t} 데이터 수집 실패(이 종목은 빼고 진행): {type(e).__name__}: {e}")
                continue
            if d:
                data_cache[t] = d
                facts_lines.append(_ticker_fact_line(t, d))
    finally:
        if driver:
            driver.quit()

    news = ea._get_recent_news_for_query(news_query, max_results=4) if news_query else []
    news_block = "\n".join(f"- {n['title']} ({n['source']}) {n['url']}" for n in news) or "- 수집된 뉴스 없음"
    macro_block = (f"- 원/달러 환율: {macro_data.get('usd_krw')} (전일 대비 {macro_data.get('usd_krw_diff_pct')}% {macro_data.get('usd_krw_direction', '')})\n"
                   f"- 미국 10년물 금리: {macro_data.get('us_10y')}\n- 공포/탐욕 지수: {macro_data.get('fear_greed')}")
    text = ("[사실 자료 - 예시 ETF 실제 데이터]\n" + ("\n".join(facts_lines) or "- (데이터 수집 실패)") + "\n\n"
            f"[오늘의 시장 수치]\n{macro_block}\n\n[최근 뉴스]\n{news_block}\n\n"
            + (_tax_fact_block() if include_tax else ""))
    return text, data_cache, news


def _closing_block(news, include_tax):
    news_items = "".join(
        f'<li><a href="{n["url"]}" target="_blank" rel="noopener">{n["source"]}</a> - {n["title"]}</li>' for n in news)
    tax_line = f"<br/>세금 관련 내용은 {ea.TAX_RULES_BASIS}이며, 세법은 바뀔 수 있으니 투자 전 최신 기준을 확인하세요." if include_tax else ""
    return (
        '<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-radius:6px;font-size:13px;line-height:1.7;">'
        '<strong>📌 데이터 출처</strong><br/>ETF 가격·배당: Yahoo Finance, 국내 ETF 정보: 네이버 금융'
        + (f'<ul style="margin:8px 0 0 18px;">{news_items}</ul>' if news_items else "")
        + "</div>"
        '<p style="margin-top:20px;font-size:12px;color:#888;line-height:1.7;">'
        "이 글은 공개 데이터를 정리한 정보 제공용 글이며, 특정 상품의 매수·매도를 권유하지 않습니다. "
        f"투자 판단과 책임은 본인에게 있습니다.{tax_line}</p>"
    )


# ------------------------------------------------------------
# 진입점
# ------------------------------------------------------------

def run_explainer(topic, etf_module):
    global ea
    ea = etf_module
    kind, _, topic_id = topic.partition(":")
    macro_data = ea.get_macro_data()
    if kind == "GUIDE":
        t = next((g for g in GUIDE_TOPICS if g["id"] == topic_id), None)
        if not t:
            print(f"❌ 알 수 없는 가이드 주제: {topic_id}")
            return
        kind_label, title_seed, article_type = "기초 가이드", t["title"], "guide"
        facts_text, data_cache, news = _collect_facts(t["tickers"], macro_data, include_tax=t.get("tax", False))
        include_tax = t.get("tax", False)
    elif kind == "ISSUE" and topic_id in ISSUE_KINDS:
        k = ISSUE_KINDS[topic_id]
        kind_label, title_seed, article_type = "이슈 해설", k["title_hint"], "issue"
        facts_text, data_cache, news = _collect_facts(k["tickers"], macro_data, news_query=k["query"], include_tax=False)
        include_tax = False
    else:
        print(f"❌ 알 수 없는 주제 형식: {topic}")
        return

    ctx = _load_json_file("confirmed_topic_context.json", None) or {}
    memo = (ctx.get("memo") or "").strip() if ctx.get("ticker") == topic else ""
    if ctx and os.path.exists("confirmed_topic_context.json"):
        os.remove("confirmed_topic_context.json")

    from topic_engine import produce_article
    produce_article(
        kind_label=kind_label, title_seed=title_seed, facts_text=facts_text, rules=_SECTION_RULES,
        category_label=f"ETF/{kind_label}", article_type=article_type, topic_id=topic_id, memo=memo,
        closing_html=_closing_block(news, include_tax),
        # 예시 종목은 그 종목의 재사용 금지·주제 분포에 넣지 않는다(종목 분석 글이 아님).
        meta={"example_tickers": list(data_cache.keys())},
    )
