"""2026-11-08: 기초 가이드 계산(guide_calcs.py) - 가짜 가격으로 숫자가 맞는지, 표·자료 글이 만들어지는지."""
import os, sys
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import pandas as pd
import guide_calcs as gc

days = pd.bdate_range("2021-01-04", periods=1300)

# 1) 총보수: 0.1%p 차이, 수익 5% 가정, 10년
r = gc.calc_expense({"A": 0.03, "B": 0.13, "C": None})
assert [x[0] for x in r["rows"]] == ["A", "B"], r
a10 = 10_000_000 * (1.05 * (1 - 0.0003)) ** 10
b10 = 10_000_000 * (1.05 * (1 - 0.0013)) ** 10
assert abs(r["rows"][0][2][(5.0, 10)] - a10) < 1 and abs(r["rows"][1][2][(5.0, 10)] - b10) < 1
f, v = gc.render_expense(r)
assert f"10년 뒤 B 쪽이 {gc._won(a10 - b10)} 적음" in f and "<table" in v and "가상의 예(실제 상품 아님): 총보수만 0.1%p 다른 두 ETF" in f and "보수 차이 0.1%p" in f and "최종 금액의 약 1.0%" in f, f
assert gc.calc_expense({"A": 0.03}) is None
print("expense ok")

# 2) 레버리지: 매일 +1%/-1% 번갈아 → 기초는 거의 제자리, 3배는 손실
base = pd.Series([100.0], index=days[:1])
vals = [100.0]
for i in range(1, len(days)):
    vals.append(vals[-1] * (1.01 if i % 2 else 0.99))
base = pd.Series(vals, index=days)
lev = [100.0]
for i in range(1, len(days)):
    lev.append(lev[-1] * (1 + 3 * (vals[i] / vals[i - 1] - 1)))
lev = pd.Series(lev, index=days)
r = gc.calc_leverage(base, lev)
w1 = r["windows"][0]
assert w1["label"] == "1년" and w1["lev"] < w1["naive"] and w1["lev"] < 0, w1
assert abs(r["flat_example"]["lev"] - ((1.3) * (1 - 3 * (1 - 1 / 1.1)) - 1) * 100) < 1e-9
f, v = gc.render_leverage(r, "QQQ", "TQQQ")
assert "제자리가 아님" in f and "TQQQ 실제" in v and f.count("연 변동성") == 1, f
print("leverage ok")

# 3) 적립식 vs 거치식: 꾸준히 오르면 거치식이 이김, 떨어졌다 회복하면 적립식이 이김
months = pd.date_range("2021-01-31", periods=61, freq="ME")
up = pd.Series([100 * 1.01 ** i for i in range(61)], index=months)
r = gc.calc_dca(up)
assert r["lump"] > r["dca"] and r["wins"]["lump"] == 61 - 12 and r["wins"]["dca"] == 0, r
v_shape = pd.Series([100 - 4 * i if i <= 12 else 52 + 4 * (i - 12) for i in range(26)], index=months[:26])
r2 = gc.calc_dca(v_shape)
assert r2["dca"] > r2["lump"], r2
f, v = gc.render_dca({"SPY": r, "QQQ": None})
assert "구간 49개 중 거치식이 더 나았던 구간 49개" in f and "<table" in v, f
print("dca ok")

# 4) 최대 낙폭: 100 → 60(-40%) → 100 회복
px = pd.Series([100.0] * 50 + [100 - i for i in range(1, 41)] + [60 + i for i in range(1, 41)] + [101.0] * 20,
               index=days[:150])
d = gc.calc_drawdown(px)
assert round(d["pct"], 1) == -40.0 and d["recovered"] and d["recover_days"] > 0, d
f, v = gc.render_drawdown({"QQQ": d, "TLT": dict(d, pct=-48.0, recovered=None, recover_days=None)})
assert "1,000만 원 → 600만 원" in v and "아직 못 되찾음" in v and f.index("TLT") < f.index("QQQ"), f
print("drawdown ok")

# 5) 배당: 해마다 10% 증가, 가격 그대로 → 연평균 +10%
divs = pd.Series([1.0 * 1.1 ** (y - 2016) / 4 for y in range(2016, 2026) for _ in range(4)],
                 index=[pd.Timestamp(f"{y}-{m:02d}-15") for y in range(2016, 2026) for m in (3, 6, 9, 12)])
divs = pd.concat([divs, pd.Series([0.5], index=[pd.Timestamp("2026-03-15")])])
close = pd.Series(50.0, index=pd.bdate_range("2016-01-04", "2026-11-06"))
r = gc.calc_dividend(divs, close)
assert r["y1"] == 2025 and abs(r["cagr"] - 10.0) < 1e-6 and abs(r["yield_now"] - r["div1"] / 50 * 100) < 1e-9, r
assert r["yoc"] and r["px_then_date"].startswith("2021"), r
f, v = gc.render_dividend({"SCHD": r, "VYM": dict(r, cagr=3.0)})
assert "연평균 +10.0%" in f and "매입가의" in f and "<table" in v
print("dividend ok")

# 6) 커버드콜: 가격은 제자리, 분배금 재투자하면 +10%
p = pd.Series(100.0, index=days[:300])
t = pd.Series([100 * 1.10 ** (i / 299) for i in range(300)], index=days[:300])
w = gc.calc_total_vs_price(p, t)
assert w[0]["label"] == "1년" and abs(w[0]["price"]) < 1e-9 and w[0]["income"] > 0, w
f, v = gc.render_covered({"JEPI": w, "QQQ": w})
assert "분배금이 보탠 몫" in f
print("covered ok")

# 7) 환헤지: 달러 +10%, 환율 +5% → 환노출 +15.5%
u = pd.Series([100 * 1.10 ** (i / 299) for i in range(300)], index=days[:300])
fx = pd.Series([1300 * 1.05 ** (i / 299) for i in range(300)], index=days[:300])
hk = pd.Series([10000 * 1.08 ** (i / 299) for i in range(300)], index=days[:300])
r = gc.calc_fx_hedge(u, fx, hk)
assert abs(r["krw_unhedged"] - ((1.10 ** (252 / 299)) * (1.05 ** (252 / 299)) - 1) * 100) < 1e-6, r
f, v = gc.render_fx_hedge(r, "GLD(금)", "KODEX 골드선물(H)")
assert "두 방식 차이" in f and "<table" in v
print("fx hedge ok")

# 계산이 없는 주제는 빈 결과, 인터넷 실패도 빈 결과(글은 가격 그래프만으로 진행)
assert gc.guide_facts("tax-accounts", {}) == ("", "")
gc._hist = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net"))
assert gc.guide_facts("leverage-decay", {}) == ("", "")
print("guide fallback ok")
