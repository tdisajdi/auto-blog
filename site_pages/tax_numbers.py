"""'세금·계좌 숫자와 날짜' 페이지(2026-11-22, 백로그 103 - 사용자 선택: 공개 전 미리 보여 주고 허락 뒤 공개).

  python site_pages/tax_numbers.py preview   lab/tax_numbers.html 로 미리 보기 파일만 만듦
  python site_pages/tax_numbers.py draft     워드프레스 '페이지'로 비공개 초안(공개된 같은 주소 페이지는 안 건드림)
  python site_pages/tax_numbers.py publish   초안을 공개로(11-22 사용자 허락), 이미 공개면 본문만 새로
원칙: 숫자·날짜는 법령 원문(lab/official, 국가법령정보센터)에서 글자로 확인한 것만. 확인 못 한 것은 '아직 확인 못 함'에 적고 숫자로 쓰지 않음.
      계좌 규칙은 ondo/account_rules.py(같은 출처)에서 가져옴 - 법이 바뀌면 그 파일과 아래 TAX를 고치고 다시 만듦.
"""
import html
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ondo import account_rules as ar  # noqa: E402

SLUG = "tax-account-numbers"
TITLE = "세금·계좌 숫자와 날짜 - 법령 원문으로 확인한 것만"
LOCAL_TAX = ("지방세법 [시행 2026. 7. 1.]",
             "https://www.law.go.kr/LSW/lsInfoR.do?lsiSeq=282559&efYd=20260701&chrClsCd=010202&ancYnChk=0")

# (항목, 내용, 법 키 또는 'local', 조문) - lab/official/701-tax-check.txt · income-tax-70/105/110.txt에서 확인
TAX = {
    "해외 상장 주식·ETF를 팔아 남긴 이익(양도소득)": [
        ("대상", "외국법인이 발행했거나 외국 시장에 상장된 주식 등", "소득세법", "제94조 ①3다"),
        ("기본공제", "한 해 양도소득에서 250만 원을 빼고 세금 계산", "소득세법", "제103조 ①2"),
        ("세율", "20%(중소기업 외 주식 등) + 지방소득세 2% = 22%", "소득세법", "제104조 ①12나 · 지방세법 제103조의3 ①12나"),
        ("신고 시기", "다음 해 5월 1일부터 5월 31일까지 확정신고(원문: 과세표준이 없거나 결손금이 있는 경우에도 적용)", "소득세법", "제110조 ①·②"),
        ("예정신고", "예정신고(양도한 달이나 반기의 말일부터 2개월 안에 하는 신고) 대상에서 해외 상장 주식 등은 빠짐 - 5월 확정신고만", "소득세법", "제105조 ①"),
    ],
    "배당·이자(금융소득)": [
        ("떼고 주는 세금(원천징수)", "배당소득 14% + 지방소득세 1.4%(소득세의 10%) = 15.4%", "소득세법", "제129조 ①2나 · 지방세법 제103조의13 ①"),
        ("종합과세 기준", "이자·배당 합계가 한 해 2천만 원을 넘으면 다른 소득과 합쳐 계산(종합과세)", "소득세법", "제14조 ③6"),
        ("신고 시기", "종합소득이 있으면 다음 해 5월 1일부터 5월 31일까지 확정신고", "소득세법", "제70조 ①"),
    ],
}

NOT_YET = [x.replace("지방소득세를 더한 공제율·세율", "연금계좌 세액공제·연금소득세에 지방소득세를 더한 비율(양도세 22%·배당 15.4%의 지방소득세는 위에서 확인함)") for x in ar.UNCONFIRMED] + [
    "국내 상장 해외지수 ETF의 매매차익이 배당소득으로 과세되는 근거(소득세법 시행령 집합투자기구 조항 - 아직 받지 않음)",
    "미국 주식 배당에 미국에서 떼는 15%(한미 조세조약 - 아직 받지 않음)",
]

_TD = 'style="border:1px solid #ddd;padding:8px;vertical-align:top;"'
_TH = 'style="border:1px solid #ddd;padding:8px;background:#f3f5f9;text-align:left;"'


def _src(law_key, article):
    if law_key in ar.LAW:
        name, url = ar.LAW[law_key]
    else:
        name, url = LOCAL_TAX
    return f'<a href="{url}" target="_blank" rel="noopener">{html.escape(name.split(" [")[0])} {html.escape(article)}</a>'


def _table(rows, cols):
    head = "".join(f"<th {_TH}>{c}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td {_TD}>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div style="overflow-x:auto;margin:16px 0;"><table style="width:100%;border-collapse:collapse;font-size:14px;"><tr>{head}</tr>{body}</table></div>'


def build_html():
    ex = ar.credit_examples()
    out = [
        f"<p>투자 글을 쓰다 보면 같은 세금 숫자와 계좌 규칙이 여러 글에 반복해서 나옵니다. 이 페이지는 그 숫자와 날짜를 "
        f"<strong>국가법령정보센터의 법령 원문에서 글자로 확인한 것만</strong> 한곳에 모아 둔 것입니다. "
        f"각 줄 끝의 조문 링크를 누르면 원문을 바로 볼 수 있습니다.</p>",
        f"<p>기준일: {ar.AS_OF}. 법이 바뀌면 이 페이지를 고칩니다. 개인 상황(소득 규모·다른 소득·계좌 상태)에 따라 실제 세금은 달라질 수 있어, "
        f"신고나 계좌 선택 전에는 원문과 국세청 안내를 함께 확인하세요. 이 페이지는 정보 정리이며 특정 상품이나 계좌를 권하지 않습니다.</p>",
    ]
    for title, rows in TAX.items():
        out.append(f"<h3>{html.escape(title)}</h3>")
        out.append(_table([(html.escape(a), html.escape(b), _src(k, c)) for a, b, k, c in rows], ("항목", "내용", "근거 조문")))
    out.append("<h3>ISA·연금저축·IRP 계좌 규칙</h3>")
    out.append(_table([(html.escape(acc), html.escape(item), html.escape(val), _src(k, art)) for acc, item, val, k, art in ar.RULES],
                      ("계좌", "항목", "내용", "근거 조문")))
    out.append(f"<p>예를 들어 연금저축·IRP에 한 해 {ex['amount'] // 10000:,}만 원을 넣어 세액공제 한도를 채우면, 공제율 12%일 때 "
               f"{ex['low'] // 10000:,}만 원, 15%일 때 {ex['high'] // 10000:,}만 원을 세금에서 뺍니다"
               f"(소득세 기준, 지방소득세는 아래 '아직 확인 못 함').</p>")
    out.append("<h3>아직 확인 못 한 것</h3>")
    out.append("<p>아래는 원문을 받지 못했거나 원문에서 표·그림으로만 나와 글자로 확인하지 못한 것입니다. 확인되기 전에는 이 사이트의 글에 숫자로 쓰지 않습니다.</p>")
    out.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in NOT_YET) + "</ul>")
    out.append("<h3>출처</h3><ul>"
               + "".join(f'<li><a href="{u}" target="_blank" rel="noopener">{html.escape(n)}</a></li>' for n, u in list(ar.LAW.values()) + [LOCAL_TAX])
               + "</ul><p>모두 국가법령정보센터(law.go.kr) 현행 법령 본문입니다.</p>")
    return "\n".join(out)


def main(mode="preview"):
    body = build_html()
    if mode == "preview":
        path = os.path.join(ROOT, "lab", "tax_numbers.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'<!doctype html><meta charset="utf-8"><title>{TITLE}</title>'
                    f'<body style="max-width:760px;margin:24px auto;padding:0 16px;font-family:sans-serif;line-height:1.7;">'
                    f"<h1>{TITLE}</h1>{body}</body>")
        print("미리 보기:", path)
        return 0
    if mode not in ("draft", "publish"):
        print(__doc__)
        return 1
    from site_pages.upload import upsert_page, refresh_page
    page = {"slug": SLUG, "title": TITLE, "html": body}
    ok, msg = upsert_page(page, mode)          # 11-22 사용자 '공개하자' - publish는 초안을 공개로
    if not ok and "이미 있어 건드리지 않음" in msg:   # 이미 공개된 뒤 법이 바뀌어 다시 만들면 본문만 새로
        ok, msg = refresh_page(page)
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "preview"))
