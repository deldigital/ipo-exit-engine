"""
03_confirm_bootstrap.py  (no API; uses data/*_d1.csv)
Questions: separating decision lag (confirmation) from execution lag, robustness via a weighted
bootstrap, and selling half at +25%.
Run: python 03_confirm_bootstrap.py
"""
import itertools
from datetime import time
import numpy as np
import pandas as pd

ET = "America/New_York"
CUTOFF = time(15, 30)
OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "FIG": 33, "CRCL": 31, "CRWV": 40, "RDDT": 34,
         "RIVN": 78, "ABNB": 68, "DASH": 102, "SNOW": 120, "UBER": 45, "LYFT": 72, "ZM": 36,
         "PINS": 19, "CAVA": 22, "KVYO": 30, "BIRK": 46, "CHYM": 27, "KLAR": 40}
MEGA = ["SPCX", "ARM", "RIVN", "UBER", "CRWV"]
MODEST = ["LYFT", "PINS", "KVYO", "BIRK", "KLAR", "RDDT"]
# bootstrap weights: closeness to ANT (huge deal, modest expected pop)
W = {s: 3.0 if s in MEGA else 2.0 if s in MODEST else 1.0 for s in OFFER}
SYMS = list(OFFER)
EXEC_LAT = 1      # minutes from decision to AJ Bell fill
N_BOOT = 5000
rng = np.random.default_rng(7)


def load(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


def hold(df, offer):
    return df[df.index.time <= CUTOFF]["close"].iloc[-1] / offer - 1


def simulate(df, offer, ke, kl, sw, arm, half_t, confirm):
    o, h, c = (df[x].to_numpy(float) for x in ["open", "high", "close"])
    times = df.index.time
    mins = (df.index - df.index[0]).total_seconds().to_numpy() / 60
    n = len(c)
    pos, cash, runmax, below = 1.0, 0.0, -np.inf, 0
    armed = arm is None
    half_done = half_t is None
    pending = None
    for i in range(n):
        if pending is not None and i == pending[0]:
            frac = min(pending[1], pos)
            cash += frac * o[i]
            pos -= frac
            pending = None
            if pos <= 1e-9:
                break
        if times[i] >= CUTOFF:
            cash += pos * c[i]
            pos = 0.0
            break
        runmax = max(runmax, h[i])
        if not armed and h[i] >= offer * (1 + arm):
            armed = True
        k = ke if (kl is None or mins[i] < sw) else kl
        below = below + 1 if (armed and c[i] < runmax * (1 - k)) else 0
        if pending is not None:
            continue
        j = min(i + EXEC_LAT, n - 1)
        if below >= confirm:
            pending = (j, pos)
        elif not half_done and h[i] >= offer * (1 + half_t):
            pending = (j, 0.5)
            half_done = True
    if pos > 0:
        cash += pos * c[-1]
    return cash / offer - 1


def main():
    data = {s: load(s) for s in SYMS}
    base = np.array([hold(data[s], OFFER[s]) for s in SYMS])
    rules = []
    for k, arm, half_t, cf in itertools.product([0.04, 0.05, 0.06, 0.08], [None, 0.10],
                                                [None, 0.25], [1, 2, 3]):
        rules.append((f"k{int(k*100):02d}" + (" arm10" if arm else "") + (" half25" if half_t else "")
                      + f" C{cf}", (k, None, 0, arm, half_t, cf)))
    for half_t, cf in itertools.product([None, 0.25], [1, 2, 3]):
        rules.append(("k10>5@60" + (" half25" if half_t else "") + f" C{cf}",
                      (0.10, 0.05, 60, None, half_t, cf)))

    V = np.array([[simulate(data[s], OFFER[s], *p) - b for s, b in zip(SYMS, base)]
                  for _, p in rules])
    names = [r[0] for r in rules]
    pw = np.array([W[s] for s in SYMS])
    pw = pw / pw.sum()
    idx = rng.choice(len(SYMS), size=(N_BOOT, len(SYMS)), p=pw)
    boot = V[:, idx].mean(axis=2)                      # rules x N_BOOT

    mega_i = [SYMS.index(s) for s in MEGA]
    T = pd.DataFrame({
        "all": V.mean(axis=1), "mega": V[:, mega_i].mean(axis=1),
        "wb_mean": boot.mean(axis=1), "wb_p5": np.percentile(boot, 5, axis=1),
        "P_beat_hold": (boot > 0).mean(axis=1), "worst_ipo": V.min(axis=1),
    }, index=names)
    pd.set_option("display.width", 200)
    show = T.copy()
    for c in ["all", "mega", "wb_mean", "wb_p5", "worst_ipo"]:
        show[c] = (show[c] * 100).round(2)
    show["P_beat_hold"] = show["P_beat_hold"].round(2)
    print("=== vs hold-to-15:30, percentage points; wb = ANT-weighted bootstrap ===")
    print(show.sort_values("wb_mean", ascending=False).head(15).to_string())

    print("\n=== Confirmation effect (mean vs hold, pts, averaged over rules) ===")
    cf = pd.Series(V.mean(axis=1), index=names)
    for c in ["C1", "C2", "C3"]:
        print(c, round(cf[[n.endswith(c) for n in names]].mean() * 100, 2))
    print("\n=== Arming / half effects (pts) ===")
    for tag in [" arm10", " half25"]:
        w_ = cf[[tag in n for n in names]].mean()
        wo = cf[[tag not in n for n in names]].mean()
        print(tag.strip(), "with", round(w_ * 100, 2), "without", round(wo * 100, 2))

    best = show.sort_values("wb_mean", ascending=False).index[:3]
    print("\n=== Per-IPO vs hold for top 3 rules (pts) ===")
    print((pd.DataFrame(V, index=names, columns=SYMS).loc[best].T * 100).round(1).to_string())
    T.to_csv("out/rules_03.csv")
    print("Saved out/rules_03.csv")


if __name__ == "__main__":
    main()
