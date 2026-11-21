"""
16_untested_ideas.py  (no API; uses data/*_d1.csv and data/*_dl.csv)
Every remaining candidate idea not yet tested, against FROZEN rule v1.1, with the adoption test fixed now:
  ADOPT only if  (1) nested-LOO gain vs v1.1 > 0 on mean and mega deals, ANT-weighted mean >= +0.5 pts
                     (9 ideas tested at once: a smaller gain is indistinguishable from luck), and
                 (2) on the 6 direct listings (never used in any selection = true holdout) mean gain >= 0.
Candidates
  STAIR      : SELL when 2 of the last 3 closes are below the floor (staircase decline)
  TAPER_10_20: trail narrows linearly 8% -> 4% between min 10 and 20 (no minute-15 cliff)
  TAPER_5_25 : same, between min 5 and 25
  DEEP3/DEEP5: immediate SELL on ONE close >= 3% / 5% below the floor (flash crash)
  LEARN p/hl : Ekstrom-Vaicenavicius-style learning overlay: Bayesian posterior on per-minute drift
               (prior N(0, 0.5%^2), exponential forgetting half-life hl); also SELL when
               P(drift < 0) > p on 2 consecutive bars and price is >2% off the high.
Benchmark: sell at the first obtainable quote, ~2 minutes after the first trade.
Run: python 16_untested_ideas.py
"""
import importlib.util
from math import comb, erf, sqrt
from datetime import time
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
SYMS, OFFER, W, MEGA, ET = r3.SYMS, r3.OFFER, r3.W, r3.MEGA, r3.ET
CUTOFF = time(15, 30)
DL = {"SPOT": 132.0, "WORK": 26.0, "PLTR": 7.25, "ASAN": 21.0, "RBLX": 45.0, "COIN": 250.0}
TAU = 0.005


def kfun(kind, m):
    if kind == "TAPER_10_20":
        a, b = 10, 20
    elif kind == "TAPER_5_25":
        a, b = 5, 25
    else:
        return 0.08 if m < 15 else 0.04
    if m < a:
        return 0.08
    if m >= b:
        return 0.04
    return 0.08 - 0.04 * (m - a) / (b - a)


def sim(df, offer, cand):
    kind = cand["kind"]
    o, h, c = (df[x].to_numpy(float) for x in ["open", "high", "close"])
    times = df.index.time
    mins = (df.index - df.index[0]).total_seconds().to_numpy() / 60
    n = len(c)
    runmax, armed, below, hist, pending, ev_cnt = -np.inf, False, 0, [], None, 0
    lam = 0.5 ** (1 / cand.get("hl", 10))
    S = Wt = V = 0.0
    for i in range(n):
        if pending is not None and i == pending:
            return o[i] / offer - 1
        if times[i] >= CUTOFF:
            return c[i] / offer - 1
        runmax = max(runmax, h[i])
        if not armed and h[i] >= offer * 1.10:
            armed = True
        fl = runmax * (1 - kfun(kind, mins[i]))
        b = armed and c[i] < fl
        below = below + 1 if b else 0
        hist.append(b)
        if kind == "STAIR":
            sell = b and sum(hist[-3:]) >= 2
        else:
            sell = below >= 2
        if kind.startswith("DEEP") and armed and c[i] < fl * (1 - cand["d"]):
            sell = True
        if kind == "LEARN" and i > 0:
            r = np.log(c[i] / c[i - 1])
            S, Wt, V = lam * S + r, lam * Wt + 1, lam * V + r * r
            if Wt >= 5:
                s2 = max(V / Wt - (S / Wt) ** 2, 1e-8)
                pv = 1 / (1 / TAU ** 2 + Wt / s2)
                pm = pv * S / s2
                pneg = 0.5 * (1 + erf((0 - pm) / sqrt(2 * pv)))
                ev_cnt = ev_cnt + 1 if pneg > cand["p"] else 0
                if armed and ev_cnt >= 2 and c[i] < runmax * 0.98:
                    sell = True
        if sell and pending is None:
            pending = min(i + 1, n - 1)
    return c[-1] / offer - 1


def load_dl(s):
    df = pd.read_csv(f"data/{s}_dl.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


cands = [("v1.1", dict(kind="BASE")), ("STAIR", dict(kind="STAIR")),
         ("TAPER_10_20", dict(kind="TAPER_10_20")), ("TAPER_5_25", dict(kind="TAPER_5_25")),
         ("DEEP3", dict(kind="DEEP3", d=0.03)), ("DEEP5", dict(kind="DEEP5", d=0.05))]
for p in [0.8, 0.9]:
    for hl in [10, 30]:
        cands.append((f"LEARN p{p} hl{hl}", dict(kind="LEARN", p=p, hl=hl)))

data = {s: r3.load(s) for s in SYMS}
dld = {s: load_dl(s) for s in DL}
base = np.array([r3.hold(data[s], OFFER[s]) for s in SYMS])
chk = max(abs(sim(data[s], OFFER[s], dict(kind="BASE")) -
              r3.simulate(data[s], OFFER[s], 0.08, 0.04, 15, 0.10, None, 2)) for s in SYMS)
print(f"sanity |sim v1.1 - research v1.1| max = {chk:.2e}")

X = np.array([[sim(data[s], OFFER[s], cd) for s in SYMS] for _, cd in cands])
XD = np.array([[sim(dld[s], DL[s], cd) for s in DL] for _, cd in cands])
V = X - base
names = [c[0] for c in cands]
wts = np.array([W[s] for s in SYMS])
mi = [SYMS.index(s) for s in MEGA]

# nested LOO: selection among {v1.1, candidate j} only, so each idea is judged on its own
rows = []
for j in range(1, len(cands)):
    g = []
    for i in range(len(SYMS)):
        m = np.ones(len(SYMS)); m[i] = 0
        pick = j if (V[j] * wts * m).sum() > (V[0] * wts * m).sum() else 0
        g.append(V[pick, i] - V[0, i])
    g = np.array(g)
    dlg = (XD[j] - XD[0]) * 100
    ok = (g.mean() > 0 and np.average(g, weights=wts) >= 0.005 and g[mi].mean() > 0 and dlg.mean() >= 0)
    rows.append(dict(idea=names[j],
                     IS_all=(V[j] - V[0]).mean() * 100, IS_mega=(V[j] - V[0])[mi].mean() * 100,
                     IS_SPCX=(V[j] - V[0])[SYMS.index("SPCX")] * 100,
                     OOS_mean=g.mean() * 100, OOS_w=np.average(g, weights=wts) * 100,
                     OOS_mega=g[mi].mean() * 100, DL_mean=dlg.mean(),
                     DL_better=int((dlg > 1e-9).sum()), DL_worse=int((dlg < -1e-9).sum()),
                     VERDICT="ADOPT" if ok else "reject"))
pd.set_option("display.width", 220)
print("\n=== Each idea vs FROZEN v1.1 (pts; IS = in-sample, OOS = nested LOO, DL = direct-listing holdout) ===")
print(pd.DataFrame(rows).set_index("idea").round(2).to_string())

print("\n=== Direct-listing holdout, exit % vs reference price ===")
print(pd.DataFrame(XD * 100, index=names, columns=list(DL)).round(1).to_string())

o2 = np.array([data[s]["open"].iloc[min(2, len(data[s]) - 1)] / OFFER[s] - 1 for s in SYMS])
d = (X[0] - o2) * 100
pos, neg = int((d > 1e-9).sum()), int((d < -1e-9).sum())
p = sum(comb(pos + neg, k) for k in range(pos, pos + neg + 1)) / 2 ** (pos + neg)
print(f"\nBenchmark: v1.1 minus 'sell at first obtainable quote (~2 min after first trade)':"
      f" mean {d.mean():+.2f} pts | mega {d[mi].mean():+.2f} | better {pos} worse {neg} | sign-test p = {p:.3f}")
print(pd.Series(d.round(1), index=SYMS).to_string())
