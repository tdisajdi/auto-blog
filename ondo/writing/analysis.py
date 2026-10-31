"""ETF 종목 분석 글을 새 편집국으로 쓴다(4단계, 2026-10-31).

예전 5조각 방식(etf_auto._generate_chained_article)은 끄고(되돌리려면 .env에 ANALYSIS_WRITER=legacy),
etf_auto가 이미 계산해 둔 자료(collected_context)와 코드가 만든 그래프·표를 그대로 받아:
  1) 그래프·표를 "시각 자료 서랍"에 넣고 → 기획이 글마다 2~3개를 골라 섹션 뒤에 배치
  2) 글은 편집국(한 번에 쓰기 + 검토 3명 + 고쳐쓰기)이 씀
  3) 맨 위에 온도 서명 띠(숫자만)
서랍에 넣지 않는 것: 연령별 포트폴리오, 경제 사이클, 매매 타이밍, 가상 포트폴리오, 반박 섹션, 투자 매력도 점수
(다른 ETF에도 그대로 들어가는 일반론이거나, 점수·타이밍이 투자 권유처럼 읽혀서),
계좌별 실수료 비교표(etf_auto._add_fee_comparison_table - 1억 원을 ISA·연금저축에 한 번에 넣는다고 가정(연 납입 한도 초과),
국내 대체 ETF 보수를 같은 값으로 가정, 10년 이익에 한 번에 과세 → 오해 소지. 대신 "tax" 계좌별 세금 계산표).
"""
import html as _html
import re

# (id, 이름, 무엇을 보여주는지, 어울리는 글) - 순서가 기본 우선순위(기획이 못 고르면 앞의 2개)
DRAWER_SPEC = [
    ("basic", "기본 정보 카드", "보수·배당·기간별 수익률·최대 낙폭 같은 핵심 숫자 카드", "모든 분석 글"),
    ("backtest", "거치식 vs 적립식 그래프", "같은 돈을 한 번에 넣었을 때와 매달 나눠 넣었을 때의 평가금액 변화(움직이는 그래프)",
     "장기 투자, 투자 방법"),
    ("competition", "비슷한 ETF 비교표", "같은 지수·비슷한 ETF와 보수·규모·수익률 비교", "비교, 상품 선택"),
    ("risk", "위기 시나리오 표", "과거 하락장 기준으로 계좌가 얼마나 줄 수 있는지", "위험, 하락장"),
    ("tax", "계좌별 세금 계산표", "한 해 이익 200만~2,000만 원일 때 해외 직접투자·국내 상장(일반계좌·ISA·연금저축)의 예상 세금(표+그래프)",
     "세금, 계좌, 한국 투자자 비용"),
    ("calendar", "손익 캘린더", "최근 몇 달 동안 날짜별로 오르고 내린 정도", "최근 흐름, 변동성"),
    ("sector", "섹터 구성", "어떤 산업에 얼마나 투자하는지", "구성, 경기 민감도"),
    ("scenario", "투자 시나리오 표", "상승·횡보·하락 시나리오별 결과", "전망, 시나리오"),
    ("macro", "시장 환경 온도계 전체", "변동성·밸류에이션·환율·인플레이션 4개 게이지", "시장 상황 자체가 주제일 때"),
]

ANALYSIS_RULES = (
    "- [계좌 원칙] 해외(미국 등) 상장 ETF는 ISA·연금저축·IRP로 직접 살 수 없습니다. 이 계좌를 언급할 때는 "
    "같은 지수의 국내 상장 ETF로만 설명하세요.\n"
    "- [투자 권유 금지] '지금 사세요', '매수 적기', '확실한 수익' 같은 표현은 금지. 판단 기준을 알려주는 글로 쓰세요.\n"
    "- [분석 원칙] 이 ETF만의 숫자(보수, 배당 내역, 기간별 수익률, 낙폭, 구성)로 설명하세요. "
    "연령별 포트폴리오·경제 사이클 같은 어느 ETF에나 들어갈 일반론 섹션은 만들지 마세요.\n"
    "- [배당 원칙] 배당 내역·증감률은 자료의 값을 그대로 쓰고, 표와 본문이 다른 숫자를 쓰지 않게 하세요.\n"
)


def demote_headings(block):
    """서랍 자료 안의 제목 태그를 굵은 글씨로 바꾼다(글의 목차·구조는 작가의 섹션만 갖도록)."""
    return re.sub(r"<h[1-4]([^>]*)>(.*?)</h[1-4]>",
                  r'<p class="ondo-figtitle" style="font-weight:700;margin:6px 0 8px;">\2</p>', block or "", flags=re.S)


def build_drawer(blocks):
    """blocks: {id: html}. 내용이 있는 것만 서랍에 넣는다. 반환: (drawer 목록, {id: html})."""
    drawer, html_by_id = [], {}
    for sid, name, desc, fits in DRAWER_SPEC:
        h = (blocks or {}).get(sid) or ""
        if len(re.sub(r"<[^>]+>", "", h).strip()) < 10 and "<script" not in h:
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", h, flags=re.S)).strip()
        drawer.append({"id": sid, "name": name, "desc": desc, "fits": fits, "text": plain[:3000]})
        html_by_id[sid] = f'<div class="ondo-visual" data-visual="{sid}" style="margin:26px 0;">{demote_headings(h)}</div>'
    return drawer, html_by_id


def strip_advice(facts_text):
    """예전 '투자 온도계' 해석 문장(매수 시점 판단)은 자료에서 뺀다."""
    return re.sub(r"\[투자 온도계\][^\[]*", "", facts_text or "")


def recent_visual_combos(state, n=3):
    out = []
    for a in reversed((state or {}).get("articles", [])):
        meta = (a.get("topic_data") or {}).get("_meta") or {}
        if meta.get("article_type") in ("analysis", "comparison") and meta.get("visuals"):
            out.append(meta["visuals"])
        if len(out) >= n:
            break
    return out


def closing_html(news):
    esc = _html.escape
    items = "".join(f'<li><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["source"])}</a> - {esc(n["title"])}</li>'
                    for n in news or [] if n.get("url"))
    return ('<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-radius:6px;font-size:13px;line-height:1.7;">'
            "<strong>📌 데이터 출처</strong><br/>ETF 가격·배당: Yahoo Finance, 국내 ETF 정보: 네이버 금융·KRX, "
            "그래프·표: ondo가 위 자료로 직접 계산"
            + (f'<ul style="margin:8px 0 0 18px;">{items}</ul>' if items else "") + "</div>"
            '<p style="margin-top:20px;font-size:12px;color:#888;line-height:1.7;">이 글은 공개 데이터를 정리한 정보 제공용 글이며, '
            "특정 상품의 매수·매도를 권유하지 않습니다. 투자 판단과 책임은 본인에게 있습니다.</p>")


def insert_visuals(body, picks, html_by_id):
    """'섹션 k 뒤' = k+1번째 <h3>(다음 섹션·FAQ·정리) 바로 앞. 그 앞의 구분선(div)보다도 앞에 넣는다."""
    heads = [m.start() for m in re.finditer(r"<h3[\s>]", body)]
    divider = '<div style="width:100%; height:1px; background-color:#ddd; margin:40px 0;"></div>'
    inserts = []
    for p in picks or []:
        h = html_by_id.get(p["id"])
        if not h:
            continue
        k = p["after_section"]
        if k < len(heads):
            pos = heads[k]
            if body[:pos].rstrip().endswith(divider):
                pos = body[:pos].rstrip().rfind(divider)
        else:
            pos = len(body)
        inserts.append((pos, h))
    for pos, h in sorted(inserts, key=lambda x: x[0], reverse=True):
        body = body[:pos] + h + body[pos:]
    return body


# ------------------------------------------------------------
# 자료표: etf_auto가 모은 원래 값으로 새로 만든다(2026-10-31).
# 예전 자료 덩어리(collected_context)에는 옛 AI용 지시문, 투자 매력도 점수, 오해하기 쉬운 이름표
# ("배당 1억 기준 160,500원" - 실제로는 투자금 1억 원의 배당에 붙는 세금)가 섞여 있어 작가가 잘못 읽었다.
# 원칙: 항목마다 기간·단위·기준을 이름표에 붙이고, 값이 없으면 줄 자체를 뺀다.
# ------------------------------------------------------------
_EMPTY = ("", None, "정보 없음", "N/A", "-", "기록 없음", "공식 홈페이지 정보 없음")


def _pct(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else None


def _num(s):
    try:
        return float(str(s).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _won(v):
    return f"약 {round(v / 10000):,}만 원" if v >= 10000 else f"약 {round(v):,}원"


def _line(label, value):
    return f"- {label}: {value}" if value not in _EMPTY else None


def ticker_facts(ticker, d, ea, today_label):
    code = ticker.replace(".KS", "")
    overseas = ea._is_overseas_listed(d)
    r = d.get("returns") or {}
    rets = ", ".join(f"{k} {_pct(v)}" for k, v in r.items() if _pct(v))
    cagr = d.get("cagr")
    divs = "; ".join(f"{x.get('date')} {x.get('val')} (직전 대비 {x.get('change', '-')})" for x in d.get("div_history") or [])
    lines = [f"[{code} - {d.get('name', code)}]",
             _line("상장", f"{d.get('listing') or ('해외 상장' if overseas else '국내 상장')}"
                          + (f", 상장일 {d['inception_date']}" if d.get("inception_date") not in _EMPTY else "")),
             _line("운용사", d.get("issuer")),
             _line("투자 대상 설명(운용사 원문 요약, 영어면 뜻만 옮길 것)", (d.get("description") or "")[:220] or None),
             _line("운용보수(연)", d.get("expense_ratio")),
             _line("순자산(규모)", d.get("aum_str")),
             _line(f"기간별 가격 수익률({today_label} 기준, 배당 제외)", rets or None),
             _line(f"상장 이후 연평균 수익률(CAGR, {d.get('inception_date', '상장일')}부터 - 상장일이 다른 ETF와 직접 비교 금지)",
                   f"{cagr * 100:.1f}%" if isinstance(cagr, (int, float)) else None),
             _line("최대 낙폭(최근 5년, 고점 대비 가장 크게 떨어진 정도)", d.get("mdd")),
             _line("배당 주기", d.get("div_cycle")),
             _line("최근 배당수익률(최근 1년 배당 ÷ 현재 가격)", d.get("yield") if not (code.isdigit() and _num(d.get("yield")) == 0) else None),
             _line("최근 배당 내역(지급일 금액, 직전 대비 증감)", divs or None),
             _line("배당 변화 결론(코드가 위 내역으로 계산 - 이 문장 그대로 인용)", d.get("dividend_stability_desc")),
             _line("배당성장률(코드 계산값 - '연평균 배당 증가율'로만 언급)", d.get("dividend_growth_rate")),
             _line("5년 전 1,000만 원을 한 번에 넣었다면(가격 기준 계산)", d.get("simulated_result")),
             _line("환율 영향", d.get("fx_exposure")),
             _line("계좌", ea.OVERSEAS_ACCOUNT_NOTE if overseas else "국내 상장 ETF라 ISA·연금저축·IRP 계좌로도 살 수 있음"),
             ]
    # 세금: 코드가 직접 계산(가정을 이름표에 붙인다)
    y = _num(d.get("yield"))
    if y and y > 0:
        div = 100_000_000 * y / 100
        rate = ea.TAX_US_DIVIDEND_WITHHOLDING if overseas else ea.TAX_DOMESTIC_DIVIDEND
        lines.append(f"- 배당 세금 예시(코드 계산): 투자금 1억 원 × 배당수익률 {y:.2f}% = 연 배당 {_won(div)} → "
                     f"세금 {_won(div * rate)}({'미국 원천징수 15%' if overseas else '배당소득세 15.4%'})")
    gain = 10_000_000
    if overseas:
        cg = max(0, gain - ea.OVERSEAS_CG_DEDUCTION) * ea.TAX_OVERSEAS_CAPITAL_GAINS
        lines.append(f"- 매매차익 세금 예시(코드 계산): 한 해 이익 1,000만 원이면 연 250만 원 공제 후 22% → 양도소득세 {_won(cg)}"
                     "(다음 해 5월 직접 신고, 해외 주식 이익·손실은 합산해서 계산)")
    else:
        lines.append(f"- 매매차익 세금 예시(코드 계산): 국내 상장 해외지수 ETF는 한 해 이익 1,000만 원이면 15.4% → {_won(gain * ea.TAX_DOMESTIC_DIVIDEND)}"
                     f", ISA(일반형)라면 200만 원 공제 후 9.9% → {_won(max(0, gain - ea.ISA_TAX_FREE_LIMIT) * ea.ISA_SEPARATE_TAX)}"
                     " (국내 주식형 ETF라면 매매차익 비과세)")
    fee = d.get("fee_impact_100m_10y")
    if fee not in _EMPTY:
        lines.append(f"- 보수 차이 예시(코드 계산): 운용보수가 0.1%p 더 높은 ETF와 비교하면 1억 원을 10년 둘 때 차이 "
                     f"{str(fee).split('(')[0].strip()}")
    return "\n".join(l for l in lines if l)


def previous_facts(previous_analyses):
    out = []
    for code, a in (previous_analyses or {}).items():
        prev = a.get("previous")
        if not prev:
            continue
        past = next((v for k, v in (prev.get("etf_data") or {}).items() if code in k and isinstance(v, dict)), None)
        if not past:
            continue
        one = (past.get("returns") or {}).get("1년")
        out.append(f"- {code} 지난 분석({prev.get('date_display')}): 배당수익률 {past.get('yield', '-')}, "
                   f"최대 낙폭 {past.get('mdd', '-')}, 1년 수익률 {_pct(one) or '-'} → 오늘 값과 비교해 무엇이 달라졌는지 설명")
    return ("[지난 분석과 비교]\n" + "\n".join(out) + "\n") if out else ""


def fact_sheet(etf_list, cache, ea, macro, news, drawer_html, today_label, previous_analyses=None):
    parts = ["[사실 자료 - 종목 데이터. 항목 이름표의 기간·단위·기준을 그대로 지켜서 쓰세요]"]
    parts += [ticker_facts(t, cache[t], ea, today_label) for t in etf_list if t in cache]
    parts.append(previous_facts(previous_analyses))
    parts.append(f"[오늘 시장 수치 - 이 ETF 설명과 직접 관련 있을 때만 쓰기]\n"
                 f"- 원/달러 환율 {macro.get('usd_krw')}, 미국 10년물 국채 금리 {macro.get('us_10y')}, "
                 f"공포·탐욕 지수 {macro.get('fear_greed')}")
    if news:
        parts.append("[관련 뉴스 - 인용할 때 매체명에 링크]\n" + "\n".join(f"- {n['title']} ({n['source']}) {n['url']}" for n in news))
    vis = []
    for sid, h in (drawer_html or {}).items():
        t = re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", h, flags=re.S)).strip()
        if t:
            vis.append(f"- {sid}: {t[:700]}")
    if vis:
        parts.append("[시각 자료에 담긴 숫자 - 기획이 고른 자료는 본문에 그대로 들어가니, 그 자료를 해석할 때 이 숫자를 쓰세요]\n" + "\n".join(vis))
    return "\n\n".join(p for p in parts if p)


# 종목 분석 글이 꼭 답해야 할 질문(순서·제목·관점은 자유). 사실 검증 담당이 빠졌는지 확인한다.
MUST_ANSWER = {
    "analysis": ["이 ETF는 무엇에 투자하나(추종 대상·구성)", "기간별 수익과 최대 낙폭은 어땠나",
                 "배당은 얼마나, 어떻게 변했나", "한국 투자자가 부담하는 비용·세금·환율 영향은",
                 "비슷한 상품과 비교해 무엇이 다른가(비교 자료가 있을 때)"],
    "comparison": ["두 ETF는 각각 무엇에 투자하나", "같은 기간 수익과 낙폭은 어떻게 달랐나", "보수·배당 차이는",
                   "한국 투자자 기준 세금·계좌·환율 차이는", "어떤 조건이면 어느 쪽이 맞는지(권유가 아닌 판단 기준)"],
}
