"""배당 지급 기록을 지급일별로 보기(2026-11-22) - 해마다 합계가 들쭉날쭉할 때 지급 횟수·시기가 바뀐 것인지 확인용.
  python site_pages/div_dates.py 005380.KS,000660.KS
"""
import sys


def main(arg):
    import yfinance as yf
    for t in arg.split(","):
        d = yf.Ticker(t.strip()).dividends
        d = d[d.index.year >= 2019]
        print(f"== {t} ({len(d)}번)")
        for idx, v in d.items():
            print(f"  {idx:%Y-%m-%d}  {v:g}")
        print("  해마다 횟수:", dict(d.groupby(d.index.year).size()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else (print(__doc__) or 1))
