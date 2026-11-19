"""실제 글(lab/translate/<번호>.ko.html)에 새 화면 틀(theme/templates/single.html의 JS + theme/ondo.css)을 입혀 미리 보기 - 사이트 올리기 전 확인용."""
import os, re, sys, json, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from site_pages import theme_push, cover
FONTS, PID, TITLE = sys.argv[1], sys.argv[2], sys.argv[3]
css = theme_push.css_block().replace("<!-- wp:html -->", "").replace("<!-- /wp:html -->", "")
css = re.sub(r'<link rel="stylesheet" href="https://cdn\.jsdelivr[^>]*>', "", css)
fontcss = cover.fonts_css(FONTS).replace("font-family:G11", "font-family:'Galmuri11'").replace("font-family:Pret", "font-family:'Pretendard Variable'")
t = theme_push.fill(open(os.path.join(ROOT, "theme", "templates", "single.html"), encoding="utf-8").read())
toccol = re.search(r'(<aside class="o-toc-col">.*?</aside>)', t, re.S).group(1)
readhead = re.search(r'(<div class="o-readbar".*?</details>)', t, re.S).group(1)
tail = re.search(r'(<div class="o-byline">.*?</script>\s*<script>.*?</script>\s*<script type="text/plain" id="o-post-js">.*?</script>\s*<script>.*?</script>)', t, re.S).group(1)
part = lambda n: theme_push.fill(re.sub(r"<!-- /?wp:html -->", "", open(os.path.join(ROOT, "theme", "parts", n + ".html"), encoding="utf-8").read()))
body = open(os.path.join(ROOT, "lab", "translate", f"{PID}.ko.html"), encoding="utf-8").read()
html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{fontcss}</style>{css}</head>
<body class="single">{part('header')}<div class="o-post-head"><div class="o-wrap"><div class="wp-block-post-terms"><a href="#">ETF·투자</a></div><h1 class="wp-block-post-title">{TITLE}</h1><div class="o-meta"><div class="wp-block-post-date">2026년 11월 19일</div><p>글 · ondo</p></div></div></div>
<main class="o-post">{toccol}<article class="o-read">{readhead}<div class="wp-block-post-content">{body}</div>{tail}</article>
<aside class="o-side"><div class="o-side-in"><div id="ondo-glossary">📖 이 글의 용어사전</div></div></aside></main>{part('footer')}</body></html>"""
out = os.path.join(ROOT, "lab", "mock")
f = os.path.join(out, f"read_v3_{PID}.html"); open(f, "w", encoding="utf-8").write(html)
jobs = [[f, os.path.join(out, f"read_v3_{PID}_desk.png"), 1440, 3600, 0], [f, os.path.join(out, f"read_v3_{PID}_mobile.png"), 390, 3400, 0], [f, os.path.join(out, f"read_v3_{PID}_desk_end.png"), 1440, 1500, 1]]
js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();for(const [f,o,w,h,end] of " + json.dumps(jobs) +
      "){const p=await b.newPage({viewport:{width:w,height:end?900:h}});const errs=[];p.on('pageerror',e=>errs.push(String(e)));await p.goto('file://'+f,{waitUntil:'networkidle'});await p.waitForTimeout(500);"
      "if(end){const y=await p.evaluate(()=>{const c=document.querySelector('.o-check');return c?c.getBoundingClientRect().top+scrollY-500:0});await p.evaluate(y=>scrollTo(0,y),y);await p.waitForTimeout(400);await p.screenshot({path:o});}"
      "else{await p.screenshot({path:o,clip:{x:0,y:0,width:w,height:h}});}"
      "const info=await p.evaluate(()=>({answer:!!document.querySelector('.o-answer'),hl:document.querySelectorAll('mark.o-hl').length,terms:document.querySelectorAll('.o-term').length,check:!!document.querySelector('.o-check'),secn:document.querySelectorAll('.o-secn').length,keyn:!!document.querySelector('.o-keyn'),over:document.documentElement.scrollWidth-document.documentElement.clientWidth}));console.log(o.split('/').pop(),JSON.stringify(info),errs.join('|'));await p.close();}await b.close();})();")
subprocess.run(["node", "-e", js], check=True)
