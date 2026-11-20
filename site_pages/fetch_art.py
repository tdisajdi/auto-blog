"""표지용 공공 명화 받기(2026-11-20 사용자 요청 '나라별 명화 도트화' 시안).

메트로폴리탄 미술관 공개 API(CC0 - isPublicDomain=True 인 작품만)에서 나라별 후보를 받아 lab/art/ 에 저장한다.
작업 환경(Claude)은 외부 사이트가 막혀 있어 깃허브 실행(site_pages=art-fetch)에서 돌린다.
저장: lab/art/<나라>.jpg + lab/art/<나라>.json(제목·작가·연도·작품 주소·이용 조건) + lab/art/fetch_log.txt
작가 사후 70년(한국 기준) - 아래 후보는 모두 19세기 이전 작품. CC0 가 아니면 받지 않는다.
"""
import json
import os
import sys
import time

import requests

API = "https://collectionapi.metmuseum.org/public/collection/v1"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab", "art")
UA = {"User-Agent": "ondo-blog-cover-fetch/1.0"}

# 나라별: 먼저 알려진 작품 번호, 안 되면 검색어(문화권·분류로 거름)
CANDIDATES = {
    "korea": {"ids": [], "search": [("Korea Joseon painting", "Korea"), ("Korean folding screen", "Korea"), ("Korea", "Korea")]},
    "usa": {"ids": [11122], "search": [("Winslow Homer", "American"), ("Hudson River School", "American")]},     # 호머 '멕시코 만류'
    "france": {"ids": [437127], "search": [("Claude Monet", "French"), ("Camille Pissarro", "French")]},     # 모네 '수련 연못 위 다리'
    "japan": {"ids": [45434], "search": [("Hokusai", "Japan"), ("Hiroshige", "Japan")]},                  # 호쿠사이 '가나가와 앞바다 파도 아래'
}


def get(url, params=None):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=40)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 + i * 2)
    return None


def obj(oid):
    r = get(f"{API}/objects/{oid}")
    return r.json() if r else None


def ok(o, want):
    if not o or not o.get("isPublicDomain") or not (o.get("primaryImage") or o.get("primaryImageSmall")):
        return False
    text = " ".join(str(o.get(k, "")) for k in ("culture", "artistNationality", "country", "artistDisplayBio", "department"))
    cls = (o.get("classification") or "") + " " + (o.get("objectName") or "")
    return want.lower() in text.lower() and any(w in cls.lower() for w in ("paint", "print", "screen", "scroll", "album"))


def pick(country, spec, log):
    for oid in spec["ids"]:
        o = obj(oid)
        if o and o.get("isPublicDomain") and (o.get("primaryImage") or o.get("primaryImageSmall")):
            return o
        log.append(f"{country}: 번호 {oid} 못 씀(공공 아님/이미지 없음/응답 없음)")
    for q, want in spec["search"]:
        r = get(f"{API}/search", {"q": q, "hasImages": "true", "isPublicDomain": "true"})
        ids = (r.json().get("objectIDs") or [])[:60] if r else []
        log.append(f"{country}: 검색 '{q}' → {len(ids)}건 확인")
        for oid in ids:
            o = obj(oid)
            if ok(o, want):
                return o
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    log, done = [], 0
    for country, spec in CANDIDATES.items():
        o = pick(country, spec, log)
        if not o:
            log.append(f"❌ {country}: 알맞은 공공 작품을 못 찾음")
            continue
        url = o.get("primaryImage") or o.get("primaryImageSmall")
        r = get(url)
        if not r:
            log.append(f"❌ {country}: 이미지 받기 실패 {url}")
            continue
        open(os.path.join(OUT, f"{country}.jpg"), "wb").write(r.content)
        meta = {k: o.get(k) for k in ("objectID", "title", "artistDisplayName", "artistDisplayBio", "objectDate", "culture",
                                      "classification", "objectURL", "creditLine", "isPublicDomain")}
        meta["license"] = "CC0 (The Metropolitan Museum of Art Open Access)"
        meta["image_url"] = url
        json.dump(meta, open(os.path.join(OUT, f"{country}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log.append(f"✅ {country}: {meta['title']} / {meta['artistDisplayName'] or meta['culture']} / {meta['objectDate']} ({len(r.content) // 1024}KB)")
        done += 1
    open(os.path.join(OUT, "fetch_log.txt"), "w", encoding="utf-8").write("\n".join(log) + "\n")
    print("\n".join(log))
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
