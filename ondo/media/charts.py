"""디자인부: 움직이는 그래프(Plotly). 그림 파일을 올리지 않고 글 안에서 바로 그린다.

워드프레스 토큰에 그림 업로드 권한이 없어도 동작한다(2026-10-31 사용자 선택: 움직이는 그래프).
ETF 종목 분석 글(etf_auto.py 백테스트 차트)과 같은 방식: Plotly를 한 번만 불러오고 차트마다 그린다.

spec 모양:
  {"title": "...", "kind": "bar" | "line", "labels": [...],
   "series": [{"name": "...", "values": [...]}, ...]   # 여러 줄
   또는 "values": [...]                               # 한 줄
   "unit": "만 원", "source": "자료 출처"}
"""
import html
import json
import uuid

from ondo.config import GOLD, NAVY

PLOTLY_SRC = "https://cdn.plot.ly/plotly-2.34.0.min.js"
PALETTE = [NAVY, GOLD, "#3a7bd5", "#8a96b0", "#2e8b57"]


def _js(obj):
    # 워드프레스가 글 안의 &를 &#038;로 바꾸는 경우가 있어(design/DESIGN_NOTES.txt) &, <, >는 유니코드 이스케이프로
    return (json.dumps(obj, ensure_ascii=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))


def _series(spec):
    if spec.get("series"):
        return [s for s in spec["series"] if s.get("values")]
    return [{"name": spec.get("title", ""), "values": spec.get("values") or []}]


def valid(spec):
    labels = list((spec or {}).get("labels") or [])
    series = _series(spec or {})
    # 점이 2개뿐이면 그래프가 주는 정보가 거의 없다(문장으로 충분)
    return bool(series) and len(labels) >= 3 and all(len(s["values"]) == len(labels) for s in series)


def plotly_html(spec):
    """spec → <figure class="ondo-chart"> 움직이는 그래프. 모양이 맞지 않으면 빈 문자열."""
    if not valid(spec):
        return ""
    cid = "ondo_chart_" + uuid.uuid4().hex[:8]
    kind = spec.get("kind") or ("bar" if len(spec["labels"]) <= 6 else "line")
    unit = spec.get("unit", "")
    data = []
    for i, s in enumerate(_series(spec)):
        color = PALETTE[i % len(PALETTE)]
        tr = {"type": "bar" if kind == "bar" else "scatter", "name": s["name"], "x": spec["labels"],
              "y": s["values"], "hovertemplate": "%{x}: %{y:,}" + unit + "<extra>" + str(s["name"]) + "</extra>"}
        if kind == "bar":
            tr["marker"] = {"color": color}
        else:
            tr.update(mode="lines+markers", line={"color": color, "width": 3})
        data.append(tr)
    layout = {"title": {"text": spec.get("title", ""), "font": {"size": 16}}, "template": "plotly_white",
              "barmode": "group", "height": 400, "margin": {"t": 60, "b": 50, "l": 60, "r": 20},
              "yaxis": {"title": unit, "tickformat": ","}, "legend": {"orientation": "h", "y": -0.18},
              "hovermode": "x unified" if kind == "line" else "closest"}
    js = (
        "<script>(function(){"
        f"function draw(){{var gd=document.getElementById('{cid}');if(!gd)return;"
        f"Plotly.newPlot(gd,{_js(data)},{_js(layout)},{{responsive:true,displaylogo:false}});}}"
        "if(window.Plotly){draw();return;}"
        "var s=document.getElementById('ondo-plotly');"
        "if(s){s.addEventListener('load',draw);return;}"
        f"s=document.createElement('script');s.id='ondo-plotly';s.src='{PLOTLY_SRC}';s.onload=draw;"
        "document.head.appendChild(s);"
        "})();</script>"
    )
    title = html.escape(spec.get("title", "데이터 그래프"))
    src = html.escape(spec.get("source", ""))
    return (f'<figure class="ondo-chart" style="margin:28px 0;">'
            f'<div id="{cid}" role="img" aria-label="{title}" style="width:100%;min-height:400px;"></div>{js}'
            f'<figcaption style="font-size:13px;color:#8a96b0;margin-top:6px;">{title}'
            + (f" · 자료: {src}" if src else "") + "</figcaption></figure>")


def table_html(title, header, rows, note=""):
    """코드가 계산한 숫자 표(AI가 만든 표와 구분되게 출처·조건 문구를 붙인다)."""
    esc = html.escape
    th = "".join(f'<th style="border:1px solid #ddd;padding:8px;background:#f3f5f9;">{esc(str(h))}</th>' for h in header)
    body = "".join("<tr>" + "".join(f'<td style="border:1px solid #ddd;padding:8px;text-align:center;">{esc(str(c))}</td>'
                                    for c in r) + "</tr>" for r in rows)
    return (f'<div class="ondo-calc" style="margin:24px 0;overflow-x:auto;">'
            f'<p style="font-weight:700;margin:0 0 8px;">{esc(title)}</p>'
            f'<table style="width:100%;border-collapse:collapse;font-size:14px;"><tr>{th}</tr>{body}</table>'
            + (f'<p style="font-size:12px;color:#8a96b0;margin-top:6px;">{esc(note)}</p>' if note else "") + "</div>")


THERMO_PARTS = [("volatility", "변동성", 0.3), ("valuation", "밸류에이션", 0.3), ("fx", "환율", 0.2), ("inflation", "인플레이션", 0.2)]


def thermo_strip(indicators, date_label=""):
    """글 맨 위 '온도' 서명 띠: 숫자만 보여주고 매수·매도 판단 문구는 넣지 않는다(2026-10-31 사용자와 결정).
    종합 온도 = 변동성 30% + 밸류에이션 30% + 환율 20% + 인플레이션 20% (있는 지표만으로 다시 나눔, etf_auto와 같은 식).
    브랜드 글자는 영어(사용자 결정: 콘셉트 요소에 들어가는 글자는 영어)."""
    vals = [(name, w, indicators.get(key)) for key, name, w in THERMO_PARTS
            if isinstance((indicators or {}).get(key), (int, float))]
    if not vals:
        return ""
    composite = sum(v * w for _, w, v in vals) / sum(w for _, w, _ in vals)
    parts = " · ".join(f"{html.escape(n)} {round(v)}°" for n, _, v in vals)
    return (f'<div class="ondo-thermo" style="margin:0 0 22px;padding:10px 14px;border-radius:8px;'
            f'background:{NAVY};color:#e8ecf4;font-size:13px;line-height:1.7;">'
            f'<span style="font-weight:800;letter-spacing:1.5px;color:{GOLD};">ONDO MARKET TEMP</span> '
            f'<strong style="font-size:15px;">{round(composite)}°</strong> '
            f'<span style="opacity:.9;">({parts})</span> '
            f'<span style="opacity:.6;">· 자체 지표, 참고용{(" · " + html.escape(date_label) + " 기준") if date_label else ""}</span></div>')
