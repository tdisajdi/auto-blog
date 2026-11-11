"""'직접 확인하는 곳' 링크(2026-11-11, Threads 응용 - 독자가 숫자를 원자료에서 스스로 확인하게).

글 끝 출처 상자에 '직접 확인: …' 한 줄로 붙인다. 코드가 붙이므로 작가 지시문과는 무관.
주소는 종목 코드·통계표 번호로 만드는 고정 형식만 쓴다(검색 결과·기사 주소 X).
"""
import html
import re


def _a(url, label):
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener nofollow">{html.escape(label)}</a>'


def ticker_link(ticker):
    t = (ticker or "").strip()
    m = re.fullmatch(r"(\d{6})(?:\.K[SQ])?", t)
    if m:   # 국내 상장(6자리) → 네이버 금융 종목 페이지
        return _a(f"https://finance.naver.com/item/main.naver?code={m.group(1)}", f"{m.group(1)} 네이버 금융")
    if re.fullmatch(r"[A-Z0-9.^=\-]{1,12}", t):
        return _a(f"https://finance.yahoo.com/quote/{t}", f"{t} Yahoo Finance")
    return ""


def kosis_link(org, tbl, name):
    return _a(f"https://kosis.kr/statHtml/statHtml.do?orgId={org}&tblId={tbl}", f"KOSIS '{name}' 통계표")


EIA_PAGES = {
    "oil": ("https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=WCESTUS1&f=W", "EIA 미국 상업용 원유 재고(주간)"),
    "gas": ("https://ir.eia.gov/ngs/ngs.html", "EIA 천연가스 저장량 주간 보고"),
}


def eia_link(kind):
    p = EIA_PAGES.get(kind)
    return _a(*p) if p else ""


def check_line(links):
    links = [x for x in links if x]
    if not links:
        return ""
    return "<br/>직접 확인: " + " · ".join(links)
