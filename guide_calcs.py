"""기초 가이드 글의 '제목 질문에 답하는 숫자'를 코드가 계산한다 (2026-11-08).

배운 원칙 1(PROJECT_STATUS 12번): 독자 가치를 가장 크게 올린 건 문장 규칙이 아니라 코드가 계산한 판단 숫자였다
(세금 가이드의 '세금 갈림길 833만 원'이 5/5를 만든 것). 세금 외 가이드는 종목 기본 자료와 가격 그래프뿐이라
작가가 일반론을 쓰고, 사실 검증이 '자료에 없는 통념'으로 지적하는 일이 반복됐다.

구조: 계산 함수(calc_*)는 숫자(pandas Series 등)만 받아 결과 dict를 돌려주는 순수 함수(시험하기 쉽게),
글 자료·표는 render_* 가, 인터넷에서 가격을 받는 건 guide_facts() 한 곳에서만 한다.
자료가 모자라면 빈 결과("", "")를 돌려준다 - 틀린 숫자보다 없는 게 낫다.
"""
import math

HEAD = "[계산 예시 - 코드가 계산한 값. 이 표와 그래프는 시스템이 본문에 넣으므로 표로 다시 만들지 말고 문장으로 해석하세요]"
PAST_NOTE = "과거 자료로 계산한 값일 뿐 앞으로도 같다는 보장은 없음."


def _pct(x, d=1):
    return f"{x:+.{d}f}%"


def _pp(x, d=1):
    """수익률끼리의 차이는 %가 아니라 %p(퍼센트포인트). 11-08 레버리지 글: '격차 -183.6%'로 나감."""
    return f"{x:+.{d}f}%p"


def _won(v):
    """원 단위 금액 → 읽기 쉬운 글자(만 원 단위 반올림)."""
    if abs(v) >= 10000:
        return f"{round(v / 10000):,}만 원"
    return f"{round(v):,}원"


def _won_month(total, n):
    """적립식 한 달 금액. 나눠떨어지지 않으면 '약 20.3만 원(1,200만 원 ÷ 59번)'처럼 - 11-20: 만 원 반올림으로
    '1,200만 원 = 매달 20만 원'(실제 59번 × 20만 = 1,180만)이 돼 글에 틀린 셈이 나감."""
    m = total / n
    if abs(m - round(m / 10000) * 10000) < 1:
        return _won(m)
    return f"약 {m / 10000:,.1f}만 원({_won(total)} ÷ {n}번)"


def _parse_pct(v):
    """'0.0945%' → 0.0945. 실패하면 None."""
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------
# 1) 총보수 차이 (expense-ratio)
# ------------------------------------------------------------

def calc_expense(fees, principal=10_000_000, years=(10, 20), gross=(5.0,)):
    """fees: {이름: 연 총보수 %}. 같은 원금·같은 수익률(보수 떼기 전)일 때 보수만 다르면 n년 뒤 얼마가 되는지.
    반환: {"rows": [(이름, 보수, {(g, n): 최종 금액})], "base": 가장 싼 이름} 또는 None."""
    fees = {k: v for k, v in fees.items() if isinstance(v, (int, float)) and 0 <= v < 5}
    if len(fees) < 2:
        return None
    rows = []
    for name, f in sorted(fees.items(), key=lambda kv: kv[1]):
        vals = {}
        for g in gross:
            for n in years:
                vals[(g, n)] = principal * ((1 + g / 100) * (1 - f / 100)) ** n
        rows.append((name, f, vals))
    return {"rows": rows, "principal": principal, "years": years, "gross": gross, "base": rows[0][0]}


def render_expense(res):
    from ondo.media import charts
    if not res:
        return "", ""
    p, ys, gs = res["principal"], res["years"], res["gross"]
    cheap = res["rows"][0]
    lines, trows = [], []
    g = gs[0]
    for name, f, vals in res["rows"]:
        cells = [name, f"{f:.4g}%"]
        for n in ys:
            diff = vals[(g, n)] - cheap[2][(g, n)]
            cells.append(f"{_won(vals[(g, n)])}" + (f" ({_won(diff)})" if name != cheap[0] else " (기준)"))
        trows.append(cells)
        if name != cheap[0]:
            lines.append(f"- 실제 두 ETF: {name}(총보수 {f:.4g}%) vs {cheap[0]}({cheap[1]:.4g}%), 보수 차이 {f - cheap[1]:.4g}%p. "
                         f"원금 {_won(p)}, 보수 떼기 전 연 {g:g}% 가정 → "
                         + ", ".join(f"{n}년 뒤 {name} 쪽이 {_won(cheap[2][(g, n)] - vals[(g, n)])} 적음" for n in ys))
    # "0.1%p 차이, 10년 뒤 얼마" 제목에 직접 답하는 가상의 예 - 실제 두 ETF와 같은 원금·같은 수익률 가정으로만 계산한다.
    # (11-08 첫 시험: 0% 가정 예시와 실제 두 ETF 예시가 우연히 둘 다 '10만 원'이 돼 작가가 섞어 써서 '치명')
    hyp = {n: p * (1 + g / 100) ** n * (1 - (1 - 0.001) ** n) for n in ys}
    drag = {n: (1 - (1 - 0.001) ** n) * 100 for n in ys}
    lines.append(f"- 가상의 예(실제 상품 아님): 총보수만 0.1%p 다른 두 ETF, 같은 원금 {_won(p)}·같은 연 {g:g}% 가정 → "
                 + ", ".join(f"{n}년 뒤 약 {_won(hyp[n])} 차이(최종 금액의 약 {drag[n]:.1f}%)" for n in ys))
    note = (f"원금 {_won(p)}을 한 번에 넣고, 보수를 떼기 전 연 {g:g}% 수익을 가정한 계산(ondo 계산). 괄호는 가장 싼 ETF와의 차이. "
            "총보수만 반영 - 매매 비용·세금·환율·추적 오차는 빼고 계산. 수익률 가정은 예시일 뿐 실제 수익이 아님.")
    header = ["ETF", "총보수"] + [f"{n}년 뒤" for n in ys]
    table = charts.table_html("같은 원금·같은 수익률이라면, 총보수만 다를 때 차이", header, trows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 총보수는 ETF 자산에서 매일 조금씩 빠져나가므로, 투자자가 따로 내는 돈이 아니라 수익률(가격)에 이미 반영된다.\n"
             "- 보수 차이는 원금이 크고 기간이 길수록 금액 차이가 커진다(복리).\n")
    return facts, table


# ------------------------------------------------------------
# 2) 3배 레버리지 (leverage-decay)
# ------------------------------------------------------------

def calc_leverage(base, lev, mult=3, windows=(("1년", 252), ("3년", 756), ("5년", 1260))):
    """base·lev: 같은 날짜 종가 Series(배당 반영 여부 같게). 구간별 기초 수익률, 레버리지 실제 수익률, '기초 × 배수' 단순 기대값,
    기초 연 변동성. 겹치는 날이 60일 미만이면 None."""
    import pandas as pd
    df = pd.concat([base.rename("b"), lev.rename("l")], axis=1, join="inner").dropna()
    if len(df) < 60:
        return None
    out = []
    for label, n in windows:
        if len(df) <= n:
            continue
        seg = df.iloc[-n - 1:]
        rb = (seg["b"].iloc[-1] / seg["b"].iloc[0] - 1) * 100
        rl = (seg["l"].iloc[-1] / seg["l"].iloc[0] - 1) * 100
        vol = float(seg["b"].pct_change().std() * math.sqrt(252) * 100)
        out.append({"label": label, "start": f"{seg.index[0]:%Y-%m-%d}", "base": rb, "lev": rl, "naive": rb * mult, "vol": vol})
    if not out:
        return None
    # 오르내림만 반복해 제자리로 돌아오는 예(순수 계산): 기초 +10% 뒤 -9.09%면 기초는 제자리, 3배는?
    up, down = 0.10, 1 / 1.10 - 1
    lev_flat = ((1 + mult * up) * (1 + mult * down) - 1) * 100
    return {"windows": out, "mult": mult, "flat_example": {"up": up * 100, "down": down * 100, "lev": lev_flat}}


def render_leverage(res, base_name, lev_name):
    from ondo.media import charts
    if not res:
        return "", ""
    m = res["mult"]
    rows, lines = [], []
    for w in res["windows"]:
        gap = w["lev"] - w["naive"]
        rows.append([w["label"], _pct(w["base"]), _pct(w["lev"]), _pct(w["naive"]), _pp(gap), f"{w['vol']:.1f}%"])
        lines.append(f"- 최근 {w['label']}({w['start']}부터): {base_name} {_pct(w['base'])}, {lev_name} 실제 {_pct(w['lev'])}, "
                     f"'{base_name} × {m}' 단순 계산 {_pct(w['naive'])} → 실제와 차이 {_pp(gap)}")
    # 변동성은 한 줄로(11-08: 구간마다 "이 기간 연 변동성 21.3%/20.9%"를 붙였더니 거의 같은 문장 세 개가 됨)
    lines.append(f"- {base_name} 연 변동성(일별 수익률 기준): " + ", ".join(f"최근 {w['label']} {w['vol']:.1f}%" for w in res["windows"]))
    fe = res["flat_example"]
    lines.append(f"- 계산 예시: 기초지수가 하루 {fe['up']:+.1f}% 오르고 다음 날 {fe['down']:+.2f}% 내려 제자리로 돌아오면, "
                 f"매일 {m}배를 따라가는 ETF는 {fe['lev']:+.2f}% (제자리가 아님)")
    note = (f"Yahoo Finance 종가(배당 반영), 거래일 기준 구간, ondo 계산. '단순 계산'은 기초 수익률 × {m}. "
            f"레버리지 ETF는 '하루' 수익률의 {m}배를 목표로 하므로 기간이 길어지면 단순 계산과 달라짐. {PAST_NOTE}")
    table = charts.table_html(f"{lev_name}는 {base_name} 수익률의 {m}배였을까", ["기간", base_name, f"{lev_name} 실제",
                              f"{base_name}×{m}", "차이", f"{base_name} 변동성"], rows, note)
    chart = charts.plotly_html({"title": f"기간별 실제 수익률 vs {m}배 단순 계산", "kind": "bar", "unit": "%",
                                "labels": [w["label"] for w in res["windows"]],
                                "series": [{"name": f"{lev_name} 실제", "values": [round(w["lev"], 1) for w in res["windows"]]},
                                           {"name": f"{base_name}×{m}", "values": [round(w["naive"], 1) for w in res["windows"]]}],
                                "source": "Yahoo Finance, ondo 계산"})
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             f"- 레버리지 ETF는 매일 기초지수 하루 수익률의 {m}배를 목표로 다시 맞춘다(일일 재조정). 그래서 오르내림이 반복되면 "
             "같은 기초 수익률이라도 결과가 달라지고, 변동성이 클수록 그 차이가 커지는 경향이 있다.\n"
             "- 한 방향으로 꾸준히 오른 기간에는 단순 계산보다 더 많이 오를 수도 있다(위 표의 '차이'가 양수인 경우).\n")
    return facts, table + chart


# ------------------------------------------------------------
# 3) 적립식 vs 거치식 (dca-vs-lump)
# ------------------------------------------------------------

def calc_dca(monthly_close, months=60, window=12):
    """monthly_close: 월말 종가 Series(배당 반영). 같은 총액을 ① 첫 달에 한 번에(거치식) ② 매달 나눠(적립식) 넣었을 때.
    전체 기간 결과 + window개월짜리 모든 구간에서 어느 쪽이 더 나았는지 횟수. 자료가 window+2개월 미만이면 None."""
    c = monthly_close.dropna()
    if len(c) < window + 2:
        return None
    c = c.iloc[-(months + 1):] if len(c) > months + 1 else c

    def one(seg):
        n = len(seg) - 1                 # 넣는 달 수(마지막 달 값으로 평가)
        end = float(seg.iloc[-1])
        lump = end / float(seg.iloc[0])                       # 1원을 첫 달에
        dca = sum(end / float(seg.iloc[i]) for i in range(n)) / n   # 1원을 n번 나눠
        return (lump - 1) * 100, (dca - 1) * 100

    lump_all, dca_all = one(c)
    wins = {"lump": 0, "dca": 0}
    worst = {"lump": None, "dca": None}
    for i in range(len(c) - window):
        seg = c.iloc[i:i + window + 1]
        l, d = one(seg)
        wins["lump" if l > d else "dca"] += 1
        worst["lump"] = l if worst["lump"] is None else min(worst["lump"], l)
        worst["dca"] = d if worst["dca"] is None else min(worst["dca"], d)
    return {"start": f"{c.index[0]:%Y-%m}", "end": f"{c.index[-1]:%Y-%m}", "n": len(c) - 1, "lump": lump_all, "dca": dca_all,
            "window": window, "wins": wins, "worst": worst}


def render_dca(results, total=12_000_000):
    """results: {종목: calc_dca 결과}."""
    from ondo.media import charts
    results = {k: v for k, v in results.items() if v}
    if not results:
        return "", ""
    rows = []
    for t, r in results.items():
        rows.append([t, f"{r['start']}~{r['end']}", _pct(r["lump"]), _pct(r["dca"]),
                     f"거치식 {r['wins']['lump']}번 / 적립식 {r['wins']['dca']}번", _pct(r["worst"]["lump"]), _pct(r["worst"]["dca"])])
    # 종목별 줄이 아니라 항목별 줄로(11-08 적립식 재시험: 종목마다 같은 모양 두 줄을 주니 작가도 "QQQ 역시…"로 같은 틀을 되풀이해 '중요')
    one = next(iter(results.values()))
    both = lambda f: ", ".join(f"{t} {f(r)}" for t, r in results.items())
    lines = [
        f"- 기간·조건: {one['start']}~{one['end']}({one['n']}개월), 같은 총액 {_won(total)}을 첫 달에 한 번에(거치식) vs "
        f"매달 {_won_month(total, one['n'])}씩(적립식)",
        "- 전체 기간 수익률(거치식 / 적립식): " + both(lambda r: f"{_pct(r['lump'])} / {_pct(r['dca'])}"),
        "- 전체 기간 평가액(거치식 / 적립식): " + both(lambda r: f"{_won(total * (1 + r['lump'] / 100))} / {_won(total * (1 + r['dca'] / 100))}"),
        f"- 이 기간 안의 {one['window']}개월짜리 구간 {one['wins']['lump'] + one['wins']['dca']}개 중 거치식 수익률이 더 높았던 구간 수: "
        + both(lambda r: f"{r['wins']['lump']}개"),
        f"- {one['window']}개월 구간 중 가장 나빴던 수익률(거치식 / 적립식): " + both(lambda r: f"{_pct(r['worst']['lump'])} / {_pct(r['worst']['dca'])}"),
    ]
    note = ("Yahoo Finance 월말 종가(배당 재투자 반영), 달러 기준(환율·세금·수수료 제외), ondo 계산. 적립식은 매달 같은 금액을 그달 말 가격에 "
            "산다고 가정. 수익률은 넣은 총액 대비. " + PAST_NOTE)
    table = charts.table_html("같은 돈을 한 번에 vs 매달 나눠서: 실제 가격으로 돌려 본 결과",
                              ["ETF", "기간", "거치식", "적립식", f"{next(iter(results.values()))['window']}개월 구간 승패",
                               "거치식 최악 구간", "적립식 최악 구간"], rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             # '유리'를 자료에 쓰면 작가가 그대로 가져가 정책 담당의 '단정 표현' 지적을 받는다(11-08 적립식 가이드) → 숫자로 비교하는 말만
             "- 거치식은 처음부터 전액이 투자돼 있고, 적립식은 나눠 넣는 동안 아직 안 넣은 돈이 남아 있어 평균 투자 기간이 더 짧다"
             "(이 계산처럼 매달 같은 금액이면 약 절반). 그래서 가격이 대체로 오른 기간에는 거치식 수익률이, 중간에 크게 떨어졌다 회복한 "
             "기간에는 싸게 더 산 적립식 수익률이 더 높게 나오는 경향이 있다.\n"
             "- 적립식은 평균 매입 단가를 고르게 하지만 수익을 보장하지 않는다.\n")
    return facts, table


# ------------------------------------------------------------
# 4) 최대 낙폭으로 버틸 수 있는지 (mdd-risk)
# ------------------------------------------------------------

def calc_drawdown(close):
    """종가 Series → 최대 낙폭 상세(고점·바닥·회복). etf_auto._drawdown_detail과 같은 계산(가격 기준)."""
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
    return {"pct": float(dd.min()) * 100, "peak": f"{peak:%Y-%m-%d}", "trough": f"{trough:%Y-%m-%d}",
            "fall_days": int((trough - peak).days),
            "recovered": f"{recovered:%Y-%m-%d}" if recovered is not None else None,
            "recover_days": int((recovered - trough).days) if recovered is not None else None,
            "now_vs_peak": (float(c.iloc[-1]) / float(c.max()) - 1) * 100}


def render_drawdown(results, amount=10_000_000):
    from ondo.media import charts
    results = {k: v for k, v in results.items() if v}
    if len(results) < 2:
        return "", ""
    rows = []
    items = sorted(results.items(), key=lambda kv: kv[1]["pct"])
    for t, r in items:
        low = amount * (1 + r["pct"] / 100)
        rec = f"{r['recover_days']:,}일 뒤({r['recovered']})" if r["recovered"] else "아직 못 되찾음"
        rows.append([t, f"{r['pct']:.1f}%", f"{_won(amount)} → {_won(low)}", f"{r['fall_days']:,}일", rec, f"{r['now_vs_peak']:.1f}%"])
    # 항목별 줄 + 이름표를 분명히(11-08 재시험: 한 줄에 '262일 동안'(하락)과 '656일 뒤'(회복)를 같이 써서 작가가 하락 기간을
    # 회복 기간으로 잘못 써 '치명' 2개. 종목별 같은 모양 줄은 같은 틀 되풀이도 부름)
    both = lambda f: ", ".join(f"{t} {f(r)}" for t, r in items)
    lines = [
        "- 최근 5년 최대 낙폭: " + both(lambda r: f"{r['pct']:.1f}%"),
        "- 하락 기간(고점에서 바닥까지 떨어지는 데 걸린 날): " + both(lambda r: f"{r['fall_days']:,}일({r['peak']}→{r['trough']})"),
        "- 회복 기간(바닥에서 다시 고점 가격을 되찾는 데 걸린 날): "
        + both(lambda r: f"{r['recover_days']:,}일({r['recovered']})" if r["recovered"] else "아직 못 되찾음"),
        f"- {_won(amount)}을 고점에 넣었다면 가장 낮을 때 평가액: " + both(lambda r: _won(amount * (1 + r['pct'] / 100))),
        "- 지금 가격의 5년 최고가 대비: " + both(lambda r: f"{r['now_vs_peak']:.1f}%"),
    ]
    note = ("Yahoo Finance 일별 종가(배당 제외 가격 기준), 최근 5년, 달러 기준, ondo 계산. '얼마까지 줄었나'는 고점에 넣었다고 가정한 예시. "
            + PAST_NOTE)
    table = charts.table_html("최근 5년, 가장 크게 떨어졌을 때와 회복까지 걸린 시간",
                              ["ETF", "최대 낙폭", "가장 낮을 때 평가액", "떨어진 기간", "고점 회복", "지금 고점 대비"], rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 최대 낙폭(MDD)은 고점에서 가장 낮은 지점까지 떨어진 비율이다. 같은 수익률이어도 낙폭이 클수록 중간에 버티기 어렵다.\n"
             "- 떨어진 만큼 되찾으려면 더 큰 상승이 필요하다(예: -50%면 +100%가 필요).\n")
    return facts, table


# ------------------------------------------------------------
# 5) 배당성장률 (dividend-growth)
# ------------------------------------------------------------

def calc_dividend(dividends, close, years=5):
    """dividends: 지급일별 주당 배당 Series, close: 일별 종가(배당 제외 가격). 다 찬 해(직전 해까지)의 연간 배당과
    years년 연평균 증가율, '5년 전 그 가격에 샀다면 지금 받는 배당률'(매입가 대비 배당률). 다 찬 해가 years+1개 미만이면 None."""
    d = dividends.dropna()
    if len(d) < 4 or len(close.dropna()) < 30:
        return None
    last_full = int(d.index[-1].year) - 1
    annual = d.groupby(d.index.year).sum()
    annual = annual[annual.index <= last_full]
    if len(annual) < years + 1:
        return None
    a0, a1 = float(annual.loc[last_full - years]), float(annual.loc[last_full])
    if a0 <= 0:
        return None
    cagr = ((a1 / a0) ** (1 / years) - 1) * 100
    c = close.dropna()
    px_now = float(c.iloc[-1])
    start = c[c.index.year == last_full - years + 1]
    px_then = float(start.iloc[0]) if len(start) else None
    return {"years": years, "y0": last_full - years, "y1": last_full, "div0": a0, "div1": a1, "cagr": cagr,
            "yield_now": a1 / px_now * 100,
            "yoc": (a1 / px_then * 100) if px_then else None, "px_then_date": f"{start.index[0]:%Y-%m-%d}" if len(start) else None,
            "series": [(int(y), round(float(v), 4)) for y, v in annual.iloc[-(years + 1):].items()]}


def render_dividend(results):
    from ondo.media import charts
    results = {k: v for k, v in results.items() if v}
    if len(results) < 2:
        return "", ""
    rows, lines = [], []
    for t, r in sorted(results.items(), key=lambda kv: -kv[1]["cagr"]):
        yoc = f"{r['yoc']:.2f}%" if r["yoc"] else "-"
        rows.append([t, f"${r['div0']:.2f} → ${r['div1']:.2f}", f"{r['cagr']:+.1f}%", f"{r['yield_now']:.2f}%", yoc])
        lines.append(f"- {t}: 주당 연간 배당 {r['y0']}년 ${r['div0']:.2f} → {r['y1']}년 ${r['div1']:.2f}, {r['years']}년 연평균 {r['cagr']:+.1f}%. "
                     f"지금 가격 기준 배당률 {r['yield_now']:.2f}%"
                     + (f", {r['px_then_date']} 가격에 샀다면 {r['y1']}년 배당은 매입가의 {r['yoc']:.2f}%" if r["yoc"] else ""))
    note = ("Yahoo Finance 배당 지급 기록(다 찬 해만, 달러, 세전), 배당률 = 직전 해 연간 배당 ÷ 가격, ondo 계산. "
            "'매입가 대비 배당률'은 그 날짜 가격에 샀다고 가정한 값. " + PAST_NOTE)
    table = charts.table_html("배당률과 배당성장률: 지금 배당률 vs 5년 전에 샀다면", ["ETF", "주당 연간 배당", "연평균 증가율",
                              "지금 가격 기준 배당률", "5년 전 매입가 대비 배당률"], rows, note)
    chart = charts.plotly_html({"title": "주당 연간 배당 흐름", "kind": "line", "unit": "$",
                                "labels": [str(y) for y, _ in next(iter(results.values()))["series"]],
                                "series": [{"name": t, "values": [v for _, v in r["series"]]} for t, r in results.items()
                                           if [y for y, _ in r["series"]] == [y for y, _ in next(iter(results.values()))["series"]]],
                                "source": "Yahoo Finance 배당 기록, ondo 계산"})
    # 11-11(백로그 6-9): 배당성장 가이드가 '배당성장률이 높으면 현금 흐름이 더 많다'고 단정했는데 자료는 DGRO(+7.1%)가 VYM(+3.8%)보다
    # 증가율이 높아도 매입가 대비 배당률은 더 낮았음(시작 배당률 차이) - 검토 셋 다 못 잡음. 순위가 엇갈리는 짝을 코드가 사실로 준다.
    cross = []
    items = list(results.items())
    for i, (ta, ra) in enumerate(items):
        for tb, rb in items[i + 1:]:
            if not (ra["yoc"] and rb["yoc"]):
                continue
            (hi, rh), (lo, rl) = ((ta, ra), (tb, rb)) if ra["cagr"] > rb["cagr"] else ((tb, rb), (ta, ra))
            if rh["yoc"] < rl["yoc"]:
                s0 = lambda r: r["div0"] / (r["div1"] / r["yoc"]) if r["yoc"] else 0     # 시작 해 배당 ÷ 그때 가격(%)
                cross.append(f"- 순위가 엇갈리는 짝(코드 계산): {hi}는 {rh['years']}년 연평균 배당 증가율({rh['cagr']:+.1f}%)이 {lo}({rl['cagr']:+.1f}%)보다 "
                             f"높지만 매입가 대비 배당률은 {rh['yoc']:.2f}%로 {lo}({rl['yoc']:.2f}%)보다 낮음 - 시작 배당률이 {lo} {s0(rl):.2f}%, {hi} {s0(rh):.2f}%로 "
                             f"{lo}가 높았기 때문. 즉 증가율만으로 현금 흐름 순위가 정해지지 않음(이번 자료 기준)")
    facts = (HEAD + "\n" + "\n".join(lines + cross) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 배당률은 '지금 가격' 대비 배당이라 가격이 내리면 높아 보일 수 있다. 배당성장률은 배당 자체가 해마다 얼마나 늘었는지다.\n"
             "- 배당이 꾸준히 늘면 처음 산 가격 대비 받는 배당 비율(매입가 대비 배당률)이 시간이 갈수록 커진다.\n")
    return facts, table + chart


# ------------------------------------------------------------
# 6) 커버드콜 분배금의 출처 (covered-call-structure)
# ------------------------------------------------------------

def calc_total_vs_price(price_close, total_close, windows=(("1년", 252), ("3년", 756))):
    """price_close: 배당 제외 종가, total_close: 배당 재투자 반영 종가(같은 종목). 구간별 가격 수익률·총수익률·분배금 몫."""
    import pandas as pd
    df = pd.concat([price_close.rename("p"), total_close.rename("t")], axis=1, join="inner").dropna()
    out = []
    for label, n in windows:
        if len(df) <= n:
            continue
        seg = df.iloc[-n - 1:]
        rp = (seg["p"].iloc[-1] / seg["p"].iloc[0] - 1) * 100
        rt = (seg["t"].iloc[-1] / seg["t"].iloc[0] - 1) * 100
        out.append({"label": label, "start": f"{seg.index[0]:%Y-%m-%d}", "price": rp, "total": rt, "income": rt - rp})
    return out or None


def render_covered(results):
    from ondo.media import charts
    results = {k: v for k, v in results.items() if v}
    if len(results) < 2:
        return "", ""
    rows, lines = [], []
    for t, ws in results.items():
        for w in ws:
            rows.append([t, w["label"], _pct(w["price"]), _pct(w["total"]), _pp(w["income"])])
    # 종목별 같은 모양 줄 대신 기간별로 종목을 나란히(11-08 적립식 재시험의 '같은 틀 되풀이' 교훈을 미리 적용)
    labels = [w["label"] for w in next(iter(results.values()))]
    for lab in labels:
        cells = [(t, next((w for w in ws if w["label"] == lab), None)) for t, ws in results.items()]
        cells = [(t, w) for t, w in cells if w]
        lines.append(f"- 최근 {lab}({cells[0][1]['start']}부터) 가격만 / 분배금 재투자 포함(총수익) / 분배금이 보탠 몫: "
                     + ", ".join(f"{t} {_pct(w['price'])} / {_pct(w['total'])} / {_pp(w['income'])}" for t, w in cells))
    note = ("Yahoo Finance 종가(가격만 / 분배금 재투자 반영), 달러·세전, ondo 계산. '분배금이 보탠 몫'은 총수익 - 가격 수익(근사). "
            + PAST_NOTE)
    table = charts.table_html("분배금을 빼면 가격은 어떻게 됐나: 가격 수익률 vs 총수익률",
                              ["ETF", "기간", "가격만", "분배금 재투자 포함", "분배금 몫"], rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 커버드콜 ETF는 보유 자산에 대한 콜옵션을 팔아 받은 돈(옵션 프리미엄)을 분배금 재원으로 쓴다.\n"
             "- 그 대가로 기초자산이 크게 오를 때의 상승분 일부를 포기한다. 분배금이 높아도 가격이 내려가면 총수익은 낮을 수 있다.\n")
    return facts, table


# ------------------------------------------------------------
# 7) 환헤지 vs 환노출 (hedged-vs-unhedged)
# ------------------------------------------------------------

def calc_fx_hedge(usd_close, fx_close, hedged_krw_close, days=252):
    """usd_close: 달러 자산(환노출로 산다고 가정), fx_close: 원/달러, hedged_krw_close: 같은 자산의 원화 환헤지 ETF.
    최근 days 거래일: 달러 기준, 원화 환산(환노출), 환헤지 ETF 수익률과 환율 변화."""
    import pandas as pd
    a = pd.concat([usd_close.rename("u"), fx_close.rename("f")], axis=1, join="inner").dropna()
    h = hedged_krw_close.dropna()
    if len(a) <= days or len(h) <= days * 0.9:
        return None
    seg = a.iloc[-days - 1:]
    start = seg.index[0]
    hs = h[h.index >= start]
    if len(hs) < days * 0.8:
        return None
    ru = (seg["u"].iloc[-1] / seg["u"].iloc[0] - 1) * 100
    rf = (seg["f"].iloc[-1] / seg["f"].iloc[0] - 1) * 100
    rk = ((seg["u"].iloc[-1] * seg["f"].iloc[-1]) / (seg["u"].iloc[0] * seg["f"].iloc[0]) - 1) * 100
    rh = (hs.iloc[-1] / hs.iloc[0] - 1) * 100
    return {"start": f"{start:%Y-%m-%d}", "usd": ru, "fx": rf, "krw_unhedged": rk, "hedged": rh,
            "fx0": float(seg["f"].iloc[0]), "fx1": float(seg["f"].iloc[-1])}


def render_fx_hedge(r, asset, hedged_name, more=()):
    """more: [(r, asset, hedged_name)] 같은 계산의 다른 자산 짝(11-21 백로그 92: 금 한 쌍뿐이라 작가가 같은 설명을 되풀이 → S&P500 짝 추가)."""
    from ondo.media import charts
    if not r:
        return "", ""
    pairs = [(r, asset, hedged_name)] + [p for p in more if p[0]]
    lines, rows = [], []
    for i, (x, a, hn) in enumerate(pairs):
        if i == 0:
            lines.append(f"- 최근 1년({x['start']}부터) 원/달러 환율 {x['fx0']:,.0f}원 → {x['fx1']:,.0f}원({_pct(x['fx'])})")
        lines.append(f"- {a}: 달러 기준 {_pct(x['usd'])}, 원화로 환산하면(환노출) {_pct(x['krw_unhedged'])}, 환헤지 ETF {hn}는 {_pct(x['hedged'])} "
                     f"→ 두 방식 차이 {_pp(x['krw_unhedged'] - x['hedged'])}")
        rows += [[f"{a} (달러 기준)", _pct(x["usd"])], [f"{a} 원화 환산(환노출)", _pct(x["krw_unhedged"])],
                 [f"{hn} (환헤지)", _pct(x["hedged"])]]
    rows.insert(0, ["원/달러 환율 변화", _pct(r["fx"])])
    note = ("Yahoo Finance 종가(배당 제외 가격), 최근 약 1년, ondo 계산. 원화 환산 = 달러 가격 × 원/달러 환율. "
            "환헤지 ETF는 운용 방식·비용·추적 대상이 달라 차이가 환율 효과만은 아님. " + PAST_NOTE)
    table = charts.table_html("같은 자산, 환율을 막았을 때와 그대로 뒀을 때(최근 1년)", ["구분", "수익률"], rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 환노출은 자산 가격 변화에 환율 변화가 더해지고(원화가 약해지면 이익), 환헤지는 환율 변화를 줄이려고 헤지 비용을 쓴다.\n"
             "- 이름 끝의 (H)는 환헤지를 뜻한다.\n"
             # 11-08 재시험: 독자가 실제로 묻는 '헤지 비용은 어디서 오나'를 작가가 맞게 썼는데 자료에 없어 '지어냄'으로 막힘 → 원리를 자료로
             "- 헤지 비용의 크기는 대체로 두 나라 단기 금리 차이에서 정해진다: 달러 금리가 원화 금리보다 높으면 원화 투자자가 환율을 고정하는 데 "
             "비용이 들고(수익률에서 깎임), 반대로 원화 금리가 더 높으면 오히려 이득이 될 수 있다. 이 비용은 운용보수와 별도로 수익률에 녹아 있다"
             "(이 자료에는 현재 비용의 정확한 크기 없음 - 숫자로 쓰지 말 것).\n"
             "- 헤지는 환율 변화를 '줄이는' 장치라 완전히 없애지는 못한다(위 계산의 차이가 환율 효과만은 아닌 이유 중 하나).\n")
    return facts, table


# ------------------------------------------------------------
# 8) 나라별 시장 (market-<나라>) - 11-21 사용자 '주식시장 큰 나라들'
# ------------------------------------------------------------
# usd: 그 나라 주식을 담은 미국 상장 대표 ETF(달러), kr: 국내 상장 같은 나라 ETF(원화, 추종 지수가 다를 수 있음)
COUNTRIES = {
    "japan": {"ko": "일본", "usd": "EWJ", "usd_name": "EWJ(iShares MSCI Japan)", "usd_index": "MSCI 일본 지수",
              "kr": "241180.KS", "kr_name": "TIGER 일본니케이225", "kr_index": "닛케이225 지수"},
    "india": {"ko": "인도", "usd": "INDA", "usd_name": "INDA(iShares MSCI India)", "usd_index": "MSCI 인도 지수",
              "kr": "453870.KS", "kr_name": "TIGER 인도니프티50", "kr_index": "니프티50 지수"},
    "china": {"ko": "중국", "usd": "MCHI", "usd_name": "MCHI(iShares MSCI China)", "usd_index": "MSCI 중국 지수(홍콩·미국 상장 중국 기업 포함)",
              "kr": "192090.KS", "kr_name": "TIGER 차이나CSI300", "kr_index": "CSI300 지수(중국 본토 상하이·선전 상장 300개)"},
    "taiwan": {"ko": "대만", "usd": "EWT", "usd_name": "EWT(iShares MSCI Taiwan)", "usd_index": "MSCI 대만 지수"},
}


def _ret(close, days):
    c = close.dropna()
    if len(c) <= days:
        return None, None
    seg = c.iloc[-days - 1:]
    return (float(seg.iloc[-1]) / float(seg.iloc[0]) - 1) * 100, seg.index[0]


def calc_country(usd_close, fx_close, ref_close=None, kr_close=None, usd_price=None):
    """usd_close: 미국 상장 나라 ETF(배당 반영), fx_close: 원/달러, ref_close: 비교용 SPY(배당 반영),
    kr_close: 국내 상장 같은 나라 ETF(원화), usd_price: 배당 제외 가격(최대 낙폭용). 1·3·5년 창."""
    import pandas as pd
    a = pd.concat([usd_close.rename("u"), fx_close.rename("f")], axis=1, join="inner").dropna()
    rows = []
    for label, days in (("1년", 252), ("3년", 756), ("5년", 1260)):
        if len(a) <= days:
            continue
        seg = a.iloc[-days - 1:]
        start = seg.index[0]
        ru = (seg["u"].iloc[-1] / seg["u"].iloc[0] - 1) * 100
        rf = (seg["f"].iloc[-1] / seg["f"].iloc[0] - 1) * 100
        rk = ((seg["u"].iloc[-1] * seg["f"].iloc[-1]) / (seg["u"].iloc[0] * seg["f"].iloc[0]) - 1) * 100
        row = {"label": label, "start": f"{start:%Y-%m-%d}", "usd": ru, "fx": rf, "krw": rk, "ref": None, "kr": None}
        if ref_close is not None:
            r = ref_close.dropna()
            r = r[r.index >= start]
            if len(r) > days * 0.9:
                row["ref"] = (float(r.iloc[-1]) / float(r.iloc[0]) - 1) * 100
        if kr_close is not None:
            k = kr_close.dropna()
            k = k[k.index >= start]
            if len(k) > days * 0.9:                 # 상장한 지 짧으면 그 창은 비움(11-21 인도 ETF는 2023년 상장)
                row["kr"] = (float(k.iloc[-1]) / float(k.iloc[0]) - 1) * 100
        rows.append(row)
    if not rows:
        return None
    dd = calc_drawdown(usd_price if usd_price is not None else usd_close)
    return {"rows": rows, "dd": dd}


def render_country(r, cfg):
    from ondo.media import charts
    if not r:
        return "", ""
    nm, un = cfg["ko"], cfg["usd_name"]
    kr = cfg.get("kr_name")
    lines = []
    for x in r["rows"]:
        s = (f"- 최근 {x['label']}({x['start']}부터): {un} 달러 기준 {_pct(x['usd'])}, 원/달러 환율 {_pct(x['fx'])}, "
             f"원화로 환산하면 {_pct(x['krw'])}")
        if x["ref"] is not None:
            s += f" / 같은 기간 미국 SPY(달러 기준) {_pct(x['ref'])}"
        if kr and x["kr"] is not None:
            s += f" / 국내 상장 {kr}(원화) {_pct(x['kr'])}"
        lines.append(s)
    d = r.get("dd")
    if d and d["pct"] <= -1:
        lines.append(f"- {un} 최근 5년 최대 낙폭(배당 제외 가격): {_pct(d['pct'])} (고점 {d['peak']} → 바닥 {d['trough']}"
                     + (f", {d['recover_days']}일 뒤 회복)" if d.get("recover_days") is not None else ", 아직 고점 회복 전)"))
    hdr = ["기간", f"{cfg['usd']} 달러 기준", "원/달러 환율", f"{cfg['usd']} 원화 환산", "SPY 달러 기준"] + ([kr] if kr else [])
    rows = [[x["label"], _pct(x["usd"]), _pct(x["fx"]), _pct(x["krw"]), _pct(x["ref"]) if x["ref"] is not None else "-"]
            + ([_pct(x["kr"]) if x["kr"] is not None else "-"] if kr else []) for x in r["rows"]]
    note = (f"Yahoo Finance 종가(배당 반영), 거래일 기준 구간, ondo 계산. 원화 환산 = 달러 가격 × 원/달러 환율. "
            f"따르는 지수 - {cfg['usd']}: {cfg['usd_index']}" + (f", {kr}: {cfg['kr_index']}(담은 종목이 다름)" if kr else "")
            + ". 세금·거래 비용 제외. " + PAST_NOTE)
    table = charts.table_html(f"{nm} 주식, 달러로 볼 때와 원화로 볼 때", hdr, rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             f"- 한국 투자자가 {nm} 주식에 투자하는 길은 크게 두 가지다: 국내 상장 ETF(원화로 거래, ISA·연금저축 계좌에서도 살 수 있음)와 "
             f"미국 등 해외 상장 ETF(달러로 거래, 이 계좌들로는 직접 살 수 없음).\n"
             "- 해외 주식의 원화 수익률은 그 나라 주가 변화와 환율 변화가 함께 만든다(위 계산의 '원화 환산'). 미국 상장 ETF는 달러 기준이라 "
             f"원화 투자자에게는 원/달러 환율이, ETF 안의 {nm} 주식에는 그 나라 통화와 달러 사이 환율도 이미 들어 있다.\n"
             "- 같은 나라 ETF라도 따르는 지수(담는 종목 수·상장 시장)가 다르면 수익률이 다르다.\n"
             "- 이 자료에는 그 나라 경제 전망·정책·뉴스가 없다(과거 가격 계산만 있음).\n")
    return facts, table


# ------------------------------------------------------------
# 파킹형(CD금리·머니마켓) ETF (parking-etf) - 11-21: 계산 자료가 없어 일반 종목 자료만 받던 주제.
# 독자 질문 '예금 대신 써도 될까'에 답하는 숫자 = 1년 수익률(1년 예금 금리와 같은 기준), 얼마나 흔들렸나(내린 날 비율·
# 가장 나빴던 하루·한 달, 최대 낙폭). 예금·CMA 금리는 자료에 없음 - 작가가 지어내지 않게 자료에 그렇게 적는다.
# ------------------------------------------------------------

def calc_parking(close):
    """원화 종가 Series(분배 없는 적립형) → 1년·상장 뒤 연환산 수익률과 흔들림. 자료가 60거래일 미만이면 None."""
    c = close.dropna()
    if len(c) < 60:
        return None
    r1, start1 = _ret(c, 252)
    days = (c.index[-1] - c.index[0]).days
    ann = ((float(c.iloc[-1]) / float(c.iloc[0])) ** (365 / days) - 1) * 100 if days >= 180 else None
    d = c.pct_change().dropna()
    m = c.resample("ME").last().pct_change().dropna() if hasattr(c.index, "to_period") else None
    dd = (c / c.cummax() - 1.0).min() * 100
    return {"start": f"{c.index[0]:%Y-%m-%d}", "end": f"{c.index[-1]:%Y-%m-%d}", "r1": r1,
            "r1_start": f"{start1:%Y-%m-%d}" if start1 is not None else None, "ann": ann,
            "down_share": float((d < 0).mean()) * 100, "worst_day": float(d.min()) * 100,
            "worst_month": float(m.min()) * 100 if m is not None and len(m) else None,
            "neg_months": int((m < 0).sum()) if m is not None else None, "months": int(len(m)) if m is not None else None,
            "mdd": float(dd)}


def render_parking(results, names, amount=10_000_000):
    from ondo.media import charts
    results = {k: v for k, v in results.items() if v}
    if not results:
        return "", ""
    nm = lambda t: f"{names.get(t) or t.replace('.KS', '')}"
    lines, rows = [], []
    for t, r in results.items():
        if r["r1"] is not None:
            lines.append(f"- {nm(t)}: 최근 1년({r['r1_start']}부터) {_pct(r['r1'], 2)} → {_won(amount)}이면 세전 약 {_won(amount * r['r1'] / 100)} 늘어남")
        if r["ann"] is not None:
            lines.append(f"- {nm(t)}: 자료 시작({r['start']})부터 연 환산 {_pct(r['ann'], 2)}")
        share = f"{r['down_share']:.1f}%" if r["down_share"] < 10 else f"{r['down_share']:.0f}%"
        worst = f"가장 크게 내린 하루 {r['worst_day']:.2f}%" if r["worst_day"] < 0 else "전날보다 내린 날 없음"
        s = f"- {nm(t)} 흔들림: 전날보다 내린 날 비율 {share}, {worst}"
        if r["worst_month"] is not None:
            s += f", 한 달 단위로 내린 달 {r['neg_months']}번/{r['months']}개월(가장 나쁜 달 {r['worst_month']:+.2f}%)"
        s += f", 최대 낙폭 {min(r['mdd'], 0) or 0:.2f}%"
        lines.append(s)
        rows.append([nm(t), _pct(r["r1"], 2) if r["r1"] is not None else "-", _pct(r["ann"], 2) if r["ann"] is not None else "-",
                     share, f"{r['worst_day']:.2f}%" if r["worst_day"] < 0 else "없음",
                     f"{r['neg_months']}/{r['months']}" if r["months"] else "-", f"{min(r['mdd'], 0) or 0:.2f}%"])
    note = ("Yahoo Finance 일별 종가(원화), 거래일 기준, ondo 계산. 세금(이익의 15.4%)·거래 비용 제외. "
            "'연 환산'은 자료 시작일부터 지금까지의 수익률을 1년 기준으로 바꾼 값. " + PAST_NOTE)
    table = charts.table_html("파킹형 ETF, 얼마나 벌고 얼마나 흔들렸나",
                              ["ETF", "최근 1년", "연 환산(자료 시작부터)", "내린 날 비율", "가장 나쁜 하루", "내린 달/전체 달", "최대 낙폭"],
                              rows, note)
    facts = (HEAD + "\n" + "\n".join(lines) + f"\n- {note}\n"
             "- (예금·CMA·파킹통장 금리 숫자는 이 자료에 없음 - 비교 금리는 독자가 직접 확인하도록 안내만)\n"
             "[일반 원리 - 교과서 수준 설명]\n"
             "- 1년 수익률은 1년짜리 예금 금리(세전)와 같은 기준이라 나란히 놓고 볼 수 있다. 다만 예금 금리는 가입할 때 정해지고, "
             "이 ETF의 수익률은 그날그날 단기 금리를 따라 바뀐다.\n"
             "- ETF는 예금자보호 대상이 아니다(예금은 금융회사당 일정 금액까지 보호).\n"
             "- 국내 주식시장에서 ETF를 팔면 돈은 영업일 기준 이틀 뒤(T+2)에 출금할 수 있다. 장이 열린 시간에만 사고팔 수 있다.\n"
             "- 이자(예금)와 이 ETF의 이익은 둘 다 세금이 15.4%다(금융소득이 1년에 2천만 원을 넘으면 종합과세 대상).\n")
    return facts, table


# ------------------------------------------------------------
# 가격 받기 + 주제별 연결 (인터넷이 필요한 부분은 여기만)
# ------------------------------------------------------------

def _hist(t, period="5y", interval="1d", adjust=True):
    import yfinance as yf
    h = yf.Ticker(t).history(period=period, interval=interval, auto_adjust=adjust)
    if h is None or h.empty:
        return None
    try:
        h.index = h.index.tz_localize(None)       # 거래소마다 시간대가 달라 날짜가 안 맞는 문제(2026-11-06 금리표 누락)
    except (TypeError, AttributeError):
        pass
    return h


def guide_facts(topic_id, data_cache, rates_effect=None):
    """가이드 주제 id → (사실 자료 글, 표·그래프 HTML). 계산이 없는 주제거나 실패하면 ("", "")."""
    try:
        if topic_id == "expense-ratio":
            fees = {t.replace(".KS", ""): _parse_pct(d.get("expense_ratio")) for t, d in data_cache.items()}
            return render_expense(calc_expense(fees))
        if topic_id == "leverage-decay":
            b, l = _hist("QQQ", period="10y"), _hist("TQQQ", period="10y")
            if b is None or l is None:
                return "", ""
            return render_leverage(calc_leverage(b["Close"], l["Close"]), "QQQ", "TQQQ")
        if topic_id == "dca-vs-lump":
            res = {}
            for t in ("SPY", "QQQ"):
                h = _hist(t, interval="1mo")
                if h is not None:
                    res[t] = calc_dca(h["Close"])
            return render_dca(res)
        if topic_id == "mdd-risk":
            res = {}
            for t in ("QQQ", "SCHD", "TLT"):
                h = _hist(t, adjust=False)
                if h is not None:
                    res[t] = calc_drawdown(h["Close"])
            return render_drawdown(res)
        if topic_id == "dividend-growth":
            import yfinance as yf
            res = {}
            for t in ("SCHD", "VYM", "DGRO"):
                h = _hist(t, period="10y", adjust=False)
                if h is not None:
                    dv = yf.Ticker(t).dividends
                    try:
                        dv.index = dv.index.tz_localize(None)
                    except (TypeError, AttributeError):
                        pass
                    res[t] = calc_dividend(dv, h["Close"])
            return render_dividend(res)
        if topic_id == "covered-call-structure":
            res = {}
            for t in ("JEPI", "QYLD", "QQQ"):
                h = _hist(t, adjust=False)
                if h is not None and "Adj Close" in h:
                    res[t] = calc_total_vs_price(h["Close"], h["Adj Close"])
            return render_covered(res)
        if topic_id == "hedged-vs-unhedged":
            g, fx, hk = _hist("GLD", period="2y"), _hist("KRW=X", period="2y"), _hist("132030.KS", period="2y")
            if g is None or fx is None or hk is None:
                return "", ""
            more = []
            sp, sh = _hist("SPY", period="2y"), _hist("143850.KS", period="2y")    # TIGER 미국S&P500선물(H)
            if sp is not None and sh is not None:
                more.append((calc_fx_hedge(sp["Close"], fx["Close"], sh["Close"]), "SPY(미국 S&P500)", "TIGER 미국S&P500선물(H)"))
            return render_fx_hedge(calc_fx_hedge(g["Close"], fx["Close"], hk["Close"]), "GLD(금)", "KODEX 골드선물(H)", more)
        if topic_id.startswith("market-"):          # 11-21 나라별 시장
            cfg = COUNTRIES.get(topic_id[7:])
            if not cfg:
                return "", ""
            u, fx = _hist(cfg["usd"], period="6y"), _hist("KRW=X", period="6y")
            if u is None or fx is None:
                return "", ""
            up = _hist(cfg["usd"], period="5y", adjust=False)
            ref = _hist("SPY", period="6y")
            kr = _hist(cfg["kr"], period="6y") if cfg.get("kr") else None
            return render_country(calc_country(u["Close"], fx["Close"], ref["Close"] if ref is not None else None,
                                               kr["Close"] if kr is not None else None,
                                               up["Close"] if up is not None else None), cfg)
        if topic_id == "parking-etf":
            res = {}
            for t in data_cache:
                h = _hist(t, period="5y")
                if h is not None:
                    res[t] = calc_parking(h["Close"])
            names = {t: (d.get("name") or "")[:30] for t, d in data_cache.items()}
            return render_parking(res, names)
        if topic_id == "bond-duration" and rates_effect:
            return rates_effect(data_cache)
    except Exception as e:
        print(f"ℹ️ 가이드 계산 실패({topic_id}): {type(e).__name__}: {e}")
    return "", ""
