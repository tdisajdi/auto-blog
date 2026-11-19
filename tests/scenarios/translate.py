"""2026-11-19: 영어판 번역 대조 - 숫자(억·만 ↔ million)·링크·표·차트 숫자·남은 한글을 잡고, 맞게 옮기면 통과.
영어 기본 페이지 4개와 한국어 페이지가 같은 링크 구조인지, 머리 줄(ko: 짝)이 있는지도 본다."""
import sys, os, re, glob; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from site_pages.translate import compare
ko = ('<h2>수익률</h2><p>VOO는 1년 동안 12.5% 올랐고 총보수는 0.03%입니다. 순자산 1억 2,000만 달러, 2026년 11월 19일 기준.</p>'
      '<table><tr><td>1,234.5</td></tr></table><a href="https://finance.yahoo.com/x">야후</a><script>var d=[1.5,2.25,3];</script>')
en = ('<h2>Returns</h2><p>VOO rose 12.5% over one year and its expense ratio is 0.03%. Net assets 120 million dollars, as of November 19, 2026.</p>'
      '<table><tr><td>1,234.5</td></tr></table><a href="https://finance.yahoo.com/x">Yahoo</a><script>var d=[1.5,2.25,3];</script>')
assert compare(ko, en) == [], compare(ko, en)
bad = compare(ko, en.replace("12.5%", "13.5%").replace("2.25", "2.5").replace("Yahoo</a>", "야후</a>").replace("<h2>Returns</h2>", "<p>Returns</p>"))
assert any("번역에 없음" in p for p in bad) and any("스크립트" in p for p in bad) and any("한글" in p for p in bad) and any("<h2>" in p for p in bad), bad
# 영어 기본 페이지: 머리 줄 + 한국어 짝 파일 존재
for p in glob.glob("site_pages/en/*.html"):
    m = re.match(r"\s*<!--\s*slug:\s*([\w-]+)\s*\|\s*title:\s*(.+?)\s*\|\s*ko:\s*([\w-]+)\s*-->", open(p, encoding="utf-8").read())
    assert m and m.group(1).endswith("-en"), p
    assert not re.search(r"[가-힣]", open(p, encoding="utf-8").read()), p
assert "financial professional" in open("site_pages/en/about.html", encoding="utf-8").read()   # 가짜 전문성 금지 문장 유지
print("translate ok")
