"""
09_market_context.py  (no API; uses data/*_d1.csv + data/QQQ_ipo_days.csv)
Does market context help tell a temporary dip from a real top?
At each floor breach compute the IPO's idiosyncratic move over the last w minutes:
    idio = IPO return - beta * QQQ return
Variant DEFER: if idio > -thr (the dip is mostly the market), demand one extra confirming close.
Variant FAST : if idio < -thr (ANT-specific selling), sell on the first close (no confirmation wait).
Every variant is compared with rule v1.1 in nested leave-one-out CV; v1.1 is itself a candidate,
so context is adopted only if it wins OUT OF SAMPLE.
Run: python 09_market_context.py
"""
import importlib.util
import itertools
from datetime import time
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
SYMS, OFFER, W, MEGA, ET = r3.SYMS, r3.OFFER, r3.W, r3.MEGA, r3.ET
CUTOFF = time(15, 30)

Q = pd.read_csv("data/QQQ_ipo_days.csv", index_col=0)
Q.index = pd.to_datetime(Q.index, utc=True).tz_convert(ET)


def sim(df, q, offer, mode=None, beta=1.5, w=5, thr=0.01,
        ke=0.08, kl=0.04, sw=15, arm=0.10, confirm=2):
    o, h, c = (df[x].to_numpy(float) for x in ["open", "high", "close"])
    qc = q.reindex(df.index).ffill().bfill()["close"].to_numpy(float)
    times = df.index.time
    mins = (df.index - df.index[0]).total_seconds().to_numpy() / 60
    n = len(c)
    pos, cash, runmax, below = 1.0, 0.0, -np.inf, 0
    armed, pending = False, None
    for i in range(n):
        if pending is not None and i == pending:
            return o[i] / offer - 1
        if times[i] >= CUTOFF:
            return c[i] / offer - 1
        runmax = max(runmax, h[i])
        if not armed and h[i] >= offer * (1 + arm):
            armed = True
        k = ke if mins[i] < sw else kl
        below = below + 1 if (armed and c[i] < runmax * (1 - k)) else 0
        need = confirm
        if below >= 1 and mode is not None and i >= w:
            idio = (c[i] / c[i - w] - 1) - beta * (qc[i] / qc[i - w] - 1)
            if mode == "DEFER" and idio > -thr:
                need = confirm + 1
            if mode == "FAST" and idio < -thr:
                need = 1
        if below >= need:
            pending = min(i + 1, n - 1)
    return c[-1] / offer - 1


data = {s: r3.load(s) for s in SYMS}
qd = {s: Q[Q["ipo"] == s][["close"]] for s in SYMS}
base = np.array([r3.hold(data[s], OFFER[s]) for s in SYMS])

# sanity: mode=None must equal research v1.1
chk = max(abs(sim(data[s], qd[s], OFFER[s]) - r3.simulate(data[s], OFFER[s], 0.08, 0.04, 15, 0.10, None, 2))
          for s in SYMS)
print(f"sanity |sim - research v1.1| max = {chk:.2e}")

cands = [("v1.1", dict())]
for mode, beta, w, thr in itertools.product(["DEFER", "FAST"], [1.0, 2.0], [5, 15], [0.01, 0.02]):
    cands.append((f"{mode} b{beta:g} w{w} t{int(thr*100)}", dict(mode=mode, beta=beta, w=w, thr=thr)))
X = np.array([[sim(data[s], qd[s], OFFER[s], **kw) for s in SYMS] for _, kw in cands])
V = X - base
names = [c[0] for c in cands]
wts = np.array([W[s] for s in SYMS])
mi = [SYMS.index(s) for s in MEGA]

IS = pd.DataFrame({"all": V.mean(1) * 100, "mega": V[:, mi].mean(1) * 100,
                   "wmean": (V * wts).sum(1) / wts.sum() * 100,
                   "vs_v11_wins": [(V[j] > V[0] + 1e-9).sum() for j in range(len(cands))],
                   "vs_v11_losses": [(V[j] < V[0] - 1e-9).sum() for j in range(len(cands))]},
                  index=names).round(2)
pd.set_option("display.width", 200)
print("\n=== In-sample (pts vs hold); wins/losses = IPOs where variant beats / trails v1.1 ===")
print(IS.sort_values("wmean", ascending=False).to_string())

oos, picks = [], []
for i in range(len(SYMS)):
    m = np.ones(len(SYMS)); m[i] = 0
    j = int(np.argmax((V * wts * m).sum(1)))
    oos.append(V[j, i] - V[0, i]); picks.append(names[j])
oos = np.array(oos)
print("\n=== Nested LOO: selected variant minus v1.1, out of sample (pts) ===")
print(pd.DataFrame({"pick": picks, "oos_gain_vs_v11": (oos * 100).round(2)}, index=SYMS).to_string())
print(f"mean {oos.mean()*100:.2f} | weighted {np.average(oos, weights=wts)*100:.2f} | "
      f"mega {oos[mi].mean()*100:.2f} | better {int((oos > 1e-9).sum())} worse {int((oos < -1e-9).sum())}")
print("Adopt context only if OOS mean, weighted AND mega are all > 0.")
