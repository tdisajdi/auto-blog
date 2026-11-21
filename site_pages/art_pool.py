"""표지용 명화 후보 모으기(2026-11-21, 사용자 결정 '자산의 나라 명화 × 80칸 도트 표지').

  python site_pages/art_pool.py            # 깃허브 실행(site_pages=art-pool) - 작업 환경은 미술관 사이트가 막혀 있음
결과: lab/art/pool/<나라>/<출처>-<번호>.jpg(긴 변 640px) + lab/art/pool/index.json(작품 정보·점수) + pool_log.txt

규칙(사용자와 정한 것):
- 이용 조건: CC0(퍼블릭 도메인)만. 시카고 미술관(is_public_domain), 클리블랜드 미술관(cc0), 메트로폴리탄(isPublicDomain).
- 작가 사후 70년: 사망 1955년 이하만(한국 저작권 기준). 사망 연도를 모르면 제작 연도 1900년 이전만.
- 색이 꽉 찬 그림: 채도(colorfulness)·여백 아닌 부분 비율로 점수 → 나라마다 점수 높은 순으로 최대 PER개 저장.
  여백 많은 수묵화(난초처럼)는 점수가 낮아 자연히 빠짐(11-20 시안에서 확인한 문제).
고르기·자르기 영역은 Claude가 그림을 직접 보고 lab/art/pool/picks.json 에 정한다(이 파일은 후보만 모음).
"""
import io
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lab", "art", "pool")
UA = {"User-Agent": "ondo-blog-cover-pool/1.0"}
PER = 50            # 나라마다 저장할 최대 수
CAP = 160           # 나라마다 받아서 점수 매길 최대 후보 수(11-21: 220 → 160, 시간 줄이기)
MAX_DEATH = 1955    # 2026년 기준 사후 70년

# 나라: 검색어 목록. AIC/CMA는 검색어 + 원산지 확인, Met은 검색어 + 문화권 확인
QUERIES = {
    "korea": ["Korean painting", "Joseon", "Korean screen", "Korea folk painting", "Kim Hong-do", "Korean landscape"],
    "japan": ["Hokusai", "Hiroshige", "Utamaro", "Kuniyoshi", "Yoshida Hiroshi", "ukiyo-e landscape", "Eisen", "Kunisada"],
    "france": ["Monet", "Renoir", "Pissarro", "Sisley", "Cezanne", "Seurat", "Signac", "Caillebotte", "Morisot",
               "Gauguin", "Bonnard", "Matisse", "Van Gogh", "Corot", "Boudin", "Guillaumin", "Derain", "Vlaminck"],
    "usa": ["Winslow Homer", "Hudson River School", "Frederic Edwin Church", "Albert Bierstadt", "Thomas Cole",
            "Childe Hassam", "John Singer Sargent", "Mary Cassatt", "George Bellows", "American Impressionism",
            "Thomas Moran", "William Merritt Chase", "John Frederick Kensett", "Fitz Henry Lane", "Martin Johnson Heade",
            "Sanford Robinson Gifford", "George Inness", "Edward Hopper", "John Henry Twachtman", "Maurice Prendergast"],
}
PLACE = {"korea": ("korea",), "japan": ("japan",), "france": ("france", "french"),
         "usa": ("united states", "america")}
KINDS = ("paint", "print", "screen", "scroll", "album", "woodblock", "drawing in color")
# 11-21 첫 결과: 미국은 호머의 흑백 목판 삽화, 프랑스는 흑백 동판화가 상위를 채움 → 두 나라는 그림(유화·파스텔)만
KINDS_BY = {"usa": ("paint", "pastel"), "france": ("paint", "pastel")}
MIN_COLOR = 16      # 채도 이 값 아래(흑백·갈색 판화)는 버림 - 호쿠사이 38, 난초 12.5, 흑백 판화 대개 10 아래


def get(url, params=None, timeout=40):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(1.5 + i * 2)
    return None


def death_year(text):
    """'Claude Monet French, 1840–1926' → 1926. 못 찾으면 None."""
    ys = re.findall(r"(1[0-9]{3})\s*[–-]\s*(1[0-9]{3})", text or "")
    return int(ys[-1][1]) if ys else None


def first_year(text):
    m = re.search(r"(1[0-9]{3})", str(text or ""))
    return int(m.group(1)) if m else None


def allowed(death, made):
    if death is not None:
        return death <= MAX_DEATH
    return made is not None and made < 1900


def from_aic(country, q, log):
    r = get("https://api.artic.edu/api/v1/artworks/search",
            {"q": q, "limit": 100, "fields": "id,title,image_id,artist_display,artist_title,date_display,date_end,"
                                             "place_of_origin,is_public_domain,classification_title"})
    data = (r.json().get("data") or []) if r else []
    out = []
    for a in data:
        if not (a.get("is_public_domain") and a.get("image_id")):
            continue
        if not any(p in str(a.get("place_of_origin", "")).lower() for p in PLACE[country]):
            continue
        if not any(k in str(a.get("classification_title", "")).lower() for k in KINDS_BY.get(country, KINDS)):
            continue
        d = death_year(a.get("artist_display"))
        if not allowed(d, a.get("date_end") or first_year(a.get("date_display"))):
            continue
        out.append({"src": "aic", "id": a["id"], "title": a.get("title"), "artist": a.get("artist_title") or "",
                    "artist_display": a.get("artist_display"), "date": a.get("date_display"), "death": d,
                    "url": f"https://www.artic.edu/artworks/{a['id']}", "license": "CC0 (Art Institute of Chicago)",
                    "img": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/843,/0/default.jpg"})
    log.append(f"{country} 시카고 '{q}': {len(data)}건 → {len(out)}건")
    return out


def from_cma(country, q, log):
    r = get("https://openaccess-api.clevelandart.org/api/artworks/",
            {"q": q, "cc0": 1, "has_image": 1, "limit": 100})
    data = (r.json().get("data") or []) if r else []
    out = []
    for a in data:
        cul = " ".join(a.get("culture") or []).lower()
        if not any(p in cul for p in PLACE[country]):
            continue
        if not any(k in str(a.get("type", "")).lower() for k in KINDS_BY.get(country, KINDS)):
            continue
        cr = (a.get("creators") or [{}])[0]
        d = cr.get("death_year")
        d = int(d) if str(d or "").isdigit() else death_year(cr.get("description"))
        if not allowed(d, a.get("creation_date_latest")):
            continue
        img = ((a.get("images") or {}).get("web") or {}).get("url")
        if not img:
            continue
        out.append({"src": "cma", "id": a["id"], "title": a.get("title"), "artist": cr.get("description") or "",
                    "artist_display": cr.get("description"), "date": a.get("creation_date"), "death": d,
                    "url": a.get("url"), "license": "CC0 (Cleveland Museum of Art)", "img": img})
    log.append(f"{country} 클리블랜드 '{q}': {len(data)}건 → {len(out)}건")
    return out


def from_met(country, q, log, cap=15):
    r = get("https://collectionapi.metmuseum.org/public/collection/v1/search",
            {"q": q, "hasImages": "true", "isPublicDomain": "true"})
    ids = ((r.json().get("objectIDs") or []) if r else [])[:cap]
    out = []
    for oid in ids:
        try:
            o = requests.get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}", headers=UA, timeout=12)
            o = o.json() if o.status_code == 200 else {}
        except Exception:
            o = {}
        if not o.get("isPublicDomain") or not o.get("primaryImageSmall"):
            continue
        text = " ".join(str(o.get(k, "")) for k in ("culture", "artistNationality", "country")).lower()
        if not any(p in text for p in PLACE[country]):
            continue
        if not any(k in (str(o.get("classification", "")) + str(o.get("objectName", ""))).lower() for k in KINDS_BY.get(country, KINDS)):
            continue
        d = first_year(o.get("artistEndDate"))
        if not allowed(d, o.get("objectEndDate")):
            continue
        out.append({"src": "met", "id": oid, "title": o.get("title"), "artist": o.get("artistDisplayName") or "",
                    "artist_display": o.get("artistDisplayBio"), "date": o.get("objectDate"), "death": d,
                    "url": o.get("objectURL"), "license": "CC0 (The Metropolitan Museum of Art)",
                    "img": o.get("primaryImageSmall")})
    log.append(f"{country} 메트 '{q}': {len(ids)}건 → {len(out)}건")
    return out


def score(im):
    """(점수, 채도, 꽉 참). 채도 = Hasler-Süsstrunk colorfulness(0~100쯤), 꽉 참 = 바탕색과 다른 칸 비율(0~1)."""
    from PIL import ImageStat
    import numpy as np
    a = np.asarray(im.convert("RGB").resize((96, 96)), dtype=float)
    rg, yb = a[..., 0] - a[..., 1], 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    color = float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))
    bg = np.median(a.reshape(-1, 3), axis=0)
    full = float((np.abs(a - bg).sum(axis=2) > 60).mean())
    w, h = im.size
    shape = 1.0 if 0.55 <= w / h <= 1.9 else 0.7            # 너무 긴 두루마리는 자르기 어려움
    return round((color / 60 + full) * shape, 3), round(color, 1), round(full, 2)


def main():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    log, index = [], {}
    old = {}
    if os.path.exists(os.path.join(OUT, "index.json")):
        old = json.load(open(os.path.join(OUT, "index.json"), encoding="utf-8"))
    for country, qs in QUERIES.items():
        cands, seen = [], set()
        for q in qs:
            for fn in (from_aic, from_cma, from_met):
                try:
                    for c in fn(country, q, log):
                        k = (c["src"], c["id"])
                        if k not in seen:
                            seen.add(k)
                            cands.append(c)
                except Exception as e:
                    log.append(f"{country} {fn.__name__} '{q}' 실패: {type(e).__name__}")
        log.append(f"== {country}: 조건 맞는 후보 {len(cands)}개, 그림 받아 점수 매기기")
        scored = []

        def fetch(c):
            # 11-21: 한 장씩 3번 다시 시도하던 방식이 30분 넘게 걸려 → 동시에 받고 늦으면 버림
            try:
                r = requests.get(c["img"], headers=UA, timeout=15)
                if r.status_code != 200:
                    return None
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.thumbnail((640, 640))
                return c, im
            except Exception:
                return None
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            for got in ex.map(fetch, cands[:CAP]):
                if not got:
                    continue
                c, im = got
                s, col, full = score(im)
                if col < MIN_COLOR:
                    continue
                c.update(score=s, color=col, full=full, w=im.size[0], h=im.size[1])
                scored.append((s, c, im))
        log.append(f"   그림 받음 {len(scored)}/{min(len(cands), CAP)}")
        scored.sort(key=lambda x: -x[0])
        os.makedirs(os.path.join(OUT, country), exist_ok=True)
        keep = []
        for s, c, im in scored[:PER]:
            name = f"{c['src']}-{c['id']}.jpg"
            im.thumbnail((640, 640))
            im.save(os.path.join(OUT, country, name), quality=86)
            c["file"] = f"{country}/{name}"
            keep.append(c)
        index[country] = keep or old.get(country, [])
        log.append(f"✅ {country}: {len(scored)}점 점수 → 상위 {len(keep)}점 저장")
    json.dump(index, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(OUT, "pool_log.txt"), "w", encoding="utf-8").write("\n".join(log) + "\n")
    print("\n".join(log))
    return 0 if any(index.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
