"""ETF 목록: 국내 ETF 자동 발굴(네이버)·분류·테마/그룹·표시 이름.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.config import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
# 국내 ETF 자동 발굴: 네이버 금융 ETF 목록에서 거래대금 상위 종목을 그날의 후보에 더한다.
# 이름으로 주제/지수 묶음을 정해서, 같은 지수의 다른 운용사 상품(예: TIGER·KODEX·ACE
# S&P500)끼리 비교 글을 만들 수 있게 한다. 레버리지·인버스는 금융 글 위험이 커서 제외.
KR_DYNAMIC_TOP_N = 40
_KR_EXCLUDE_PATTERN = r"레버리지|인버스|2X|곱버스|합성.*인버스"
_KR_UNDERLYING_RULES = [
    # (이름 패턴, 묶음, 주제) - 위에서부터 먼저 맞는 것을 쓴다
    (r"S&P\s?500|에스앤피500", "S&P500", "미국 대표지수"),
    (r"나스닥\s?100|NASDAQ\s?100", "나스닥100", "미국 대표지수"),
    (r"배당다우존스", "미국 배당다우존스", "배당"),
    (r"다우존스\s?30|다우30", "다우30", "미국 대표지수"),
    (r"테크\s?TOP\s?10|빅테크|매그니피센트|M7", "미국 빅테크", "섹터"),
    (r"반도체", "반도체", "섹터"),
    (r"2차전지|이차전지", "2차전지", "섹터"),
    (r"골드|금현물|금선물", "금", "원자재"),
    (r"은선물|실버", "은", "원자재"),
    (r"CD.{0,3}금리|KOFR|SOFR|머니마켓|MMF|단기금리|초단기", "파킹형(초단기금리)", "채권"),
    (r"미국채\s?30년|미국\s?30년|30년국채", "미국 장기국채", "채권"),
    (r"미국채\s?10년|미국\s?10년", "미국 중기국채", "채권"),
    (r"국고채\s?10년", "한국 국고채10년", "채권"),
    (r"국고채\s?30년", "한국 국고채30년", "채권"),
    (r"코스닥\s?150", "코스닥150", "국내 주식"),
    (r"(^|\s)200(TR)?$|코스피\s?200|KOSPI\s?200", "코스피200", "국내 주식"),
]
_KR_CATEGORY_THEME = {"1": "국내 주식", "2": "섹터", "4": "해외 주식", "5": "원자재", "6": "채권"}
_DYNAMIC_UNIVERSE = {}


def _classify_kr_etf(name, category=None):
    """국내 ETF 이름(과 네이버 분류)으로 (주제, 묶음)을 정한다. 제외 대상이면 None."""
    name = str(name or "")
    if str(category) == "3" or re.search(_KR_EXCLUDE_PATTERN, name, flags=re.IGNORECASE):
        return None
    underlying = next(((g, th) for pat, g, th in _KR_UNDERLYING_RULES
                       if re.search(pat, name, flags=re.IGNORECASE)), None)
    if re.search(r"커버드콜|프리미엄|타겟위클리|위클리|옵션", name):
        return "커버드콜", f"커버드콜:{underlying[0] if underlying else name}"
    if underlying:
        return underlying[1], underlying[0]
    if re.search(r"배당", name):
        return "배당", name
    return _KR_CATEGORY_THEME.get(str(category), "기타"), name


_KR_ETF_NAMES = {}


NAVER_KR_INFO_URL = "https://m.stock.naver.com/api/stock/{code}/integration"


def _naver_kr_pairs(data):
    """네이버 모바일 종목 데이터(JSON)에서 {'key': 이름, 'value': 값} 묶음을 모두 모아 {이름: 값}으로."""
    out = {}

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("key"), str) and "value" in x:
                out.setdefault(x["key"], str(x["value"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return out


def _naver_kr_info(code):
    """국내 ETF 펀드보수·기초지수 등(2026-11-08). 깃허브 서버에선 네이버 금융 화면에 '보수'가 안 나와(요소 없음) 국내 운용사
    비교 글의 핵심인 보수가 비었다 → check_sources 진단으로 열리는 것을 확인한 모바일 데이터 주소에서 읽는다. 실패하면 {}."""
    try:
        r = requests.get(NAVER_KR_INFO_URL.format(code=str(code).replace(".KS", "")), timeout=(8, 20),
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        return _naver_kr_pairs(r.json()) if r.status_code == 200 else {}
    except Exception as e:
        print(f"   ⚠️ 네이버 모바일 종목 자료 실패: {type(e).__name__}")
        return {}


def _kr_etf_name(code):
    """국내 ETF 코드 → 이름(KRX ETF 목록). 실패하면 None."""
    if not _KR_ETF_NAMES:
        try:
            df = fdr.StockListing('ETF/KR')
            _KR_ETF_NAMES.update({str(r.get('Symbol', '')).zfill(6): str(r.get('Name', '')) for _, r in df.iterrows()})
        except Exception as e:
            print(f"ℹ️ 국내 ETF 이름 목록 못 받음: {type(e).__name__}")
            return None
    return _KR_ETF_NAMES.get(str(code).replace('.KS', '').zfill(6)) or None


def load_dynamic_kr_etfs(top_n=KR_DYNAMIC_TOP_N):
    """거래대금 상위 국내 ETF를 불러와 _DYNAMIC_UNIVERSE에 채운다. 실패해도 고정 목록만으로 진행."""
    if _DYNAMIC_UNIVERSE:
        return _DYNAMIC_UNIVERSE
    try:
        df = fdr.StockListing('ETF/KR')
        if 'Amount' in df.columns:
            df = df.sort_values('Amount', ascending=False)
        added = 0
        for _, row in df.iterrows():
            if added >= top_n:
                break
            code = f"{str(row.get('Symbol', '')).zfill(6)}.KS"
            meta = _classify_kr_etf(row.get('Name'), row.get('Category'))
            if not meta or code in ETF_UNIVERSE:
                continue
            _DYNAMIC_UNIVERSE[code] = {"theme": meta[0], "group": meta[1], "name": str(row.get('Name'))}
            added += 1
        print(f"✅ 거래대금 상위 국내 ETF {len(_DYNAMIC_UNIVERSE)}개를 후보에 추가했습니다.")
    except Exception as e:
        print(f"⚠️ 국내 ETF 목록 조회 실패(고정 목록만으로 진행): {type(e).__name__}: {e}")
    return _DYNAMIC_UNIVERSE


def _universe():
    merged = dict(_DYNAMIC_UNIVERSE)
    merged.update(ETF_UNIVERSE)
    return merged


def _normalize_ticker(raw):
    t = str(raw).strip().upper()
    if re.fullmatch(r"\d{6}", t):
        t += ".KS"
    return t


def _etf_meta(ticker, name=None):
    """티커의 주제/묶음/이름. 목록에 없는 국내 ETF는 이름이 있으면 이름으로 분류한다
    (예전에 자동 발굴로 썼던 종목도 발행 기록에 저장된 이름으로 다시 분류됨)."""
    t = _normalize_ticker(ticker)
    meta = _universe().get(t)
    if meta:
        return meta
    if name and t.endswith(".KS"):
        cls = _classify_kr_etf(name)
        if cls:
            return {"theme": cls[0], "group": cls[1], "name": name}
    return {"theme": "기타", "group": t, "name": name or t}


def _etf_theme(ticker, name=None):
    return _etf_meta(ticker, name)["theme"]


def _etf_group(ticker, name=None):
    return _etf_meta(ticker, name)["group"]


def _etf_display_name(ticker):
    t = _normalize_ticker(ticker)
    name = _universe().get(t, {}).get("name")
    return name or t.replace(".KS", "")


def _article_ticker_names(article):
    data = article.get('etf_data') or article.get('topic_data') or {}
    return {_normalize_ticker(k): (v or {}).get('name') for k, v in data.items()
            if not str(k).startswith('_') and isinstance(v, dict)}


def _article_tickers(article):
    """저장된 글 기록에서 그 글이 다룬 티커 목록을 꺼낸다. 발행 때 함께 저장된
    데이터(etf_data/topic_data)의 키를 우선 쓰고, 없으면 제목에서 티커를 찾는다.
    제목 검색은 앞뒤가 영숫자가 아닐 때만 인정해 QQQM 글을 QQQ로 착각하지 않는다."""
    data = article.get('etf_data') or article.get('topic_data') or {}
    keys = [_normalize_ticker(k) for k in data if not str(k).startswith('_')]
    if keys:
        return keys
    title = article.get('title', '')
    found = []
    for t in _universe():
        code = t.replace('.KS', '')
        if re.search(rf'(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])', title):
            found.append(t)
    return found

__all__ = [k for k in dir() if not k.startswith('__')]
