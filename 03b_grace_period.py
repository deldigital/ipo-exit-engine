"""
03b_grace_period.py  (no API; reuses simulate() from script 03)
Question from the SPCX replay: the 4% trail sold SpaceX 16 minutes in, during the opening chop.
Test a wider trail for the first G minutes, then 4%. Adopt ONLY if it beats the baseline on
weighted-bootstrap mean AND mega mean, without a worse 5th percentile.
Run: python 03b_grace_period.py
"""
import importlib.util
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)

SYMS, OFFER, W, MEGA = r3.SYMS, r3.OFFER, r3.W, r3.MEGA
data = {s: r3.load(s) for s in SYMS}
base = np.array([r3.hold(data[s], OFFER[s]) for s in SYMS])

rules = [("BASE k04 arm10 C2", (0.04, None, 0, 0.10, None, 2))]
for ke in [0.06, 0.08, 0.10]:
    for g in [15, 30, 60]:
        rules.append((f"k{int(ke*100):02d} first {g}m -> k04", (ke, 0.04, g, 0.10, None, 2)))

V = np.array([[r3.simulate(data[s], OFFER[s], *p) - b for s, b in zip(SYMS, base)] for _, p in rules])
names = [r[0] for r in rules]
pw = np.array([W[s] for s in SYMS]); pw = pw / pw.sum()
idx = np.random.default_rng(7).choice(len(SYMS), size=(r3.N_BOOT, len(SYMS)), p=pw)
boot = V[:, idx].mean(axis=2)
mi = [SYMS.index(s) for s in MEGA]
T = pd.DataFrame({"all": V.mean(1), "mega": V[:, mi].mean(1), "wb_mean": boot.mean(1),
                  "wb_p5": np.percentile(boot, 5, axis=1), "P_beat_hold": (boot > 0).mean(1),
                  "worst_ipo": V.min(1)}, index=names)
show = T.copy()
for c in ["all", "mega", "wb_mean", "wb_p5", "worst_ipo"]:
    show[c] = (show[c] * 100).round(2)
show["P_beat_hold"] = show["P_beat_hold"].round(2)
pd.set_option("display.width", 200)
print("=== Grace-period test (vs hold, pts) ===")
print(show.to_string())
print("\n=== Mega IPOs per rule (pts vs hold) ===")
print((pd.DataFrame(V[:, mi], index=names, columns=MEGA) * 100).round(1).to_string())
