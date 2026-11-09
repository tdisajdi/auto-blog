"""ETF 자료: 시세·배당·낙폭·거시 지표·뉴스·세금/보수 계산·지난 분석 찾기.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.universe import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
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


















MACRO_CACHE_TTL = 3600
TICKER_CACHE_TTL = 1800
































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
                    macro_info["usd_krw_diff_pct"] = round(diff_pct, 2)   # 반올림 없이 글에 '1.214117186666646%'가 들어갔음
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


def _drawdown_detail(close):
    """최대 낙폭이 언제 시작(고점)해서 언제 바닥이었고, 고점 가격을 언제 되찾았는지(못 되찾았으면 None) 코드가 계산한다.
    2026-11-06: '최대 낙폭 -24.52%'만으로는 독자가 판단하기 어렵다 - "떨어지면 회복까지 얼마나 걸렸나"가 장기 보유의 실제 판단 기준.
    가격 기준(배당 제외). 실패하면 None."""
    try:
        c = close.dropna()
        if len(c) < 30:
            return None
        dd = c / c.cummax() - 1.0
        trough = dd.idxmin()
        peak = c.loc[:trough].idxmax()
        peak_px = float(c.loc[peak])
        after = c.loc[trough:]
        rec = after[after >= peak_px]
        recovered = rec.index[0] if len(rec) else None
        day = lambda d: f"{d:%Y-%m-%d}" if hasattr(d, "strftime") else str(d)
        out = {"pct": round(float(dd.min()) * 100, 2), "peak": day(peak), "trough": day(trough),
               "fall_days": int((trough - peak).days) if hasattr(trough - peak, "days") else None,
               "recovered": day(recovered) if recovered is not None else None,
               "recover_days": int((recovered - trough).days) if recovered is not None and hasattr(recovered - trough, "days") else None,
               "now_vs_peak": round((float(c.iloc[-1]) / peak_px - 1) * 100, 2)}
        return out
    except Exception:
        return None


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
    mdd_detail = None   # 최대 낙폭의 고점·바닥·회복 날짜와 회복에 걸린 기간(2026-11-06)
    simulated_result = "정보 없음"
    cagr = None  # 실제 데이터로 계산 성공한 경우에만 값이 채워짐 (임의 기본값 없음)
    current_price = 0.0
    calculated_yield = "0.00%"
    div_cycle = "정보 없음"
    expense_ratio = "N/A"
    kr_index = None
    kr_info = {}
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
                    mdd_detail = _drawdown_detail(df_5y['Close'])
                    
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

        # 2-0. 펀드보수·기초지수: 네이버 모바일 데이터(브라우저 없이) - 화면 스크래핑보다 먼저, 화면에서 못 읽어도 남는다
        kr_info = _naver_kr_info(raw_code)
        fee = kr_info.get("펀드보수") or kr_info.get("총보수")
        if fee and re.search(r"\d", fee):
            expense_ratio = fee if fee.endswith("%") else f"{fee}%"
        kr_index = kr_info.get("기초지수") or None
        # 2. 메타 정보 (네이버 금융 스크래핑)
        try:
            driver.get(f"https://finance.naver.com/item/main.naver?code={raw_code}")
            time.sleep(2)
            
            try:
                short_name = driver.find_element(By.XPATH, "//div[@class='wrap_company']/h2/a").text
            except Exception:
                short_name = raw_code
            if not short_name or short_name == raw_code:
                # 네이버 화면을 못 읽으면 이름이 숫자 코드만 남아 환율 영향 판단(_fx_exposure_label)이 빠졌다(2026-10-31)
                short_name = _kr_etf_name(raw_code) or raw_code
            
            # AUM (시가총액으로 대체)
            try:
                market_cap_text = driver.find_element(By.ID, "_market_sum").text
                aum_str = f"약 {market_cap_text}억 원"
            except Exception as e:
                print(f"   ⚠️ AUM 스크래핑 실패: {type(e).__name__}: {e}")
            
            dfs = pd.read_html(StringIO(driver.page_source))
            for df in dfs:
                df_str = df.to_string()
                if ("펀드보수" in df_str or "총보수" in df_str) and expense_ratio == "N/A":
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
            # shortName은 "…S&P 500 ETF T"처럼 잘려서 글에 그대로 나갔다 → 정식 이름 우선
            short_name = info.get('longName') or info.get('shortName') or raw_code
            
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
                    mdd_detail = _drawdown_detail(h_mdd['Close'])
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
        "yield": calculated_yield, "returns": returns, "mdd": mdd_val, "mdd_detail": mdd_detail,
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
        "fx_exposure": _fx_exposure_label(is_kr, short_name),
        "listing": "국내 상장" if is_kr else "해외 상장",
        # 하루 거래대금(네이버 모바일 자료, 전일 기준) - 거의 같은 두 국내 ETF를 고를 때 남는 차이(2026-11-08 운용사 비교)
        "trade_value": kr_info.get("대금") if is_kr else None,
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
        "index": info.get('category', '정보 없음') if not is_kr else (kr_index or "정보 없음"),
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
TAX_RULES_BASIS = "2026년 10월 기준 세법"   # 2026-10-31 확인: ISA 한도는 2025년과 같음. 2027년 개편안은 국회 심의 중
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
    """해외 상장인가(ISA·연금계좌로 직접 못 사는가). 환노출 여부와는 다른 질문이라 상장 위치로 판단한다."""
    d = d or {}
    if d.get('listing'):
        return d['listing'] == "해외 상장"
    return str(d.get('fx_exposure', '')).startswith('있음 (해외 상장')   # 예전 기록 호환


# 국내 상장이라도 해외 자산을 담으면 환율 영향을 받는다(예: 360750 TIGER 미국S&P500은 환노출형).
# 예전에는 "국내 상장 = 환노출 없음"으로 처리해서 글에 사실 오류가 나갔다(2026-10-31).
_FOREIGN_ASSET_WORDS = ("미국", "S&P", "나스닥", "NASDAQ", "다우", "글로벌", "선진국", "신흥국", "차이나", "중국",
                        "일본", "인도", "베트남", "유럽", "독일", "필라델피아", "반도체TOP", "빅테크", "MSCI",
                        "달러", "국채", "TLT", "금현물", "골드", "원유", "WTI")


def _fx_exposure_label(is_kr, name):
    if not is_kr:
        return "있음 (해외 상장, 달러로 거래)"
    n = str(name or "")
    if "(H)" in n or "헤지" in n:
        return "환헤지형 (국내 상장, 환율 영향을 줄인 상품)"
    if any(w.lower() in n.lower() for w in _FOREIGN_ASSET_WORDS):
        return "있음 (국내 상장이지만 해외 자산, 환헤지 안 함)"
    return "확인 필요"


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

__all__ = [k for k in dir() if not k.startswith('__')]
