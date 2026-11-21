"""
13_live_open_test.py  (offline; drives the REAL live.py + engine.py with synthetic prints)
Checks run before the 15:00 freeze:
  A. +20% open at the cross is accepted (filter seeded by first print, not by the $83 offer).
  B. Odd lots / bad condition codes are filtered, as in the backtest.
  C. A genuine >15% level shift is accepted after 3 agreeing prints (screen cannot freeze).
  D. Failover: IEX prints are ignored while Finnhub's QQQ heartbeat is alive; used if Finnhub dies.
  E. Engine state sequence through the 15-minute switch from x0.92 to x0.96.
Run: python 13_live_open_test.py   Every line should say PASS.
"""
import time
import pandas as pd
from engine import ExitEngine, Rule, ET
from live import LiveFeeds

eng = ExitEngine(83.0, Rule())
bars = []


def on_bar(m, o, h, l, c):
    bars.append((m, o, h, l, c))
    eng.on_bar(m, o, h, l, c)


f = LiveFeeds("ANTTEST", on_bar, backup_keys=("k", "s"))
st = f.state
T0 = pd.Timestamp("2026-11-19 12:15:00", tz=ET)


def ms(sec):
    return int((T0 + pd.Timedelta(seconds=sec)).value // 1_000_000)


def check(name, ok):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")


# heartbeat alive: QQQ trade on Finnhub
f._trade("QQQ", ms(0), 600.0, "finnhub", 100, [])
# D1: IEX print for ANT arrives first while Finnhub alive -> ignored
f._trade("ANTTEST", ms(1), 99.0, "alpaca", 500, ["@"])
check("D1 IEX print ignored while Finnhub heartbeat alive", st["tick"] is None)
# A: opening cross print +20% on Finnhub
f._trade("ANTTEST", ms(2), 99.6, "finnhub", 2_000_000, [])
check("A  +20% opening cross accepted", st["tick"] == 99.6)
# B: odd lot far away and an out-of-sequence print
f._trade("ANTTEST", ms(3), 120.0, "finnhub", 5, ["I"])
f._trade("ANTTEST", ms(4), 104.0, "finnhub", 300, ["Z"])
check("B  odd lot and out-of-sequence prints filtered", st["tick"] == 99.6 and st["filtered"] == 2)
# normal trading for 20 minutes: up to ~$103 then a dip
px = 99.6
for s in range(5, 20 * 60, 7):
    px = px * (1.0004 if s < 600 else 0.9996)
    f._trade("ANTTEST", ms(s), round(px, 2), "finnhub", 200, [])
    if s % 60 < 7:
        f._trade("QQQ", ms(s), 600.0, "finnhub", 100, [])
# C: genuine level shift +18% (three agreeing prints)
lvl = round(px * 1.18, 2)
for k in range(3):
    f._trade("ANTTEST", ms(20 * 60 + k), lvl, "finnhub", 500, [])
check("C  genuine >15% level shift accepted after 3 prints", st["tick"] == lvl and st["resets"] == 1)
# D2: Finnhub dies -> IEX used
st["fh_ts"] = time.time() - 20
f._trade("ANTTEST", ms(20 * 60 + 10), lvl * 1.001, "alpaca", 100, ["@"])
check("D2 IEX used when Finnhub silent > 15 s", st["source"] == "alpaca" and st["alp_used"] >= 1)
f.builder.add(ms(21 * 60 + 5), lvl)          # force the last bar to close
states = [e[1] for e in eng.events]
check("E  engine went LIVE then ARMED (opened above $91.30)", states[:2] == ["LIVE", "ARMED"])
print(f"     bars built: {len(bars)} | events: {[(e[0].tz_convert('Europe/London').strftime('%H:%M'), e[1]) for e in eng.events]}")
print(f"     trail now x{1 - eng.k_now:.2f} (after 15 min should be 0.96) | day high ${eng.runmax:.2f} | floor ${eng.floor:.2f}")
check("E  trail switched to x0.96 after 15 minutes", abs(eng.k_now - 0.04) < 1e-12)
