"""공개 글 사실 검증 다시 하기(2026-11-19 - 가벼운 모델 사실 검증으로 통과했던 글 뒷정리).

  python site_pages/fact_recheck.py <글번호>
그 글의 마지막 기록(logs)에서 [사실 자료]를 꺼내, 지금 사이트에 올라 있는 본문(사람 읽기 뒤 고친 판)을
좋은 모델로만 사실 검증한다(Gemini 1~2번). 글은 바꾸지 않는다. 결과는 lab/recheck/<번호>.json.
치명·중요가 나오면 lab/patches/<번호>.json 으로 고칠 곳을 Claude가 만든다(patch:번호).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(pid):
    import requests
    import blog_engine as be
    from ondo.writing import desk, llm
    from ondo.checks import editlog
    from site_pages.publish_passed import passed_log, patches_in, plain
    h = {"Authorization": f"Bearer {be.WP_OAUTH_TOKEN}"}
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{be.WP_SITE_ID}/posts/{pid}", headers=h,
                     params={"context": "edit", "fields": "ID,title,status,content,slug"}, timeout=30)
    if not r.ok:
        print("글 받기 실패:", r.status_code)
        return 1
    j = r.json()
    f, _ok, _score = passed_log(pid, j.get("slug"))
    if not f:
        print("기록(logs) 없음 - 사실 자료를 몰라 검증 못 함")
        return 1
    d = json.load(open(f, encoding="utf-8"))
    facts = d.get("facts") or ""
    html = f"<h1>{j['title']}</h1>" + j["content"]
    text = desk.review_text(html)
    common = desk.prompt("review_common", today=desk._today(), text=text)
    log = editlog.EditLog(d.get("article_type", "guide"), f"recheck-{pid}", j["title"])
    p = desk.prompt("review_fact", category_label=d.get("category") or "", facts=facts, must="") + common
    res = llm.call(p, step="사실 다시 검증", log=log, tier="strong_only", json_out=True, thinking=8192)
    data = llm.parse_json(res.text)
    if not isinstance(data, dict):
        print("좋은 모델이 답하지 않음(503 등) - 나중에 다시")
        return 1
    norm = desk._norm(text)
    issues = [it for it in data.get("issues") or [] if isinstance(it, dict) and desk._quote_found(it.get("quote", ""), norm)]
    out = {"post": pid, "status": j["status"], "model": res.model, "log": os.path.basename(f), "issues": issues,
           "patch_applied": bool(patches_in(pid, plain(j["content"])))}   # 11-20: 고친 글을 봤다는 증거(공개 두 번째 길에 씀)
    os.makedirs(os.path.join(ROOT, "lab", "recheck"), exist_ok=True)
    open(os.path.join(ROOT, "lab", "recheck", f"{pid}.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    serious = [i for i in issues if i.get("severity") in ("치명", "중요")]
    print(f"사실 다시 검증({res.model}): 지적 {len(issues)}개, 치명·중요 {len(serious)}개")
    for i in issues:
        print(f" - [{i.get('severity')}] {str(i.get('quote'))[:60]} → {str(i.get('problem'))[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 and sys.argv[1].isdigit() else (print(__doc__) or 1))
