"""글 화면 2안 시안(11-19 사용자: '본문이 재미없어 보이고, 왼쪽 목차와 본문 사이가 멀다, 왼쪽처럼 우리만의 느낌을').
사이트 CSS(theme/ondo.css) + 새 본문 부품 CSS를 입혀 세금 글 일부를 다시 꾸민 모형. 실제 사이트는 안 바꿈."""
import os, re, sys, json, subprocess, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from site_pages import theme_push, cover

FONTS = sys.argv[1] if len(sys.argv) > 1 else None
css = theme_push.css_block().replace("<!-- wp:html -->", "").replace("<!-- /wp:html -->", "")
css = re.sub(r'<link rel="stylesheet" href="https://cdn\.jsdelivr[^>]*>', "", css)
fontcss = cover.fonts_css(FONTS).replace("font-family:G11", "font-family:'Galmuri11'").replace("font-family:Pret", "font-family:'Pretendard Variable'")
thermo = theme_push.svg(True)
part = lambda n: theme_push.fill(re.sub(r"<!-- /?wp:html -->", "", open(os.path.join(ROOT, "theme", "parts", n + ".html"), encoding="utf-8").read()))

NEW_CSS = """
/* ---- 2안: 왼쪽 목차를 본문에 붙인 '계기판' + 본문 부품 ---- */
@media(min-width:1361px){.o-post{grid-template-columns:230px minmax(0,var(--o-read)) 280px;gap:0 28px}}
.o-toc-col{padding-top:6px}
.v2-dash{position:sticky;top:96px;background:var(--o-card);border:2px solid var(--o-ink);box-shadow:6px 6px 0 var(--o-ink);}
.v2-dash .o-readtemp{display:flex;align-items:center;gap:10px;padding:14px 14px 12px;border-bottom:2px dashed var(--o-line)}
.v2-dash .o-readtemp svg{width:26px;height:auto}
.v2-dash .o-readtemp .o-px{font-size:13px}
.v2-dash .o-toc{position:static;border:0;padding:12px 14px 14px;max-height:none}
.v2-dash .v2-key{border-top:2px dashed var(--o-line);padding:12px 14px 14px;font-size:13px}
.v2-dash .v2-key b{display:block;font-size:22px;font-weight:800;color:var(--o-ink);font-variant-numeric:tabular-nums}
.v2-tag{font-family:var(--o-px);font-size:11px;letter-spacing:.08em;color:#fff;background:var(--o-navy);padding:4px 8px;display:inline-block}
/* 결론 먼저 카드 */
.v2-answer{border:2px solid var(--o-ink);box-shadow:6px 6px 0 var(--o-ink);background:var(--o-card);margin:0 0 36px}
.v2-answer .h{display:flex;justify-content:space-between;align-items:center;background:var(--o-navy);color:#fff;padding:8px 14px;font-family:var(--o-px);font-size:12px;letter-spacing:.12em}
.v2-answer .tiles{display:grid;grid-template-columns:repeat(3,1fr)}
.v2-answer .t{padding:16px 16px 14px;border-right:2px dashed var(--o-line)}.v2-answer .t:last-child{border-right:0}
.v2-answer .t b{display:block;font-size:30px;font-weight:800;line-height:1.15;font-variant-numeric:tabular-nums}
.v2-answer .t span{font-size:14px;color:var(--o-ink-2)}
.v2-gauge{padding:6px 16px 18px}
.v2-gauge .bar{display:grid;grid-template-columns:repeat(20,1fr);gap:3px;position:relative}
.v2-gauge .bar i{height:16px;display:block}
.v2-gauge .mk{position:relative;height:30px}
.v2-gauge .mk em{position:absolute;top:4px;transform:translateX(-50%);font-style:normal;font-family:var(--o-px);font-size:11px;white-space:nowrap}
.v2-gauge .mk em:before{content:'';position:absolute;left:50%;top:-10px;width:2px;height:8px;background:var(--o-ink)}
/* 질문 소제목 */
.v2-q{font-family:'Galmuri11',var(--o-sans)!important;font-size:24px!important;border:0!important;padding:0!important;display:flex;gap:12px;align-items:flex-start}
.v2-q:before{content:'Q';flex:none;font-family:var(--o-px);font-size:15px;color:#fff;background:var(--o-cold);width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;box-shadow:3px 3px 0 var(--o-ink);margin-top:2px}
/* 숫자 강조·용어 */
.v2-n{font-weight:800;background:linear-gradient(transparent 62%,#ffe08a 62%);font-variant-numeric:tabular-nums}
.v2-term{border-bottom:2px dotted var(--o-cold);cursor:help;position:relative}
.v2-term .tip{position:absolute;max-width:80vw;left:0;top:130%;width:260px;background:var(--o-ink);color:#fff;font-size:13px;line-height:1.6;padding:10px 12px;z-index:5;box-shadow:4px 4px 0 var(--o-cold)}
/* VS 카드 */
.v2-vs{display:grid;grid-template-columns:1fr 54px 1fr;align-items:stretch;margin:22px 0 30px}
.v2-vs .c{border:2px solid var(--o-ink);background:var(--o-card);box-shadow:5px 5px 0 var(--o-ink)}
.v2-vs .c .hd{padding:8px 12px;color:#fff;font-family:var(--o-px);font-size:13px;letter-spacing:.06em}
.v2-vs .c dl{margin:0;padding:10px 12px}.v2-vs .c dt{font-size:12px;color:var(--o-ink-3)}.v2-vs .c dd{margin:0 0 8px;font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
.v2-vs .x{display:flex;align-items:center;justify-content:center;font-family:var(--o-px);font-size:18px}
/* 온도계 한마디 */
.v2-note{display:flex;gap:14px;align-items:flex-start;margin:6px 0 30px}
.v2-note .m{flex:none;width:34px}
.v2-note .b{position:relative;background:#fff8e1;border:2px solid var(--o-ink);padding:12px 14px;font-size:16px;line-height:1.7}
.v2-note .b:before{content:'ONDO NOTE';display:block;font-family:var(--o-px);font-size:11px;letter-spacing:.1em;color:var(--o-warm);margin-bottom:4px}
/* 도트 막대 비교 */
.v2-bars{border:2px solid var(--o-ink);background:var(--o-card);padding:14px 16px;margin:20px 0 30px;box-shadow:6px 6px 0 var(--o-line)}
.v2-bars .r{display:grid;grid-template-columns:86px 1fr 92px;gap:10px;align-items:center;margin:6px 0;font-size:14px}
.v2-bars .cells{display:grid;grid-template-columns:repeat(40,1fr);gap:2px}.v2-bars .cells i{height:12px;display:block;background:#ece6d6}
.v2-bars .lg{font-family:var(--o-px);font-size:11px;display:flex;gap:16px;margin-bottom:8px}
.v2-bars .lg span:before{content:'';display:inline-block;width:10px;height:10px;margin-right:6px;background:currentColor}
/* 체크리스트 */
.v2-check{border:2px solid var(--o-ink);background:var(--o-card);padding:14px 16px;margin:24px 0}
.v2-check li{list-style:none;display:flex;gap:10px;align-items:flex-start;margin:8px 0}
.v2-check li:before{content:'';flex:none;width:16px;height:16px;border:2px solid var(--o-ink);margin-top:5px;box-shadow:2px 2px 0 var(--o-cold)}
.v2-check ul{padding:0;margin:0}
@media(max-width:700px){.v2-answer .tiles{grid-template-columns:1fr}.v2-answer .t{border-right:0;border-bottom:2px dashed var(--o-line)}.v2-vs{grid-template-columns:1fr;gap:10px}.v2-vs .x{height:20px}}
"""

def gauge():
    cells = "".join(f'<i style="background:{"#3d6dff" if i < 8 else "#ff8a3d"}"></i>' for i in range(20))
    return (f'<div class="v2-gauge"><div class="bar">{cells}</div><div class="mk">'
            f'<em style="left:0%">0</em><em style="left:41.6%">833만 원 = 같음</em><em style="left:100%;transform:translateX(-100%)">2,000만 원</em></div></div>')

def bars():
    rows = [("200만 원", 0, 30.8), ("500만 원", 55, 77), ("1,000만 원", 165, 154), ("2,000만 원", 385, 308)]
    out = ['<div class="v2-bars"><div class="lg"><span style="color:#3d6dff">해외 상장 (22%, 250만 공제)</span><span style="color:#ff8a3d">국내 상장 (15.4%)</span></div>']
    for lab, a, b in rows:
        for v, c, show in ((a, "#3d6dff", True), (b, "#ff8a3d", False)):
            n = round(v / 385 * 40)
            cells = "".join(f'<i style="background:{c}"></i>' if i < n else "<i></i>" for i in range(40))
            out.append(f'<div class="r"><span>{lab if show else ""}</span><div class="cells">{cells}</div><b>{round(v)}만 원</b></div>')
    out.append('<div style="font-size:12px;color:#5c6575;margin-top:8px">한 해 이익별 세금 · 이 ETF에서만 이익이 난 경우 · 2026년 10월 세법으로 ondo 계산</div></div>')
    return "".join(out)

BODY = f"""
<div class="v2-answer"><div class="h"><span>ONDO READOUT · 결론 먼저</span><span>30 SEC</span></div>
<div class="tiles"><div class="t"><b>833만 원</b><span>한 해 이익이 이만큼이면 두 쪽 세금이 같아요</span></div>
<div class="t"><b style="color:#3d6dff">이보다 적으면</b><span>해외 상장 ETF 세금이 적음 (250만 원 공제)</span></div>
<div class="t"><b style="color:#ff8a3d">이보다 많으면</b><span>국내 상장 ETF 세금이 적음 (15.4% 단일)</span></div></div>{gauge()}</div>

<p>매달 50만 원씩 S&amp;P500에 넣는 직장인이라면, 같은 지수라도 <b>어느 시장에 상장된 ETF냐</b>에 따라 내는 세금이 달라져요. 갈림길은 한 해 이익 <span class="v2-n">833만 원</span>입니다.</p>

<h3 class="v2-q">같은 S&amp;P500인데, 뭐가 다른가요?</h3>
<div class="v2-vs"><div class="c"><div class="hd" style="background:#3d6dff">SPY · 미국 상장</div><dl><dt>운용보수</dt><dd>0.09%</dd><dt>1년 수익률 (달러 기준)</dt><dd>11.39%</dd><dt>5년 최대 낙폭</dt><dd>-24.50%</dd></dl></div>
<div class="x">VS</div>
<div class="c"><div class="hd" style="background:#ff8a3d">TIGER 미국S&amp;P500 · 국내 상장</div><dl><dt>운용보수</dt><dd>0.007%</dd><dt>1년 수익률 (원화 기준)</dt><dd>-0.62%</dd><dt>5년 최대 낙폭</dt><dd>-19.15%</dd></dl></div></div>
<div class="v2-note"><div class="m">{thermo}</div><div class="b">같은 지수인데 1년 수익률이 이렇게 다른 건, SPY는 <b>달러</b>로, TIGER는 <b>원화</b>로 잰 숫자라서예요. 그 사이 원/달러 환율 변화가 함께 들어갔어요.</div></div>
<p><span class="v2-term">운용보수<span class="tip">ETF 운용사가 매년 자산에서 떼어 가는 비용. 따로 내는 돈이 아니라 가격에 이미 반영돼요.</span></span>는 TIGER 쪽이 훨씬 낮지만, 세금까지 보면 이야기가 달라져요.</p>

<h3 class="v2-q">이익이 얼마면, 세금이 얼마예요?</h3>
<p>해외 상장은 <span class="v2-n">250만 원</span>을 빼고 <span class="v2-n">22%</span>, 국내 상장은 처음부터 <span class="v2-n">15.4%</span>. 그래서 이익이 작을 땐 해외 상장이, 커지면 국내 상장이 덜 내요.</p>
{bars()}

<h3 class="v2-q">내가 확인할 것 3가지</h3>
<div class="v2-check"><ul><li>한 해 이익이 833만 원을 넘을 것 같은가?</li><li>이자·배당을 합쳐 금융소득이 한 해 2,000만 원을 넘을 수 있나?</li><li>ISA(3년)·연금저축(55세 이후 수령) 조건을 지킬 수 있나?</li></ul></div>
"""

TOC = """<nav class="o-toc"><span class="o-px">CONTENTS</span><ol>
<li><a class="is-on" href="#">같은 S&amp;P500인데, 뭐가 다른가요?</a></li><li><a href="#">이익이 얼마면, 세금이 얼마예요?</a></li>
<li><a href="#">절세 계좌는 어떻게 달라요?</a></li><li><a href="#">내가 확인할 것 3가지</a></li></ol></nav>"""

html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{fontcss}</style>{css}<style>{NEW_CSS}</style></head><body class="single">{part('header')}
<div class="o-post-head"><div class="o-wrap"><div class="wp-block-post-terms"><a href="#">ETF</a></div>
<h1 class="wp-block-post-title">해외 상장 ETF vs 국내 상장 ETF, 한 해 이익 833만 원이 가르는 세금 차이</h1><div class="o-meta"><div class="wp-block-post-date">2026년 11월 19일</div><p>글 · ondo</p></div></div></div>
<main class="o-post"><aside class="o-toc-col"><div class="v2-dash"><div class="o-readtemp">{thermo}<span class="o-px">READ <b>19</b>%</span></div>{TOC}
<div class="v2-key"><span class="v2-tag">KEY NUMBER</span><b>833만 원</b>세금이 같아지는 한 해 이익</div></div></aside>
<article class="o-read"><div class="wp-block-post-content">{BODY}</div></article>
<aside class="o-side"><div class="o-side-in"><div style="border:2px solid #18202c;box-shadow:4px 4px 0 #e3dccb;background:#fffdf7;padding:14px 16px;font-weight:700">환율 정보 센터 ▸</div><div style="border:2px solid #18202c;box-shadow:4px 4px 0 #e3dccb;background:#fffdf7;padding:14px 16px;font-weight:700">이 글의 용어사전 ▸</div></div></aside></main></body></html>"""

out = os.path.join(ROOT, "lab", "mock")
open(os.path.join(out, "read_v2.html"), "w", encoding="utf-8").write(html)
jobs = [[os.path.join(out, "read_v2.html"), os.path.join(out, "read_v2_desk.png"), 1440, 2300], [os.path.join(out, "read_v2.html"), os.path.join(out, "read_v2_mobile.png"), 390, 2600]]
js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();for(const [f,o,w,h] of " + json.dumps(jobs) +
      "){const p=await b.newPage({viewport:{width:w,height:h}});await p.goto('file://'+f,{waitUntil:'networkidle'});await p.waitForTimeout(400);"
      "await p.screenshot({path:o,fullPage:false,clip:{x:0,y:0,width:w,height:h}});await p.close();}await b.close();})();")
subprocess.run(["node", "-e", js], check=True)
print("ok")
