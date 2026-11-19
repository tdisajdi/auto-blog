"""2026-11-19: 계좌 문장 권유 꼴 자동 고침 - 'ETF를 선택/활용해야'는 '~하는 방법이 있다'로, 제도 조건('3년 가입해야')은 그대로."""
import sys, os; os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from ondo.checks import lint
out = lint.fix_and_check("<p>절세 혜택은 국내 상장 ETF를 선택해야 하며, 자세한 건 가이드에 있습니다.</p><p>동일 지수의 국내 상장 ETF를 활용해야 합니다.</p>")
html = out[0]
assert "선택하는 방법이 있으며" in html and "활용하는 방법이 있습니다" in html and "해야" not in lint.text_of(html), html
out2 = lint.fix_and_check("<p>ISA는 3년 가입해야 합니다.</p>")
assert "가입해야 합니다" in out2[0], out2[0]
print("lintfix ok")
