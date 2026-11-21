"""
02_rule_search.py  (no API needed, uses data/*_d1.csv from script 01)
Questions: a time-split trail, trail width, decision lag (1 vs 2 minutes), selling half at a target
and trailing the rest, arming level and hard stop, and robustness across deal groups.
Run:  python 02_rule_search.py
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
GROUPS = {
    "MEGA": ["SPCX", "ARM", "RIVN", "UBER", "CRWV"],         # closest to ANT: huge deal, modest pop
    "MODEST": ["SPCX", "ARM", "RIVN", "UBER", "CRWV", "LYFT", "PINS", "KVYO", "BIRK", "KLAR", "RDDT"],
    "ALL": list(OFFER),
}


def load(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


def hold(df, offer):
    return df[df.index.time <= CUTOFF]["close"].iloc[-1] / offer - 1


def simulate(df, offer, ke, kl, sw, arm, stop, half_t, lat):
    o, h, c = (df[x].to_numpy(float) for x in ["open", "high", "close"])
    times = df.index.time
    mins = (df.index - df.index[0]).total_seconds().to_numpy() / 60
    n = len(c)
    pos, cash, runmax = 1.0, 0.0, -np.inf
    armed = arm is None
    half_done = half_t is None
    pending = None  # (exec_index, fraction)
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
        if pending is not None:
            continue
        j = min(i + lat, n - 1)
        k = ke if (kl is None or mins[i] < sw) else kl
        if armed and c[i] < runmax * (1 - k):
            pending = (j, pos)
        elif stop is not None and mins[i] >= 5 and c[i] < offer * (1 + stop):
            pending = (j, pos)
        elif not half_done and h[i] >= offer * (1 + half_t):
            pending = (j, 0.5)
            half_done = True
    if pending is not None and pos > 0:
        cash += pos * c[-1]
        pos = 0.0
    if pos > 0:
        cash += pos * c[-1]
    return cash / offer - 1


def main():
    data = {s: load(s) for s in OFFER}
    base = {s: hold(data[s], OFFER[s]) for s in OFFER}
    grid = itertools.product(
        [0.04, 0.05, 0.06, 0.08, 0.10, 0.12],          # ke: trail width
        [(None, 0), (0.05, 60), (0.05, 120)],          # (kl, switch minute)
        [None, 0.10, 0.20],                            # arm level vs offer
        [None, -0.05],                                 # hard stop vs offer
        [None, 0.15, 0.20, 0.25],                      # sell half at target
        [1, 2],                                        # latency in minutes
    )
    rows = []
    for ke, (kl, sw), arm, stop, half_t, lat in grid:
        label = (f"k{int(ke*100):02d}" + (f">{int(kl*100)}@{sw}" if kl else "")
                 + (f" arm{int(arm*100)}" if arm else "") + (f" stop{int(stop*100)}" if stop else "")
                 + (f" half{int(half_t*100)}" if half_t else "") + f" L{lat}")
        for s in OFFER:
            r = simulate(data[s], OFFER[s], ke, kl, sw, arm, stop, half_t, lat)
            rows.append(dict(rule=label, lat=lat, sym=s, exit=r, vs_hold=r - base[s]))
    R = pd.DataFrame(rows)
    R.to_csv("out/rules_02.csv", index=False)

    pd.set_option("display.width", 200)
    summ = {}
    for g, syms in GROUPS.items():
        sub = R[R.sym.isin(syms)]
        a = sub.groupby("rule").agg(mean_exit=("exit", "mean"), worst=("exit", "min"),
                                    vs_hold=("vs_hold", "mean"), worst_vs_hold=("vs_hold", "min"))
        summ[g] = a
        print(f"\n=== {g} (n={len(syms)}) top 10 by mean vs hold-to-15:30, % ===")
        print((a.sort_values("vs_hold", ascending=False).head(10) * 100).round(1).to_string())

    comb = pd.concat({g: summ[g]["vs_hold"] for g in summ}, axis=1)
    comb["score"] = comb.mean(axis=1)
    comb["min_grp"] = comb[list(GROUPS)].min(axis=1)
    print("\n=== ROBUST: top 15 by average of group means (each column = group mean vs hold, %) ===")
    print((comb.sort_values("score", ascending=False).head(15) * 100).round(1).to_string())

    l1 = R[R.lat == 1].groupby(R.rule.str.replace(" L1", ""))["exit"].mean()
    l2 = R[R.lat == 2].groupby(R.rule.str.replace(" L2", ""))["exit"].mean()
    print(f"\nLatency cost (2 min vs 1 min), mean across rules: {(l1 - l2).mean()*100:.2f} pts")
    print("Hold-to-15:30 baseline, % :", {g: round(np.mean([base[s] for s in syms]) * 100, 1)
                                          for g, syms in GROUPS.items()})
    print("Saved out/rules_02.csv")


if __name__ == "__main__":
    main()
