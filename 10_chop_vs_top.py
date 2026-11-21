"""
10_chop_vs_top.py  (no API; uses data/*_d1.csv)
Can opening chop be told apart from a real top at the moment the floor breaks?
Two families, kept small on purpose (more candidates = more selection noise):
  VWAP : if the breach happens while price is still above the session VWAP (x(1+v)),
         treat it as chop and demand `extra` more confirming closes.
  BOCPD: Bayesian online changepoint detection (Adams & MacKay 2007, Normal-Gamma model) on
         1-min % returns. E[mu] = posterior expected drift of the current regime.
         DEFER: E[mu] >= 0 at the breach -> one extra close.  FAST: E[mu] < -0.10 %/min and a
         changepoint is likely in the last 5 min (P(run<5) > 0.5) -> sell on the first close.
Nested leave-one-out vs rule v1.1 (v1.1 is a candidate). Adopt only if OOS mean, weighted and
mega gains are all > 0.
Run: python 10_chop_vs_top.py
"""
import importlib.util
import math
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
SYMS, OFFER, W, MEGA = r3.SYMS, r3.OFFER, r3.W, r3.MEGA
from datetime import time
CUTOFF = time(15, 30)
lgamma = np.vectorize(math.lgamma)


def bocpd(x, hazard, mu0=0.0, k0=1.0, a0=1.0, b0=1.0):
    """x: 1-min returns in %. Returns E[mu] of current regime and P(run length < 5), per step."""
    R = np.array([1.0])
    mu, k, a, b = np.array([mu0]), np.array([k0]), np.array([a0]), np.array([b0])
    emu, prec = np.zeros(len(x)), np.zeros(len(x))
    H = 1.0 / hazard
    for t, xt in enumerate(x):
        df = 2 * a
        scale2 = b * (k + 1) / (a * k)
        z = (xt - mu) ** 2 / (df * scale2)
        logp = (lgamma((df + 1) / 2) - lgamma(df / 2) - 0.5 * np.log(np.pi * df * scale2)
                - (df + 1) / 2 * np.log1p(z))
        pred = np.exp(logp)
        growth = R * pred * (1 - H)
        cp = (R * pred * H).sum()
        R = np.concatenate([[cp], growth])
        R /= R.sum()
        mu_n = (k * mu + xt) / (k + 1)
        b_n = b + k * (xt - mu) ** 2 / (2 * (k + 1))
        mu = np.concatenate([[mu0], mu_n]); k = np.concatenate([[k0], k + 1])
        a = np.concatenate([[a0], a + 0.5]); b = np.concatenate([[b0], b_n])
        emu[t] = (R * mu).sum()
        prec[t] = R[:5].sum()
    return emu, prec


def features(df):
    c = df["close"].to_numpy(float)
    r = np.r_[0.0, np.diff(np.log(c)) * 100]
    cv = (df["vwap"] * df["volume"]).cumsum() / df["volume"].cumsum()
    f = {"vwap": cv.to_numpy(float)}
    for hz in [30, 60]:
        f[f"emu{hz}"], f[f"prec{hz}"] = bocpd(r, hz)
    return f


def sim(df, f, offer, fam=None, p=None, ke=0.08, kl=0.04, sw=15, arm=0.10, confirm=2):
    o, h, c = (df[x].to_numpy(float) for x in ["open", "high", "close"])
    times = df.index.time
    mins = (df.index - df.index[0]).total_seconds().to_numpy() / 60
    n, runmax, below, armed, pending = len(c), -np.inf, 0, False, None
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
        if below >= 1 and fam == "VWAP" and c[i] > f["vwap"][i] * (1 + p["v"]):
            need = confirm + p["extra"]
        if below >= 1 and fam == "BOCPD":
            em, pr = f[f"emu{p['hz']}"][i], f[f"prec{p['hz']}"][i]
            if p["mode"] == "DEFER" and em >= 0:
                need = confirm + 1
            if p["mode"] == "FAST" and em < -0.10 and pr > 0.5:
                need = 1
        if below >= need:
            pending = min(i + 1, n - 1)
    return c[-1] / offer - 1


data = {s: r3.load(s) for s in SYMS}
feat = {s: features(data[s]) for s in SYMS}
base = np.array([r3.hold(data[s], OFFER[s]) for s in SYMS])
chk = max(abs(sim(data[s], feat[s], OFFER[s]) - r3.simulate(data[s], OFFER[s], 0.08, 0.04, 15, 0.10, None, 2))
          for s in SYMS)
print(f"sanity |sim - research v1.1| max = {chk:.2e}")

cands = [("v1.1", None, None)]
for v in [0.0, 0.02]:
    for extra in [1, 2]:
        cands.append((f"VWAP v{int(v*100)} +{extra}", "VWAP", dict(v=v, extra=extra)))
for hz in [30, 60]:
    for mode in ["DEFER", "FAST"]:
        cands.append((f"BOCPD h{hz} {mode}", "BOCPD", dict(hz=hz, mode=mode)))
X = np.array([[sim(data[s], feat[s], OFFER[s], fam, p) for s in SYMS] for _, fam, p in cands])
V = X - base
names = [c[0] for c in cands]
wts = np.array([W[s] for s in SYMS])
mi = [SYMS.index(s) for s in MEGA]
pd.set_option("display.width", 200)
IS = pd.DataFrame({"all": V.mean(1) * 100, "mega": V[:, mi].mean(1) * 100,
                   "wmean": (V * wts).sum(1) / wts.sum() * 100,
                   "SPCX": V[:, SYMS.index("SPCX")] * 100,
                   "wins_vs_v11": [(V[j] > V[0] + 1e-9).sum() for j in range(len(cands))],
                   "losses_vs_v11": [(V[j] < V[0] - 1e-9).sum() for j in range(len(cands))]},
                  index=names).round(2)
print("\n=== In-sample (pts vs hold) ===")
print(IS.sort_values("wmean", ascending=False).to_string())

oos, picks = [], []
for i in range(len(SYMS)):
    m = np.ones(len(SYMS)); m[i] = 0
    j = int(np.argmax((V * wts * m).sum(1)))
    oos.append(V[j, i] - V[0, i]); picks.append(names[j])
oos = np.array(oos)
print("\n=== Nested LOO: selected minus v1.1, out of sample (pts) ===")
print(pd.DataFrame({"pick": picks, "gain": (oos * 100).round(2)}, index=SYMS).T.to_string())
print(f"mean {oos.mean()*100:.2f} | weighted {np.average(oos, weights=wts)*100:.2f} | "
      f"mega {oos[mi].mean()*100:.2f} | better {int((oos > 1e-9).sum())} worse {int((oos < -1e-9).sum())}")
print("Adopt only if OOS mean, weighted AND mega are all > 0.")
