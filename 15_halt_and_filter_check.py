"""
15_halt_and_filter_check.py   Final checks before the 15:00 freeze.
Part A (offline): LULD halt behaviour through the REAL live.py + engine.py.
  A1 WARNING just before a halt, halt (no trades), reopen below floor -> SELL on the first
     post-halt bar (two completed bars WITH trades; empty minutes do not count).
  A2 Pre-halt bar above floor, reopen bars below floor -> SELL only after TWO post-halt bars.
  A3 Reopen gap of +18% (outside the 15% filter) -> accepted as a level shift, screen keeps updating.
Part B (Alpaca API): is the live size filter (<100 shares) the same as the backtest's odd-lot
  condition 'I'? Checks 200k raw SpaceX trades, and compares minute highs rebuilt from the
  filtered ticks with the vendor minute highs used in the backtest.
Run: python 15_halt_and_filter_check.py
"""
import os
import pandas as pd
import requests
from dotenv import load_dotenv
from engine import ExitEngine, Rule, ET
from live import LiveFeeds

T0 = pd.Timestamp("2026-11-19 12:15:00", tz=ET)


def ms(sec):
    return int((T0 + pd.Timedelta(seconds=sec)).value // 1_000_000)


def check(name, ok, extra=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name} {extra}")


def scenario(pre_halt_px, reopen_px, label):
    eng = ExitEngine(83.0, Rule())
    bars = []
    f = LiveFeeds("HALTTEST", lambda *b: (bars.append(b), eng.on_bar(*b)))
    q = lambda s: f._trade("QQQ", ms(s), 600.0, "finnhub", 100, [])
    t, px = 0, 95.0
    for s in range(0, 20 * 60, 5):              # 20 min: rise to ~105, past the grace period
        px = min(px * 1.0015, 105.0)
        f._trade("HALTTEST", ms(s), round(px, 2), "finnhub", 200, []); q(s)
    for s in range(20 * 60, 21 * 60, 5):        # minute 20: last bar before the halt
        f._trade("HALTTEST", ms(s), pre_halt_px, "finnhub", 200, []); q(s)
    # HALT: minutes 21-25, no ANT trades (QQQ keeps trading)
    for s in range(21 * 60, 26 * 60, 5):
        q(s)
    for s in range(26 * 60, 28 * 60, 2):        # reopen auction print + trading
        f._trade("HALTTEST", ms(s), reopen_px, "finnhub", 50_000 if s == 26 * 60 else 300, []); q(s)
    f._trade("HALTTEST", ms(28 * 60 + 1), reopen_px, "finnhub", 300, [])   # closes minute 27
    times = [b[0] for b in bars]
    gap = [((times[i] - times[i - 1]).total_seconds() / 60) for i in range(1, len(times))]
    return eng, f, bars, max(gap) if gap else 0, label


# floor after grace = 105 * 0.96 = 100.80
eng, f, bars, gap, _ = scenario(100.0, 99.0, "A1")
sig = eng.signal
check("A1 halt leaves no empty bars (largest gap between bars, min)", gap >= 5, f"= {gap:.0f}")
check("A1 WARNING before halt + reopen below floor -> SELL on first post-halt bar",
      sig is not None and sig["ts"] == T0 + pd.Timedelta(minutes=27),
      f"(signal {sig['ts'].strftime('%H:%M') if sig else None} ET, expected 12:42)")

eng, f, bars, gap, _ = scenario(102.0, 99.0, "A2")
sig = eng.signal
check("A2 pre-halt bar above floor -> SELL only on the SECOND post-halt bar (empty minutes not counted)",
      sig is not None and sig["ts"] == T0 + pd.Timedelta(minutes=28),
      f"(signal {sig['ts'].strftime('%H:%M') if sig else None} ET, expected 12:43)")

eng, f, bars, gap, _ = scenario(104.0, round(104.0 * 1.18, 2), "A3")
st = f.state
check("A3 +18% reopen accepted as level shift, screen updates",
      st["tick"] == round(104.0 * 1.18, 2) and st["resets"] >= 1,
      f"(tick {st['tick']}, resets {st['resets']}, prints rejected first {st['rejected']})")
for p in os.listdir("logs"):
    if "HALTTEST" in p:
        os.remove(os.path.join("logs", p))

# ---------------- Part B: size filter vs condition 'I' ----------------
load_dotenv()
HDR = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}
day = pd.to_datetime(pd.read_csv("data/SPCX_d1.csv", index_col=0).index, utc=True)[0]
params = dict(start=day.isoformat(), end=(day + pd.Timedelta(hours=2)).isoformat(), limit=10000, feed="sip")
rows = []
for _ in range(20):
    js = requests.get("https://data.alpaca.markets/v2/stocks/SPCX/trades", headers=HDR,
                      params=params, timeout=30).json()
    rows += [(t["s"], "I" in (t.get("c") or [])) for t in js.get("trades") or []]
    if not js.get("next_page_token"):
        break
    params["page_token"] = js["next_page_token"]
d = pd.DataFrame(rows, columns=["size", "I"])
small_noI = int(((d["size"] < 100) & ~d["I"]).sum())
big_I = int(((d["size"] >= 100) & d["I"]).sum())
print(f"\nPart B: {len(d):,} raw SPCX trades | size<100 without 'I': {small_noI} | 'I' with size>=100: {big_I}")
check("B1 size<100 filter == odd-lot condition 'I' (round lot 100)", small_noI == 0 and big_I == 0)

s1 = pd.read_csv("data/SPCX_d1_1s.csv", index_col=0); s1.index = pd.to_datetime(s1.index, utc=True)
m1 = pd.read_csv("data/SPCX_d1.csv", index_col=0); m1.index = pd.to_datetime(m1.index, utc=True)
hi = s1["high"].resample("60s").max().dropna()
common = hi.index.intersection(m1.index)
dh = (hi.loc[common] / m1.loc[common, "high"] - 1).abs()
print(f"minute HIGH from filtered ticks vs vendor: identical in {(dh < 1e-6).mean():.1%} of minutes, "
      f"max diff {dh.max():.3%}")
check("B2 running high definitions agree (max minute-high diff < 0.1%)", dh.max() < 0.001)
