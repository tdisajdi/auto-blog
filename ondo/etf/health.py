"""주간 상태 점검 리포트(텔레그램).
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.approval import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
# ============================================================
# [신규] 상태 점검 부서 (무료 - 주간 리포트를 텔레그램으로 전송)
# ============================================================

# ============================================================
# [신규] 3번 부서: 기획
# ============================================================





# ============================================================
# [신규] SEO/제목 최적화 부서
# ============================================================



def send_weekly_health_report():
    """
    [상태 점검 부서] 최근 7일간의 발행 현황을 집계해서 텔레그램으로 요약
    보고한다. API 호출 없이 article_state.json의 notes 필드(어떤 경로로
    발행됐는지 기록된 문자열)만 파싱하므로 완전 무료.
    """
    state = _load_state()
    now = datetime.now()
    week_ago = now - pd.Timedelta(days=7)

    recent = []
    for a in state.get('articles', []):
        ts = a.get('timestamp', '')
        if not ts:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        if ts_dt >= week_ago:
            recent.append(a)

    drafts_n = sum(1 for a in recent if a.get('status') == 'draft')
    recent = [a for a in recent if a.get('status') != 'draft']   # 임시글은 '발행'으로 세지 않는다(2026-11-02)
    total = len(recent)
    fallback_count = sum(1 for a in recent if 'selenium' in a.get('notes', '') or 'manual paste' in a.get('notes', ''))
    low_quality_count = sum(1 for a in recent if 'low quality override' in a.get('notes', ''))

    lines = [f"📊 이번 주 발행 현황 ({week_ago.date()} ~ {now.date()})", ""]
    lines.append(f"공개 발행: {total}편 / 임시글: {drafts_n}편")
    if total > 0:
        lines.append(f"API 완전자동 발행: {total - fallback_count}편")
        lines.append(f"반자동(Selenium/수동 붙여넣기) 폴백: {fallback_count}편")
        if low_quality_count:
            lines.append(f"⚠️ 품질 낮음에도 강제 발행된 글: {low_quality_count}편 - 한 번 확인해보시는 걸 추천해요")
    elif not drafts_n:
        lines.append("이번 주 쓴 글이 없습니다 - 워크플로우가 정상 실행되고 있는지 확인해보세요.")

    # [신규] 예산/한도 감시 부서 - 이번 주 API 호출 통계 집계
    usage_log = _load_json_file(API_USAGE_LOG_FILE, [])
    weekly_usage = [u for u in usage_log if u.get("timestamp") and datetime.fromisoformat(u["timestamp"]) >= week_ago]
    if weekly_usage:
        total_calls = sum(u.get("total_calls", 0) for u in weekly_usage)
        by_model_agg = {}
        switch_agg = {}
        for u in weekly_usage:
            for model, count in u.get("by_model", {}).items():
                by_model_agg[model] = by_model_agg.get(model, 0) + count
            for model, count in u.get("model_switch_events", {}).items():
                switch_agg[model] = switch_agg.get(model, 0) + count

        lines.append("")
        lines.append(f"🔧 이번 주 Gemini 호출: 총 {total_calls}회")
        for model, count in sorted(by_model_agg.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {model}: {count}회")
        if switch_agg:
            most_exhausted = max(switch_agg.items(), key=lambda x: x[1])
            lines.append(f"⚠️ 가장 자주 소진되어 전환된 모델: {most_exhausted[0]} ({most_exhausted[1]}회) - 우선순위를 낮추는 걸 고려해보세요")

    # 편집 기록부(logs/) 주간 요약: 쓰기 방식, 점수 변화, 막힌 모델, 거부된 키 번호, 자주 나온 지적
    try:
        from ondo.checks.editlog import weekly_summary
        lines += weekly_summary()
    except Exception as e:
        lines.append(f"(편집 기록 요약 실패: {type(e).__name__})")

    # 주간 점검(키·워드프레스 토큰·자료원·사이트 화면 캡처) - ondo/checks/weekly.py
    try:
        from ondo.checks import weekly
        from blog_engine import _telegram_send_photo
        from blog_engine import get_wordpress_recent_posts
        posts = get_wordpress_recent_posts() or []
        lines += weekly.run_all(send_photo=_telegram_send_photo, latest_url=posts[0].get("link") if posts else None)
    except Exception as e:
        lines.append(f"(주간 점검 실패: {type(e).__name__})")

    message = "\n".join(lines)
    _telegram_send_message(message)
    print("✅ 주간 상태 점검 리포트 전송 완료")
    print(message)

__all__ = [k for k in dir() if not k.startswith('__')]
