"""기업 소개 글(2026-11-20 사용자 요청 - 백로그 85, lab/THINKING 11-20 '개별 종목 글').

구조(사용자 결정): ① 기업 소개 글 = 어떤 회사인지·규모·주요 사업·숫자(최대 낙폭·배당·이 회사를 담은 ETF와 비중).
제품·기술·발표 소식은 이 글에 쓰지 않고 신기술·특허 분야 글(③)에서 따로 자세히 - ③ 글 링크는 나중에 이 글 아래 목록으로 붙는다.
쓰지 않는 것: 목표주가·실적 전망·증권사 의견·최근 뉴스(작가가 자료 밖 숫자를 지어낼 위험 + 상록이 아님).
진입: python etf_auto.py --topic COMPANY:AAPL  (etf_auto가 run_company로 넘김)
자료: Yahoo Finance(회사 정보·재무·가격·배당·ETF 상위 보유 종목). 국내 ETF 보유 종목은 Yahoo에 없어 etf_auto의 네이버 수집을 씀.
"""
import re

COMPANIES = {
    # etfs: 이 회사를 상위에 담은 대표 ETF(보유 비중은 실행 때 자료로 확인 - 상위 10위 밖이면 표에서 빠짐)
    "AAPL": {"ko": "애플", "en": "Apple", "etfs": ["SPY", "QQQ", "XLK"], "seed": "애플 주식"},
    "MSFT": {"ko": "마이크로소프트", "en": "Microsoft", "etfs": ["SPY", "QQQ", "XLK"], "seed": "마이크로소프트 주식"},
    "NVDA": {"ko": "엔비디아", "en": "NVIDIA", "etfs": ["SPY", "QQQ", "SMH"], "seed": "엔비디아 주식"},
    "005930.KS": {"ko": "삼성전자", "en": "Samsung Electronics", "etfs": ["069500.KS", "091160.KS"], "seed": "삼성전자 주식"},
    # 11-21 사용자 '주식시장 큰 곳 알아보자' - 서학개미 보관금액 상위(예탁결제원 11-18: 테슬라·엔비디아·팔란티어·애플·알파벳·
    # 아이온큐·MS 순)와 시가총액 상위(11월 애플·엔비디아·MS·알파벳·아마존·브로드컴·TSMC·일라이 릴리·버크셔·SK하이닉스)를 합침
    "TSLA": {"ko": "테슬라", "en": "Tesla", "etfs": ["SPY", "QQQ", "XLY"], "seed": "테슬라 주식"},
    "GOOGL": {"ko": "알파벳", "en": "Alphabet", "etfs": ["SPY", "QQQ", "XLC"], "seed": "구글 주식"},
    "AMZN": {"ko": "아마존", "en": "Amazon", "etfs": ["SPY", "QQQ", "XLY"], "seed": "아마존 주식"},
    "META": {"ko": "메타", "en": "Meta Platforms", "etfs": ["SPY", "QQQ", "XLC"], "seed": "메타 주식"},
    "AVGO": {"ko": "브로드컴", "en": "Broadcom", "etfs": ["SPY", "QQQ", "SMH"], "seed": "브로드컴 주식"},
    "PLTR": {"ko": "팔란티어", "en": "Palantir", "etfs": ["SPY", "QQQ", "XLK"], "seed": "팔란티어 주식"},
    "TSM": {"ko": "TSMC", "en": "TSMC", "etfs": ["SMH", "SOXX"], "seed": "TSMC 주식"},
    "LLY": {"ko": "일라이 릴리", "en": "Eli Lilly", "etfs": ["SPY", "XLV"], "seed": "일라이릴리 주식"},
    "BRK-B": {"ko": "버크셔 해서웨이", "en": "Berkshire Hathaway", "etfs": ["SPY", "XLF"], "seed": "버크셔 해서웨이 주식"},
    "JPM": {"ko": "JP모건", "en": "JPMorgan Chase", "etfs": ["SPY", "XLF"], "seed": "JP모건 주식"},
    # 한국: 'ko'는 네이버 금융 보유 종목 표의 이름과 같아야 비중을 찾음(NAVER는 영문 표기)
    "000660.KS": {"ko": "SK하이닉스", "en": "SK hynix", "etfs": ["069500.KS", "091160.KS"], "seed": "SK하이닉스 주식"},
    "005380.KS": {"ko": "현대차", "en": "Hyundai Motor", "etfs": ["069500.KS", "091180.KS"], "seed": "현대차 주식"},
    "000270.KS": {"ko": "기아", "en": "Kia", "etfs": ["069500.KS", "091180.KS"], "seed": "기아 주식"},
    "373220.KS": {"ko": "LG에너지솔루션", "en": "LG Energy Solution", "etfs": ["069500.KS", "305720.KS"], "seed": "LG에너지솔루션 주식"},
    "207940.KS": {"ko": "삼성바이오로직스", "en": "Samsung Biologics", "etfs": ["069500.KS", "244580.KS"], "seed": "삼성바이오로직스 주식"},
    "105560.KS": {"ko": "KB금융", "en": "KB Financial Group", "etfs": ["069500.KS", "091170.KS"], "seed": "KB금융 주식"},
    "035420.KS": {"ko": "NAVER", "en": "NAVER", "etfs": ["069500.KS"], "seed": "네이버 주식"},
}

EMPTY = (None, "", "N/A", "nan")


def country_tag(ticker):
    """11-21 나라 태그(백로그 95): 본사 나라. 국내 상장은 한국, TSMC는 대만(미국 상장이지만 대만 회사), 나머지 미국."""
    if ticker.endswith(".KS") or ticker.isdigit():
        return "한국"
    return {"TSM": "대만"}.get(ticker, "미국")


def eun(word):
    """조사 은/는(11-21: '엔비디아은'·'테슬라은'이 표 제목에 나옴). 끝 글자에 받침이 있으면 '은'. 영문 끝(TSMC·NAVER)은 '는'."""
    ch = (word or "").strip()[-1:]
    if "가" <= ch <= "힣":
        return word + ("은" if (ord(ch) - 0xAC00) % 28 else "는")
    return word + ("은" if ch in "LMNlmn013678" else "는")
PAST_NOTE = "과거 자료로 계산한 값일 뿐 앞으로도 같다는 보장은 없음."


def norm(ticker):
    t = (ticker or "").strip().upper()
    return t + ".KS" if re.fullmatch(r"\d{6}", t) else t


def is_kr(ticker):
    return ticker.endswith((".KS", ".KQ"))


def money(v, kr=False, usd_krw=None):
    """큰 금액을 읽기 쉽게. 한국 회사는 원(조·억), 미국 회사는 달러(조·억 달러) + usd_krw가 있으면 원화 환산."""
    if not isinstance(v, (int, float)):
        return None
    if kr:
        return f"{v / 1e12:,.1f}조 원" if abs(v) >= 1e12 else f"{v / 1e8:,.0f}억 원"
    s = f"{v / 1e12:,.2f}조 달러" if abs(v) >= 1e12 else f"{v / 1e8:,.0f}억 달러"
    if usd_krw:
        krw = v * usd_krw
        s += f"(약 {krw / 1e12:,.0f}조 원)" if abs(krw) >= 1e12 else f"(약 {krw / 1e8:,.0f}억 원)"
    return s


def parse_profile(info):
    """yfinance info → 회사 기본 사실(값 없는 항목은 뺌)."""
    info = info or {}
    out = {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"), "industry": info.get("industry"),
        "country": info.get("country"), "city": info.get("city"),
        "employees": info.get("fullTimeEmployees"),
        "market_cap": info.get("marketCap"), "revenue": info.get("totalRevenue"),
        "currency": info.get("financialCurrency") or info.get("currency"),
        "summary": (info.get("longBusinessSummary") or "").strip(),
        "website": info.get("website"),
    }
    return {k: v for k, v in out.items() if v not in EMPTY}


def parse_financials(income_stmt, years=4):
    """yfinance income_stmt(행=항목, 열=회계연도 말일) → [(연도, 매출, 영업이익, 순이익)] 오래된 것부터."""
    if income_stmt is None or getattr(income_stmt, "empty", True):
        return []
    def row(*names):
        for n in names:
            if n in income_stmt.index:
                return income_stmt.loc[n]
        return None
    rev, op, net = row("Total Revenue", "Operating Revenue"), row("Operating Income"), row("Net Income", "Net Income Common Stockholders")
    if rev is None:
        return []
    out = []
    for col in income_stmt.columns:
        r = rev.get(col)
        try:
            r = float(r)
        except (TypeError, ValueError):
            continue
        if r != r:          # NaN
            continue
        f = lambda s: (float(s.get(col)) if s is not None and s.get(col) == s.get(col) and s.get(col) is not None else None)
        out.append((int(getattr(col, "year", str(col)[:4])), r, f(op), f(net)))
    out.sort(key=lambda x: x[0])
    return out[-years:]


def weight_in(holdings, symbol, name=""):
    """ETF 상위 보유 종목 표(DataFrame: index=Symbol, 'Holding Percent'(0~1) / 또는 [{'symbol','name','weight'(%)}]) → 비중 %."""
    if holdings is None:
        return None
    base = symbol.split(".")[0].upper()
    if isinstance(holdings, list):
        for h in holdings:
            s = str(h.get("symbol", "")).split(".")[0].upper()
            if s == base or (name and name in str(h.get("name", ""))):
                try:
                    return float(h.get("weight"))
                except (TypeError, ValueError):
                    return None
        return None
    if getattr(holdings, "empty", True):
        return None
    for idx, r in holdings.iterrows():
        if str(idx).split(".")[0].upper() == base or (name and name.lower() in str(r.get("Name", "")).lower()):
            try:
                v = float(r.get("Holding Percent"))
            except (TypeError, ValueError):
                return None
            return v * 100 if v <= 1 else v
    return None


def div_odd_lines(div, f2):
    """해마다 배당과, 다른 해보다 확 큰 해 표시(11-21 삼성전자: 2020년이 다른 해의 2배 가까이 - 시작 해가 이런 해면
    '연평균 -11%'처럼 실제 흐름보다 나쁘게 보임). 원인(특별배당 등)은 자료에 없으니 쓰지 않게."""
    ser = div.get("series") or []
    if len(ser) < 3:
        return []
    # 11-21 엔비디아: 꾸준히 늘어난 배당(2024·2025년)을 '가운데값의 1.5배'로 이상한 해라고 표시함 →
    # 앞뒤 해(있는 쪽) 모두보다 1.5배 넘게 튄 해만(삼성전자 2020년은 다음 해의 2배라 그대로 잡힘)
    odd = []
    for i, (y, v) in enumerate(ser):
        nb = [ser[j][1] for j in (i - 1, i + 1) if 0 <= j < len(ser)]
        if nb and min(nb) > 0 and v >= max(nb) * 1.5:
            odd.append(y)
    out = ["- 해마다 주당 배당: " + ", ".join(f"{y}년 {f2(v)}" for y, v in ser)]
    if odd:
        out.append(f"- {', '.join(f'{y}년' for y in odd)}은 앞뒤 해보다 지급이 크게 많았음(1.5배 넘음). "
                   f"시작 해가 이런 해면 연평균 증가율이 평소 흐름보다 나쁘게 나옴 - 연평균 숫자만으로 '배당이 줄고 있다'고 쓰지 말고 "
                   f"해마다 숫자를 함께 볼 것. 많았던 이유는 자료에 없으니 짐작해 쓰지 말 것")
    return out


def build(ticker, *, profile, fin, dd, div, weights, usd_krw=None, years_dd=10):
    """모은 자료 → (사실 자료 글, 시스템이 넣는 표 HTML). weights: [(ETF, 이름, 비중%)]."""
    from ondo.media import charts
    import guide_calcs as gc
    c = COMPANIES.get(ticker, {})
    kr = is_kr(ticker)
    code = ticker.replace(".KS", "").replace(".KQ", "")
    nm = c.get("ko") or profile.get("name") or code
    lines = [f"[회사 기본 정보 - Yahoo Finance 회사 정보]",
             f"- 이름: {nm} ({profile.get('name', c.get('en', ''))}, 종목 코드 {code}, {'한국' if kr else '미국'} 상장)"]
    for label, key in (("업종(섹터)", "sector"), ("세부 업종", "industry"), ("본사 국가", "country")):
        if profile.get(key):
            lines.append(f"- {label}: {profile[key]}")
    if profile.get("employees"):
        lines.append(f"- 직원 수(정규직): {int(profile['employees']):,}명")
    if profile.get("market_cap"):
        lines.append(f"- 시가총액(자료 받은 날 기준): {money(profile['market_cap'], kr, None if kr else usd_krw)}")
    if profile.get("summary"):
        lines.append("- 회사 소개 원문(Yahoo, 영어 - 이 범위 안에서만 우리말로 풀어 쓸 것, 원문에 없는 제품·비중·순위는 쓰지 말 것): "
                     + profile["summary"][:1500])
    rows_fin = []
    if fin:
        lines.append("[연간 실적 - Yahoo Finance 손익계산서, 회계연도 기준]")
        for y, r, op, net in fin:
            parts = [f"매출 {money(r, kr)}"]
            if op is not None:
                parts.append(f"영업이익 {money(op, kr)}(영업이익률 {op / r * 100:.1f}%)")
            if net is not None:
                parts.append(f"순이익 {money(net, kr)}")
            lines.append(f"- {y}년: " + ", ".join(parts))
            rows_fin.append([f"{y}년", money(r, kr), money(op, kr) if op is not None else "-",
                             f"{op / r * 100:.1f}%" if op is not None else "-", money(net, kr) if net is not None else "-"])
        if len(fin) >= 2 and fin[0][1] > 0:
            n = fin[-1][0] - fin[0][0]
            if n > 0:
                lines.append(f"- 매출 변화: {fin[0][0]}년 → {fin[-1][0]}년 {(fin[-1][1] / fin[0][1] - 1) * 100:+.1f}% "
                             f"(연평균 {((fin[-1][1] / fin[0][1]) ** (1 / n) - 1) * 100:+.1f}%)")
    if dd:
        rec = f"{dd['recover_days']:,}일 뒤({dd['recovered']}) 고점 가격 회복" if dd["recovered"] else "아직 고점 가격을 못 되찾음"
        lines += [f"[가격 흔들림 - 최근 {years_dd}년 일별 종가(배당 제외 가격), ondo 계산]",
                  f"- 최대 낙폭: {dd['pct']:.1f}% (고점 {dd['peak']} → 바닥 {dd['trough']}, 떨어지는 데 {dd['fall_days']:,}일)",
                  f"- 회복: {rec}",
                  f"- 지금 가격의 {years_dd}년 최고가 대비: {dd['now_vs_peak']:.1f}%",
                  f"- 1,000만 원을 그 고점에 넣었다면 가장 낮을 때 평가액: {gc._won(10_000_000 * (1 + dd['pct'] / 100))}"]
    if div:
        f2 = (lambda v: f"{v:,.0f}원") if kr else (lambda v: f"${v:.3f}" if abs(v) < 0.1 else f"${v:.2f}")   # 11-21 아주 작은 배당($0.016)이 $0.02로 뭉개짐
        lines += ["[배당 - Yahoo Finance 배당 지급 기록, 다 찬 해만, 세전]",
                  f"- 주당 연간 배당: {div['y0']}년 {f2(div['div0'])} → {div['y1']}년 {f2(div['div1'])}, {div['years']}년 연평균 {div['cagr']:+.1f}%",
                  f"- 지금 가격 기준 배당률: {div['yield_now']:.2f}%"]
        lines += div_odd_lines(div, f2)
    elif div is None:
        lines.append("[배당] - 배당 기록이 짧거나 없어 계산하지 않음(배당 이야기는 쓰지 말 것)")
    rows_w = []
    if weights:
        lines.append(f"[이 회사를 담은 ETF - 각 ETF 상위 보유 종목 자료(Yahoo Finance{'·네이버 금융' if kr else ''}), 자료 받은 날 기준]")
        for etf, ename, w in weights:
            share = 1_000_000 * w / 100
            lines.append(f"- {etf.replace('.KS', '')}({ename}): {nm} 비중 {w:.2f}% → 이 ETF에 100만 원을 넣으면 그중 약 {gc._won(share)}이 {nm} 몫")
            rows_w.append([f"{etf.replace('.KS', '')}" + (f" {ename}" if ename and ename != etf else ""), f"{w:.2f}%", gc._won(share)])
        lines.append("- 비중은 매일 조금씩 바뀜(가격 변동·리밸런싱). 직접 사면 100%가 이 회사, ETF로 사면 나머지는 다른 종목에 나뉨 - 어느 쪽이 낫다고 판단하지 말 것")
    facts = "\n".join(lines) + "\n"
    html = ""
    if rows_fin:
        html += charts.table_html(f"{nm} 연간 실적", ["회계연도", "매출", "영업이익", "영업이익률", "순이익"], rows_fin,
                                  "Yahoo Finance 손익계산서(회계연도 기준), ondo 정리." + ("" if kr else " 달러 기준."))
    if rows_w:
        html += charts.table_html(f"ETF로 사면 {eun(nm)} 얼마나 들어갈까", ["ETF", f"{nm} 비중", "100만 원 중 몫"], rows_w,
                                  "각 ETF 상위 보유 종목 자료(자료 받은 날 기준), ondo 계산. 비중은 매일 바뀜. " + PAST_NOTE.replace("과거 자료로 계산한 값일 뿐 ", ""))
    return facts, html


RULES = (
    "- [기업 소개 글 범위] 이 글은 회사가 무엇을 하는지·규모·숫자(실적·낙폭·배당·ETF 비중)를 정리하는 글입니다. "
    "신제품·발표·최근 뉴스·소송·경영진 이야기는 쓰지 마세요(자료에 없음 - 제품·기술 소식은 다른 글에서 따로 다룹니다).\n"
    "- [전망 금지] 목표주가·앞으로의 실적 전망·증권사 의견·'성장이 기대된다' 같은 예측을 쓰지 마세요. 과거와 지금의 숫자만.\n"
    "- [사업 설명] 회사 소개는 자료의 Yahoo 소개 원문 범위 안에서만 쓰세요. 원문에 없는 제품별 매출 비중·시장 점유율·순위는 쓰지 마세요.\n"
    "- [직접 vs ETF] 직접 사는 것과 ETF로 사는 것 중 무엇이 낫다고 판단하지 마세요. 비중 숫자로 '얼마가 들어가는지'만 보여 주세요.\n"
)


# ------------------------------------------------------------
# 자료 받기(네트워크) + 진입점
# ------------------------------------------------------------

def _collect(ticker, ea, macro_data):
    import yfinance as yf
    import guide_calcs as gc
    t = yf.Ticker(ticker)
    try:
        profile = parse_profile(t.info)
    except Exception as e:
        print(f"⚠️ 회사 정보 실패: {type(e).__name__}: {e}")
        profile = {}
    try:
        fin = parse_financials(t.income_stmt)
    except Exception as e:
        print(f"⚠️ 실적 자료 실패: {type(e).__name__}: {e}")
        fin = []
    h = gc._hist(ticker, period="10y")
    dd = gc.calc_drawdown(h["Close"]) if h is not None else None
    div = None
    try:
        hd = gc._hist(ticker, period="10y", adjust=False)
        if hd is not None and "Dividends" in hd:
            div = gc.calc_dividend(hd["Dividends"][hd["Dividends"] > 0], hd["Close"], years=5)
            if div is None and float(hd["Dividends"].sum()) > 0:
                div = False          # 배당은 있으나 5년치가 안 됨 → '배당 쓰지 말 것' 줄도 안 넣음
    except Exception as e:
        print(f"⚠️ 배당 자료 실패: {type(e).__name__}: {e}")
    c = COMPANIES.get(ticker, {})
    weights, driver = [], None
    try:
        for etf in c.get("etfs", []):
            w, ename = None, etf
            try:
                if is_kr(etf):
                    if driver is None:
                        driver = ea._create_chrome_driver()
                    d = ea.get_etf_real_data(etf, driver, macro_data) or {}
                    ename = d.get("name") or etf
                    w = weight_in(d.get("top_holdings") or [], ticker, c.get("ko", ""))
                else:
                    fd = yf.Ticker(etf).funds_data
                    w = weight_in(fd.top_holdings, ticker, c.get("en", ""))
                    try:
                        inf = yf.Ticker(etf).info      # 11-20: shortName은 잘림('…S&P 500 ETF T') → longName 먼저
                        ename = inf.get("longName") or inf.get("shortName") or etf
                    except Exception:
                        ename = etf
            except Exception as e:
                print(f"⚠️ {etf} 보유 종목 실패: {type(e).__name__}: {e}")
            if isinstance(w, (int, float)) and 0 < w <= 100:
                weights.append((etf, ename, w))
    finally:
        if driver:
            driver.quit()
    return profile, fin, dd, div, weights


def title_seed(ticker, has_weights=True, has_div=True):
    c = COMPANIES.get(ticker, {})
    nm = c.get("ko") or ticker
    tail = ", 그리고 ETF로 사면 담기는 비중" if has_weights else ""      # 11-21: 비중 자료 없으면 제목에서도 뺌
    head = "매출·낙폭·배당" if has_div else "매출·낙폭"                 # 11-22 테슬라: 배당 없는데 제목에 '배당' → 첫 판 '치명'
    return f"{eun(nm)} 어떤 회사인가: {head}{tail}"


def closing_html(ticker, weights, has_div=True):
    from ondo.media import sources
    links = [sources.ticker_link(ticker)] + [sources.ticker_link(e) for e, _, _ in weights]
    kr = is_kr(ticker)
    return ('<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-radius:6px;font-size:13px;line-height:1.7;">'
            '<strong>📌 데이터 출처</strong><br/>회사 정보·실적·가격' + ("·배당" if has_div else "") + ("·ETF 보유 종목" if weights and not kr else "")
            + ": Yahoo Finance" + (", 국내 ETF 보유 종목: 네이버 금융" if kr and weights else "")   # 11-21: 비중 못 받았으면 안 적음
            + sources.check_line(links) + "</div>"
            '<p style="margin-top:20px;font-size:12px;color:#5c6575;line-height:1.7;">'
            "이 글은 공개 데이터를 정리한 정보 제공용 글이며, 특정 종목의 매수·매도를 권유하지 않습니다. 투자 판단과 책임은 본인에게 있습니다.</p>")


def run_company(ticker, ea):
    ticker = norm(ticker)
    if ticker not in COMPANIES:
        print(f"❌ 아직 준비 안 된 회사: {ticker} (ondo/company.py COMPANIES에 넣어야 함)")
        return
    macro = ea.get_macro_data()
    try:
        usd_krw = float(str(macro.get("usd_krw", "")).replace("원", "").replace(",", ""))
    except ValueError:
        usd_krw = None
    profile, fin, dd, div, weights = _collect(ticker, ea, macro)
    if not profile and not fin and not dd:
        print("❌ 자료를 거의 못 받아 글을 쓰지 않음")
        return
    facts, visual = build(ticker, profile=profile, fin=fin, dd=dd, div=div, weights=weights, usd_krw=usd_krw)
    from topic_engine import produce_article
    import explainer_engine as xe
    c = COMPANIES[ticker]
    produce_article(kind_label="기업 소개", title_seed=title_seed(ticker, bool(weights), div is not None), facts_text=facts,
                    rules=xe._SECTION_RULES + RULES + ("- [표 금지] 이 글에는 시스템이 계산표를 넣습니다. 본문에 <table>을 새로 만들지 말고, "
                                                       "숫자는 문장으로 해석하세요.\n" if "<table" in visual else ""),
                    category_label="ETF/기업 소개", article_type="company", topic_id=ticker.replace(".KS", ""),
                    closing_html=closing_html(ticker, weights, div is not None), visual_html=visual,
                    meta={"company": ticker, "company_ko": c["ko"], "tags": [c["ko"], country_tag(ticker)]}, search_seed=c.get("seed", ""))
