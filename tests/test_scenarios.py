"""시험실: 가짜 데이터로 전체 흐름을 돌려보는 시나리오 시험.

tests/scenarios/ 안의 파일 하나가 시나리오 하나다(예: 승인 버튼, 그림 받기, 글 발행).
각 시나리오는 저장소의 코드를 빈 임시 폴더에 복사해 그 안에서 돌린다 - 상태 파일(json)이
저장소를 더럽히지 않고, 시나리오끼리 서로 영향을 주지 않게 하기 위해서다.
진짜 키는 넣지 않는다(가짜 값만). 인터넷이 필요한 부분은 시나리오 안에서 가짜로 바꿔 끼운다.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = sorted((ROOT / "tests" / "scenarios").glob("*.py"))

FAKE_ENV = {
    "PLATFORM": "wordpress", "WP_SITE_URL": "x", "WP_ACCESS_TOKEN": "x", "BLOG_NAME": "x",
    "GEMINI_API_KEY": "a,b,c,d,e", "BLOG_CATEGORY": "etf", "NONINTERACTIVE": "1",
}
# 진짜 키가 환경에 있더라도 시험에서는 절대 쓰지 않는다
BLOCKED = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WP_OAUTH_TOKEN", "WP_SITE_ID", "UNSPLASH_ACCESS_KEY",
           "KOSIS_API_KEY", "EIA_API_KEY", "SERPAPI_KEY", "DOTENV_CONTENTS"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(scenario, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    for f in ROOT.glob("*.py"):
        shutil.copy(f, work / f.name)
    shutil.copytree(ROOT / "ondo", work / "ondo", ignore=shutil.ignore_patterns("__pycache__"))
    env = {k: v for k, v in os.environ.items() if k not in BLOCKED}
    env.update(FAKE_ENV)
    env["MPLCONFIGDIR"] = str(tmp_path / "mpl")
    r = subprocess.run([sys.executable, str(scenario), str(work)], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr)[-3000:]
    assert r.returncode == 0, f"시나리오 {scenario.stem} 실패:\n{out}"
    assert " ok" in r.stdout, f"시나리오 {scenario.stem}이 끝까지 가지 않음:\n{out}"
