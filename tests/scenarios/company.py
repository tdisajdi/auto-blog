"""2026-11-20: 기업 소개 글 자료(ondo/company.py) - 가짜 Yahoo 자료로 사실 글·표가 맞게 나오는지(네트워크 없음)."""
import os, sys
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import pandas as pd
from ondo import company as co
import guide_calcs as gc

assert co.norm("005930") == "005930.KS" and co.norm("aapl") == "AAPL"
assert co.money(3.5e12) == "3.50조 달러" and co.money(9.4e10) == "940억 달러"
assert co.money(1e11, usd_krw=1400) == "1,000억 달러(약 140조 원)", co.money(1e11, usd_krw=1400)
assert co.money(3.0e14, kr=True) == "300.0조 원"

p = co.parse_profile({"longName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
                      "fullTimeEmployees": 164000, "marketCap": 3.5e12, "longBusinessSummary": "Apple designs phones.", "country": "N/A"})
assert p["name"] == "Apple Inc." and "country" not in p and p["employees"] == 164000

cols = [pd.Timestamp("2022-09-30"), pd.Timestamp("2023-09-30"), pd.Timestamp("2024-09-30"), pd.Timestamp("2025-09-30")][::-1]
inc = pd.DataFrame([[416e9, 391e9, 383e9, 394e9], [133e9, 123e9, 114e9, 119e9], [112e9, 94e9, 97e9, 100e9]],
                   index=["Total Revenue", "Operating Income", "Net Income"], columns=cols)
fin = co.parse_financials(inc)
assert [f[0] for f in fin] == [2022, 2023, 2024, 2025] and fin[-1][1] == 416e9, fin
assert co.parse_financials(None) == [] and co.parse_financials(pd.DataFrame()) == []

h = pd.DataFrame({"Name": ["NVIDIA", "Apple Inc", "Microsoft"], "Holding Percent": [0.075, 0.068, 0.062]},
                 index=pd.Index(["NVDA", "AAPL", "MSFT"], name="Symbol"))
assert abs(co.weight_in(h, "AAPL") - 6.8) < 1e-9
assert co.weight_in(h, "TSLA") is None and co.weight_in(None, "AAPL") is None
assert co.weight_in([{"symbol": "-", "name": "삼성전자", "weight": 24.5}], "005930.KS", "삼성전자") == 24.5

days = pd.bdate_range("2016-01-04", periods=2500)
vals = [100 + i * 0.05 for i in range(1200)] + [160 - i * 0.2 for i in range(200)] + [120 + i * 0.1 for i in range(1100)]
dd = gc.calc_drawdown(pd.Series(vals, index=days))
facts, html = co.build("AAPL", profile=p, fin=fin, dd=dd, div=None,
                       weights=[("SPY", "SPDR S&P 500", 6.8), ("QQQ", "Invesco QQQ", 8.9)], usd_krw=1400)
for s in ["애플 (Apple Inc., 종목 코드 AAPL, 미국 상장)", "직원 수(정규직): 164,000명", "3.50조 달러(약 4,900조 원)",
          "2025년: 매출 4,160억 달러, 영업이익 1,330억 달러(영업이익률 32.0%)", "최대 낙폭: -", "SPY(SPDR S&P 500): 애플 비중 6.80% → 이 ETF에 100만 원을 넣으면 그중 약 7만 원이 애플 몫",
          "배당 기록이 짧거나 없어", "어느 쪽이 낫다고 판단하지 말 것", "원문에 없는 제품·비중·순위는 쓰지 말 것"]:
    assert s in facts, (s, facts)
assert html.count("<table") == 2 and "ETF로 사면 애플은 얼마나 들어갈까" in html and "8.90%" in html
f2, h2 = co.build("AAPL", profile=p, fin=[], dd=None, div=False, weights=[])
assert "<table" not in h2 and "[배당]" not in f2
assert "애플은 어떤 회사인가" in co.title_seed("AAPL")
c = co.closing_html("AAPL", [("SPY", "x", 6.8)])
assert "AAPL Yahoo Finance" in c and "SPY Yahoo Finance" in c and "매수·매도를 권유하지 않습니다" in c
assert "2020년은 앞뒤 해보다" in co.div_odd_lines({"series": [(2020, 2994), (2021, 1444), (2022, 1444), (2023, 1444), (2024, 1446), (2025, 1668)]}, str)[1]
assert len(co.div_odd_lines({"series": [(2020, 1.0), (2021, 1.1), (2022, 1.2)]}, str)) == 1
# 11-21 꾸준히 늘어난 배당(엔비디아)은 '튄 해'가 아님
assert len(co.div_odd_lines({"series": [(2020, 0.016), (2021, 0.016), (2022, 0.016), (2023, 0.016), (2024, 0.034), (2025, 0.04)]}, str)) == 1
assert len(co.div_odd_lines({"series": [(2021, 1.0), (2022, 1.0), (2023, 3.0), (2024, 1.0)]}, str)) == 2   # 가운데 튄 해는 잡음
print("company ok")
# 11-21 조사 은/는
assert [co.eun(x) for x in ("애플", "엔비디아", "테슬라", "TSMC", "NAVER", "KB금융")] == ["애플은", "엔비디아는", "테슬라는", "TSMC는", "NAVER는", "KB금융은"]
print("josa ok")
# 11-22 배당 없는 회사는 제목 씨앗에서 '배당' 뺌
assert "배당" not in co.title_seed("TSLA", True, False) and "배당" in co.title_seed("AAPL", True, True)
print("title seed div ok")
