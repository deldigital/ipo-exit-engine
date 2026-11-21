"""
01_fetch_and_profile.py
First pass over day-one data: time to peak, pullbacks before the peak, giveback after the peak,
a volatility-scaled trail, and a replay of trailing exits.

Data: Alpaca free plan, historical SIP 1-minute bars (all US exchanges).
Setup:
  pip install alpaca-py pandas numpy python-dotenv
  .env file in this folder:
    ALPACA_KEY=your_key
    ALPACA_SECRET=your_secret
Run:
  python 01_fetch_and_profile.py
"""
import os
from datetime import time
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment

ET = "America/New_York"
OUT, DATA = "out", "data"
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

# ticker, IPO offer price, approx first trading date, tag
IPOS = [
    ("SPCX", 135.0, "2026-06-12", "mega"),
    ("CBRS", 185.0, "2026-05-14", "hot_ai"),   # Cerebras: ticker/date to verify in output
    ("ARM", 51.0, "2023-09-14", "mega"),
    ("FIG", 33.0, "2025-07-31", "hot"),
    ("CRCL", 31.0, "2025-06-05", "hot"),
    ("CRWV", 40.0, "2025-03-28", "ai"),
    ("RDDT", 34.0, "2024-03-21", "hot"),
    ("RIVN", 78.0, "2021-11-10", "mega"),
    ("ABNB", 68.0, "2020-12-10", "hot"),
    ("DASH", 102.0, "2020-12-09", "hot"),
    ("SNOW", 120.0, "2020-09-16", "hot"),
    ("UBER", 45.0, "2019-05-10", "mega_neg"),
    ("LYFT", 72.0, "2019-03-29", "neg"),
    ("ZM", 36.0, "2019-04-18", "hot"),
    ("PINS", 19.0, "2019-04-18", "mid"),
    ("CAVA", 22.0, "2023-06-15", "hot"),
    ("KVYO", 30.0, "2023-09-20", "mid"),
    ("BIRK", 46.0, "2023-10-11", "neg"),
    ("CHYM", 27.0, "2025-06-12", "mid"),
    ("KLAR", 40.0, "2025-09-10", "mid"),
]

TRAIL_PCT = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12]
TRAIL_SIG = [3, 5, 8, 12, 16]        # floor = runmax * (1 - m * live 1-min sigma)
LATENCY_BARS = 1                      # alert -> AJ Bell fill ~ next minute open
CUTOFF_ET = time(15, 30)              # 20:30 UK hard exit


def first_day(client, sym, approx):
    d = pd.Timestamp(approx)
    req = StockBarsRequest(
        symbol_or_symbols=sym, timeframe=TimeFrame.Day,
        start=(d - pd.Timedelta(days=7)).to_pydatetime(),
        end=(d + pd.Timedelta(days=14)).to_pydatetime(),
        feed=DataFeed.SIP, adjustment=Adjustment.RAW)
    df = client.get_stock_bars(req).df
    if df.empty:
        return None
    return df.index.get_level_values("timestamp")[0].tz_convert(ET).date()


def minute_bars(client, sym, day):
    s = pd.Timestamp(f"{day} 09:30", tz=ET).tz_convert("UTC")
    e = pd.Timestamp(f"{day} 16:00", tz=ET).tz_convert("UTC")
    req = StockBarsRequest(
        symbol_or_symbols=sym, timeframe=TimeFrame.Minute,
        start=s.to_pydatetime(), end=e.to_pydatetime(),
        feed=DataFeed.SIP, adjustment=Adjustment.RAW)
    df = client.get_stock_bars(req).df
    if df.empty:
        return df
    df = df.xs(sym, level="symbol").copy()
    df.index = df.index.tz_convert(ET)
    df = df[(df.index.time >= time(9, 30)) & (df.index.time < time(16, 0))]
    return df[["open", "high", "low", "close", "volume", "vwap", "trade_count"]]


def profile(df, offer):
    o, h, l, c = (df[x].to_numpy(float) for x in ["open", "high", "low", "close"])
    t = df.index
    mins = np.asarray((t - t[0]).total_seconds() / 60.0)
    ip = int(np.argmax(h))
    prev_max = np.maximum.accumulate(np.concatenate([[h[0]], h[:-1]]))
    dd = 1 - l / prev_max
    pre_pb = float(dd[:ip + 1].max()) if ip > 0 else 0.0
    r = np.diff(np.log(c))
    sig30 = float(np.std(r[:30])) if len(r) >= 30 else float(np.std(r))

    def gb(k):
        j = ip + k
        return float(1 - c[j] / h[ip]) if j < len(c) else np.nan

    open_930 = t[0].normalize() + pd.Timedelta(hours=9, minutes=30)
    return dict(
        first_ET=t[0].strftime("%H:%M"),
        min_to_first=(t[0] - open_930).total_seconds() / 60,
        open_r=o[0] / offer - 1, high_r=h[ip] / offer - 1,
        low_r=l.min() / offer - 1, close_r=c[-1] / offer - 1,
        min_to_peak=mins[ip],
        prepk_pb=pre_pb,
        prepk_pb_sig=pre_pb / sig30 if sig30 > 0 else np.nan,
        sig1m_30=sig30, sig1m_day=float(np.std(r)),
        gb5=gb(5), gb15=gb(15), gb30=gb(30),
        postpk_dd=float(1 - l[ip:].min() / h[ip]),
    )


def ewma_sig(c, hl=10):
    r = pd.Series(np.log(c)).diff()
    return r.ewm(halflife=hl, min_periods=5).std().to_numpy()


def trail_exit(df, offer, k=None, m=None):
    h, c, o = (df[x].to_numpy(float) for x in ["high", "close", "open"])
    times = df.index.time
    ip = int(np.argmax(h))
    runmax = np.maximum.accumulate(h)
    sig = ewma_sig(c) if m is not None else None
    for i in range(len(c)):
        if times[i] >= CUTOFF_ET:
            return c[i] / offer - 1, "cutoff", False
        if k is not None:
            floor = runmax[i] * (1 - k)
        else:
            if np.isnan(sig[i]):
                continue
            floor = runmax[i] * (1 - m * sig[i])
        if c[i] < floor:
            j = min(i + LATENCY_BARS, len(c) - 1)
            return o[j] / offer - 1, "trail", i < ip
    return c[-1] / offer - 1, "eod", False


def hold_to_cutoff(df, offer):
    sub = df[df.index.time <= CUTOFF_ET]
    return sub["close"].iloc[-1] / offer - 1


def main():
    load_dotenv()
    client = StockHistoricalDataClient(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    profs, grid = [], []
    bars = {}
    for sym, offer, approx, tag in IPOS:
        try:
            day = first_day(client, sym, approx)
            if day is None:
                print(f"[skip] {sym}: no daily bars near {approx}")
                continue
            df = minute_bars(client, sym, day)
            if df.empty or len(df) < 30:
                print(f"[skip] {sym}: too few minute bars on {day}")
                continue
            df.to_csv(f"{DATA}/{sym}_d1.csv")
            bars[sym] = (df, offer)
            p = profile(df, offer)
            p.update(sym=sym, tag=tag, day=str(day), bars=len(df))
            profs.append(p)
            base = hold_to_cutoff(df, offer)
            for k in TRAIL_PCT:
                r, why, early = trail_exit(df, offer, k=k)
                grid.append(dict(sym=sym, rule=f"pct{int(k*100):02d}", exit_r=r,
                                 why=why, premature=early, high_r=p["high_r"], base=base))
            for m in TRAIL_SIG:
                r, why, early = trail_exit(df, offer, m=m)
                grid.append(dict(sym=sym, rule=f"sig{m:02d}", exit_r=r,
                                 why=why, premature=early, high_r=p["high_r"], base=base))
        except Exception as ex:
            print(f"[error] {sym}: {ex}")

    P = pd.DataFrame(profs).set_index("sym")
    P.to_csv(f"{OUT}/profile.csv")
    G = pd.DataFrame(grid)
    G.to_csv(f"{OUT}/trail_grid.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pct = ["open_r", "high_r", "low_r", "close_r", "prepk_pb", "gb5", "gb15", "gb30", "postpk_dd"]
    show = P.copy()
    show[pct] = (show[pct] * 100).round(1)
    show[["sig1m_30", "sig1m_day"]] = (show[["sig1m_30", "sig1m_day"]] * 100).round(2)
    show["prepk_pb_sig"] = show["prepk_pb_sig"].round(1)
    print("\n=== DAY-ONE PROFILE (returns vs offer, %; sig = 1-min log-return std, %) ===")
    print(show[["tag", "day", "first_ET", "min_to_first", "open_r", "high_r", "low_r", "close_r",
                "min_to_peak", "prepk_pb", "prepk_pb_sig", "sig1m_30", "sig1m_day",
                "gb5", "gb15", "gb30", "postpk_dd"]].to_string())

    G["capture"] = np.where(G["high_r"] > 0, G["exit_r"] / G["high_r"], np.nan)
    G["vs_base"] = G["exit_r"] - G["base"]
    agg = G.groupby("rule").agg(
        mean_exit=("exit_r", "mean"), med_exit=("exit_r", "median"),
        mean_capture=("capture", "mean"), mean_vs_hold=("vs_base", "mean"),
        premature=("premature", "sum"), n=("sym", "count"))
    for col in ["mean_exit", "med_exit", "mean_vs_hold"]:
        agg[col] = (agg[col] * 100).round(1)
    agg["mean_capture"] = agg["mean_capture"].round(2)
    print("\n=== TRAIL RULES, all IPOs (exit %, capture = exit/peak, vs_hold = vs selling 15:30 ET) ===")
    print(agg.to_string())

    wide = G.pivot(index="sym", columns="rule", values="exit_r") * 100
    print("\n=== EXIT % BY IPO AND RULE ===")
    print(wide.round(1).to_string())
    print(f"\nHold-to-15:30 baseline mean: {G.drop_duplicates('sym')['base'].mean()*100:.1f}%")
    print("\nSaved: out/profile.csv, out/trail_grid.csv, data/*_d1.csv")


if __name__ == "__main__":
    main()
