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

# 독자가 실제로 검색하는 말(자동완성)을 모을 짧은 검색어(2026-11-08, topic_engine.search_questions_block)
SEARCH_SEEDS = {"overseas-vs-domestic-tax": "해외 ETF 세금", "expense-ratio": "ETF 총보수", "covered-call-structure": "커버드콜 ETF",
                "hedged-vs-unhedged": "환헤지 ETF", "tr-vs-pr": "TR ETF", "dca-vs-lump": "적립식 거치식",
                "mdd-risk": "MDD 최대낙폭", "tax-accounts": "ISA 연금저축 ETF", "dividend-growth": "배당성장률",
                "bond-duration": "채권 ETF 금리", "leverage-decay": "레버리지 ETF", "parking-etf": "파킹형 ETF",
                "fx": "환율 해외 ETF", "rates": "금리 채권 ETF", "sentiment": "공포탐욕지수"}

ISSUE_KINDS = {
    # 11-08 재시험 2번 미통과: 제목('확인할 것')이 넓어 작가가 빈자리를 일반 지식(환전 전략·야간 선물·iNAV)으로 채움.
    # 국내 ETF 2개는 계산표에 안 쓰이는데 보수·낙폭 숫자만 늘려 '파편적 나열' 지적 → 제목을 계산표가 답하는 질문으로 좁히고 종목도 계산에 쓰는 것만.
    "fx": {"label": "환율", "query": "원/달러 환율",
           "title_hint": "최근 1년 원/달러 환율 변화가 해외 ETF의 원화 수익률을 얼마나 바꿨나",
           "tickers": ["SPY", "QQQ", "GLD"]},
    "rates": {"label": "금리", "query": "미국 10년물 국채 금리",
              "title_hint": "금리 변화가 채권 ETF와 성장주 ETF에 주는 영향",
              "tickers": ["TLT", "IEF", "SHY", "QQQ"]},
    "sentiment": {"label": "투자심리", "query": "미국 증시 공포 탐욕 지수",
                  "title_hint": "시장 심리가 한쪽으로 쏠릴 때 ETF 투자자가 볼 것",
                  "tickers": ["SPY", "QQQ", "SCHD", "TLT"]},
}

# 공통 글쓰기 규칙은 ondo/writing/prompts/rules.txt에 있고, 여기에는 ETF 글 전용 규칙만 둔다.
_SECTION_RULES = (
    "- [계좌 원칙] 해외(미국 등) 상장 ETF는 ISA·연금저축·IRP로 직접 살 수 없습니다. 이 계좌를 언급할 때는 "
    "같은 지수의 국내 상장 ETF로만 설명하세요. 왜 살 수 없는지(법령·제도상 이유)는 자료에 없으니 이유를 지어 설명하지 마세요\n"
    # ↑ 11-08 환헤지 가이드 '국내 해외탁송 체계 때문', 그 전 '국내 법령상 국내 상장 자산만' - 이유를 지어내 '중요'·'치명'이 반복됨

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

_EMPTY = ("정보 없음", "N/A", "확인 필요", "", None, "-")


def _ticker_fact_line(ticker, d):
    """종목 한 줄 자료. 값이 없거나 믿기 어려운 항목은 아예 넣지 않는다(글에 '확인 필요'·N/A가 새지 않게)."""
    r = d.get("returns", {}) or {}
    one_year = r.get("1년")
    cagr = d.get("cagr")
    yld = d.get("yield")
    # 국내 ETF 배당수익률은 수집이 안 되면 0.00%로 찍힌다(360750도 실제로는 분배금을 줌) → 0이면 뺀다
    if ticker.endswith(".KS") and str(yld).strip() in ("0.00%", "0%", "0.0%"):
        yld = None
    items = [
        # listing 값이 이미 '해외 상장'/'국내 상장'이라 이름표를 붙이면 '상장 해외 상장'이 됐다(2026-11-08)
        ("", d.get("listing")),
        ("운용보수", d.get("expense_ratio")),
        ("배당수익률", yld),
        ("최근 1년 배당 합계 증가율(전년 대비)", d.get("dividend_growth_rate")),   # 11-10: 1년 변화인데 '배당성장률'로만 적혀 연평균처럼 읽힘
        ("1년 수익률", f"{one_year:.2f}%" if isinstance(one_year, (int, float)) else None),
        # 11-10: 코드는 CAGR을 최근 5년 자료(5년이 안 되면 있는 만큼)로 재는데 '상장 이후'로 이름 붙어 있었다 → 잰 기간대로.
        # 5년치가 다 있는 종목끼리는 기간이 같아 비교해도 된다. 기간이 짧은 종목만 비교 금지를 붙인다.
        (("최근 5년 연평균(CAGR)" if isinstance(d.get("cagr_years"), (int, float)) and d["cagr_years"] >= 4.9
          else f"상장 이후 연평균(CAGR, 약 {d['cagr_years']:.1f}년치 - 기간이 달라 다른 종목과 직접 비교하면 안 됨)"
          if isinstance(d.get("cagr_years"), (int, float)) else "연평균(CAGR, 기간이 달라 종목끼리 직접 비교하면 안 됨)"),
         f"{cagr * 100:.1f}%" if isinstance(cagr, (int, float)) else None),
        ("최대 낙폭(5년)", d.get("mdd")),
        ("환율 영향", d.get("fx_exposure")),
    ]
    body = ", ".join(f"{k} {v}".strip() for k, v in items if v not in _EMPTY)
    return f"- {ticker.replace('.KS', '')} ({d.get('name', '')}): {body}"


def drop_overlapping_metrics(facts_text, calc_facts, keep_dividend=False):
    """계산표가 자기 기준으로 다시 계산한 숫자는 종목 기본 자료에서 뺀다 - 숫자는 한 기준만(11-08 배운 원칙 12).
    한 글에 '1년 수익률'(QQQ 8.11% vs +5.8%, 레버리지)·'최대 낙폭'(TLT -43.70% vs -50.0%, 최대 낙폭 가이드)이 두 개씩 나왔다.
    상장 이후 연평균(CAGR)은 "직접 비교 금지" 경고와 숫자를 같이 주니 작가가 비교해 모순(적립식 가이드) → 계산표가 있으면 늘 뺀다."""
    out = re.sub(r", (?:상장 이후 |최근 5년 )?연평균\(CAGR[^)]*\) -?[\d.]+%", "", facts_text)
    if re.search(r"1년|수익률", calc_facts):
        out = re.sub(r", 1년 수익률 -?[\d.]+%", "", out)
    if "최대 낙폭" in calc_facts:
        out = re.sub(r", 최대 낙폭\(5년\) -?[\d.]+%", "", out)
    # 배당 주제가 아니면 배당수익률·배당성장률도 뺀다 - 작가가 받은 숫자를 다 쓰려고 상관없는 문단에 끼워 넣음
    # (11-08 레버리지·적립식 가이드 두 번: "배당수익률 1.03%에 배당성장률 4.54%인 SPY…")
    if not keep_dividend:
        out = re.sub(r", (?:배당(?:수익률|성장률)|최근 1년 배당 합계 증가율\(전년 대비\)) -?[\d.]+%", "", out)
    return out


def _tax_fact_block():
    return (
        f"[세법 사실 자료 - {ea.TAX_RULES_BASIS}]\n"
        f"- 국내 일반계좌: 해외지수·채권형 국내 ETF의 매매차익·분배금 {ea.TAX_DOMESTIC_DIVIDEND * 100:.1f}% (국내 주식형 ETF 매매차익은 비과세)\n"
        f"- 미국 상장 ETF: 배당 미국 원천징수 {ea.TAX_US_DIVIDEND_WITHHOLDING * 100:.0f}%, 매매차익 연 {ea.OVERSEAS_CG_DEDUCTION // 10000}만 원 공제 후 "
        f"{ea.TAX_OVERSEAS_CAPITAL_GAINS * 100:.0f}% 양도소득세(다음 해 5월 국세청 홈택스 등으로 직접 신고)\n"
        f"- ISA(정식 이름: 개인종합자산관리계좌): {ea.ISA_TAX_FREE_LIMIT // 10000}만 원(서민형 400만 원)까지 비과세, 초과분 {ea.ISA_SEPARATE_TAX * 100:.1f}% 분리과세, 3년 의무가입, 연 2,000만 원 납입 한도\n"
        f"- 연금저축/IRP: 인출 전까지 과세 이연, 연금 수령 시 3.3~5.5%\n"
        "- 금융소득종합과세: 이자·배당 등 금융소득이 한 해 2,000만 원을 넘으면 넘는 부분은 다른 소득과 합쳐 과세(해외 ETF 배당도 포함)\n"
        "- 국내 상장 해외지수 ETF는 매도할 때 보유기간 동안의 이익에 과세되며, 다른 상품의 손실과 합산(손익 통산)되지 않음\n"
        "- ISA 제도는 2027년 시행을 목표로 한 개편안이 국회 심의 중(확정 전이므로 바뀐다고 단정하지 말 것)\n"
        f"- {ea.OVERSEAS_ACCOUNT_NOTE}\n"
    )


# ------------------------------------------------------------
# 시각 자료 (코드가 정확한 숫자로 만든다 - 글마다 꼭 필요한 것 1개, 2026-10-31 사용자 선택)
# ------------------------------------------------------------

TAX_EXAMPLE_GAINS = [2_000_000, 5_000_000, 10_000_000, 20_000_000]


def _won(v):
    return f"{round(v / 10000):,}만 원" if v >= 10000 else f"{round(v):,}원"


def tax_scenarios():
    """이익 규모별·계좌별 세금 계산. 반환: (사실 자료 글, 표+그래프 HTML).
    가정은 표 아래와 자료에 함께 적는다(글이 조건 없이 단정하지 않게)."""
    from ondo.media import charts
    names = ["해외 상장 ETF (일반계좌)", "국내 상장 해외지수 ETF (일반계좌)", "ISA 일반형 (3년 유지)", "연금저축 (연금 수령)"]

    def taxes(g):
        return [max(0, g - ea.OVERSEAS_CG_DEDUCTION) * ea.TAX_OVERSEAS_CAPITAL_GAINS,
                g * ea.TAX_DOMESTIC_DIVIDEND,
                max(0, g - ea.ISA_TAX_FREE_LIMIT) * ea.ISA_SEPARATE_TAX,
                g * ea.PENSION_TAX]
    rows = [[_won(g)] + [_won(t) for t in taxes(g)] for g in TAX_EXAMPLE_GAINS]
    note = ("가정: 한 해에 이 ETF에서만 이익이 난 경우, 분배금·환율 변동·거래 비용 제외. 해외 상장 ETF는 연 250만 원 공제는 "
            "해외 주식 전체 합산 기준. 연금저축은 55세 이후 연금으로 받을 때 3.3~5.5% 중 5.5%로 계산(중도 인출은 16.5%). "
            "국내 일반계좌는 이자·배당 등 금융소득이 한 해 2,000만 원을 넘으면 종합과세로 더 낼 수 있음. "
            f"{ea.TAX_RULES_BASIS}, ondo가 직접 계산.")
    table = charts.table_html("이익 규모별 예상 세금 (계좌별)", ["한 해 이익"] + names, rows, note)
    chart = charts.plotly_html({
        "title": "이익 규모별 예상 세금 비교", "kind": "bar", "unit": "만 원",
        "labels": [_won(g) for g in TAX_EXAMPLE_GAINS],
        "series": [{"name": n, "values": [round(taxes(g)[i] / 10000, 1) for g in TAX_EXAMPLE_GAINS]}
                   for i, n in enumerate(names)],
        "source": f"{ea.TAX_RULES_BASIS} 세율로 ondo 계산"})
    facts = ("[계산 예시 - 코드가 세율로 직접 계산한 값. 이 표와 그래프는 시스템이 본문에 넣으므로 표로 다시 만들지 말고, "
             "숫자를 인용해 '어떤 경우에 어느 쪽 세금이 적은지' 문장으로 해석하세요]\n"
             + "\n".join(f"- 한 해 이익 {r[0]}: " + ", ".join(f"{n} {t}" for n, t in zip(names, r[1:])) for r in rows)
             + f"\n- {note}\n" + _tax_breakeven_line())
    return facts, table + chart


def _tax_breakeven_line():
    """일반계좌끼리 세금이 같아지는 한 해 이익(갈림길)을 세율로 계산(2026-11-06). 작가가 '약 835만 원'을 스스로 계산했다가
    자료에 없는 숫자로 '치명' 지적을 받았는데, 독자에게 가장 쓸모 있는 판단 기준이라 코드가 정확히 계산해서 준다.
    해외 상장: (이익 − 공제) × 해외세율, 국내 상장: 이익 × 국내세율 → 같아지는 이익 = 공제 × 해외세율 ÷ (해외세율 − 국내세율)"""
    ro, rd, ded = ea.TAX_OVERSEAS_CAPITAL_GAINS, ea.TAX_DOMESTIC_DIVIDEND, ea.OVERSEAS_CG_DEDUCTION
    if ro <= rd:
        return ""
    be = ded * ro / (ro - rd)
    return (f"- 갈림길(코드 계산): 일반계좌끼리 비교하면 한 해 이익이 약 {_won(be)}일 때 두 방식의 세금이 같다. 그보다 적으면 해외 상장 ETF "
            f"쪽 세금이 적고, 많으면 국내 상장 해외지수 ETF 쪽 세금이 적다(해외 {ro * 100:.0f}%·연 {_won(ded)} 공제, 국내 {rd * 100:.1f}% 기준). "
            "단, 국내 상장 쪽 이익은 배당소득으로 잡혀 이자·배당 등 금융소득이 한 해 2,000만 원을 넘으면 종합과세로 세금이 더 늘 수 있어 "
            "이익이 큰 경우엔 이 갈림길이 달라질 수 있다.\n")


def price_chart(tickers, data_cache):
    """예시 ETF 1년 흐름(시작=100으로 맞춘 월말 값). 2개 이상 받아오면 그래프 HTML, 아니면 빈 문자열."""
    from ondo.media import charts
    try:
        import yfinance as yf
    except ImportError:
        return ""
    series, labels = [], None
    for t in tickers:
        if t not in data_cache:
            continue
        try:
            close = yf.Ticker(t).history(period="1y", interval="1mo")["Close"].dropna()
        except Exception as e:
            print(f"ℹ️ {t} 1년 가격 못 받음: {type(e).__name__}")
            continue
        if len(close) < 6:
            continue
        lab = [d.strftime("%y.%m") for d in close.index]
        if labels is None:
            labels = lab
        if lab != labels:
            continue      # 거래소마다 날짜가 다르면 섞지 않는다
        name = (data_cache[t].get("name") or t.replace(".KS", ""))[:20]
        series.append({"name": name, "values": [round(v / close.iloc[0] * 100, 1) for v in close]})
    if len(series) < 2:
        return ""
    return charts.plotly_html({"title": "예시 ETF 최근 1년 흐름 (시작=100)", "kind": "line", "labels": labels,
                               "series": series, "unit": "", "source": "Yahoo Finance 월말 종가, ondo 계산(환율 반영 전 각 통화 기준)"})


def fx_effect(data_cache):
    """환율 이슈 글용: 최근 1년 원/달러 변화가 해외 상장 ETF의 원화 수익률을 얼마나 바꿨는지 코드가 계산(2026-11-03).
    반환: (사실 자료 글, 표+그래프 HTML). 계산에 필요한 값이 없으면 ("", "")."""
    from ondo.media import charts
    try:
        import yfinance as yf
        fx = yf.Ticker("KRW=X").history(period="1y")["Close"].dropna()
        fx0, fx1 = float(fx.iloc[0]), float(fx.iloc[-1])
    except Exception as e:
        print(f"ℹ️ 환율 1년 자료 못 받음: {type(e).__name__}")
        return "", ""
    fx_chg = fx1 / fx0 - 1
    rows, labels, usd, krw, rev = [], [], [], [], []
    for t, d in data_cache.items():
        r = (d.get("returns") or {}).get("1년")
        if t.endswith(".KS") or not isinstance(r, (int, float)):
            continue
        r = r / 100
        k = (1 + r) * (1 + fx_chg) - 1          # 원화로 본 수익률
        k_rev = (1 + r) * (1 - fx_chg) - 1      # 환율이 같은 폭만큼 반대로 움직였다면
        name = t
        rows.append([name, f"{r * 100:+.1f}%", f"{k * 100:+.1f}%", f"{k_rev * 100:+.1f}%"])
        labels.append(name); usd.append(round(r * 100, 1)); krw.append(round(k * 100, 1)); rev.append(round(k_rev * 100, 1))
    if not rows:
        return "", ""
    note = (f"원/달러 환율 {fx0:,.0f}원 → {fx1:,.0f}원({fx_chg * 100:+.1f}%, 최근 1년, Yahoo Finance). 원화 수익률 = "
            "(1+달러 수익률)×(1+환율 변화)-1, 배당·세금·환전 수수료 제외, ondo 계산. '반대였다면'은 환율이 같은 폭만큼 "
            "반대로 움직였다고 가정한 값.")
    table = charts.table_html("최근 1년, 환율이 바꾼 원화 수익률", ["ETF", "달러 기준", "원화 기준(실제 환율)", "환율이 반대였다면"],
                              rows, note)
    chart = charts.plotly_html({"title": "달러 기준 vs 원화 기준 1년 수익률", "kind": "bar", "unit": "%", "labels": labels,
                                "series": [{"name": "달러 기준", "values": usd}, {"name": "원화 기준", "values": krw},
                                           {"name": "환율이 반대였다면", "values": rev}],
                                "source": "Yahoo Finance, ondo 계산"})
    # 11-09: 종목마다 같은 꼴의 줄을 주자 작가가 'SPY는…, QQQ는…, GLD는…'으로 세 번 되풀이해 독자 편집 '중요'(환율 고정 시험).
    # → 코드가 공통 결론(환율 때문에 생긴 차이의 범위)을 한 줄로 먼저 주고, 종목별 줄은 '표에 있음 - 대표 1개만, 빠져도 누락 아님'으로.
    # 11-10: '대표 1개만 … 나머지는 표를 가리키세요'를 사실 검증이 규칙으로 읽어 세 종목을 쓴 글을 '중요'로 잡고, 독자 편집은
    # 반대로 '표만 가리키고 해석 없음'을 잡아 서로 부딪힘 → 명령 대신 허용('골라 써도/묶어 써도 됨')으로만 준다.
    gaps = [k - u for u, k in zip(usd, krw)]
    # 11-10 사람 읽기: '-8.2~-7.4%p 달라짐'을 작가가 '-8.2~-7.4%p 낮아졌다'로 옮겨 이중 부정(오히려 높아졌다는 뜻으로 읽힘)
    # → 방향은 말로, 크기는 부호 없이 준다
    lo, hi = sorted(abs(g) for g in gaps)[0], sorted(abs(g) for g in gaps)[-1]
    way = "낮아짐" if all(g < 0 for g in gaps) else "높아짐" if all(g > 0 for g in gaps) else None
    summary = ((f"- 공통 결론(코드 계산): 원/달러 환율이 {abs(fx_chg) * 100:.1f}% {'내려' if fx_chg < 0 else '올라'} "
                f"{len(rows)}개 ETF 모두 원화 수익률이 달러 기준보다 {lo:.1f}~{hi:.1f}%p {way} "
                "(이 문장은 부호 없이 '%p 낮아짐/높아짐'으로 쓸 것 - '-%p 낮아짐'처럼 겹쳐 쓰지 말 것)")
               if len(rows) >= 2 and way else "")
    facts = ("[계산 예시 - 코드가 계산한 값. 이 표와 그래프는 시스템이 본문에 넣으므로 표로 다시 만들지 말고 문장으로 해석하세요]\n"
             + (summary + "\n" if summary else "")
             + "- 종목별 값(표·그래프에 모두 들어감 - 한두 종목만 골라 써도, 여러 종목을 한 문장에 묶어 써도 됨. "
               "본문에 없는 종목은 누락이 아님):\n"
             + "\n".join(f"  - {a}: 달러 기준 1년 {b}, 원화 기준 {c}, 환율이 반대로 같은 폭 움직였다면 {e}" for a, b, c, e in rows)
             + f"\n- {note}\n- 국내 상장 해외 자산 ETF 중 환헤지 안 한 상품(예: 360750)의 원화 수익률에는 이미 환율 변화가 들어 있고, "
             "이름에 (H)가 붙은 환헤지 상품은 환율 영향을 줄이는 대신 헤지 비용이 든다.\n")
    return facts, table + chart


def _weekly(close):
    """주간(금요일) 종가. 시간대를 떼고 날짜로 맞춘다: ^TNX는 시카고, ETF는 뉴욕 시간이라 그대로 합치면
    같은 주인데도 하나도 안 겹쳤다(2026-11-03 금리 글 첫 시험에서 계산표가 조용히 빠짐)."""
    c = close.dropna()
    if getattr(c.index, "tz", None) is not None:
        c.index = c.index.tz_localize(None)
    c.index = c.index.normalize()
    return c.resample("W-FRI").last().dropna()


def rates_effect(data_cache):
    """금리 이슈 글용(2026-11-03): 최근 1년 주간 자료로 '미국 10년물 금리가 0.1%p 오른 주에 각 ETF가 평균 몇 % 움직였나'를
    코드가 계산한다(회귀 기울기). 일반 이론(금리↑→채권↓)만 쓰면 사실 검증이 '자료에 없는 통념'으로 지적해서, 실제 숫자로 보여준다.
    반환: (사실 자료 글, 표+그래프 HTML). 자료가 부족하면 ("", "")."""
    from ondo.media import charts
    try:
        import yfinance as yf
        tnx_w = _weekly(yf.Ticker("^TNX").history(period="1y")["Close"])
    except Exception as e:
        print(f"ℹ️ 금리 1년 자료 못 받음: {type(e).__name__}")
        return "", ""
    if len(tnx_w) < 30:
        return "", ""
    y0, y1 = float(tnx_w.iloc[0]), float(tnx_w.iloc[-1])
    dy = tnx_w.diff().dropna()                      # 주간 금리 변화(%p)
    rows, labels, sens = [], [], []
    for t in data_cache:
        if t.endswith(".KS"):
            continue
        try:
            px = _weekly(yf.Ticker(t).history(period="1y")["Close"])
            ret = (px.pct_change() * 100).dropna()  # 주간 가격 변화(%)
            both = ret.to_frame("r").join(dy.to_frame("dy"), how="inner").dropna()
            if len(both) < 30 or float(both["dy"].var()) == 0:
                print(f"ℹ️ 금리 반응 계산 건너뜀({t}): 겹치는 주 {len(both)}개")
                continue
            beta = float(both["r"].cov(both["dy"]) / both["dy"].var())   # 금리 1%p당 % 변화
            corr = float(both["r"].corr(both["dy"]))
            up = both[both["dy"] > 0]["r"].mean()
            down = both[both["dy"] < 0]["r"].mean()
            p_chg = (float(px.iloc[-1]) / float(px.iloc[0]) - 1) * 100
        except Exception as e:
            print(f"ℹ️ 금리 반응 계산 실패({t}): {type(e).__name__}: {e}")
            continue
        per = beta * 0.1
        rows.append([t, f"{per:+.2f}%", f"{up:+.2f}%", f"{down:+.2f}%", f"{p_chg:+.1f}%"])
        labels.append(t); sens.append(round(per, 2))
        rows[-1].append(f"{corr:+.2f}")
    if not rows:
        print("ℹ️ 금리 반응 계산: 쓸 수 있는 종목 없음")
        return "", ""
    n_up = int((dy > 0).sum()); n_down = int((dy < 0).sum())
    note = (f"미국 10년물 금리 {y0:.2f}% → {y1:.2f}%({y1 - y0:+.2f}%p, 최근 1년, Yahoo Finance ^TNX). 주간 종가 기준, 배당 제외 가격 변화. "
            f"'0.1%p당 평균 반응'은 금리 변화와 가격 변화의 회귀 기울기 × 0.1, ondo 계산. 금리가 오른 주 {n_up}번, 내린 주 {n_down}번. "
            "지난 1년의 평균일 뿐 앞으로도 같다는 보장은 없음. 여기 '1년 가격 변화'는 주간 종가로 다시 계산한 배당 제외 값이라 "
            "위 종목 자료의 '1년 수익률'과 조금 다를 수 있음 - 둘을 같은 숫자처럼 나란히 쓰지 말 것.")
    table = charts.table_html("최근 1년, 금리가 움직인 주에 ETF 가격은 어떻게 움직였나",
                              ["ETF", "금리 0.1%p 오를 때 평균", "금리 오른 주 평균", "금리 내린 주 평균", "1년 가격 변화", "같이 움직인 정도"],
                              [r[:5] + [r[5]] for r in rows], note + " '같이 움직인 정도'는 상관계수(-1~+1, 음수면 반대로 움직임).")
    chart = charts.plotly_html({"title": "금리 0.1%p 오를 때 평균 가격 반응(최근 1년, 주간)", "kind": "bar", "unit": "%",
                                "labels": labels, "values": sens, "source": "Yahoo Finance, ondo 계산"})
    facts = ("[계산 예시 - 코드가 계산한 값. 이 표와 그래프는 시스템이 본문에 넣으므로 표로 다시 만들지 말고 문장으로 해석하세요]\n"
             + "\n".join(f"- {r[0]}: 금리 0.1%p 오를 때 평균 {r[1]}, 금리 오른 주 평균 {r[2]}, 내린 주 평균 {r[3]}, "
                         f"1년 가격 변화 {r[4]}, 상관계수 {r[5]}" for r in rows)
             + f"\n- {note}\n"
             # 맞는 일반 원리인데 자료에 없어서 '통념'으로 지적받던 문장을 자료로 준다(2026-11-06)
             "[일반 원리 - 이 범위 안에서만 설명하고, 실제 크기는 위 계산 숫자로 말하세요]\n"
             "- 채권 가격은 금리와 반대로 움직이고, 만기(듀레이션)가 길수록 같은 금리 변화에 더 크게 움직인다.\n"
             "- 성장주는 먼 미래의 이익이 가치에서 차지하는 비중이 커서 금리가 오르면 불리하다고 흔히 설명되지만, 실제 반응은 "
             "실적 등 다른 요인에 따라 달라질 수 있다(위 계산표의 상관계수가 그 크기를 보여 줌).\n")
    return facts, table + chart


VIX_BANDS = [(0, 15, "15 미만(차분)"), (15, 20, "15~20"), (20, 30, "20~30(불안)"), (30, 999, "30 이상(공포)")]


def sentiment_effect():
    """투자심리 이슈 글용(2026-11-03): 최근 10년 실제 자료로 'VIX(변동성 지수)가 어느 구간이었던 날 이후 S&P 500(SPY)이
    1개월·3개월 동안 평균 얼마나, 몇 % 확률로 올랐나'를 코드가 계산한다. 금리 글처럼 일반론만으로는 통과를 못 해서
    미리 계산 예시를 준다. 매수 시점 판단이 아니라 '과거에 이랬다'는 통계로만 쓰게 한다.
    반환: (사실 자료 글, 표+그래프 HTML). 자료가 부족하면 ("", "")."""
    from ondo.media import charts
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX").history(period="10y")["Close"].dropna()
        spy = yf.Ticker("SPY").history(period="10y")["Close"].dropna()
        for c in (vix, spy):
            if getattr(c.index, "tz", None) is not None:
                c.index = c.index.tz_localize(None)
            c.index = c.index.normalize()
    except Exception as e:
        print(f"ℹ️ VIX·SPY 10년 자료 못 받음: {type(e).__name__}")
        return "", ""
    import pandas as pd
    df = pd.DataFrame({"vix": vix, "spy": spy}).dropna()
    if len(df) < 500:
        print(f"ℹ️ 투자심리 계산: 겹치는 날 {len(df)}일뿐이라 건너뜀")
        return "", ""
    df["f1"] = (df["spy"].shift(-21) / df["spy"] - 1) * 100       # 약 1개월(거래일 21일) 뒤
    df["f3"] = (df["spy"].shift(-63) / df["spy"] - 1) * 100       # 약 3개월(거래일 63일) 뒤
    cur = float(df["vix"].iloc[-1])
    rows, labels, avg3 = [], [], []
    for lo, hi, name in VIX_BANDS:
        b = df[(df["vix"] >= lo) & (df["vix"] < hi)]
        f1, f3 = b["f1"].dropna(), b["f3"].dropna()
        if len(f3) < 20:
            continue
        mark = " ← 지금" if lo <= cur < hi else ""
        rows.append([name + mark, f"{len(b):,}일", f"{f1.mean():+.1f}%", f"{(f1 > 0).mean() * 100:.0f}%",
                     f"{f3.mean():+.1f}%", f"{(f3 > 0).mean() * 100:.0f}%", f"{f3.min():+.1f}%"])
        labels.append(name); avg3.append(round(float(f3.mean()), 1))
    if len(rows) < 2:
        return "", ""
    start = df.index[0]
    note = (f"{start:%Y년 %m월}~최근 거래일 자료(Yahoo Finance ^VIX, SPY 종가, 배당 제외). 오늘 VIX {cur:.1f}. 각 구간의 '그날'에 샀다고 "
            "가정했을 때 약 1개월(21거래일)·3개월(63거래일) 뒤 가격 변화의 평균과 오른 비율, 3개월 뒤 가장 나빴던 경우. ondo 계산. "
            "과거 통계일 뿐 앞으로도 같다는 보장은 없고, 매수·매도 시점 신호가 아님.")
    table = charts.table_html("VIX 구간별, 그 뒤 S&P 500(SPY)은 어떻게 움직였나",
                              ["VIX 구간", "해당 날짜 수", "1개월 뒤 평균", "1개월 뒤 오른 비율", "3개월 뒤 평균",
                               "3개월 뒤 오른 비율", "3개월 뒤 가장 나빴던 경우"], rows, note)
    chart = charts.plotly_html({"title": "VIX 구간별 3개월 뒤 SPY 평균 가격 변화", "kind": "bar", "unit": "%",
                                "labels": labels, "values": avg3, "source": "Yahoo Finance, ondo 계산"})
    facts = ("[계산 예시 - 코드가 계산한 값. 이 표와 그래프는 시스템이 본문에 넣으므로 표로 다시 만들지 말고 문장으로 해석하세요]\n"
             "- VIX는 S&P 500 옵션 가격으로 계산한 '앞으로 30일 동안 예상되는 변동 폭' 지수(시카고옵션거래소 발표). 높을수록 시장이 불안해한다는 뜻\n"
             + "\n".join(f"- VIX {r[0]}: {r[1]}, 1개월 뒤 평균 {r[2]}(오른 비율 {r[3]}), 3개월 뒤 평균 {r[4]}(오른 비율 {r[5]}), "
                         f"3개월 뒤 가장 나빴던 경우 {r[6]}" for r in rows)
             + f"\n- {note}\n"
             "- 이 통계를 독자의 '확인 기준'으로 쓸 때는 '앞으로 얼마나 흔들릴 수 있는지(3개월 뒤 가장 나빴던 경우)'로 쓰고, "
             "'오를 확률이 높은 구간인지'를 기준으로 제시하지 마세요(매수 시점 판단처럼 읽힘).\n")
    return facts, table + chart


def market_thermometers():
    """이슈 글용 4대 거시 온도계(변동성·밸류에이션·환율·인플레이션). '매수 위험' 같은 판단 문구 배너는 넣지 않는다."""
    try:
        h = ea._build_macro_thermometers_chart(ea.get_macro_thermometer_indicators())
    except Exception as e:
        print(f"ℹ️ 온도계 만들기 실패: {type(e).__name__}")
        return ""
    return f'<figure class="ondo-chart" style="margin:28px 0;">{h}</figure>' if h else ""


_OFF_TOPIC_NEWS = ("비트코인", "이더리움", "가상자산", "암호화폐", "디지털자산", "코인", "지캐시", "리플", "솔라나", "도지", "스테이블")


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

    # 검색어 뒤에 'ETF'가 붙어서 '공포 탐욕 지수 ETF'에 비트코인·코인 ETF 기사가 섞였다(2026-11-03 투자심리 글) → 넉넉히 받고 걸러냄
    news = [n for n in (ea._get_recent_news_for_query(news_query, max_results=10) if news_query else [])
            if not any(w in n.get("title", "") for w in _OFF_TOPIC_NEWS)][:4]
    news_block = "\n".join(f"- {n['title']} ({n['source']}) {n['url']}" for n in news) or "- 수집된 뉴스 없음"
    # 공포/탐욕 지수는 투자심리 글에만(11-08: 환율 글·운용사 비교 글에서 '공포 지수 22 → 환율 변동성 확대·전략' 같은 지어낸 관계와
    # 투자 조언을 계속 끌어냄 - 그 글들의 질문에 필요한 숫자가 아니다)
    fg = "공포" in str(news_query or "") or "탐욕" in str(news_query or "")
    macro_block = (f"- 원/달러 환율: {macro_data.get('usd_krw')}{_day_move(macro_data)}\n"
                   f"- 미국 10년물 금리: {macro_data.get('us_10y')}"
                   + (f"\n- 공포/탐욕 지수: {macro_data.get('fear_greed')}" if fg else ""))
    # 오늘의 시장 수치(환율·금리·공포지수)는 이슈 글에만. 기초 가이드는 오래 읽히는 글이라 도입에 넣으면 어색했다.
    market = f"[오늘의 시장 수치]\n{macro_block}\n\n" if news_query else ""
    # 계좌 규칙은 글쓰기 규칙에만 있고 사실 자료엔 없어서, 맞는 문장인데도 사실 검증이 '지어냄'으로 지적했다(2026-11-03 금리 글)
    if not include_tax and any(not t.endswith(".KS") for t in data_cache):
        # 세금 가이드가 아니어도 작가가 해외 ETF 세금을 맞게 쓰는데 자료에 없어 '치명'(11-08 레버리지 가이드) → 핵심 두 줄만 자료로
        market += (f"[계좌 사실]\n- {ea.OVERSEAS_ACCOUNT_NOTE}\n"
                   # 11-09: 여기에 세율 숫자(15%·22%·250만 원)를 주면서 규칙으로는 '세율 숫자 쓰지 말 것'이라 해서 작가는 자료대로 숫자를
                   # 쓰고 검토는 잡았다 놓쳤다 했다(환율 글, 채점 흔들림 측정 3번 중 1번 놓침) → 세금 글이 아니면 숫자 없이 사실만 준다
                   # 11-09 저녁: '사실만 한두 문장으로'라고 주자 검토가 세 줄을 꼭 넣을 내용으로 보고 '누락'(환율 연달아 시험 2판·3판) → '빠져도 누락 아님'을 밝힘
                   f"[세금 참고 - {ea.TAX_RULES_BASIS}. 이 글의 주제가 아니므로 꼭 쓸 필요 없음(빠져도 누락 아님). 쓴다면 숫자 없이 아래 사실과 맞게 한두 문장만 - 이 목록을 다 옮기지 말 것]\n"
                   "- 미국 상장 ETF 매매차익은 양도소득세 대상이고 다음 해 5월에 직접 신고한다(세율·공제액은 세금 가이드에서 다룸)\n"
                   "- 미국 상장 ETF 배당은 미국에서 세금을 먼저 떼고(원천징수) 들어오며, 해외에서 낸 세금은 국내 세금에서 빼 준다(외국납부세액공제)\n"
                   "- 이자·배당 등 금융소득이 한 해 일정 금액을 넘으면 다른 소득과 합쳐 과세된다(금융소득종합과세, 기준 금액은 세금 가이드에서 다룸)\n\n")
    text = ("[사실 자료 - 예시 ETF 실제 데이터]\n" + ("\n".join(facts_lines) or "- (데이터 수집 실패)") + "\n\n"
            f"{market}[최근 뉴스]\n{news_block}\n\n"
            + (_tax_fact_block() if include_tax else ""))
    return text, data_cache, news


def _day_move(macro_data):
    """전일 대비 변화가 0.0%처럼 의미 없으면 아예 빼서 글에 '전일 대비 0.0%' 같은 군더더기가 안 들어가게 한다."""
    try:
        pct = float(macro_data.get("usd_krw_diff_pct"))
    except (TypeError, ValueError):
        return ""
    if abs(pct) < 0.05:
        return ""
    # 반올림 없이 '1.214117186666646%'가 글에 그대로 들어갔다(2026-11-08) → 소수 둘째 자리까지
    return f" (전일 대비 {pct:.2f}% {macro_data.get('usd_krw_direction', '')})".rstrip(" )") + ")"


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
        if include_tax:
            calc_facts, visual = tax_scenarios()
            facts_text += "\n" + calc_facts
        else:
            # 세금 외 가이드: 제목 질문에 답하는 숫자를 코드가 계산(2026-11-08, guide_calcs.py). 실패하면 가격 그래프만.
            import guide_calcs
            calc_facts, visual = guide_calcs.guide_facts(topic_id, data_cache, rates_effect=rates_effect)
            if calc_facts:
                facts_text = drop_overlapping_metrics(facts_text, calc_facts,
                                                      keep_dividend=topic_id in ("dividend-growth", "covered-call-structure"))
                facts_text += "\n" + calc_facts
            visual = visual or price_chart(t["tickers"], data_cache)
    elif kind == "ISSUE" and topic_id in ISSUE_KINDS:
        k = ISSUE_KINDS[topic_id]
        kind_label, title_seed, article_type = "이슈 해설", k["title_hint"], "issue"
        facts_text, data_cache, news = _collect_facts(k["tickers"], macro_data, news_query=k["query"], include_tax=False)
        include_tax = False
        visual = ""
        if topic_id == "fx":       # 환율 글: "환율이 실제로 수익률을 얼마나 바꿨나"를 코드가 계산해서 제목 질문에 답하게
            calc_facts, visual = fx_effect(data_cache)
            if calc_facts:         # 11-08 재시험: 배당성장률 등 주제와 먼 종목 숫자를 길게 나열('일반론') → 가이드처럼 겹치는·무관한 숫자 뺌
                facts_text = drop_overlapping_metrics(facts_text, calc_facts) + "\n" + calc_facts
        elif topic_id == "sentiment":  # 투자심리 글: VIX 구간별 그 뒤 SPY 성과(과거 통계)
            calc_facts, visual = sentiment_effect()
            facts_text += ("\n" + calc_facts) if calc_facts else ""
        elif topic_id == "rates":  # 금리 글: "금리가 움직일 때 실제로 얼마나 움직였나"를 코드가 계산(2026-11-03)
            calc_facts, visual = rates_effect(data_cache)
            facts_text += ("\n" + calc_facts) if calc_facts else ""
        visual = visual or market_thermometers()
    else:
        print(f"❌ 알 수 없는 주제 형식: {topic}")
        return

    ctx = _load_json_file("confirmed_topic_context.json", None) or {}
    memo = (ctx.get("memo") or "").strip() if ctx.get("ticker") == topic else ""
    if ctx and os.path.exists("confirmed_topic_context.json"):
        os.remove("confirmed_topic_context.json")

    from topic_engine import produce_article
    from ondo.media import charts
    try:     # 글 맨 위 온도 서명 띠(숫자만). ETF·시장 글에만 들어간다.
        top = charts.thermo_strip(ea.get_macro_thermometer_indicators(), datetime.now().strftime("%m월 %d일"))
    except Exception as e:
        print(f"ℹ️ 온도 띠 실패: {type(e).__name__}")
        top = ""
    produce_article(top_html=top,
        kind_label=kind_label, title_seed=title_seed, facts_text=facts_text,
        # 코드가 만든 계산표가 들어가는 글은 작가가 표를 또 만들지 않는다(2026-11-06 금리 글: 손으로 만든 표의 칸이 어긋나 '치명')
        rules=_SECTION_RULES + ("- [표 금지] 이 글에는 시스템이 계산표를 넣습니다. 본문에 <table>을 새로 만들지 말고, 숫자는 문장으로 "
                                "해석하세요.\n" if "<table" in (visual or "") else "")
              # 11-08 적립식 가이드: 세금 사실을 주자 세금 소제목·세금 FAQ까지 만들고, 자료에 없는 결론('국내 추가 원천징수 없음')도 씀
              # 11-08 오후: '짧게'로는 부족 - 세금 가이드 외 8개 가이드에서 막은 지적의 22%(58개 중 13개)가 세금·계좌(서류 절차·이유 지어내기)
              + ("- [세금·계좌는 한두 문장만] 이 글의 주제는 세금이 아닙니다. 본문에 세율 숫자·신고 절차·서류·계좌 제한의 이유를 쓰지 마세요. "
                 "필요하면 '해외 상장 ETF는 ISA·연금저축·IRP로 직접 살 수 없다'는 문장 하나와 '세금은 해외 상장 vs 국내 상장 ETF 세금 비교 "
                 "가이드에서 다룬다'는 문장 하나까지만 쓰세요. 이 내용은 글 전체에서 한 번만 - 세금·계좌 소제목이나 FAQ로 다시 다루지 마세요.\n" if not include_tax else ""),
        category_label=f"ETF/{kind_label}", article_type=article_type, topic_id=topic_id, memo=memo,
        closing_html=_closing_block(news, include_tax), visual_html=visual,
        # 예시 종목은 그 종목의 재사용 금지·주제 분포에 넣지 않는다(종목 분석 글이 아님).
        meta={"example_tickers": list(data_cache.keys())},
        search_seed=SEARCH_SEEDS.get(topic_id, ""),
    )
