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
from site_pages.translate import company_tags_en
assert company_tags_en(["애플", "ETF"]) == ["Apple"] and company_tags_en(["삼성전자"]) == ["Samsung Electronics"] and company_tags_en(None) == []
print("translate ok")

# 11-21 873: '1조 7,357억'은 한 숫자로 대조
from site_pages.translate import _merge_jo_eok as _mj
assert _mj("약 1조 7,357억 달러") == "약 17357억 달러" and _mj("333.6조 원") == "333.6조 원"
print("jo-eok merge ok")
# 11-25 823: 한국어 '3배'와 영어 '3x'는 같은 숫자(대조가 3x를 못 읽어 예약 영어판이 멈춤)
from site_pages import translate as tr
assert not tr.compare("<p>기간별 실제 수익률 vs 3배 단순 계산</p>", "<p>Actual return vs 3x simple calculation</p>"), "3x"
print("3x ok")
