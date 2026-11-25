"""디자인 규칙 검사가 11-25 실제 실수 3가지를 잡는지, 지금 테마는 통과하는지."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site_pages"))
import design_lint  # noqa: E402


def _probs(*lines):
    return design_lint.lint_lines(list(enumerate(lines, 1)))


def test_catches_past_mistakes():
    assert _probs("var LINE='#e3e8f2';")                                     # 차가운 회색
    assert _probs("tg.className='o-px-tag';tg.textContent='DATA · 눌러서 보기';")  # 한글 도트 글자
    assert _probs("f.parentNode.insertBefore(box,f); f.style.display='none';")  # 그래프 숨김
    assert _probs('<span class="o-px">읽기</span>')


def test_allows_good():
    assert not _probs("'plot_bgcolor':'#fffdf7', 'line':'#e3dccb', color:var(--o-hot)")
    assert not _probs('<div class="o-readtemp" title="이 글을 읽은 만큼"><span class="o-px">READ</span></div>')
    assert not _probs("tg.className='o-px-tag';tg.textContent='DATA';")
    assert not _probs("x{color:#123456} /* 색 허용: 사용자 확인 11-25 */")


def test_current_theme_passes():
    root = design_lint.ROOT
    files = [os.path.join(root, "theme", f) for f in ("ondo.css", "icons.py")] + \
        [os.path.join(root, "theme", "templates", "single.html"), os.path.join(root, "site_pages", "mascot.py")]
    assert not design_lint.run(files)
