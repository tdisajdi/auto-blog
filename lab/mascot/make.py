"""ondo 캐릭터 3종 시안(픽셀) - 11-24 사용자 요청. 사이트에는 아직 안 붙임(404·소개·바닥글, 애드센스 승인 뒤)."""
PAL = {"K": "#2b2b3a", "W": "#ffffff", "R": "#e8504a", "P": "#f6a5a5", "B": "#4a7fd8", "L": "#cfe0fb",
       "Y": "#f5c542", "O": "#f08a3c", "G": "#4fb286", "g": "#bfe8d3", "S": "#9aa6b8", "r": "#ffd9d6"}
LEGS_A = ["...K....K...", "..KK....KK.."]
LEGS_B = ["....K..K....", "...KK..KK..."]
CHARS = [
 ("온도", "길잡이 · 시장의 '온도'를 재요", "지금 시장이 뜨거운지 차가운지 숫자로 알려 주는 대표 캐릭터. 글 첫머리·소개 페이지 담당.", [
  ".....KK.....", "....KWWK....", "....KWWKK...", "....KWWK....", "....KRRKK...", "....KRRK....",
  "...KKRRKK...", "..KRRRRRRK..", ".KRKRRRRKRK.", ".KrRRRRRRrK.", ".KRRRKKRRRK.", "..KRRRRRRK..",
  "...KKKKKK..."]),
 ("눈금", "계산 담당 · 숫자는 코드로", "수익률·배당·낙폭을 직접 계산하는 캐릭터. 표·차트 근처, '계산 방법' 설명 담당.", [
  "............", "..KKKKKKKK..", ".KBBBBBBBBK.", ".KBWKBBWKBK.", ".KBBBBBBBBK.", ".KBBBKKBBBK.",
  ".KLLLLLLLLK.", ".KLLLLLLRLK.", ".KLLLLOLRLK.", ".KLYLLOLRLK.", ".KLYLLOLRLK.", ".KLLLLLLLLK.",
  "..KKKKKKKK.."]),
 ("출처", "확인 담당 · 안경 쓰고 근거부터", "숫자의 출처·법령 원문을 확인하는 캐릭터. '출처'·'아직 확인 못 함' 칸, 404 페이지 담당.", [
  "..K......K..", "..KKKKKKKK..", ".KGGGGGGGGK.", ".KWWWKKWWWK.", ".KWKWGGWKWK.", ".KWWWGGWWWK.",
  ".KGGGOOGGGK.", ".KGGggggGGK.", ".KKggggggKK.", ".KKggggggKK.", ".KGggggggGK.", "..KggggggK..",
  "...KKKKKK..."]),
]

def svg(rows, px):
    w = max(len(r) for r in rows)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*px}" height="{len(rows)*px}" shape-rendering="crispEdges">']
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c in PAL:
                out.append(f'<rect x="{x*px}" y="{y*px}" width="{px}" height="{px}" fill="{PAL[c]}"/>')
    return "".join(out) + "</svg>"

cards, walkers = [], []
for i, (name, role, desc, body) in enumerate(CHARS):
    a, b = svg(body + LEGS_A, 10), svg(body + LEGS_B, 10)
    cards.append(f'<div class="card"><div class="big">{a}</div><h2>{name}</h2><p class="role">{role}</p><p>{desc}</p></div>')
    walkers.append(f'<div class="walker" style="animation-delay:-{i*5}s"><div class="fa">{svg(body+LEGS_A,4)}</div><div class="fb">{svg(body+LEGS_B,4)}</div><span>{name}</span></div>')

html = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ondo 캐릭터 시안</title>
<style>
:root{{--bg:#f6f7fb;--ink:#22252e;--sub:#5b6170;--card:#fff;--line:#e3e6ee}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181d;--ink:#eceef3;--sub:#a3a9b6;--card:#20232a;--line:#2f333c}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,sans-serif;line-height:1.6}}
main{{max-width:880px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px;margin:0 0 4px}} .note{{color:var(--sub);font-size:14px;margin:0 0 20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;text-align:center}}
.card h2{{margin:10px 0 0;font-size:20px}} .role{{color:#e8504a;font-weight:600;margin:2px 0 8px;font-size:14px}}
.card p{{font-size:14px;color:var(--sub);margin:0}}
.strip{{position:relative;height:110px;margin-top:28px;border-bottom:2px solid var(--line);overflow:hidden;background:var(--card);border-radius:12px 12px 0 0}}
.walker{{position:absolute;bottom:0;animation:walk 15s linear infinite;text-align:center}}
.walker span{{position:absolute;top:-22px;left:50%;transform:translateX(-50%);font-size:12px;background:#2b2b3a;color:#fff;padding:1px 7px;border-radius:8px;white-space:nowrap}}
.fa,.fb{{animation:step .5s steps(1) infinite}} .fb{{position:absolute;inset:0;animation-delay:-.25s}}
@keyframes step{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes walk{{from{{left:-60px}}to{{left:100%}}}}
@media (prefers-reduced-motion:reduce){{.walker,.fa,.fb{{animation:none}} .walker{{position:static;display:inline-block;margin:30px 16px 0}}}}
</style><main>
<h1>ondo 캐릭터 시안 (1차)</h1>
<p class="note">블로그 이름 '온도'에서 출발한 3명, 각자 맡은 일이 있습니다. 쓰는 곳: 404·소개 페이지·바닥글(글 본문 X), 애드센스 승인 뒤. 나중에 홍보 그림에도 사용.</p>
<div class="grid">{''.join(cards)}</div>
<div class="strip">{''.join(walkers)}</div>
<p class="note" style="margin-top:8px">↑ 바닥글에서 걸어다니는 모습 예시</p>
</main>"""
open("mascot_preview.html", "w", encoding="utf-8").write(html)
print("ok")
