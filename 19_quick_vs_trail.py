"""
19_quick_vs_trail.py  (no API; needs data/*_d1.csv, data/*_dl.csv, out/18_sip_bars.csv)
Follows from 18 (H5): on ANT, selling at the first obtainable quote beat rule v1.1. Is that general,
and can the "sell at once" days be recognised at or before the open?
Run: python 19_quick_vs_trail.py

PRE-REGISTERED (written 21:45 UK, 19 Nov, before running)
 H9   Across 27 deals (20 IPOs, 6 direct listings, ANT) rule v1.1 beats "sell at +2 min" on the mean.
      Prior: 13/20 IPOs beat the open in the 02:05 check.
 H10  The rule's edge over quick selling shrinks as the opening premium grows (hot opens fade):
      Spearman rho(edge, open premium) < 0.
 H11  A weak first minute predicts quick selling wins: rho(edge, first-minute return) > 0.
 H12  A two-regime policy (sell at +2 min when a predictor crosses a threshold chosen in-sample,
      else v1.1) beats v1.1 by > 1 point in leave-one-out. Expected: FAIL (n = 27, overfitting risk).
 All returns are % of offer (reference price for direct listings). Rule frozen; nothing here changes it.
"""
from math import comb
import numpy as np
import pandas as pd
from engine import ExitEngine, Rule

ET = "America/New_York"
OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "FIG": 33, "CRCL": 31, "CRWV": 40, "RDDT": 34,
         "RIVN": 78, "ABNB": 68, "DASH": 102, "SNOW": 120, "UBER": 45, "LYFT": 72, "ZM": 36,
         "PINS": 19, "CAVA": 22, "KVYO": 30, "BIRK": 46, "CHYM": 27, "KLAR": 40}
DL = {"SPOT": 132.0, "WORK": 26.0, "PLTR": 7.25, "ASAN": 21.0, "RBLX": 45.0, "COIN": 250.0}
MEGA = ["SPCX", "ARM", "RIVN", "UBER", "CRWV"]
MODEST = ["LYFT", "PINS", "KVYO", "BIRK", "KLAR", "RDDT"]
CUT = pd.Timestamp("15:30").time()


def weight(s, kind):
    if s == "ANT":
        return 3.0
    if kind == "DL":
        return 2.0
    return 3.0 if s in MEGA else 2.0 if s in MODEST else 1.0


def load_csv(path, rename=None):
    df = pd.read_csv(path, index_col=0)
    if rename:
        df = df.rename(columns=rename)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df[["open", "high", "low", "close"]].astype(float)


def deals():
    out = []
    for s, off in OFFER.items():
        out.append((s, "IPO", off, load_csv(f"data/{s}_d1.csv")))
    for s, ref in DL.items():
        try:
            out.append((s, "DL", ref, load_csv(f"data/{s}_dl.csv")))
        except FileNotFoundError:
            print(f"[skip] {s}: data/{s}_dl.csv missing (run 14 first)")
    ant = load_csv("out/18_sip_bars.csv", {"o": "open", "h": "high", "l": "low", "c": "close"})
    out.append(("ANT", "IPO", 83.0, ant))
    return out


def rule_exit(df, off):
    eng = ExitEngine(off, Rule())
    for ts, r in df.iterrows():
        eng.on_bar(ts, r["open"], r["high"], r["low"], r["close"])
        if eng.signal:
            break
    s = eng.signal
    if s is None:
        return df["close"].iloc[-1], df["close"].iloc[-1], "eod", len(df) - 1
    i = df.index.get_loc(s["ts"] - pd.Timedelta(seconds=60))
    nxt = df["open"].iloc[i + 1] if i + 1 < len(df) else s["price"]
    return s["price"], nxt, s["reason"].split()[0], i


def sign_p(w, n):
    k = min(w, n - w)
    return min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2 ** n)


rows = []
for s, kind, off, df in deals():
    df = df[[t.time() < pd.Timestamp("16:00").time() for t in df.index]]
    pre = df[[t.time() <= CUT for t in df.index]]
    hold = pre["close"].iloc[-1]
    v_close, v_next, why, i_sig = rule_exit(df, off)
    o0 = df["open"].iloc[0]
    rows.append(dict(
        sym=s, kind=kind, w=weight(s, kind),
        open_prem=(o0 / off - 1) * 100,
        r1=(df["close"].iloc[0] / o0 - 1) * 100,                 # first-minute return (known at +1 min)
        rng1=((df["high"].iloc[0] - df["low"].iloc[0]) / o0) * 100,
        peak_min=float(np.argmax(df["high"].to_numpy())),
        high=(df["high"].max() / off - 1) * 100,
        hold=(hold / off - 1) * 100,
        q1=(df["close"].iloc[1] / off - 1) * 100,
        q2=(df["close"].iloc[2] / off - 1) * 100,
        q3=(df["close"].iloc[3] / off - 1) * 100,
        v11=(v_close / off - 1) * 100,
        v11_lag=(v_next / off - 1) * 100,
        exit_min=i_sig, why=why))
T = pd.DataFrame(rows).set_index("sym")
T["edge_q2"] = T["v11"] - T["q2"]
T["edge_q1"] = T["v11"] - T["q1"]
T["edge_hold"] = T["v11"] - T["hold"]
T.to_csv("out/19_quick_vs_trail.csv")

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
print("=" * 100)
print("19  QUICK SALE vs RULE v1.1   (all figures = % of offer / reference; edge = v11 minus alternative, points)")
print("=" * 100)
print(T[["kind", "open_prem", "r1", "rng1", "peak_min", "high", "q1", "q2", "q3", "v11", "v11_lag", "hold",
         "edge_q1", "edge_q2", "edge_hold", "exit_min", "why"]].round(1).to_string())


def summary(col, sub, label):
    x, w = sub[col], sub["w"]
    wins = int((x > 0).sum()); n = int((x != 0).sum())
    print(f"  {label:26s} mean {x.mean():+6.2f} | weighted {np.average(x, weights=w):+6.2f} | median {x.median():+6.2f}"
          f" | v11 better {wins}/{len(x)} | sign p {sign_p(wins, n):.2f}")


print("\n--- H9  RULE v1.1 minus alternative (points of offer) ---")
for grp, sub in [("ALL 27", T), ("IPOs 21", T[T.kind == "IPO"]), ("Direct listings", T[T.kind == "DL"]),
                 ("Mega + ANT", T.loc[[s for s in MEGA + ["ANT"] if s in T.index]])]:
    print(f"{grp}:")
    summary("edge_q1", sub, "vs sell at +1 min")
    summary("edge_q2", sub, "vs sell at +2 min")
    summary("edge_hold", sub, "vs hold to 15:30 ET")
h9 = T["edge_q2"].mean() > 0
print(f"H9 -> {'PASS' if h9 else 'FAIL'} (mean edge vs +2 min {T['edge_q2'].mean():+.2f})")
print(f"Execution lag check: v11 at next-minute open instead of signal close changes mean by "
      f"{(T['v11_lag'] - T['v11']).mean():+.2f} points")

print("\n--- H10 / H11  WHAT PREDICTS THE EDGE? (Spearman rank correlation with edge vs +2 min) ---")
preds = ["open_prem", "r1", "rng1"]
for p in preds:
    rho = T[["edge_q2", p]].rank().corr().iloc[0, 1]
    print(f"  rho(edge_q2, {p:9s}) = {rho:+.2f}")
rho10 = T[["edge_q2", "open_prem"]].rank().corr().iloc[0, 1]
rho11 = T[["edge_q2", "r1"]].rank().corr().iloc[0, 1]
print(f"H10 -> {'PASS' if rho10 < 0 else 'FAIL'} | H11 -> {'PASS' if rho11 > 0 else 'FAIL'}"
      "   (|rho| < 0.38 is not significant at 5% with n = 27)")
print("  For reference, rho(edge_q2, peak_min) = "
      f"{T[['edge_q2', 'peak_min']].rank().corr().iloc[0, 1]:+.2f} (peak timing is NOT known in advance)")

print("\n--- H12  TWO-REGIME POLICY, LEAVE-ONE-OUT ---")


def policy_payoff(sub, p, thr, direction):
    quick = (sub[p] >= thr) if direction == "high" else (sub[p] <= thr)
    return np.where(quick, sub["q2"], sub["v11"])


for p, direction in [("open_prem", "high"), ("r1", "low"), ("rng1", "high")]:
    loo = []
    for j in T.index:
        tr = T.drop(j)
        cands = sorted(set(tr[p].round(2))) + [np.inf if direction == "high" else -np.inf]
        best = max(cands, key=lambda t: policy_payoff(tr, p, t, direction).mean())
        loo.append(float(policy_payoff(T.loc[[j]], p, best, direction)[0]))
    loo = np.array(loo)
    d = loo - T["v11"].to_numpy()
    print(f"  quick-sell when {p} is {direction:4s}: LOO mean {loo.mean():+6.2f} vs v11 {T['v11'].mean():+6.2f} "
          f"vs always +2 min {T['q2'].mean():+6.2f} | gain over v11 {d.mean():+.2f}, better {int((d > 0).sum())} / worse {int((d < 0).sum())}")
print("H12 -> PASS only if a gain over v11 is > +1.00 AND better > worse. Otherwise v1.1 stays.")
print("\nSaved out/19_quick_vs_trail.csv.")
