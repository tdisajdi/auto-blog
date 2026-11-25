"""디자인 규칙 검사(2026-11-25, 사용자 '규칙을 계속 까먹는데 답이 없나?').
글로 적은 규칙은 재발하고(L2 3번·L21), 코드로 막은 규칙은 재발 0 → 기계가 볼 수 있는 디자인 규칙은 여기서 막는다.

  python site_pages/design_lint.py                 마지막 테마 확인(lab/theme_ok.json) 뒤 theme/에 더한 줄 검사
  python site_pages/design_lint.py 시안.css 시안.js  시안 파일 통째로 검사(사용자에게 보이기 전에)
theme_push.py approve 가 먼저 돌리고, 걸리면 확인 기록을 남기지 않는다.
새 색이 꼭 필요하면 그 줄에 /* 색 허용: 이유 */ 를 적는다(사용자 확인 받은 것만).

막는 것(전부 실제로 어긴 일에서 나옴):
 1 색: theme/ondo.css :root 색(대표색·잉크·종이) 밖의 새 색 - 11-25 시안에 차가운 회색 #e3e8f2·#fbfcfe·#8a96b0
 2 도트 글자는 영어만: o-px 계열 요소에 한글 - 11-25 'DATA · 눌러서 보기'
 3 움직이는 그래프 유지: 그래프(ondo-chart·js-plotly-plot)를 숨기거나 지우거나 갈아끼움 - 11-25 정지 도트 막대 시안
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
NEUTRAL = {"#fff", "#ffffff", "#000", "#000000"}


def _ok_base():
    return subprocess.run(["git", "log", "-1", "--format=%H", "--", "lab/theme_ok.json"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip() or "HEAD"


def palette():
    """허용 색 = :root 색 + 마지막 확인 때 테마에 이미 있던 색(아이콘 음영 등 사용자 확인을 거친 것)."""
    css = open(os.path.join(ROOT, "theme", "ondo.css"), encoding="utf-8").read()
    root = css[css.index(":root"):css.index("}", css.index(":root"))]
    r = subprocess.run(["git", "grep", "-hoiE", "#[0-9a-f]{6}\\b|#[0-9a-f]{3}\\b", _ok_base(), "--", "theme/", "site_pages/mascot.py"], cwd=ROOT,
                       capture_output=True, text=True)
    old = r.stdout
    if r.returncode or not old:       # 얕은 복제(CI)라 옛 커밋이 없으면 지금 파일 기준
        old = subprocess.run(["git", "grep", "-hoiE", "#[0-9a-f]{6}\\b|#[0-9a-f]{3}\\b", "--", "theme/", "site_pages/mascot.py"],
                             cwd=ROOT, capture_output=True, text=True).stdout
    return {c.lower() for c in HEX.findall(root)} | {c.split(":")[-1].lower() for c in old.split()} | NEUTRAL


def lint_lines(lines, where=""):
    pal, out = palette(), []
    for n, l in lines:
        if ":root" in l or "--o-" in l and re.search(r"--o-[\w-]+\s*:", l):
            continue
        bad = sorted({c.lower() for c in HEX.findall(l)} - pal) if "색 허용:" not in l else []
        if bad:
            out.append(f"{where}{n}: 사이트 색이 아님 {', '.join(bad)} → var(--o-…) 또는 :root 색을 쓸 것")
        pxtext = re.findall(r"class=[\"'][^\"']*\bo-px[\w-]*[^\"']*[\"'][^>]*>([^<]*)", l) + \
            re.findall(r"o-px[\w-]*['\"];?[^;]{0,40};\s*\w+\.(?:textContent|innerText)\s*=\s*['\"]([^'\"]*)", l)
        if any(re.search(r"[가-힣]", t) for t in pxtext):
            out.append(f"{where}{n}: 도트(o-px) 글자에 한글 → 도트 글자는 영어만(DESIGN_NOTES 브랜드 층)")
        if re.search(r"(ondo-chart|js-plotly-plot|\bf\b)[^\n]{0,80}(display\s*[:=]\s*['\"]?none|\.remove\(\)|replaceWith|replaceChild)", l) \
                or re.search(r"(ondo-chart|js-plotly-plot)[^{]*\{[^}]*display\s*:\s*none", l):
            out.append(f"{where}{n}: 움직이는 그래프를 숨기거나 바꿈 → 그래프는 그대로, 모양만(DESIGN_NOTES 데이터 층)")
    return out


def added_since_ok():
    base = _ok_base()
    diff = subprocess.run(["git", "diff", "-U0", base, "--", "theme/", "site_pages/mascot.py"], cwd=ROOT, capture_output=True, text=True).stdout
    out, fn, n = [], "", 0
    for l in diff.split("\n"):
        if l.startswith("+++ "):
            fn = l[6:]
        elif l.startswith("@@"):
            n = int(re.search(r"\+(\d+)", l).group(1))
        elif l.startswith("+"):
            out.append((f"{fn}:{n}", l[1:]))
            n += 1
    return out


def run(files=None):
    probs = []
    if files:
        for f in files:
            probs += lint_lines([(i + 1, l) for i, l in enumerate(open(f, encoding="utf-8").read().split("\n"))], f + ":")
    else:
        probs = lint_lines(added_since_ok())
    for p in probs:
        print("❌", p)
    print(f"디자인 검사: 문제 {len(probs)}개")
    return probs


if __name__ == "__main__":
    sys.exit(1 if run(sys.argv[1:]) else 0)
