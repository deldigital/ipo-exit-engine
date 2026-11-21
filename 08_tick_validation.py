"""
08_tick_validation.py  (no API; needs data/*_d1_1s.csv from script 07)
Trailing exits and decision lag at second resolution, on the 4 closest analogues (SPCX, CBRS, ARM, RIVN).
VALIDATION ONLY: 4 IPOs are too few to select rules on. We check whether minute-bar conclusions hold.
  1. Data check: 1-min bars rebuilt from ticks vs Alpaca minute bars.
  2. True peak and pre-peak dips at 1-second resolution vs 1-minute.
  3. Rule v1.1 with a realistic execution delay: fill L seconds after the SELL signal
     (L = 10..120 s), at the 1-s close, plus a worst case (lowest print in that window).
  4. Faster decisions: v1.1 on 30-s and 15-s bars (confirmation scaled to the same 2 minutes).
Run: python 08_tick_validation.py
"""
import numpy as np
import pandas as pd
from engine import ExitEngine, Rule, ET, UK

OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "RIVN": 78}
LAGS = [10, 20, 30, 45, 60, 90, 120]


def load1s(sym):
    df = pd.read_csv(f"data/{sym}_d1_1s.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


def load1m(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


def resample(df, sec):
    r = df.resample(f"{sec}s", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return r.dropna(subset=["close"])


def run(bars, offer, sec, confirm):
    eng = ExitEngine(offer, Rule(confirm=confirm), bar_sec=sec)
    for ts, b in bars.iterrows():
        eng.on_bar(ts, b.open, b.high, b.low, b.close)
        if eng.signal:
            return eng.signal["ts"], eng.signal["reason"]
    return None, "EOD"


def fill_at(s1, t, lag):
    after = s1[s1.index >= t + pd.Timedelta(seconds=lag)]
    window = s1[(s1.index >= t) & (s1.index < t + pd.Timedelta(seconds=lag))]
    px = after["close"].iloc[0] if len(after) else s1["close"].iloc[-1]
    worst = window["low"].min() if len(window) else px
    return px, min(worst, px)


def prepeak_dip(h, l):
    ip = int(np.argmax(h))
    prev = np.maximum.accumulate(np.concatenate([[h[0]], h[:-1]]))
    return float((1 - l / prev)[:ip + 1].max()) if ip > 0 else 0.0, ip


rows, lagrows, fast = [], [], []
for sym, off in OFFER.items():
    s1, m1 = load1s(sym), load1m(sym)
    r1m = resample(s1, 60)
    common = r1m.index.intersection(m1.index)
    diff = (r1m.loc[common, "close"] / m1.loc[common, "close"] - 1).abs()
    dip1s, ip1s = prepeak_dip(s1["high"].to_numpy(), s1["low"].to_numpy())
    dip1m, _ = prepeak_dip(m1["high"].to_numpy(), m1["low"].to_numpy())
    peak_t = s1.index[ip1s]
    hold = m1[m1.index.time <= pd.Timestamp("15:30").time()]["close"].iloc[-1] / off - 1
    rows.append(dict(sym=sym, bars_match=f"{(diff < 0.001).mean():.0%}", max_close_diff=f"{diff.max():.2%}",
                     peak_1s=s1["high"].max() / off - 1, peak_1m=m1["high"].max() / off - 1,
                     peak_uk=peak_t.tz_convert(UK).strftime("%H:%M:%S"),
                     dip_1s=dip1s, dip_1m=dip1m, hold=hold))
    t_sig, why = run(r1m, off, 60, 2)
    for lag in LAGS:
        if t_sig is None:
            break
        px, worst = fill_at(s1, t_sig, lag)
        lagrows.append(dict(sym=sym, lag=lag, exit=px / off - 1, worst=worst / off - 1,
                            capture=(px / off - 1) / (s1["high"].max() / off - 1)))
    for sec, cf in [(60, 2), (30, 4), (15, 8)]:
        t, why = run(resample(s1, sec), off, sec, cf)
        px, _ = fill_at(s1, t, 30) if t is not None else (m1["close"].iloc[-1], None)
        fast.append(dict(sym=sym, bars=f"{sec}s C{cf}", signal_uk=t.tz_convert(UK).strftime("%H:%M:%S") if t is not None else "-",
                         why=why, exit_30s_lag=px / off - 1, vs_hold=px / off - 1 - hold))

pd.set_option("display.width", 200)
T = pd.DataFrame(rows).set_index("sym")
for c in ["peak_1s", "peak_1m", "dip_1s", "dip_1m", "hold"]:
    T[c] = (T[c] * 100).round(2)
print("=== 1. Data check + 2. peak and pre-peak dip, 1-second vs 1-minute (%) ===")
print(T.to_string())

L = pd.DataFrame(lagrows)
print("\n=== 3. Rule v1.1 (1-min decisions): exit % vs execution delay in seconds ===")
print((L.pivot(index="sym", columns="lag", values="exit") * 100).round(2).to_string())
print("\nworst print inside the delay window (%):")
print((L.pivot(index="sym", columns="lag", values="worst") * 100).round(2).to_string())
print("\ncapture of 1-s peak:")
print(L.pivot(index="sym", columns="lag", values="capture").round(3).to_string())

F = pd.DataFrame(fast)
F["exit_30s_lag"] = (F["exit_30s_lag"] * 100).round(2)
F["vs_hold"] = (F["vs_hold"] * 100).round(2)
print("\n=== 4. Decision bar length (same 2-min confirmation), 30 s execution delay ===")
print(F.to_string(index=False))
print("\nMean vs hold by bar length:", F.groupby("bars")["vs_hold"].mean().round(2).to_dict())
