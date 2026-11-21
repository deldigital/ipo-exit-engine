"""
12_ant_monte_carlo.py  (no API)
P&L distribution in GBP for the ANT position, rule v1.1 (live engine code) vs holding to 20:30 UK.
Paths: time-aligned stationary block bootstrap of 1-min returns from the mega + modest-pop IPOs,
each normalised by its own volatility and rescaled to a sampled ANT volatility; open premium and
first-trade time sampled from the priors below. ASSUMPTIONS were set after script 11 and the allocation.
Run: python 12_ant_monte_carlo.py
"""
import numpy as np
import pandas as pd
from engine import ExitEngine, Rule, ET

# ---------------- ASSUMPTIONS (edit) ----------------
SHARES = int(__import__("sys").argv[__import__("sys").argv.index("--shares") + 1]) if "--shares" in __import__("sys").argv else 35
OFFER = 83.0
GBPUSD = 1.315
# open premium scenarios vs $83. Script 11: open/perp(T-1h) = 0.47 (SPCX), 1.05 (CBRS); ANT perp +18.5%
SCENARIOS = [("grey market 19 Nov (+20-26%)", 0.23, 0.03),  # Bloomberg grey market, perp ~$100-102.5
             ("perp-calibrated", 0.14, 0.05),      # 0.76 x 18.5%
             ("SpaceX-like weak open", 0.087, 0.04),  # 0.47 x 18.5%
             ("grey-market (FT: +4% block)", 0.06, 0.02),  # open +4% to +8%
             ("old prior", 0.05, 0.06)]
FIRST_TRADE_ET = ("11:45", "13:30")      # uniform window for the IPO cross
import sys
BLOCK = int(sys.argv[sys.argv.index("--block") + 1]) if "--block" in sys.argv else 20  # mean block, min
N_SIM = 5000
POOL = {"SPCX": 3, "ARM": 3, "RIVN": 3, "UBER": 3, "CRWV": 3,
        "LYFT": 2, "PINS": 2, "KVYO": 2, "BIRK": 2, "KLAR": 2, "RDDT": 2}
# ----------------------------------------------------
rng = np.random.default_rng(11)


def load(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


paths, sigs, wts = [], [], []
for s, w in POOL.items():
    c = load(s)["close"].to_numpy(float)
    r = np.diff(np.log(c))
    paths.append(r / r.std()); sigs.append(r.std()); wts.append(w)
wts = np.array(wts, float) / sum(wts)
print("pool sigma (1-min, %):", {s: round(x * 100, 2) for s, x in zip(POOL, sigs)})


def gen_path(n):
    sig = rng.choice(sigs, p=wts) * rng.uniform(0.8, 1.2)
    out, t = np.empty(n), 0
    while t < n:
        k = rng.choice(len(paths), p=wts)
        L = max(1, int(rng.geometric(1 / BLOCK)))
        src = paths[k]
        start = min(max(0, t + rng.integers(-10, 11)), len(src) - 1)
        seg = src[start:start + L]
        if len(seg) == 0:
            continue
        m = min(len(seg), n - t)
        out[t:t + m] = seg[:m]
        t += m
    return out * sig, sig


def gbp(exit_px):
    proceeds = SHARES * exit_px
    return (proceeds - SHARES * OFFER) / GBPUSD - 5.0 - 0.0075 * proceeds / GBPUSD



def run(open_mean, open_sd):
    rule_pnl, hold_pnl, peaks, closes, caps, reasons = [], [], [], [], [], []
    for _ in range(N_SIM):
        lo, hi = [pd.Timestamp(f"2026-11-19 {x}", tz=ET) for x in FIRST_TRADE_ET]
        first = lo + pd.Timedelta(minutes=int(rng.integers(0, int((hi - lo).total_seconds() // 60) + 1)))
        end = pd.Timestamp("2026-11-19 15:31", tz=ET)
        n = int((end - first).total_seconds() // 60)
        r, sig = gen_path(n)
        p0 = OFFER * (1 + rng.normal(open_mean, open_sd))
        c = p0 * np.exp(np.cumsum(r))
        o = np.r_[p0, c[:-1]]
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.4 * sig, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.4 * sig, n)))
        idx = pd.date_range(first, periods=n, freq="1min")
        eng = ExitEngine(OFFER, Rule())
        fill = None
        for i in range(n):
            eng.on_bar(idx[i], o[i], h[i], l[i], c[i])
            if eng.signal:
                fill = c[i] if eng.signal["reason"].startswith("CUTOFF") else o[min(i + 1, n - 1)]
                reasons.append(eng.signal["reason"].split(":")[0].split(" ")[0])
                break
        if fill is None:
            fill = c[-1]; reasons.append("EOD")
        cut = int(np.searchsorted(idx, pd.Timestamp("2026-11-19 15:30", tz=ET)))
        hold_px = c[min(cut, n - 1)]
        rule_pnl.append(gbp(fill)); hold_pnl.append(gbp(hold_px))
        pk = h.max() / OFFER - 1
        peaks.append(pk); closes.append(hold_px / OFFER - 1)
        caps.append((fill / OFFER - 1) / pk if pk > 0.02 else np.nan)
    return (np.array(rule_pnl), np.array(hold_pnl), np.array(peaks), np.array(closes),
            np.array(caps), pd.Series(reasons))


q = [5, 25, 50, 75, 95]
for name, om, osd in SCENARIOS:
    R, H, PK, CL, CAP, RS = run(om, osd)
    print(f"\n=== {name}: open {om:+.1%} +/- {osd:.0%} | {SHARES} sh, GBP after sale costs, {N_SIM} sims ===")
    T = pd.DataFrame({"rule_v1.1": np.percentile(R, q), "hold_to_2030": np.percentile(H, q),
                      "rule_minus_hold": np.percentile(R - H, q)}, index=[f"P{x}" for x in q]).round(0)
    print(T.to_string())
    print(f"mean rule {R.mean():.0f} | hold {H.mean():.0f} | P(loss) rule {(R<0).mean():.1%} hold {(H<0).mean():.1%}"
          f" | P(loss>150) rule {(R<-150).mean():.1%} hold {(H<-150).mean():.1%} | P(rule>hold) {(R>H).mean():.1%}")
    print(f"sim 20:30 price median {np.median(CL):+.1%} (perp-implied close ~ +15%) | sim day high median "
          f"{np.median(PK):+.1%} (perp-implied ~ +24%) | capture median {np.nanmedian(CAP):.2f}")
    print("exit reasons:", RS.value_counts(normalize=True).round(2).to_dict())
