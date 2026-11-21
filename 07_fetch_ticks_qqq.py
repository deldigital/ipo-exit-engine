"""
07_fetch_ticks_qqq.py  (Alpaca API; run while 06 is being read)
Tick-level data for the 4 closest analogues -> 1-second OHLC bars (regular session only).
QQQ 1-minute bars on all 20 IPO days.
Bad prints removed using SIP condition codes (out-of-sequence, odd lot, average price, etc).
Run: python 07_fetch_ticks_qqq.py   (several minutes; prints progress)
"""
import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment

ET = "America/New_York"
TICK_SYMS = ["SPCX", "CBRS", "ARM", "RIVN"]
BAD_COND = {"Z", "U", "T", "4", "7", "W", "H", "I", "B", "C", "N", "P", "R", "V"}
load_dotenv()
HDR = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}


def ipo_day(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    return pd.to_datetime(df.index, utc=True).tz_convert(ET)[0].date()


def fetch_ticks(sym, day):
    s = pd.Timestamp(f"{day} 09:30", tz=ET).tz_convert("UTC").isoformat()
    e = pd.Timestamp(f"{day} 16:00", tz=ET).tz_convert("UTC").isoformat()
    url = f"https://data.alpaca.markets/v2/stocks/{sym}/trades"
    params = dict(start=s, end=e, limit=10000, feed="sip")
    agg, n_raw, n_kept, pages = [], 0, 0, 0
    while True:
        r = requests.get(url, headers=HDR, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(5)
            continue
        r.raise_for_status()
        js = r.json()
        tr = js.get("trades") or []
        n_raw += len(tr)
        rows = [(t["t"], t["p"], t["s"]) for t in tr if not (set(t.get("c") or []) & BAD_COND)]
        n_kept += len(rows)
        if rows:
            d = pd.DataFrame(rows, columns=["t", "p", "s"])
            d["t"] = pd.to_datetime(d["t"], utc=True, format="ISO8601").dt.floor("s")
            g = d.groupby("t").agg(open=("p", "first"), high=("p", "max"), low=("p", "min"),
                                   close=("p", "last"), volume=("s", "sum"), n=("p", "size"))
            agg.append(g)
        pages += 1
        if pages % 25 == 0:
            print(f"  {sym}: {pages} pages, {n_raw:,} trades")
        tok = js.get("next_page_token")
        if not tok:
            break
        params["page_token"] = tok
    df = pd.concat(agg)
    df = df.groupby(level=0).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                 close=("close", "last"), volume=("volume", "sum"), n=("n", "sum"))
    df.index = df.index.tz_convert(ET)
    return df, n_raw, n_kept


def main():
    for sym in TICK_SYMS:
        day = ipo_day(sym)
        t0 = time.time()
        df, n_raw, n_kept = fetch_ticks(sym, day)
        df.to_csv(f"data/{sym}_d1_1s.csv")
        print(f"{sym} {day}: {n_raw:,} trades, kept {n_kept:,} ({n_kept/n_raw:.1%}), "
              f"{len(df):,} one-second bars, first {df.index[0].time()}, {time.time()-t0:.0f}s")

    client = StockHistoricalDataClient(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    out = []
    for f in sorted(os.listdir("data")):
        if not f.endswith("_d1.csv"):
            continue
        sym = f.split("_")[0]
        day = ipo_day(sym)
        req = StockBarsRequest(symbol_or_symbols="QQQ", timeframe=TimeFrame.Minute,
                               start=pd.Timestamp(f"{day} 09:30", tz=ET).tz_convert("UTC").to_pydatetime(),
                               end=pd.Timestamp(f"{day} 16:00", tz=ET).tz_convert("UTC").to_pydatetime(),
                               feed=DataFeed.SIP, adjustment=Adjustment.RAW)
        q = client.get_stock_bars(req).df.xs("QQQ", level="symbol")
        q.index = q.index.tz_convert(ET)
        q["ipo"] = sym
        out.append(q[["open", "high", "low", "close", "volume", "ipo"]])
    pd.concat(out).to_csv("data/QQQ_ipo_days.csv")
    print(f"QQQ minute bars saved for {len(out)} IPO days -> data/QQQ_ipo_days.csv")


if __name__ == "__main__":
    main()
