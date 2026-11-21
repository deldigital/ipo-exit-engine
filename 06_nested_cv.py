"""
06_nested_cv.py  (no API; uses data/*_d1.csv)
Does the whole rule-selection procedure beat holding out of sample?
For each IPO i: hide it, pick the best rule on the other 19 (ANT-weighted, same criterion we used),
then score that rule on IPO i. Repeat for all 20. Objective = exit price (higher exit = more of the
day's peak captured; peak is fixed per IPO, so maximising exit == maximising capture).
Run: python 06_nested_cv.py
"""
import importlib.util
import itertools
from collections import Counter
from math import comb
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
SYMS, OFFER, W, MEGA = r3.SYMS, r3.OFFER, r3.W, r3.MEGA

# ---- candidate rule space (180 rules) ----
rules = []
for k, grace, arm, cf in itertools.product(
        [0.04, 0.05, 0.06, 0.08, 0.10],
        [None, (0.08, 15), (0.08, 30), (0.10, 15)],
        [None, 0.10, 0.20],
        [1, 2, 3]):
    if grace is None:
        p = (k, None, 0, arm, None, cf)
        g = ""
    else:
        if grace[0] <= k:
            continue                       # grace trail must be wider than base trail
        p = (grace[0], k, grace[1], arm, None, cf)
        g = f" g{int(grace[0]*100)}/{grace[1]}m"
    rules.append((f"k{int(k*100):02d}{g}" + (f" arm{int(arm*100)}" if arm else "") + f" C{cf}", p))

data = {s: r3.load(s) for s in SYMS}
base = np.array([r3.hold(data[s], OFFER[s]) for s in SYMS])
peak = np.array([data[s]["high"].max() / OFFER[s] - 1 for s in SYMS])
X = np.array([[r3.simulate(data[s], OFFER[s], *p) for s in SYMS] for _, p in rules])  # exit returns
V = X - base                                                                          # vs hold
names = [r[0] for r in rules]
w = np.array([W[s] for s in SYMS])
print(f"rules: {len(rules)}   IPOs: {len(SYMS)}")


def select(mask, how):
    ww = w * mask
    if how == "wmean":
        score = (V * ww).sum(1) / ww.sum()
    else:  # wmedian-like robust: weighted mean of the middle 80% (trim 10% each side per rule)
        score = np.array([np.average(np.clip(v[mask > 0], *np.percentile(v[mask > 0], [10, 90])),
                                     weights=w[mask > 0]) for v in V])
    return int(np.argmax(score))


rows = []
for how in ["wmean", "trimmed"]:
    for i, s in enumerate(SYMS):
        mask = np.ones(len(SYMS)); mask[i] = 0
        j = select(mask, how)
        rows.append(dict(proc=how, sym=s, chosen=names[j], oos_vs_hold=V[j, i], exit=X[j, i],
                         hold=base[i], peak=peak[i], capture=X[j, i] / peak[i] if peak[i] > 0 else np.nan))
R = pd.DataFrame(rows)


def sign_p(v):
    pos, neg = int((v > 1e-9).sum()), int((v < -1e-9).sum())
    n = pos + neg
    return pos, neg, (sum(comb(n, k) for k in range(pos, n + 1)) / 2 ** n if n else np.nan)


pd.set_option("display.width", 220)
for how in ["wmean", "trimmed"]:
    sub = R[R.proc == how].set_index("sym")
    v = sub["oos_vs_hold"].to_numpy()
    pos, neg, p = sign_p(v)
    wm = np.average(v, weights=w)
    print(f"\n=== Nested LOO, selection = {how} (out-of-sample, pts vs hold) ===")
    show = sub[["chosen", "oos_vs_hold", "exit", "hold", "peak", "capture"]].copy()
    for c in ["oos_vs_hold", "exit", "hold", "peak"]:
        show[c] = (show[c] * 100).round(1)
    show["capture"] = show["capture"].round(2)
    print(show.to_string())
    print(f"OOS mean {v.mean()*100:.2f} | ANT-weighted {wm*100:.2f} | mega {sub.loc[MEGA,'oos_vs_hold'].mean()*100:.2f}"
          f" | wins {pos} losses {neg} ties {len(v)-pos-neg} | one-sided sign-test p = {p:.3f}")
    print("Mean capture (exit/peak): rule", round(sub["capture"].mean(), 3),
          " hold", round(np.nanmean(base / np.where(peak > 0, peak, np.nan)), 3))
    print("Chosen-rule frequency:", Counter(sub["chosen"]).most_common(5))

print("\n=== Reference ===")
print(f"Average of ALL 180 rules (no selection): {V.mean()*100:.2f} pts | in-sample best: {V.mean(1).max()*100:.2f}")
v11 = names.index("k04 g8/15m arm10 C2")
print(f"Rule v1.1 in-sample: {V[v11].mean()*100:.2f} pts (biased: chosen on the same data)")
R.to_csv("out/nested_cv_06.csv", index=False)
