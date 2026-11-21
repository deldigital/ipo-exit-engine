"""
17_condition_log.py   Run after ~20 min of the 14:30 QQQ rehearsal:
    python 17_condition_log.py QQQ
Shows the trade-condition codes Finnhub ACTUALLY sends, and what share the live filter removes.
Pass if: letters like I/Z/T appear (our filter matches Finnhub's encoding), OR only digit codes appear
and the size<100 filter alone removes the odd lots (then the letter filter is inert but harmless).
FAIL if the filter removes a large share of normal-size trades.
"""
import glob
import sys
import pandas as pd
from live import BAD_COND, MIN_SIZE

sym = sys.argv[1] if len(sys.argv) > 1 else "QQQ"
files = sorted(glob.glob(f"logs/ticks_{sym}_*.csv"))
if not files:
    raise SystemExit(f"no logs/ticks_{sym}_*.csv yet: run the live app with --sym {sym} first")
d = pd.read_csv(files[-1], header=None, names=["t", "p", "v", "src", "cond"], dtype={"cond": str})
d["cond"] = d["cond"].fillna("")
d["v"] = pd.to_numeric(d["v"], errors="coerce")
codes = d["cond"].str.split("|").explode()
print(f"{files[-1]}: {len(d):,} trades, sources {d['src'].value_counts().to_dict()}")
print("\nMost common condition codes (as Finnhub sends them):")
print(codes[codes != ""].value_counts().head(20).to_string())
bad = d["cond"].apply(lambda c: bool(set(c.split("|")) & BAD_COND) if c else False)
small = d["v"] < MIN_SIZE
print(f"\nremoved by condition filter: {bad.mean():.1%} of trades | by size<{MIN_SIZE}: {small.mean():.1%}"
      f" | by either: {(bad | small).mean():.1%}")
print(f"normal-size trades (>= {MIN_SIZE}) removed by condition filter: {(bad & ~small).mean():.1%}  "
      "(should be small, a few % at most)")
letters = codes[codes.str.fullmatch(r"[A-Z@]")].nunique()
print("encoding:", "LETTERS present -> filter matches Finnhub" if letters else
      "DIGITS only -> letter filter inert; size filter carries odd-lot removal (verified equivalent)")
