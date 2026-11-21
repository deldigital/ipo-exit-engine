"""
20_risk_and_split.py  (no API; needs out/19_quick_vs_trail.csv)
Follows from 19: v1.1 and "sell at +2 min" tie on the mean but win on different days (edge driven by
peak timing, which is not knowable at the open). So compare RISK, and test a fixed 50/50 split.
Run: python 20_risk_and_split.py

PRE-REGISTERED (21:50 UK, 19 Nov). The split is fixed at 50/50 in advance: no parameter is fitted.
 H13  The 50/50 split (half sold at +2 min, half run by v1.1) has a smaller MAXIMUM regret than
      either v1.1 or +2 min alone (regret = best of {+2 min, v1.1, hold} minus the strategy).
 H14  The 50/50 split has a higher 10th percentile than v1.1 alone (fewer bad days).
 H15  v1.1 and +2 min are statistically indistinguishable: weighted-bootstrap P(v11 mean > q2 mean)
      lies between 0.30 and 0.70.
 H16  Both active exits beat holding: bootstrap P(mean > hold) > 0.90 for v1.1, +2 min and the split.
 Same 27 deals as script 19, so these are risk descriptions of one sample, not new out-of-sample evidence.
"""
import numpy as np
import pandas as pd

T = pd.read_csv("out/19_quick_vs_trail.csv", index_col=0)
T["split"] = 0.5 * T["q2"] + 0.5 * T["v11"]
S = ["q1", "q2", "v11", "split", "hold"]
best = T[["q2", "v11", "hold"]].max(axis=1)
w = T["w"].to_numpy()
rng = np.random.default_rng(20)
pd.set_option("display.width", 200)

print("=" * 96)
print("20  RISK PROFILE OF DAY-ONE EXITS (27 deals, % of offer; regret = best of q2/v11/hold minus strategy)")
print("=" * 96)
rows = []
for s in S:
    x = T[s]
    reg = best - x
    cap = (x / T["high"]).where(T["high"] > 5)          # share of the offer-to-high move kept (deals with high > +5%)
    rows.append(dict(strategy=s, mean=x.mean(), wmean=np.average(x, weights=w), median=x.median(),
                     p10=x.quantile(0.10), worst=x.min(), mean_regret=reg.mean(), p90_regret=reg.quantile(0.9),
                     max_regret=reg.max(), worst_deal=reg.idxmax(), median_capture=cap.median()))
R = pd.DataFrame(rows).set_index("strategy")
print(R.round(2).to_string())

print("\nPer-deal regret, largest first (points):")
reg_tbl = pd.DataFrame({s: best - T[s] for s in ["q2", "v11", "split"]})
reg_tbl["peak_min"] = T["peak_min"]
print(reg_tbl.sort_values("v11", ascending=False).round(1).head(10).to_string())

h13 = R.loc["split", "max_regret"] < min(R.loc["v11", "max_regret"], R.loc["q2", "max_regret"])
h14 = R.loc["split", "p10"] > R.loc["v11", "p10"]
print(f"\nH13 split has the smallest max regret -> {'PASS' if h13 else 'FAIL'} "
      f"(split {R.loc['split','max_regret']:.1f}, v11 {R.loc['v11','max_regret']:.1f}, q2 {R.loc['q2','max_regret']:.1f})")
print(f"H14 split 10th percentile above v11 -> {'PASS' if h14 else 'FAIL'} "
      f"(split {R.loc['split','p10']:.1f}, v11 {R.loc['v11','p10']:.1f})")

print("\n--- Weighted bootstrap of mean differences (10,000 draws, ANT-style weights) ---")
p = w / w.sum()
n = len(T)
pairs = [("v11", "q2"), ("split", "v11"), ("split", "q2"), ("v11", "hold"), ("q2", "hold"), ("split", "hold")]
res = {}
for a, b in pairs:
    d = (T[a] - T[b]).to_numpy()
    boots = np.array([d[rng.choice(n, n, p=p)].mean() for _ in range(10000)])
    res[(a, b)] = (boots > 0).mean()
    print(f"  {a:5s} - {b:5s}: mean {d.mean():+6.2f} | 90% CI {np.percentile(boots, 5):+6.2f} to {np.percentile(boots, 95):+6.2f}"
          f" | P(>0) {res[(a, b)]:.2f}")
h15 = 0.30 <= res[("v11", "q2")] <= 0.70
h16 = all(res[(s, "hold")] > 0.90 for s in ["v11", "q2", "split"])
print(f"H15 v11 vs q2 indistinguishable -> {'PASS' if h15 else 'FAIL'} (P = {res[('v11','q2')]:.2f})")
print(f"H16 all active exits beat hold with P > 0.90 -> {'PASS' if h16 else 'FAIL'}")

print("\n--- What the split would have done on ANT (34 shares) ---")
FX, sh = 105.03 / 80.1316, 34
for s in ["q2", "v11", "split", "hold"]:
    px = 83 * (1 + T.loc["ANT", s] / 100)
    gbp = sh * px / FX * (1 - 0.0075) - (10 if s == "split" else 5)
    print(f"  {s:5s} ${px:7.2f}  P&L GBP {gbp - 2148.79:7.2f}" + ("   (two deals: GBP 10 fees)" if s == "split" else ""))
print("\nSaved nothing new.")
