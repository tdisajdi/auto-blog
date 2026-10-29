"""테크 카테고리 자동 발행 진입점.

실제 로직은 전부 news_engine.py(발굴~발행~홍보)와 blog_engine.py(발행/검수/
API 공용 엔진)에 있다. 이 파일은 테크 카테고리 고유 설정값만 채워서
run_news_pipeline()을 호출하는 얇은 래퍼다.

GitHub Actions 스케줄(publish_news.yml)이 매주 월요일에만 이 스크립트를
실행하므로, 예전 tech.py처럼 스크립트 내부에서 요일을 확인할 필요가 없다.
"""

import os

# [중요] blog_engine.py는 모듈 import 시점에 BLOG_CATEGORY 환경변수를 읽어
# 상태 파일 이름(tech_article_state.json 등)을 정한다. GitHub Actions 워크플로우가
# 이미 이 값을 설정해주지만, 로컬에서 직접 실행할 때(또는 이 값을 안 넣고 실행해도)
# 같은 이름을 쓰도록 여기서도 기본값을 정해둔다(이미 설정돼 있으면 안 건드림).
os.environ.setdefault("BLOG_CATEGORY", "tech")

from news_engine import run_news_pipeline

RSS_URLS = [
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
]

FALLBACK_IMAGE_KEYWORDS = ("technology innovation", "software logic")


def main():
    run_news_pipeline(
        category_code="tech",
        category_label="테크",
        rss_urls=RSS_URLS,
        fallback_image_keywords=FALLBACK_IMAGE_KEYWORDS,
    )


if __name__ == "__main__":
    main()
