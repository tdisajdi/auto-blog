"""온도판(데이터 페이지) 시제품 - 2026-11-11 사용자 결정. AI 호출 없이 공개 시세로 '1년 범위 속 지금 위치'를 그린다.
- 온도 = 지난 1년 최저 0° ~ 최고 100° 사이 지금 값의 위치(사실 숫자, 해석이 갈리지 않음). 매수·매도 판단 문구는 넣지 않는다.
- 예전 '종합 시장 온도'(가중치·밸류에이션 근사)는 시제품에서 뺐다 - 근거를 설명하기 어려운 숫자는 데이터 페이지 신뢰를 깎는다.
- 워드프레스 '페이지'(주소 ondo-board)로 비공개 초안. 공개 페이지는 건드리지 않음(site_pages/upload.py 보호 장치)."""
import html
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ondo.config import NAVY, NAVY_LIGHT, GOLD, TEXT, MUTED   # noqa: E402

# (티커, 이름, 단위, 소수 자리, 높을 때/낮을 때 무엇을 뜻하나 - 사실 설명만)
ITEMS = [
    ("KRW=X", "원/달러 환율", "원", 1, "높을수록 원화가 약함(달러로 사는 해외 자산은 원화로 비싸짐)"),
    ("^TNX", "미국 10년물 국채 금리", "%", 3, "높을수록 채권 가격은 낮음(금리와 채권 가격은 반대로 움직임)"),
    ("^VIX", "변동성 지수(VIX)", "", 2, "높을수록 시장이 앞으로 크게 움직일 거라고 보는 정도가 큼"),
    ("BZ=F", "브렌트유", "달러/배럴", 2, "가장 가까운 만기 선물 가격 - 만기 교체 때 하루 값이 튈 수 있음"),
    ("GC=F", "금", "달러/온스", 1, "가장 가까운 만기 선물 가격"),
    ("^GSPC", "S&P 500", "", 0, "미국 대형주 500개 지수(배당 제외)"),
    ("^KS11", "코스피", "", 0, "한국 유가증권시장 지수(배당 제외)"),
]


def card_stats(close):
    """close: 최근 1년 일별 종가(pandas Series). 반환: 지금 값·1년 최저/최고(날짜)·위치·평균 대비·1주·1달 변화. 자료가 짧으면 None."""
    c = close.dropna()
    if len(c) < 60:
        return None
    last = float(c.iloc[-1])
    lo, hi = float(c.min()), float(c.max())
    pos = (last - lo) / (hi - lo) * 100 if hi > lo else 50.0
    avg = float(c.mean())
    pick = lambda n: float(c.iloc[-1 - n]) if len(c) > n else None
    w, m = pick(5), pick(21)
    return {"last": last, "lo": lo, "hi": hi, "lo_date": f"{c.idxmin():%Y-%m-%d}", "hi_date": f"{c.idxmax():%Y-%m-%d}",
            "pos": round(pos), "vs_avg": (last / avg - 1) * 100, "w1": (last / w - 1) * 100 if w else None,
            "m1": (last / m - 1) * 100 if m else None, "as_of": f"{c.index[-1]:%Y-%m-%d}"}


def band(pos):
    """위치를 말로 - 사실 묘사만(좋다/나쁘다 없음)."""
    return "지난 1년 중 아주 높은 편" if pos >= 85 else "지난 1년 중 높은 편" if pos >= 60 else \
        "지난 1년 중간쯤" if pos > 40 else "지난 1년 중 낮은 편" if pos > 15 else "지난 1년 중 아주 낮은 편"


def _fmt(v, d):
    return f"{v:,.{d}f}"


def _pct(v):
    return "-" if v is None else f"{v:+.1f}%"


def render(cards, updated):
    """cards: [(item, stats)]. 페이지 HTML(스타일 포함) - 휴대폰에서도 한 줄 카드로 내려옴."""
    css = f"""<style>
.ob{{background:{NAVY};color:{TEXT};padding:22px 16px;border-radius:12px;font-family:inherit}}
.ob h2{{color:{GOLD};font-size:20px;margin:6px 0 4px}} .ob .sub{{color:{MUTED};font-size:13px;margin:0 0 16px}}
.ob-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
.ob-card{{background:{NAVY_LIGHT};border-radius:10px;padding:14px}}
.ob-name{{font-weight:700;font-size:15px}} .ob-val{{font-size:22px;font-weight:800;margin:4px 0}}
.ob-unit{{font-size:12px;color:{MUTED};font-weight:400}}
.ob-bar{{position:relative;height:10px;border-radius:5px;background:linear-gradient(90deg,#2c5aa0,#8a96b0,#c0392b);margin:10px 0 4px}}
.ob-dot{{position:absolute;top:-4px;width:4px;height:18px;background:{GOLD};border-radius:2px}}
.ob-temp{{color:{GOLD};font-weight:800}} .ob-row{{font-size:12.5px;color:{MUTED};line-height:1.7}}
.ob-note{{font-size:12px;color:{MUTED};margin-top:6px}} .ob-sec{{margin-top:22px;font-size:13.5px;line-height:1.8}}
.ob-sec h3{{color:{GOLD};font-size:16px;margin:0 0 6px}}
</style>"""
    out = [css, '<div class="ob">', '<h2>ONDO BOARD · 1년 범위로 보는 지금</h2>',
           f'<p class="sub">지난 1년 가장 낮았던 값을 0°, 가장 높았던 값을 100°로 놓고 지금 값의 위치를 보여 줍니다. {html.escape(updated)} 기준 · 자료: Yahoo Finance</p>',
           '<div class="ob-grid">']
    for (tk, name, unit, d, meaning), s in cards:
        out.append(
            f'<div class="ob-card"><div class="ob-name">{html.escape(name)}</div>'
            f'<div class="ob-val">{_fmt(s["last"], d)} <span class="ob-unit">{html.escape(unit)}</span></div>'
            f'<div class="ob-bar"><span class="ob-dot" style="left:calc({s["pos"]}% - 2px)"></span></div>'
            f'<div class="ob-row"><span class="ob-temp">{s["pos"]}°</span> · {band(s["pos"])}</div>'
            f'<div class="ob-row">1년 최저 {_fmt(s["lo"], d)} ({s["lo_date"]}) · 최고 {_fmt(s["hi"], d)} ({s["hi_date"]})</div>'
            f'<div class="ob-row">1년 평균 대비 {_pct(s["vs_avg"])} · 1주 {_pct(s["w1"])} · 1달 {_pct(s["m1"])}</div>'
            f'<div class="ob-note">{html.escape(meaning)} · {s["as_of"]} 종가</div></div>')
    out.append('</div>')
    out.append('<div class="ob-sec"><h3>온도를 읽는 법</h3>'
               '<p>온도는 "지금 값이 지난 1년 범위에서 어디쯤인가"만 뜻합니다. 100°라고 더 오를 수 없다는 뜻이 아니고, 0°라고 바닥이라는 뜻도 아닙니다. '
               '같은 숫자를 뉴스에서 봤을 때 "1년 기준으로 높은 편인지 낮은 편인지"를 바로 가늠하는 용도입니다.</p></div>')
    out.append('<div class="ob-sec"><h3>계산 방법</h3>'
               '<p>온도 = (지금 값 − 1년 최저) ÷ (1년 최고 − 1년 최저) × 100. 1년 평균 대비 = 지금 값 ÷ 최근 1년 일별 종가 평균 − 1. '
               '1주·1달 변화 = 5거래일·21거래일 전 종가와 비교. 원유·금은 가장 가까운 만기 선물이라 만기 교체 시점에 값이 튈 수 있습니다. '
               '지수는 배당을 뺀 가격입니다. 자료를 받지 못한 지표는 그날 빠집니다.</p>'
               '<p>이 페이지는 투자 권유가 아닙니다(<a href="/disclaimer" style="color:#e8b944">면책 안내</a>).</p></div>')
    out.append('</div>')
    return "\n".join(out)


def build():
    import yfinance as yf
    cards = []
    for it in ITEMS:
        try:
            s = card_stats(yf.Ticker(it[0]).history(period="1y")["Close"])
            if s:
                cards.append((it, s))
            else:
                print(f"ℹ️ {it[1]}: 자료 부족 - 뺌")
        except Exception as e:
            print(f"ℹ️ {it[1]}: 못 받음({type(e).__name__}) - 뺌")
    from ondo.config import kst_now
    return cards, render(cards, f"{kst_now():%Y-%m-%d %H:%M} (한국 시간)")


def main(status="draft"):
    cards, page = build()
    print(f"온도판 카드 {len(cards)}/{len(ITEMS)}개")
    if len(cards) < 4:
        print("카드가 너무 적어 올리지 않음")
        return 1
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site_pages"))
    import upload
    ok, msg = upload.upsert_page({"slug": "ondo-board", "title": "ONDO BOARD · 1년 범위로 보는 지금", "html": page}, status)
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "draft"))
