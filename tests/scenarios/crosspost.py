"""글끼리 비교 점검(11-24, L11): 되풀이 문단·정리 첫째 틀·링크 없는 글 언급·시점 말·같은 숫자 다름 + lint 연결."""
import os, sys
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
from ondo.checks import crosspost as cp
from ondo.checks import lint

acc = "<p>해외(미국 등) 상장 ETF는 ISA·연금저축·IRP 계좌로 직접 살 수 없습니다. 이 계좌들의 세제 혜택은 국내 상장 ETF로 받습니다.</p>"
summ = "<h3>정리</h3><p>앞으로 볼 때는 첫째 보수, 둘째 낙폭, 셋째 세금을 봅니다.</p>"
posts = [(1, "", f"<p>A 글 고유 내용 하나 둘 셋.</p>{acc}<p>SCHD의 5년 최대 낙폭은 -18.9%였습니다.</p>{summ}"),
         (2, "", f"<p>B 글 다른 내용.</p>{acc}<p>SCHD 5년 최대 낙폭은 -16.84%입니다.</p><p>세금 비교 가이드에서 자세히 다룹니다.</p>"),
         (3, "", f"<p>C 글.</p>{acc}<p>ISA 개편안이 국회 심의 중입니다.</p><p><a href='x'>세금 비교 가이드</a>에서 자세히 다룹니다.</p>"
                 "<div class='o-cover'>표지</div><p>📌 데이터 출처 Yahoo Finance 이 글은 공개 데이터를 정리한</p>")]
kinds = {}
for k, ids, what in cp.check(posts):
    kinds.setdefault(k, []).append(ids)
assert (1, 2, 3) in kinds["되풀이 문단"], kinds                      # 계좌 문단 3편
assert kinds["정리 첫째·둘째·셋째 틀"] == [(1,)]
assert kinds["링크 없는 글 언급"] == [(2,)]                          # 3번은 링크 있음
assert kinds["시점 타는 말"] == [(3,)]
assert kinds["같은 숫자가 글마다 다름"] == [(1, 2)]
_, issues, _ = lint.fix_and_check("<h1>t</h1>" + "<p>" + "가" * 2600 + "</p>" + summ)
assert any("첫째·둘째·셋째" in i for i in issues), issues
print("crosspost ok")
