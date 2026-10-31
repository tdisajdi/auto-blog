"""설정 - 여러 부서가 같이 쓰는 값은 여기 한 곳에서만 정한다.

사이트 디자인(대표색 등)을 바꿀 때는 이 파일의 색과 design/ 폴더를 같이 바꾼다
(자세한 목록은 design/DESIGN_NOTES.txt).
"""
from datetime import datetime, timedelta, timezone

# ── 사이트 ──
SITE_NAME = "DATA-DRIVEN INSIGHTS"
SITE_HOST = "ondo99.com"
AUTHOR = "ondo"   # 가짜 자격·전문성을 붙이지 않는다

# ── 사이트 색 (design/hub.html, post-dark-theme.css와 같은 값) ──
NAVY = "#0e1a30"
NAVY_DEEP = "#0b1428"
NAVY_LIGHT = "#16244a"
GOLD = "#e8b944"
TEXT = "#e8ecf4"
MUTED = "#8a96b0"

# ── 분야 ── 코드 이름 → 워드프레스 카테고리 주소(slug) / 영문 표시 이름
CATEGORY_SLUGS = {
    "etf": "etf", "trend": "trend", "tech": "patents", "patent": "patents",
    "bio": "biotech", "energy": "energy", "society": "society",
}
CATEGORY_EN = {"etf": "ETF", "trend": "TREND", "tech": "TECH & PATENTS", "bio": "BIOTECH",
               "energy": "ENERGY & CLIMATE", "society": "POPULATION & SOCIETY"}

# ── 시간 ── 블로그 기준은 한국 시간
KST = timezone(timedelta(hours=9))


def kst_now():
    """지금 한국 시간 (시간대 정보 없는 datetime - 저장 파일에 쓰기 편하게)."""
    return datetime.now(KST).replace(tzinfo=None)
