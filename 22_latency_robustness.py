"""
22_latency_robustness.py  (no API; data/*_d1.csv, data/*_dl.csv, out/18_sip_bars.csv, out/19_quick_vs_trail.csv)
Follows from 21: a fixed sale time is fragile in the first minutes (1-minute moves 3.1x larger than later),
and a manual retail seller cannot control the exact minute. Is rule v1.1 robust to execution delay?
Run: python 22_latency_robustness.py

PRE-REGISTERED (22:00 UK, 19 Nov)
 H20  A 1-minute execution delay moves v1.1's result far less than it moves a fixed sale at minute 5:
      cross-deal std of the delay impact for v1.1 is under half that of the minute-5 sale.
 H21  Same for 2- and 3-minute delays.
 H22  With a random 0-3 minute retail delay (uniform, 2,000 draws per deal), v1.1's mean is within 1 point
      of the minute-5 sale's mean AND its 10th percentile is higher.
 Delayed execution = close of the bar d minutes after the decision bar.
"""
import numpy as np
import pandas as pd
from engine import ExitEngine, Rule

ET = "America/New_York"
OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "FIG": 33, "CRCL": 31, "CRWV": 40, "RDDT": 34,
         "RIVN": 78, "ABNB": 68, "DASH": 102, "SNOW": 120, "UBER": 45, "LYFT": 72, "ZM": 36,
         "PINS": 19, "CAVA": 22, "KVYO": 30, "BIRK": 46, "CHYM": 27, "KLAR": 40}
DL = {"SPOT": 132.0, "WORK": 26.0, "PLTR": 7.25, "ASAN": 21.0, "RBLX": 45.0, "COIN": 250.0}
T19 = pd.read_csv("out/19_quick_vs_trail.csv", index_col=0)
rng = np.random.default_rng(22)


def load_csv(path, rename=None):
    df = pd.read_csv(path, index_col=0)
    if rename:
        df = df.rename(columns=rename)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    df = df[["open", "high", "low", "close"]].astype(float)
    return df[[t.time() < pd.Timestamp("16:00").time() for t in df.index]]


D = {s: (o, load_csv(f"data/{s}_d1.csv")) for s, o in OFFER.items()}
for s, r in DL.items():
    D[s] = (r, load_csv(f"data/{s}_dl.csv"))
D["ANT"] = (83.0, load_csv("out/18_sip_bars.csv", {"o": "open", "h": "high", "l": "low", "c": "close"}))


def signal_bar(df, off):
    eng = ExitEngine(off, Rule())
    for ts, r in df.iterrows():
        eng.on_bar(ts, r["open"], r["high"], r["low"], r["close"])
        if eng.signal:
            return df.index.get_loc(eng.signal["ts"] - pd.Timedelta(seconds=60))
    return len(df) - 1


rows = []
for s, (off, df) in D.items():
    c = df["close"].to_numpy()
    n = len(c)
    i_v = signal_bar(df, off)
    val = lambda i: (c[min(i, n - 1)] / off - 1) * 100
    rows.append(dict(sym=s, w=T19.loc[s, "w"], **{f"v11_d{d}": val(i_v + d) for d in range(4)},
                     **{f"m5_d{d}": val(5 + d) for d in range(4)}))
R = pd.DataFrame(rows).set_index("sym")

print("=" * 92)
print("22  EXECUTION-DELAY ROBUSTNESS: rule v1.1 vs fixed sale at minute 5 (% of offer, 27 deals)")
print("=" * 92)
print(" delay   v11 mean  impact mean  impact std | min5 mean  impact mean  impact std | std ratio v11/min5")
ok = []
for d in range(4):
    iv = R[f"v11_d{d}"] - R["v11_d0"]
    im = R[f"m5_d{d}"] - R["m5_d0"]
    ratio = iv.std() / im.std() if d else float("nan")
    if d:
        ok.append(ratio < 0.5)
    print(f"  {d} min   {R[f'v11_d{d}'].mean():7.2f}   {iv.mean():+8.2f}   {iv.std():8.2f}  | "
          f"{R[f'm5_d{d}'].mean():7.2f}   {im.mean():+8.2f}   {im.std():8.2f}  | {ratio:6.2f}")
print(f"H20 (1-min) -> {'PASS' if ok[0] else 'FAIL'} | H21 (2- and 3-min) -> {'PASS' if all(ok[1:]) else 'FAIL'}")

print("\nLargest 1-minute delay impacts (points):")
imp = pd.DataFrame({"v11": R["v11_d1"] - R["v11_d0"], "min5": R["m5_d1"] - R["m5_d0"]})
print(imp.reindex(imp.abs().max(axis=1).sort_values(ascending=False).index).head(8).round(1).to_string())

print("\n--- H22  RANDOM RETAIL DELAY 0-3 MIN (uniform), 2,000 draws per deal ---")
draws = {}
for strat in ["v11", "m5"]:
    M = R[[f"{strat}_d{d}" for d in range(4)]].to_numpy()
    pick = rng.integers(0, 4, size=(len(R), 2000))
    draws[strat] = np.take_along_axis(M, pick, axis=1)
for strat in ["v11", "m5"]:
    x = draws[strat]
    per_deal_std = x.std(axis=1)
    print(f"  {strat:4s}: mean {x.mean():6.2f} | 10th pct {np.percentile(x, 10):6.2f} | "
          f"average within-deal spread caused by delay {per_deal_std.mean():5.2f} pts")
h22 = abs(draws["v11"].mean() - draws["m5"].mean()) <= 1 and np.percentile(draws["v11"], 10) > np.percentile(draws["m5"], 10)
print(f"H22 -> {'PASS' if h22 else 'FAIL'}")
R.to_csv("out/22_latency.csv")
print("\nSaved out/22_latency.csv.")
