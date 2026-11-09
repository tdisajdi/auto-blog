"""ETF 주제 고르기: 최근 글 테마·쿨다운·후보 발굴·검색 관심도·AI 토론·검색 성과.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.visuals import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
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

__all__ = [k for k in dir() if not k.startswith('__')]
