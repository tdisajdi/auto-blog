"""2026-11-19: 계좌 문장 권유 꼴 자동 고침 - 'ETF를 선택/활용해야'는 '~하는 방법이 있다'로, 제도 조건('3년 가입해야')은 그대로."""
import sys, os; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from ondo.checks import lint
out = lint.fix_and_check("<p>절세 혜택은 국내 상장 ETF를 선택해야 하며, 자세한 건 가이드에 있습니다.</p><p>동일 지수의 국내 상장 ETF를 활용해야 합니다.</p>")
html = out[0]
assert "선택하는 방법이 있으며" in html and "활용하는 방법이 있습니다" in html and "해야" not in lint.text_of(html), html
out2 = lint.fix_and_check("<p>ISA는 3년 가입해야 합니다.</p>")
assert "가입해야 합니다" in out2[0], out2[0]
print("lintfix ok")

# 11-20 강조 규칙: 굵게는 본문 섹션당 1개, 숫자 든 사실 문장만(도입·FAQ·정리·금지 표현·숫자 없는 것은 풂)
h = ('<p><strong>도입 12%</strong> 시작</p><h3>보수 차이</h3><p>설명. <strong>10년 뒤 16만 원 차이가 납니다.</strong> 또 <strong>20년 53만 원</strong></p>'
     '<p><strong>숫자 없음</strong></p><h3>계좌</h3><p><strong>반드시 선택하세요 3개</strong></p><h3>자주 묻는 질문</h3><p><strong>FAQ 5%</strong></p>'
     '<h3>정리</h3><p><strong>한 줄 정리:</strong> 끝 1개</p>')
f = []
out = lint._keep_section_answers(h, f)
assert out.count("<strong>") == 2 and "<strong>10년 뒤 16만 원 차이가 납니다.</strong>" in out and "<strong>한 줄 정리:</strong>" in out, out
assert f and "5곳" in f[0], f
print("strong rule ok")

# 11-22 백로그 105: 앞 숫자만 다시 늘어놓는 문장(같은 섹션·앞 섹션), 도입·새 숫자 있는 비교는 안 잡음
from ondo.checks import lint as _L
_h = ("<p>현대차 매출은 186.3조 원, 최대 낙폭 -65.8%입니다.</p>"
      "<h3>매출</h3><p>매출은 142.2조 원에서 186.3조 원으로 늘었습니다. 증가율은 142.2조 원 대비 31.0%입니다. "
      "매출은 142.2조 원과 186.3조 원이었습니다.</p>"
      "<h3>낙폭</h3><p>최대 낙폭은 -65.8%이고 회복에 172일이 걸렸습니다. 매출 142.2조 원과 186.3조 원을 다시 봅니다.</p>")
_r = _L.repeat_sentences(_h)
assert [(w, s[:9]) for _, w, s in _r] == [("같은 섹션", "매출은 142.2"), ("앞 섹션", "매출 142.2조")], _r
print("repeat sentences ok")
