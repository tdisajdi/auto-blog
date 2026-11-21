"""세계 주식시장 지도 페이지(2026-11-21 사용자 '나라별 시가총액 같은 건 여러 자료를 통합해 ondo 식으로, 출처 명확히').

  python site_pages/market_map.py draft     # 깃허브 실행(site_pages=market-map) - 비공개 초안 페이지로 올림(공개는 사용자 확인 뒤)
  python site_pages/market_map.py publish   # 공개(11-21 사용자 '공개하자'), 이미 공개면 숫자만 갱신
  python site_pages/market_map.py preview   # 자료만 받아 lab/market_map.html·json 으로 저장(올리지 않음)

자료(모두 코드가 받아 계산, 숫자를 손으로 적지 않음):
- 세계은행 WDI CM.MKT.LCAP.CD: 상장 국내 기업 시가총액(현재 달러, 원자료는 세계거래소연맹 WFE) - 나라마다 가장 최근 연도
- 세계은행 WDI CM.MKT.LCAP.GD.ZS: 시가총액 ÷ GDP(%)
- Yahoo Finance: 나라별 미국 상장 대표 ETF 가격(배당 반영)·원/달러 환율 → 1년 수익(달러·원화 환산), 5년 최대 낙폭(배당 제외 가격)
세계은행에 대만 자료는 없음(표에 '자료 없음'). 연도가 나라마다 다를 수 있어 표에 연도를 함께 적는다.
"""
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SLUG = "world-stock-markets"
TITLE = "세계 주식시장 지도: 나라별 시가총액과 투자하는 길"
WB = "https://api.worldbank.org/v2/country/{codes}/indicator/{ind}"
WB_PAGE = "https://data.worldbank.org/indicator/{ind}"

# (세계은행 코드, 이름, 미국 상장 대표 ETF, 국내 상장 같은 나라 ETF 예시 - 확인된 것만, ondo 글 주소 조각)
COUNTRIES = [
    ("USA", "미국", "SPY", "", ""),
    ("CHN", "중국", "MCHI", "TIGER 차이나CSI300", ""),
    ("JPN", "일본", "EWJ", "TIGER 일본니케이225", ""),
    ("HKG", "홍콩", "EWH", "", ""),
    ("IND", "인도", "INDA", "TIGER 인도니프티50", ""),
    ("CAN", "캐나다", "EWC", "", ""),
    ("GBR", "영국", "EWU", "", ""),
    ("FRA", "프랑스", "EWQ", "", ""),
    ("DEU", "독일", "EWG", "", ""),
    ("SAU", "사우디아라비아", "KSA", "", ""),
    ("CHE", "스위스", "EWL", "", ""),
    ("KOR", "한국", "EWY", "KODEX 200 등 국내 주식", ""),
    ("AUS", "호주", "EWA", "", ""),
    ("TWN", "대만", "EWT", "", ""),          # 세계은행 자료 없음
]


def wb_latest(ind, codes, n=1):
    """세계은행 지표의 나라별 최근 값. n=1이면 {코드: (연도, 값)}, n=2면 {코드: [(최근), (그 전)]}."""
    import requests
    r = requests.get(WB.format(codes=";".join(codes), ind=ind), params={"format": "json", "mrnev": n, "per_page": 800},
                     timeout=40)
    j = r.json()
    out = {}
    for row in (j[1] if isinstance(j, list) and len(j) > 1 and j[1] else []):
        if row.get("value") is not None:
            out.setdefault(row["countryiso3code"], []).append((int(row["date"]), float(row["value"])))
    for k in out:
        out[k].sort(reverse=True)
    return {k: v[0] for k, v in out.items()} if n == 1 else out


def jump_flag(series, etf_ratio=None):
    """11-21: 세계은행 인도 시가총액이 2024년 5.13조 → 2025년 10.56조 달러(1년에 2배)인데 인도 ETF 값은 거의 그대로 -
    집계 방식이 바뀐 것으로 보임. 반면 한국은 1.8배였지만 같은 해 한국 ETF도 크게 올라 실제 변화.
    → 시가총액 변화 배수를 같은 해 그 나라 ETF 가격 변화(달러)와 견줘 1.5배 넘게 어긋나면 (그 전 해, 값)을 돌려줌.
    ETF 자료가 없으면 2배 넘게 바뀐 경우만."""
    if not series or len(series) < 2:
        return None
    (y1, v1), (y0, v0) = series[0], series[1]
    if v0 <= 0 or y1 - y0 != 1:
        return None
    cap_ratio = v1 / v0
    gap = cap_ratio / etf_ratio if etf_ratio else cap_ratio
    lim = 1.5 if etf_ratio else 2.0
    if gap > lim or gap < 1 / lim:
        return (y0, v0)
    return None


def year_ratio(close, y0, y1):
    """연말 가격 비율(y1년 마지막 거래일 ÷ y0년 마지막 거래일). 자료가 없으면 None."""
    try:
        a = close[close.index.year == y0]
        b = close[close.index.year == y1]
        if len(a) and len(b):
            return float(b.iloc[-1]) / float(a.iloc[-1])
    except Exception:
        pass
    return None


def etf_stats(t, fx):
    """1년 달러 수익·원화 환산 수익(배당 반영), 5년 최대 낙폭(배당 제외 가격)."""
    import guide_calcs as gc
    import pandas as pd
    h = gc._hist(t, period="2y")
    p = gc._hist(t, period="5y", adjust=False)
    out = {}
    if h is not None and fx is not None:
        a = pd.concat([h["Close"].rename("u"), fx["Close"].rename("f")], axis=1, join="inner").dropna()
        if len(a) > 252:
            seg = a.iloc[-253:]
            out["start"] = f"{seg.index[0]:%Y-%m-%d}"
            out["usd"] = (seg["u"].iloc[-1] / seg["u"].iloc[0] - 1) * 100
            out["krw"] = ((seg["u"].iloc[-1] * seg["f"].iloc[-1]) / (seg["u"].iloc[0] * seg["f"].iloc[0]) - 1) * 100
    if p is not None:
        d = gc.calc_drawdown(p["Close"])
        if d:
            out["mdd"] = d["pct"]
    return out


def collect():
    import guide_calcs as gc
    codes = [c[0] for c in COUNTRIES if c[0] != "TWN"] + ["WLD"]
    cap2 = wb_latest("CM.MKT.LCAP.CD", codes, n=2)
    cap = {k: v[0] for k, v in cap2.items()}
    gdp = wb_latest("CM.MKT.LCAP.GD.ZS", codes)
    fx = gc._hist("KRW=X", period="2y")
    rows = []
    for code, ko, etf, kr, link in COUNTRIES:
        st = {}
        try:
            st = etf_stats(etf, fx)
        except Exception as e:
            print(f"ℹ️ {etf} 가격 실패: {type(e).__name__}")
        ser = cap2.get(code)
        er = None
        if ser and len(ser) > 1:
            try:
                hh = gc._hist(etf, period="5y")
                er = year_ratio(hh["Close"], ser[1][0], ser[0][0]) if hh is not None else None
            except Exception:
                er = None
        rows.append({"code": code, "ko": ko, "etf": etf, "kr": kr, "link": link,
                     "cap": cap.get(code), "gdp": gdp.get(code), "jump": jump_flag(ser, er), "etf_year_ratio": er, **st})
    return {"world": cap.get("WLD"), "rows": rows}


def _pct(x, d=1):
    return "-" if x is None else f"{x:+.{d}f}%"


def build_html(data):
    """자료 → 페이지 본문 HTML(인터넷 없이 시험할 수 있게 계산과 분리)."""
    from ondo.media import charts
    world = data.get("world")
    rows = [r for r in data["rows"]]
    rows.sort(key=lambda r: -(r["cap"][1] if r.get("cap") else -1))
    years = sorted({r["cap"][0] for r in rows if r.get("cap")})
    yr = f"{years[0]}년" if len(years) == 1 else (f"{years[0]}~{years[-1]}년" if years else "")
    trow = []
    flags = []
    for i, r in enumerate(rows, 1):
        c = r.get("cap")
        jp = r.get("jump")
        share = (c[1] / world[1] * 100) if (c and world and world[0] == c[0] and not jp) else None
        cell = f"{c[1] / 1e12:,.2f}조 달러 ({c[0]})" if c else "세계은행 자료 없음"
        if jp:
            cell += f" ※ {jp[0]}년 {jp[1] / 1e12:,.2f}조"
            er = r.get("etf_year_ratio")
            flags.append(f"{r['ko']}: {c[0]}년 값이 {jp[0]}년({jp[1] / 1e12:,.2f}조 달러)의 {c[1] / jp[1]:.1f}배인데"
                         + (f", 같은 해 {r['etf']} 가격은 {(er - 1) * 100:+.0f}%만 움직였습니다" if er else "")
                         + ". 집계 방식이 달라졌을 수 있어 세계 대비 비중에서 뺐습니다.")
            flags.append("세계은행 세계 합계에는 이 값이 그대로 들어 있어, 다른 나라의 '세계 대비' 비중이 실제보다 조금 낮게 나올 수 있습니다.")
        if c and world and c[0] < world[0] - 2:
            flags.append(f"{r['ko']}: 세계은행의 가장 최근 값이 {c[0]}년이라 다른 나라와 시점이 다릅니다.")
        trow.append([str(i) if c else "-", r["ko"], cell,
                     f"{share:.1f}%" if share is not None else "-",
                     f"{r['gdp'][1]:,.0f}%" if r.get("gdp") else "-",
                     r["etf"], _pct(r.get("usd")), _pct(r.get("krw")), _pct(r.get("mdd"))])
    note = ("시가총액·GDP 대비: 세계은행 세계개발지표(WDI) CM.MKT.LCAP.CD·CM.MKT.LCAP.GD.ZS(원자료 세계거래소연맹 WFE), 나라마다 가장 최근 연도. "
            "세계 대비 = 그 나라 ÷ 세계 합계(같은 연도일 때만). ETF 1년 수익: Yahoo Finance 종가(배당 반영), 원화 환산 = 달러 가격 × 원/달러 환율. "
            "최대 낙폭: 최근 5년, 배당 제외 가격. ETF는 그 나라 주식을 담은 미국 상장 대표 ETF 하나일 뿐 그 나라 시장 전체와 같지 않음. "
            "ondo 계산. 과거 자료로 계산한 값일 뿐 앞으로도 같다는 보장은 없음.")
    table = charts.table_html(f"나라별 주식시장 크기와 대표 ETF ({yr} 시가총액 기준)",
                              ["순위", "나라", "상장 기업 시가총액", "세계 대비", "GDP 대비", "미국 상장 대표 ETF",
                               "1년 수익(달러)", "1년 수익(원화 환산)", "5년 최대 낙폭"], trow, note)
    top = [r for r in rows if r.get("cap") and world and r["cap"][0] == world[0] and not r.get("jump")][:10]   # 같은 연도·급변 없는 것만
    chart = ""
    if world and top:
        chart = charts.plotly_html({"title": "세계 주식시장에서 각 나라가 차지하는 비중(%)", "kind": "bar", "unit": "%",
                                    "labels": [r["ko"] for r in top],
                                    "values": [round(r["cap"][1] / world[1] * 100, 1) for r in top],
                                    "source": "세계은행 WDI(원자료 WFE), ondo 계산"})
    us = next((r for r in rows if r["code"] == "USA"), None)
    us_share = (us["cap"][1] / world[1] * 100) if (us and us.get("cap") and world and us["cap"][0] == world[0]) else None
    kr_list = "".join(f"<li>{html.escape(r['ko'])}: 국내 상장 {html.escape(r['kr'])} / 미국 상장 {r['etf']}</li>"
                      for r in rows if r.get("kr"))
    intro = (f"<p>세계 주식시장에서 어느 나라가 얼마나 큰지, 그리고 그 나라 주식에 어떤 길로 투자할 수 있는지를 공개 자료로 한 페이지에 모았습니다. "
             + (f"세계은행 자료로 보면 미국 상장 기업의 시가총액은 세계 전체의 약 {us_share:.0f}%입니다. " if us_share else "")
             + "숫자는 모두 코드가 공식 자료에서 받아 계산했고, 아래에 출처를 밝혔습니다.</p>")
    how = ("<h3>이 표를 읽는 법</h3>"
           "<p><strong>시가총액</strong>은 그 나라 거래소에 상장된 국내 기업 주식의 값을 모두 더한 것입니다. "
           "<strong>GDP 대비</strong>는 시가총액을 그 나라 한 해 경제 규모(GDP)로 나눈 값으로, 100%가 넘으면 주식시장이 경제 규모보다 크다는 뜻입니다. "
           "같은 기업이 여러 나라에 상장하거나, 해외에 상장한 기업(예: 미국에 상장한 중국 기업)은 나라별 합계에서 다르게 잡힐 수 있습니다.</p>"
           "<p><strong>원화 환산 수익</strong>은 달러로 거래되는 ETF를 원화로 바꿨을 때의 수익입니다. 달러 수익과의 차이는 그 기간 원/달러 환율 변화에서 나옵니다.</p>")
    invest = ("<h3>한국에서 이 나라들에 투자하는 길</h3>"
              "<p>한국 투자자는 같은 나라 주식에 크게 두 가지 길로 투자할 수 있습니다. 국내 상장 ETF는 원화로 거래되고 ISA·연금저축 계좌에서도 살 수 있습니다. "
              "미국 상장 ETF는 달러로 거래되고, 이 계좌들로는 직접 살 수 없습니다. 같은 나라라도 따르는 지수가 다르면 담은 종목과 수익률이 다릅니다.</p>"
              + (f"<ul>{kr_list}</ul>" if kr_list else "")
              + "<p>외국 투자자는 자기 나라 증권사를 통해 미국 상장 나라별 ETF(예: 한국은 EWY)나 그 나라 거래소에 직접 투자합니다.</p>")
    src = ('<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-radius:6px;font-size:13px;line-height:1.7;">'
           "<strong>📌 데이터 출처</strong><br/>"
           f'시가총액: <a href="{WB_PAGE.format(ind="CM.MKT.LCAP.CD")}" target="_blank" rel="noopener nofollow">세계은행 WDI - 상장 국내 기업 시가총액(현재 달러)</a> '
           '(원자료 <a href="https://www.world-exchanges.org/our-work/statistics" target="_blank" rel="noopener nofollow">세계거래소연맹 WFE</a>)<br/>'
           f'GDP 대비: <a href="{WB_PAGE.format(ind="CM.MKT.LCAP.GD.ZS")}" target="_blank" rel="noopener nofollow">세계은행 WDI - 시가총액(GDP 대비 %)</a><br/>'
           "ETF 가격·환율: Yahoo Finance · 계산: ondo<br/>"
           "세계은행 자료는 1년에 한 번 갱신되어 최근 연도가 1~2년 전일 수 있습니다. 대만은 세계은행 자료에 없습니다.</div>")
    disc = ('<p style="margin-top:20px;font-size:12px;color:#5c6575;line-height:1.7;">이 페이지는 공개 데이터를 정리한 정보 제공용이며, '
            "특정 나라·상품의 매수·매도를 권유하지 않습니다. 투자 판단과 책임은 본인에게 있습니다.</p>")
    warn = ("<h3>자료를 볼 때 주의할 점</h3><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in flags) + "</ul>") if flags else ""
    return intro + table + chart + warn + how + invest + src + disc


def main(mode="preview"):
    data = collect()
    page_html = build_html(data)
    os.makedirs(os.path.join(ROOT, "lab"), exist_ok=True)
    json.dump(data, open(os.path.join(ROOT, "lab", "market_map.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    open(os.path.join(ROOT, "lab", "market_map.html"), "w", encoding="utf-8").write(page_html)
    print("세계 합계:", data.get("world"), "| 나라:", [(r["ko"], r.get("cap")) for r in data["rows"]])
    if mode not in ("draft", "publish"):
        return 0
    from site_pages.upload import upsert_page, refresh_page
    page = {"slug": SLUG, "title": TITLE, "html": page_html}
    # 11-21 사용자 '공개하자' - publish는 초안을 공개로. 이미 공개된 페이지면 숫자만 새로(refresh)
    ok, msg = upsert_page(page, mode)
    if not ok and "이미 있어 건드리지 않음" in msg:
        ok, msg = refresh_page(page)
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["preview"])))
