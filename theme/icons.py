"""글 소제목 도트 장식(2026-11-12 사용자 선택: '말랑 아이콘 + 분야색 줄').

- 소제목(h3) 위에 그 글 분야색 도트 줄 + 왼쪽 끝에 주제 아이콘 하나.
- 색은 분야만 뜻함(ETF 파랑·에너지 주황·인구사회 청록). 온도색은 실제 온도(온도판·읽기 온도계)에만.
- 아이콘은 소제목 글자를 보고 고름(JS) - 글 본문은 안 바꾸므로 작가·검토·교열과 무관, 옛 초안에도 그대로 붙음.
- 그림은 12x12 도트를 코드가 그림: 검정 테두리 대신 같은 색 계열 진한 테두리 + 빛·그림자 칸(DESIGN.md 도트 원칙).
theme_push.css_block()이 css_rules()를, fill()이 {{ICON_JS}}를 넣는다.
"""
import urllib.parse

SIL = {  # '#'=모양, 'x'=무늬
    "coin": ["....####....", "..########..", ".##########.", ".###xxxx###.", "####x##x####", "####x##x####", "####x##x####", "####x##x####", ".###xxxx###.", ".##########.", "..########..", "....####...."],
    "tax": ["..########..", "..########..", "..#xxxxx##..", "..########..", "..#xxxx###..", "..########..", "..#xxxxx##..", "..########..", "..#xxx####..", "..########..", "..########..", "..##.##.##.."],
    "fx": ["............", "............", "############", "#xx######xx#", "#x###xx###x#", "####x##x####", "####x##x####", "#x###xx###x#", "#xx######xx#", "############", "............", "............"],
    "risk": ["............", ".....##.....", "....####....", "....#xx#....", "...##xx##...", "...##xx##...", "..###xx###..", "..###xx###..", ".##########.", ".####xx####.", "############", "############"],
    "faq": [".##########.", "############", "####xxx#####", "###x###x####", "#######x####", "######x#####", "#####x######", "############", "#####x######", ".##########.", "..###.......", "..##........"],
    "flag": [".##.........", ".########...", ".#########..", ".##########.", ".#########..", ".########...", ".##.........", ".##.........", ".##.........", ".##.........", ".##.........", "####........"],
    "chart": ["............", "........###.", "........###.", "....###.###.", "....###.###.", "....###.###.", "###.###.###.", "###.###.###.", "###.###.###.", "###.###.###.", "###.###.###.", "............"],
    "info": ["....####....", "...######...", "..########..", "..##xx####..", "..#x######..", "..########..", "...######...", "....####....", "....xxxx....", "....####....", "....xxxx....", ".....##....."],
}
PAL = {  # 테두리, 그림자, 바탕, 빛, 무늬
    "coin": ("#9a5a12", "#e0a020", "#f4c44e", "#fff0b0", "#b06a10"),
    "tax": ("#4a5d80", "#d6dde9", "#ffffff", "#ffffff", "#8fa0bf"),
    "fx": ("#1d6b52", "#4fb98a", "#7fd6a8", "#c9f2dc", "#1d6b52"),
    "risk": ("#9a3a12", "#e26a22", "#ff9d4d", "#ffd2a0", "#5a1d08"),
    "faq": ("#157a85", "#2bb3c0", "#63d2dc", "#c6f1f4", "#ffffff"),
    "flag": ("#8a2a1e", "#d63a28", "#ff5a44", "#ffb0a3", "#8a2a1e"),
    "chart": ("#2a3fa8", "#2f5ae0", "#5b85ff", "#b9cbff", "#2a3fa8"),
    "info": ("#9a6b00", "#f0b400", "#ffd65a", "#fff3c0", "#9a6b00"),
}
# 소제목 글자 → 아이콘(위에서부터 먼저 맞는 것). '흐름' 같은 넓은 말(chart)은 뒤로. 못 맞추면 info(전구).
RULES = [
    ("faq", "자주 묻는|질문"),
    ("flag", "정리|요약|결론|체크"),
    ("coin", "배당|분배|이자|현금"),
    ("tax", "세금|계좌|비용|보수|세제"),
    ("fx", "환율|달러|원화|환헤지|환노출"),
    ("risk", "낙폭|위험|하락|손실|MDD|회복"),
    ("chart", "수익|성과|흐름|추이|비교|가격|지표|통계"),
]


def soft_icon(k):
    rows, (o, sh, f, h, d) = SIL[k], PAL[k]
    inside = lambda x, y: 0 <= y < 12 and 0 <= x < 12 and rows[y][x] in "#x"
    px = []
    for y in range(12):
        for x in range(12):
            ch = rows[y][x]
            if ch not in "#x":
                continue
            if not all(inside(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                col = o
            elif ch == "x":
                col = d
            elif not inside(x, y - 2) and not inside(x - 2, y):
                col = h
            elif not inside(x, y - 2) or not inside(x - 2, y) or (y > 0 and rows[y - 1][x] == "x"):
                col = f
            elif not inside(x, y + 2) or not inside(x + 2, y):
                col = sh
            else:
                col = f
            px.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{col}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" shape-rendering="crispEdges">{"".join(px)}</svg>'


def uri(svg):
    return "data:image/svg+xml," + urllib.parse.quote(svg)


def css_rules():
    sel = ".o-read .wp-block-post-content h3"
    out = [
        "/* ── 11-12 글 소제목 장식: 분야색 도트 줄 + 말랑 아이콘(theme/icons.py가 만듦) ── */",
        ":root { --h3-line: var(--t-etf, #3d6dff); }",
        'body:has(.o-post-head a[href*="/category/energy/"]) { --h3-line: var(--t-energy, #ff8a3d); }',
        'body:has(.o-post-head a[href*="/category/society/"]) { --h3-line: var(--t-society, #2bb3c0); }',
        f"{sel} {{ position: relative; margin-top: 3.2em !important; padding-top: 44px !important; border-left: 0 !important; padding-left: 0 !important;"
        " background: repeating-linear-gradient(90deg, var(--h3-line) 0 6px, transparent 6px 10px) 44px 14px / calc(100% - 44px) 4px no-repeat; }",
        f'{sel}::after {{ content: ""; position: absolute; left: 0; top: 0; width: 32px; height: 32px; background: no-repeat center / 32px 32px; image-rendering: pixelated; }}',
        # 글마다 들어 있는 회색 구분선(소제목 앞 div)은 이제 소제목 줄이 대신함 → 숨김
        '.o-read .wp-block-post-content > div[style*="height:1px"] { display: none !important; }',
    ]
    out += [f'{sel}[data-ic="{k}"]::after {{ background-image: url("{uri(soft_icon(k))}"); }}' for k in SIL]
    return "\n".join(out)


def js():
    """소제목에 data-ic를 붙이는 한 줄(o-toc-js 안에서 실행 - '&'·'<' 쓰지 않음)."""
    rules = ",".join(f"['{k}',/{pat}/]" for k, pat in RULES)
    return ("(function(){var R=[" + rules + "];document.querySelectorAll('.o-read .wp-block-post-content h3').forEach(function(h){"
            "var t=h.textContent;for(var i=0;i<R.length;i++){if(R[i][1].test(t)){h.setAttribute('data-ic',R[i][0]);return;}}"
            "h.setAttribute('data-ic','info');});})();")


def pick(text):
    """파이썬 쪽 같은 규칙(시험용)."""
    import re
    for k, pat in RULES:
        if re.search(pat, text):
            return k
    return "info"
