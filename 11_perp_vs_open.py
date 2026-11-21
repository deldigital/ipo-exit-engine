"""
11_perp_vs_open.py  (Hyperliquid public API, no key)
Opening model: how did trade.xyz pre-IPO perps compare with the real Nasdaq open and close?
1. Lists every market on the xyz dex whose name could be SpaceX, Cerebras or Anthropic.
2. Pulls hourly candles around each listing; compares perp price at T-72h/-24h/-12h/-1h before
   the first trade with the actual open, high and close (from data/*_d1.csv).
3. Prints the ANT perp over the last 7 days.
Run: python 11_perp_vs_open.py
"""
import requests
import pandas as pd

URL = "https://api.hyperliquid.xyz/info"
ET = "America/New_York"
KEYS = ["SPC", "SPACE", "CBRS", "CEREB", "ANT"]
IPO = {"SPCX": 135.0, "CBRS": 185.0}


def post(body):
    r = requests.post(URL, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def candles(coin, start, end, interval="1h"):
    js = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": interval,
                                                  "startTime": int(start.timestamp() * 1000),
                                                  "endTime": int(end.timestamp() * 1000)}})
    if not js:
        return pd.DataFrame()
    df = pd.DataFrame(js)
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    for c in ["o", "h", "l", "c"]:
        df[c] = df[c].astype(float)
    return df.set_index("t")[["o", "h", "l", "c"]]


meta = post({"type": "meta", "dex": "xyz"})
names = [u["name"] for u in meta["universe"]]
hits = [n for n in names if any(k in n.upper() for k in KEYS)]
print(f"xyz dex markets: {len(names)} | candidates: {hits}")

for sym, offer in IPO.items():
    d1 = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    d1.index = pd.to_datetime(d1.index, utc=True)
    first = d1.index[0]
    o, hi, cl = d1["open"].iloc[0], d1["high"].max(), d1["close"].iloc[-1]
    found = False
    for coin in [n for n in hits if sym[:3] in n.upper() or (sym == "SPCX" and "SPACE" in n.upper())
                 or (sym == "CBRS" and "CEREB" in n.upper())]:
        df = candles(coin, first - pd.Timedelta(days=5), first + pd.Timedelta(days=1))
        if df.empty:
            print(f"{sym}: {coin} no candles in window")
            continue
        found = True
        print(f"\n=== {sym} via {coin}: IPO ${offer}, first trade {first.tz_convert(ET):%Y-%m-%d %H:%M} ET ===")
        for hrs in [72, 24, 12, 1]:
            t = first - pd.Timedelta(hours=hrs)
            prior = df[df.index <= t]
            if len(prior):
                px = prior["c"].iloc[-1]
                print(f"  perp T-{hrs:>2}h: ${px:8.2f}  premium {px/offer-1:+.1%}")
        print(f"  ACTUAL open ${o:.2f} ({o/offer-1:+.1%})  high ${hi:.2f} ({hi/offer-1:+.1%})  "
              f"close ${cl:.2f} ({cl/offer-1:+.1%})")
        pre = df[df.index <= first - pd.Timedelta(hours=1)]
        if len(pre):
            p1 = pre["c"].iloc[-1] / offer - 1
            print(f"  ratio open/perp(T-1h) = {(o/offer-1)/p1:.2f}   close/perp = {(cl/offer-1)/p1:.2f}"
                  f"   high/perp = {(hi/offer-1)/p1:.2f}")
    if not found:
        print(f"{sym}: no matching perp found on xyz dex (may have been delisted or renamed)")

ant = [n for n in hits if "ANT" in n.upper()]
for coin in ant:
    now = pd.Timestamp.now(tz="UTC")
    df = candles(coin, now - pd.Timedelta(days=7), now, "4h")
    if len(df):
        print(f"\n=== {coin} last 7 days (4h closes, vs $83) ===")
        s = df["c"].resample("1D").last().dropna()
        print(pd.DataFrame({"close": s.round(2), "prem_vs_83": (s / 83 - 1).map("{:+.1%}".format)}).to_string())
