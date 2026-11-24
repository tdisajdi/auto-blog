"""기록 크기 한도(2026-11-24): 매 대화 읽는 파일이 커지면 토큰만 쓰고 놓치는 것도 늘어남(11-24 PROJECT_STATUS 542줄·CHANGELOG 42만 자).
넘으면 이 시험이 실패 → 지금 상태만 남기기(PROJECT_STATUS) / python site_pages/archive_logs.py 7 (CHANGELOG·THINKING)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMITS = {                      # 파일: 최대 줄 수
    "CLAUDE.md": 60,
    "lab/DECISIONS.txt": 80,
    "PROJECT_STATUS.txt": 450,
    "CHANGELOG.txt": 2500,      # 넘으면 archive_logs.py
    "lab/THINKING.txt": 2500,
}


def test_doc_sizes():
    over = []
    for f, n in LIMITS.items():
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            k = sum(1 for _ in open(p, encoding="utf-8"))
            if k > n:
                over.append(f"{f} {k}줄 > {n}")
    assert not over, "기록이 너무 김: " + ", ".join(over)
