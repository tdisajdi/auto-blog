"""규칙 장치(.claude/hooks)가 11-25 실제 상황에서 맞게 반응하는지."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, ".claude", "hooks")
sys.path.insert(0, HOOKS)
from thinking_check import needs_debate  # noqa: E402


def _design(prompt):
    r = subprocess.run([sys.executable, os.path.join(HOOKS, "design_rules.py")], input=json.dumps({"prompt": prompt}),
                       capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": ROOT})
    return r.stdout


def test_design_hook_topics():
    out = _design("표 뭔가 좀 에매하고, 이 그래프도 픽셀컨셉에 귀여운 느낌")
    assert "움직이는 Plotly" in out and "[순서" in out
    assert _design("오늘 올라갈 글들은 뭐가있지?") == ""
    assert _design("<task-notification>background done</task-notification>") == ""
    assert "캐릭터" in _design("캐릭터를 글 중간에 넣으면?")


def test_thinking_check():
    long = "저는 이 방법을 추천합니다. " + "독자가 숫자를 더 빨리 읽게 하려는 이유입니다. " * 25
    assert needs_debate(long)
    assert not needs_debate(long + " 반대 측: 무늬가 방해 - 확인 결과 문제 없음")
    assert not needs_debate("반영 확인했습니다. 추천안대로 올렸습니다.")
