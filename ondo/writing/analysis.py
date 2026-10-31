"""ETF 종목 분석 글을 새 편집국으로 쓴다(4단계, 2026-10-31).

예전 5조각 방식(etf_auto._generate_chained_article)은 끄고(되돌리려면 .env에 ANALYSIS_WRITER=legacy),
etf_auto가 이미 계산해 둔 자료(collected_context)와 코드가 만든 그래프·표를 그대로 받아:
  1) 그래프·표를 "시각 자료 서랍"에 넣고 → 기획이 글마다 2~3개를 골라 섹션 뒤에 배치
  2) 글은 편집국(한 번에 쓰기 + 검토 3명 + 고쳐쓰기)이 씀
  3) 맨 위에 온도 서명 띠(숫자만)
서랍에 넣지 않는 것: 연령별 포트폴리오, 경제 사이클, 매매 타이밍, 가상 포트폴리오, 반박 섹션, 투자 매력도 점수
(다른 ETF에도 그대로 들어가는 일반론이거나, 점수·타이밍이 투자 권유처럼 읽혀서).
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
    ("fees", "실제 비용 비교표", "보수와 세금을 포함한 실제 비용 비교", "비용, 세금, 계좌"),
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
        drawer.append({"id": sid, "name": name, "desc": desc, "fits": fits})
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
