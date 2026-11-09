"""온도(ondo) ETF 부서 실행 입구 - 명령줄 처리와 종목 분석 글 쓰기.
역할별 코드는 ondo/etf/ 에 있다(2026-11-09 나눔): config·universe·data·visuals·selection·approval·health.
다른 파일이 etf_auto.X 로 쓰던 이름은 그대로 쓸 수 있게 모두 여기로 다시 내보낸다."""
from ondo.etf.health import *  # noqa: F401,F403

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
