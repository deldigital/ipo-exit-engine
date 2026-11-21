"""
14_direct_listings.py  (Alpaca API) - CONTEXT ONLY, rule stays frozen.
Rationale: the closest analogues for day-one insider supply are direct listings.
Reference prices are not offer prices, so we report moves relative to the OPEN as well.
Run: python 14_direct_listings.py
"""
import importlib.util
import os
from datetime import time
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from engine import Rule, UK

spec = importlib.util.spec_from_file_location("s01", "01_fetch_and_profile.py")
s01 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s01)
import app

DL = [("SPOT", 132.0, "2018-04-03"), ("WORK", 26.0, "2019-06-20"), ("PLTR", 7.25, "2020-09-30"),
      ("ASAN", 21.0, "2020-09-30"), ("RBLX", 45.0, "2021-03-10"), ("COIN", 250.0, "2021-04-14")]
load_dotenv()
client = StockHistoricalDataClient(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
rows = []
for sym, ref, approx in DL:
    day = s01.first_day(client, sym, approx)
    df = s01.minute_bars(client, sym, day)
    if df.empty:
        print(f"[skip] {sym}"); continue
    df.to_csv(f"data/{sym}_dl.csv")
    o, h, c = df["open"].iloc[0], df["high"].max(), df[df.index.time <= time(15, 30)]["close"].iloc[-1]
    ip = int(df["high"].values.argmax())
    r, why, t = app.run_engine_on(df, ref, Rule())
    rows.append(dict(sym=sym, day=str(day), first_uk=df.index[0].tz_convert(UK).strftime("%H:%M"),
                     open_vs_ref=o / ref - 1, high_vs_open=h / o - 1, close1530_vs_open=c / o - 1,
                     close_vs_high=c / h - 1, min_to_peak=(df.index[ip] - df.index[0]).total_seconds() / 60,
                     rule_vs_hold=(r + 1) * ref / c - 1, rule_exit_uk=t, why=why))
T = pd.DataFrame(rows).set_index("sym")
for col in ["open_vs_ref", "high_vs_open", "close1530_vs_open", "close_vs_high", "rule_vs_hold"]:
    T[col] = (T[col] * 100).round(1)
pd.set_option("display.width", 200)
print("=== Direct listings: day-one shape (%), rule v1.1 vs hold-to-15:30 ET (% of hold price) ===")
print(T.to_string())
print(f"\npeaked within 30 min: {(T.min_to_peak <= 30).mean():.0%} | mean close vs high {T.close_vs_high.mean():.1f}%"
      f" | rule beat hold on {(T.rule_vs_hold > 0).sum()}/{len(T)}, mean {T.rule_vs_hold.mean():+.1f}%")
