"""주간 점검 강화(2026-11-02): 일요일 상태 점검 리포트에 붙는 항목.

- Gemini 키마다 1번씩 아주 짧게 불러서 살아 있는지(이름표로 알려줌 - 텔레그램은 개인 채팅이라 괜찮음)
- 워드프레스 토큰이 그림 올리기·카테고리 읽기를 할 수 있는지(지금 토큰은 글 권한만 있어서 막혀 있음)
- 자료원(EIA 원유 재고, KOSIS 통계)이 응답하는지
- 사이트 화면 캡처(넓은 화면·휴대폰): 사람이 한눈에 깨진 데가 없는지 볼 수 있게 텔레그램으로 보냄
점검은 읽기만 하고 아무것도 바꾸지 않는다. 하나가 실패해도 나머지는 계속한다.
"""
import os

import requests

from ondo import keys

PING_MODEL = "gemini-3.5-flash-lite"


def check_keys():
    from ondo.writing import llm
    ok, bad = 0, []
    for no, label, key in keys.gemini_keys():
        payload = {"contents": [{"parts": [{"text": "1"}]}], "generationConfig": {"maxOutputTokens": 4}}
        try:
            r = llm._post(llm.API.format(model=PING_MODEL), payload, key)
            code = r.status_code
            text = r.text
        except Exception as e:
            code, text = 0, type(e).__name__
        if code == 200:
            ok += 1
        elif code == 429:
            ok += 1            # 한도는 시간이 지나면 풀린다 - 키 자체는 살아 있음
        else:
            kind = keys.classify_error(code, text) or f"HTTP {code}"
            bad.append(f"{keys.name_of(key)}: {keys.ADVICE.get(kind, kind)}")
    lines = [f"🔑 Gemini 키: {ok}개 정상" + (f", {len(bad)}개 문제" if bad else "")]
    lines += [f"  - {b}" for b in bad]
    return lines


def check_wordpress():
    token, site = os.environ.get("WP_OAUTH_TOKEN"), os.environ.get("WP_SITE_ID")
    if not (token and site):
        return ["📝 워드프레스: 토큰 없음"]
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{site}"
    h = {"Authorization": f"Bearer {token}"}
    out = []
    for label, url in [("글 목록", f"{base}/posts/?number=1&status=draft"), ("그림(미디어)", f"{base}/media/?number=1"),
                       ("카테고리", f"{base}/categories/slug:etf")]:
        try:
            code = requests.get(url, headers=h, timeout=20).status_code
        except Exception as e:
            code = type(e).__name__
        out.append(f"{label} {'✅' if code == 200 else '❌ ' + str(code)}")
    line = "📝 워드프레스 토큰: " + " / ".join(out)
    if "❌" in line:
        line += "\n  - 그림·카테고리가 ❌면 토큰 권한이 글(posts)뿐인 것: get_wp_oauth_token.py로 다시 받기(그냥 Enter)"
    return [line]


def check_sources():
    out = []
    try:
        from topic_engine import KOSIS_TABLES, _eia_weekly, _kosis_key, kosis_data
        out.append("EIA 원유 " + ("✅" if _eia_weekly("oil") else "❌") + " / EIA 가스 " + ("✅" if _eia_weekly("gas") else "❌"))
        if _kosis_key():
            rows, err = kosis_data(**{k: KOSIS_TABLES[0][k] for k in ("org", "tbl", "prd", "n")})
            out.append("KOSIS " + ("✅" if rows else f"❌ {str(err)[:60]}"))
        else:
            out.append("KOSIS 키 없음")
    except Exception as e:
        out.append(f"점검 실패 {type(e).__name__}")
    return ["📊 자료원: " + " / ".join(out)]


def site_screenshots(send_photo, latest_url=None):
    """사이트 첫 화면(넓은 화면)과 최근 글(휴대폰) 캡처를 텔레그램으로. Playwright가 없으면 건너뜀."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["🖼️ 사이트 화면: 캡처 도구 없음(건너뜀)"]
    site = os.environ.get("WP_SITE_URL", "https://ondo99.com").rstrip("/")
    shots = [("첫 화면 (넓은 화면)", site, {"width": 1440, "height": 1100}, "home.png")]
    if latest_url:
        shots.append(("최근 공개 글 (휴대폰)", latest_url, {"width": 390, "height": 1600}, "post.png"))
    out = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for label, url, size, path in shots:
                page = b.new_page(viewport=size)
                try:
                    resp = page.goto(url, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(2500)          # 그래프가 그려질 시간
                    page.screenshot(path=path)
                    send_photo(path=path, caption=f"🖼️ 주간 화면 점검 - {label}\n{url}")
                    out.append(f"{label} ✅ ({resp.status if resp else '?'})")
                except Exception as e:
                    out.append(f"{label} ❌ {type(e).__name__}")
                finally:
                    page.close()
                    if os.path.exists(path):
                        os.remove(path)
            b.close()
    except Exception as e:
        out.append(f"캡처 실패 {type(e).__name__}")
    return ["🖼️ 사이트 화면: " + " / ".join(out)]


def run_all(send_photo=None, latest_url=None):
    lines = ["", "🩺 주간 점검"]
    for fn in (check_keys, check_wordpress, check_sources):
        try:
            lines += fn()
        except Exception as e:
            lines.append(f"{fn.__name__} 실패: {type(e).__name__}")
    if send_photo:
        lines += site_screenshots(send_photo, latest_url)
    return lines
