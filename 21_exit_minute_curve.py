"""
21_exit_minute_curve.py  (no API; data/*_d1.csv, data/*_dl.csv, out/18_sip_bars.csv, out/19_quick_vs_trail.csv)
Follows from 20: selling at +1 min instead of +2 min cost 2.8 points on the mean (CRCL regret 53.7).
"Sell at once" may be fragile to the exact minute, which a manual retail seller cannot control.
Run: python 21_exit_minute_curve.py

PRE-REGISTERED (21:55 UK, 19 Nov)
 H17  No fixed sell-minute k (0..120), chosen in-sample, beats v1.1 by more than 1 point in leave-one-out.
 H18  Fragility: the cross-deal spread (std) of one-minute changes in exit value is larger for k = 0..4
      than for k = 15..30, by at least 2x.
 H19  Grace whipsaw: in at most 4 of 27 deals did v1.1 sell inside the 15-minute grace period while the
      day high came later and ended >= 10% above the exit price (the CAVA pattern).
"""
import numpy as np
import pandas as pd
from engine import ExitEngine, Rule

ET = "America/New_York"
OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "FIG": 33, "CRCL": 31, "CRWV": 40, "RDDT": 34,
         "RIVN": 78, "ABNB": 68, "DASH": 102, "SNOW": 120, "UBER": 45, "LYFT": 72, "ZM": 36,
         "PINS": 19, "CAVA": 22, "KVYO": 30, "BIRK": 46, "CHYM": 27, "KLAR": 40}
DL = {"SPOT": 132.0, "WORK": 26.0, "PLTR": 7.25, "ASAN": 21.0, "RBLX": 45.0, "COIN": 250.0}
K = 121
T19 = pd.read_csv("out/19_quick_vs_trail.csv", index_col=0)


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
syms = list(D)

# exit value (% of offer) if sold at the close of minute k after the first bar
M = pd.DataFrame({s: [(df["close"].iloc[min(k, len(df) - 1)] / off - 1) * 100 for k in range(K)]
                  for s, (off, df) in D.items()})
v11 = T19.loc[syms, "v11"]
w = T19.loc[syms, "w"].to_numpy()

print("=" * 90)
print("21  SELL AT A FIXED MINUTE k vs RULE v1.1   (% of offer; 27 deals)")
print("=" * 90)
print(" k(min)   mean   wmean  median   v11-mean  v11 better")
for k in [0, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120]:
    x = M.loc[k]
    print(f"  {k:4d}  {x.mean():6.1f}  {np.average(x, weights=w):6.1f}  {x.median():6.1f}   "
          f"{(v11 - x).mean():+6.2f}   {int((v11 > x).sum()):2d}/27")
print(f"  v11   {v11.mean():6.1f}  {np.average(v11, weights=w):6.1f}  {v11.median():6.1f}")
kbest = int(M.mean(axis=1).idxmax())
print(f"In-sample best fixed minute: k = {kbest} (mean {M.loc[kbest].mean():.1f}); this is fitted, see LOO below")

print("\n--- H17  LEAVE-ONE-OUT: pick the best minute on 26 deals, apply to the 27th ---")
loo, picks = [], []
for j in syms:
    tr = M.drop(columns=j)
    k = int(tr.mean(axis=1).idxmax())
    picks.append(k)
    loo.append(M.loc[k, j])
loo = np.array(loo)
d = loo - v11.to_numpy()
print(f"LOO fixed-minute mean {loo.mean():.2f} vs v11 {v11.mean():.2f} | gain {d.mean():+.2f} | "
      f"better {int((d > 0).sum())} / worse {int((d < 0).sum())} | minutes picked: {sorted(set(picks))}")
print(f"H17 -> {'PASS' if d.mean() <= 1.0 else 'FAIL'} (no fixed minute beats v1.1 by > 1 point out of sample)")

print("\n--- H18  FRAGILITY OF A FIXED SALE TIME ---")
step = M.diff().iloc[1:]                       # change in exit value from waiting one more minute
early = step.loc[1:4].stack().std()
late = step.loc[15:30].stack().std()
print(f"Std of one-minute change across deals: minutes 1-4 {early:.2f} pts | minutes 15-30 {late:.2f} pts | ratio {early/late:.1f}x")
for k in range(1, 6):
    print(f"  minute {k-1}->{k}: mean {step.loc[k].mean():+5.2f}, std {step.loc[k].std():5.2f}, "
          f"largest |move| {step.loc[k].abs().max():5.1f} ({step.loc[k].abs().idxmax()})")
print(f"H18 -> {'PASS' if early >= 2 * late else 'FAIL'}")

print("\n--- H19  GRACE-PERIOD WHIPSAW (v1.1 sold in minutes < 15, later high >= 10% above exit) ---")
n_ws = 0
for s in syms:
    off, df = D[s]
    em = int(T19.loc[s, "exit_min"])
    ex_px = off * (1 + T19.loc[s, "v11"] / 100)
    if em < 15 and em + 1 < len(df):
        later_hi = df["high"].iloc[em + 1:].max()
        if later_hi >= ex_px * 1.10:
            n_ws += 1
            print(f"  {s:5s} sold min {em:2d} at {T19.loc[s,'v11']:+6.1f}%, later high {(later_hi/off-1)*100:+6.1f}% "
                  f"(+{(later_hi/ex_px-1)*100:.0f}% above exit), hold to 15:30 {T19.loc[s,'hold']:+6.1f}%")
print(f"H19 -> {'PASS' if n_ws <= 4 else 'FAIL'} ({n_ws} of 27 deals)")
M.to_csv("out/21_exit_by_minute.csv")
print("\nSaved out/21_exit_by_minute.csv.")
