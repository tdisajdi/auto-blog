"""기준을 통과했는데 임시글로 남은 글을 공개로(2026-11-19 - 다시 쓰기 경로가 상태를 안 바꾸던 문제의 뒷정리).
  python site_pages/publish_passed.py <글번호>
안전장치: logs/ 안에 그 글(?p=번호)의 기록이 있고 마지막 '편집장 검토'가 통과(passed)이며,
그 판의 사실 검증(본·확인)을 좋은 모델이 했을 때만 공개한다(11-19).
두 번째 길(11-20 '임시글 → Claude 읽기·고치기 → 좋은 모델 사실 검증 통과만 공개'):
  자동 검토가 사소한 지적만 남기고 끝났고(치명·중요 없음), Claude 고침(lab/patches/<번호>.json)이 지금 글에 들어가 있고,
  그 고친 글을 좋은 모델이 다시 사실 검증해(lab/recheck/<번호>.json, patch_applied=true) 치명·중요가 0개일 때."""
import glob
import re
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def passed_log(pid, slug=None):
    """그 글의 기록 중 가장 늦게 시작한 것(started_at) - 깃허브에선 파일 시각이 모두 같아 시각 정렬은 못 씀."""
    best = None
    for f in glob.glob(os.path.join(ROOT, "logs", "*", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        res = d.get("result") or {}
        if not isinstance(res, dict):
            continue
        url = str(res.get("url", ""))
        if (f"?p={pid}" not in url and str(pid) != str(res.get("post_id", ""))
                and not (slug and url.rstrip("/").endswith("/" + slug))):   # 공개 글은 주소가 slug로 남음(11-19)
            continue
        if best is None or str(d.get("started_at", "")) > str(best[1].get("started_at", "")):
            best = (f, d)
    if not best:
        return None, False, None
    reviews = [s for s in best[1].get("steps", []) if str(s.get("step", "")).startswith("편집장 검토")]
    ok = bool(reviews and reviews[-1].get("passed"))
    if ok and not strong_fact(best[1], reviews[-1]["step"].split()[-1]):
        print("주의: 통과 기록이지만 사실 검증(본·확인)을 좋은 모델이 하지 않음 - 통과로 치지 않음(11-19 규칙)")
        ok = False
    return best[0], ok, reviews[-1].get("score") if reviews else None


def strong_fact(d, round_no):
    """그 판의 본 검토(N)와 확인 검토(N+10) 사실 검증이 모두 좋은 모델로 끝났나(11-19: 가벼운 모델 통과 막기)."""
    from ondo.writing import llm
    strong = set(llm.models_for("strong_only"))
    calls = [c for c in d.get("calls") or [] if isinstance(c, dict) and c.get("status") == "ok"]
    for r in (str(round_no), str(int(round_no) + 10)):
        done = [c for c in calls if str(c.get("step", "")).startswith(f"검토 {r}(사실 검증)")]
        if not done or done[-1].get("model") not in strong:
            return False
    return True


SERIOUS = ("[치명", "[중요")


def _norm(t):
    import re
    return re.sub(r"\s+", " ", t or "").strip()


def _frag(s):
    """고침 조각의 태그 뺀 글자 - 조각이 태그 중간에서 시작·끝나도('>SPY …</td' 꼴) 남은 꺾쇠 조각을 버림(11-20 768)."""
    s = re.sub(r"^[^<]*?>", "", s or "", count=1) if re.match(r"^[^<]*>", s or "") else (s or "")
    s = re.sub(r"<[^>]*$", "", s)
    return _norm(plain(s))


def patches_in(pid, text):
    """lab/patches/<번호>.json 의 고침이 모두 글에 들어가 있나(새 문구는 있고 옛 문구는 없음). 고침 파일 없으면 None."""
    pf = os.path.join(ROOT, "lab", "patches", f"{pid}.json")
    if not os.path.exists(pf):
        return None
    try:
        items = json.load(open(pf, encoding="utf-8"))
    except Exception:
        return False
    t = _norm(text)
    items = [i for i in items if i.get("field", "content") == "content"]   # 요약문(excerpt) 고침은 본문에 없음
    # 고침 문구도 태그 뺀 글자로 비교(11-20: 'S&amp;P'·'</td>'가 든 고침이 본문 글자와 안 맞던 문제)
    # 11-21: 옛 문구가 새 문구 안에 그대로 들어 있는 고침(앞에 말 덧붙이기, 857 FAQ)은 '옛 문구 없음'을 볼 수 없음 → 새 문구만 확인
    def ok(i):
        n, o = _frag(i.get("new")), _frag(i.get("old")) if i.get("old") else ""
        return n in t and (not o or o in n or o not in t)
    # 11-22: 나중 고침이 앞 고침의 새 문구를 통째로 덮어쓴 경우(정리 섹션을 새로 쓰며 그 안의 옛 고침 문장이 사라짐, 776·809)
    # 앞 고침은 '나중 고침의 옛 문구 안에 들어 있고, 그 나중 고침이 반영됨'이면 반영된 것으로 본다.
    def superseded(k):     # 11-24: 나중 고침이 앞 고침의 새 문구 '일부'만 바꾼 경우도(patch_post와 같게, 823). 덮어쓰기가 여러 번 겹쳐도(앞 고침 → 첫 정리 → 최종 정리) 끝까지 따라감
        n = _frag(items[k].get("new"))
        return bool(n) and any((n in _frag(items[j].get("old")) or (len(_frag(items[j].get("old"))) >= 8 and _frag(items[j].get("old")) in n))
                               and (ok(items[j]) or superseded(j))
                               for j in range(k + 1, len(items)))
    return bool(items) and all(ok(i) or superseded(k) for k, i in enumerate(items))


def claude_route(pid, logf, d, text):
    """두 번째 길 판정 → (통과?, 이유). d=그 글의 기록, text=지금 사이트 본문(태그 뺀 글자)."""
    from ondo.writing import llm
    reviews = [s for s in d.get("steps", []) if str(s.get("step", "")).startswith("편집장 검토")]
    if not reviews:
        return False, "편집장 검토 기록 없음"
    if any(str(i).startswith(SERIOUS) for i in reviews[-1].get("issues") or []):
        return False, "마지막 자동 검토에 치명·중요 지적이 남음"
    if not patches_in(pid, text):
        return False, "Claude 고침(lab/patches)이 없거나 글에 다 들어가지 않음"
    rf = os.path.join(ROOT, "lab", "recheck", f"{pid}.json")
    if not os.path.exists(rf):
        return False, "고친 뒤 좋은 모델 사실 검증(lab/recheck) 없음"
    rc = json.load(open(rf, encoding="utf-8"))
    if rc.get("model") not in set(llm.models_for("strong_only")):
        return False, f"다시 검증 모델이 좋은 모델이 아님({rc.get('model')})"
    if rc.get("log") != os.path.basename(logf):
        return False, "다시 검증이 다른 기록 기준"
    if not rc.get("patch_applied"):
        return False, "다시 검증이 고침 전 글을 본 것일 수 있음(patch_applied 없음) - fact-recheck 다시"
    if any(i.get("severity") in ("치명", "중요") for i in rc.get("issues") or []):
        return False, "다시 검증에서 치명·중요 지적"
    return True, "Claude 고침 + 좋은 모델 다시 검증 통과"


def plain(html_text):
    """태그 뺀 글자(고침 문구 대조용)."""
    import html as _h
    import re
    return _h.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", html_text or "", flags=re.S)))


def site_text(pid, h):
    import requests
    import blog_engine as be
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}", headers=h,
                     params={"context": "edit", "fields": "content"}, timeout=30)
    return plain(r.json().get("content", "")) if r.ok else ""


def first_in_category(pid, h):
    """11-20(백로그 76) → 11-24: 이 글로 그 분야가 글 3편(theme_push.MIN_POSTS)이 되면 theme-push - 빈 분야라 숨겼던 메뉴·첫 화면 카드를 다시 보이게."""
    try:
        import requests
        import blog_engine as be
        from site_pages.theme_push import MIN_POSTS
        j = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}", headers=h,
                         params={"fields": "categories"}, timeout=20).json()
        firsts = [c.get("slug") for c in (j.get("categories") or {}).values() if c.get("post_count") == MIN_POSTS]
        if firsts:
            print("분야 첫 공개 글 → 메뉴 다시 보이게(theme-push):", firsts)
            from site_pages import theme_push
            theme_push.main("push")
    except Exception as e:
        print("분야 첫 글 확인 실패(메뉴는 다음 theme-push 때):", type(e).__name__)


def main(pid):
    import requests
    import blog_engine as be
    f, ok, score = passed_log(pid)
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    if not ok and f:
        ok, why = claude_route(pid, f, json.load(open(f, encoding="utf-8")), site_text(pid, h))
        print(("두 번째 길 통과: " if ok else "두 번째 길도 안 됨: ") + why)
    if not ok:
        print(f"공개 안 함: 통과 기록 없음({f}, 점수 {score})")
        return 1
    base = f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}"
    data = {"status": "publish"}
    try:   # 11-21: 글 끝 표지 그림 설명 상자(표지와 같은 그림) - 실패해도 공개는 그대로
        import html as _h
        from ondo.media import art_note
        g = requests.get(base, headers=h, params={"context": "edit", "fields": "title,content,categories"}, timeout=30).json()
        cats = [c.get("slug") for c in (g.get("categories") or {}).values()]
        box = art_note.for_post(_h.unescape(g.get("title") or ""), cats[0] if cats else "etf")
        if box and g.get("content"):
            data["content"] = art_note.inject(g["content"], box)
    except Exception as e:
        print("ℹ️ 표지 그림 설명 못 넣음:", type(e).__name__, e)
    r = requests.post(base, headers=h, data=data, timeout=30)
    j = r.json() if r.ok else {}
    print(f"공개: {r.status_code} {j.get('status')} {j.get('URL')} (근거 {os.path.basename(f)}, 점수 {score})")
    if j.get("status") == "publish":
        from site_pages.pll_plugin import flush_sitemap
        flush_sitemap()
        first_in_category(pid, h)
        from ondo import indexnow        # 11-22: 빙 등 검색엔진에 새 글 알림(실패해도 공개는 그대로)
        print(indexnow.submit([j.get("URL") or ""])[1])
    return 0 if j.get("status") == "publish" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 and sys.argv[1].isdigit() else (print(__doc__) or 1))
