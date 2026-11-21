"""
18_postmortem.py  -  ANT day-one post-mortem (19 Nov 2026). Run after 21:15 UK:  python 18_postmortem.py

PRE-REGISTERED HYPOTHESES (written 21:15 UK, before any post-trade data was pulled)
 H1  Capture: the $105.03 exit kept >= 60% of the $83 -> day-high move.
 H2  Rule beat holding to the 20:30 UK cut-off AND to the 21:00 official close.
 H3  Backup feed: IEX 1-min closes sat within 0.2% of SIP closes in the trade window,
     and the engine run on SIP bars fires SELL in the same minute (+/- 1) as live.
 H4  Peak not tradable: ANT traded at >= $113 for under 60 seconds in total.
 H5  Rule beat the first obtainable quote (SIP close 1, 2 and 3 minutes after the first trade).
 H6  Perp (script 11 mapping, T-1h premium p): high ~ 83(1+1.31p) and close ~ 83(1+0.83p), each within 5%;
     the perp overstated the open (SpaceX pattern).
 H7  Finnhub stopped delivering ALL trades (not only ANT) around 16:53-16:54 UK while the socket stayed open.
 H8  EXPLORATORY (not a test): the perp led the stock by >= 1 minute after the open.

Outputs: printed report + out/18_postmortem.txt + out/18_sip_bars.csv + out/18_sip_trades_window.csv
"""
import os
import sys
import time
import json
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from engine import ExitEngine, Rule

ET, UK = "America/New_York", "Europe/London"
DAY = "2026-11-19"
SYM, OFFER, SHARES = "ANT", 83.0, 34
EXIT_PX, EXIT_GBP = 105.03, 2699.04
COST_GBP = 2148.79
FX = 105.03 / 80.1316                     # implied by the AJ Bell contract (USD per GBP)
BAD_COND = {"Z", "U", "T", "W", "H", "I", "B", "C", "N", "P", "R", "V"}
TRADE_WIN = ("11:44", "12:30")             # ET window for full SIP trades (16:44-17:30 UK)
os.makedirs("out", exist_ok=True)
load_dotenv()
HDR = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


def gbp(px):
    return SHARES * px / FX * (1 - 0.0075) - 5


def uk(ts):
    return ts.tz_convert(UK).strftime("%H:%M:%S")


def get_json(url, params):
    for _ in range(8):
        r = requests.get(url, headers=HDR, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(5)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("rate limited")


def sip_bars(tf="1Min"):
    s = pd.Timestamp(f"{DAY} 09:30", tz=ET).tz_convert("UTC").isoformat()
    e = pd.Timestamp(f"{DAY} 16:00", tz=ET).tz_convert("UTC").isoformat()
    url = f"https://data.alpaca.markets/v2/stocks/{SYM}/bars"
    p = dict(timeframe=tf, start=s, end=e, limit=10000, feed="sip", adjustment="raw")
    out = []
    while True:
        j = get_json(url, p)
        out += j.get("bars") or []
        if not j.get("next_page_token"):
            break
        p["page_token"] = j["next_page_token"]
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.set_index("t")[["o", "h", "l", "c", "v", "n", "vw"]]


def sip_daily():
    url = f"https://data.alpaca.markets/v2/stocks/{SYM}/bars"
    try:   # free tier: end must be >= 15 min in the past, so stop at the 21:00 UK close
        j = get_json(url, dict(timeframe="1Day", start=f"{DAY}T00:00:00Z", end=f"{DAY}T21:00:00Z",
                               feed="sip", adjustment="raw"))
        return (j.get("bars") or [None])[0]
    except Exception as ex:
        print(f"(daily bar unavailable: {ex}; using the last minute bar as the close)")
        return None


def sip_trades(a, b):
    s = pd.Timestamp(f"{DAY} {a}", tz=ET).tz_convert("UTC").isoformat()
    e = pd.Timestamp(f"{DAY} {b}", tz=ET).tz_convert("UTC").isoformat()
    url = f"https://data.alpaca.markets/v2/stocks/{SYM}/trades"
    p = dict(start=s, end=e, limit=10000, feed="sip")
    rows, pages = [], 0
    while True:
        j = get_json(url, p)
        for t in j.get("trades") or []:
            rows.append((t["t"], t["p"], t["s"], "|".join(t.get("c") or []), t.get("x", "")))
        pages += 1
        if pages % 20 == 0:
            print(f"  ...{len(rows):,} trades")
        if not j.get("next_page_token"):
            break
        p["page_token"] = j["next_page_token"]
    df = pd.DataFrame(rows, columns=["t", "p", "s", "c", "x"])
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    return df


def clean(df):
    bad = df["c"].apply(lambda c: bool(set(c.split("|")) & BAD_COND) if c else False)
    return df[(~bad) & (df["s"] >= 100)]


def run_engine(bars):
    eng = ExitEngine(OFFER, Rule())
    for ts, r in bars.iterrows():
        eng.on_bar(ts, r["o"], r["h"], r["l"], r["c"])
    return eng


def hl_candles():
    s = int(pd.Timestamp(f"{DAY} 14:00", tz=UK).timestamp() * 1000)
    e = int(pd.Timestamp(f"{DAY} 21:05", tz=UK).timestamp() * 1000)
    body = {"type": "candleSnapshot", "req": {"coin": "xyz:ANT", "interval": "1m", "startTime": s, "endTime": e}}
    r = requests.post("https://api.hyperliquid.xyz/info", json=body, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    for k in "ohlc":
        df[k] = df[k].astype(float)
    return df.set_index("t")[["o", "h", "l", "c"]]


# ---------------------------------------------------------------- data
say("=" * 78)
say("18 POST-MORTEM  ANT  19 Nov 2026   (hypotheses H1-H8 pre-registered in the header)")
say("=" * 78)
bars = sip_bars()
if bars.empty:
    sys.exit("No SIP bars yet. Wait until 21:20 UK and rerun.")
bars.to_csv("out/18_sip_bars.csv")
daily = sip_daily()
first = bars.index[0]
hi_ts = bars["h"].idxmax()
say(f"\nSIP 1-min bars: {len(bars)} | first bar {uk(first)} UK | open ${bars['o'].iloc[0]:.2f}")
say(f"SIP day high ${bars['h'].max():.2f} in bar {uk(hi_ts)} UK ({(hi_ts-first).total_seconds()/60:.0f} min after first bar)"
    f" | low ${bars['l'].min():.2f} | last bar close ${bars['c'].iloc[-1]:.2f}")
if daily:
    say(f"SIP daily bar: O {daily['o']} H {daily['h']} L {daily['l']} C {daily['c']} V {daily['v']:,} (C = official close)")
close_px = daily["c"] if daily else bars["c"].iloc[-1]

print(f"\nFetching SIP trades {TRADE_WIN[0]}-{TRADE_WIN[1]} ET (16:44-17:30 UK)...")
tr = sip_trades(*TRADE_WIN)
tr.to_csv("out/18_sip_trades_window.csv", index=False)
trc = clean(tr)
say(f"SIP trades in window: {len(tr):,} raw | {len(trc):,} after our live filters (size>=100, bad conditions)")
first_print = tr.sort_values("t").iloc[0]
say(f"First SIP print {uk(first_print['t'])} UK at ${first_print['p']:.2f} (size {first_print['s']}, cond {first_print['c']})")

# ---------------------------------------------------------------- H1 / H2 / H5 outcome
say("\n--- H1 / H2 / H5  OUTCOME ---")
dayhi = bars["h"].max()
cap = (EXIT_PX - OFFER) / (dayhi - OFFER)
say(f"H1 capture of $83 -> SIP high: {cap:.1%}   -> {'PASS' if cap >= 0.60 else 'FAIL'}")
cut = bars[[t.time() < pd.Timestamp('15:30').time() for t in bars.index.tz_convert(ET)]]
cut_px = cut["c"].iloc[-1]
rows = [("Exit by rule (contract)", EXIT_PX, EXIT_GBP - COST_GBP),
        ("Hold to 20:30 UK cut-off", cut_px, gbp(cut_px) - COST_GBP),
        ("Hold to 21:00 official close", close_px, gbp(close_px) - COST_GBP)]
for k in (1, 2, 3):
    if len(bars) > k:
        px = bars["c"].iloc[k]
        rows.append((f"First obtainable quote, +{k} min", px, gbp(px) - COST_GBP))
rows.append(("SIP day high (hindsight)", dayhi, gbp(dayhi) - COST_GBP))
for name, px, pl in rows:
    say(f"  {name:32s} ${px:8.2f}  {px/OFFER-1:+7.1%}  P&L GBP {pl:8.2f}")
h2 = EXIT_PX > cut_px and EXIT_PX > close_px
say(f"H2 rule beat hold to 20:30 and to close -> {'PASS' if h2 else 'FAIL'}")
h5 = all(EXIT_PX > bars["c"].iloc[k] for k in (1, 2, 3) if len(bars) > k)
say(f"H5 rule beat first obtainable quote (+1,+2,+3 min) -> {'PASS' if h5 else 'FAIL'}")

# ---------------------------------------------------------------- H4 tradable peak
say("\n--- H4  HOW TRADABLE WAS THE PEAK? (filtered SIP trades) ---")
sec = trc.set_index("t")["p"].resample("1s").max().dropna()
for lvl in (114, 113, 112, 110):
    above = sec[sec >= lvl]
    vol = trc.loc[trc["p"] >= lvl, "s"].sum()
    if len(above):
        say(f"  >= ${lvl}: {len(above):4d} seconds with a trade there, {vol:,} shares, first {uk(above.index[0])} last {uk(above.index[-1])} UK")
    else:
        say(f"  >= ${lvl}: never")
s113 = int((sec >= 113).sum())
say(f"H4 seconds at >= $113: {s113} -> {'PASS (peak not tradable)' if s113 < 60 else 'FAIL (peak was tradable)'}")
pk = trc.loc[trc["p"].idxmax()]
say(f"Highest filtered print ${pk['p']:.2f} at {uk(pk['t'])} UK, size {pk['s']}")

# ---------------------------------------------------------------- H3 backup feed vs SIP
say("\n--- H3  OUR LIVE BARS (IEX backup) vs SIP ---")
blog = f"logs/bars_{SYM}_{DAY.replace('-', '')}.csv"
ours = pd.read_csv(blog, header=None, names=["m", "o", "h", "l", "c"])
ours["m"] = pd.to_datetime(ours["m"], utc=True)
ours = ours.drop_duplicates("m", keep="last").set_index("m")
rebuilt = trc.set_index("t")["p"].resample("1min").ohlc().dropna()
cmp = pd.DataFrame({"our_h": ours["h"], "our_c": ours["c"], "sip_h": bars["h"], "sip_c": bars["c"],
                    "flt_h": rebuilt["high"], "flt_c": rebuilt["close"]}).dropna()
win = cmp[(cmp.index >= first) & (cmp.index <= first + pd.Timedelta(minutes=20))]
say(" bar(UK)  our_high  sip_high  flt_high | our_close sip_close flt_close  close_diff")
for ts, r in win.iterrows():
    say(f"  {ts.tz_convert(UK).strftime('%H:%M')}  {r.our_h:8.2f}  {r.sip_h:8.2f}  {r.flt_h:8.2f} | "
        f"{r.our_c:8.2f}  {r.sip_c:8.2f}  {r.flt_c:8.2f}  {r.our_c/r.sip_c-1:+.3%}")
mad = (win["our_c"] / win["sip_c"] - 1).abs()
say(f"Max |close diff| ours vs SIP: {mad.max():.3%} | mean {mad.mean():.3%}")
for label, b in (("SIP bars", bars), ("SIP rebuilt with our filters", rebuilt.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}))):
    eng = run_engine(b)
    s = eng.signal
    say(f"Engine on {label:30s}: " + (f"{s['reason']} at {uk(s['ts'])} UK, close ${s['price']:.2f}" if s else "no signal")
        + f" | high ${eng.runmax:.2f}")
    if label == "SIP bars":
        sip_sig = s
live_sell = pd.Timestamp(f"{DAY} 17:01", tz=UK)
same = sip_sig is not None and abs((sip_sig["ts"] - live_sell).total_seconds()) <= 120
say(f"H3 -> {'PASS' if (mad.max() <= 0.002 and same) else 'FAIL'} (close diff <= 0.2% and SIP signal within 1 min of live 17:01)")

# ---------------------------------------------------------------- H7 Finnhub silence
say("\n--- H7  WHEN DID FINNHUB GO SILENT? (our tick log) ---")
tl = pd.read_csv(f"logs/ticks_{SYM}_{DAY.replace('-', '')}.csv", header=None, names=["t", "p", "v", "src", "c"])
tl["t"] = pd.to_datetime(tl["t"], unit="ms", utc=True)
tl = tl[tl["t"] >= first - pd.Timedelta(minutes=5)]
fh = tl[tl["src"] == "finnhub"].sort_values("t")
al = tl[tl["src"] == "alpaca"].sort_values("t")
say(f"Finnhub ANT ticks logged: {len(fh):,} | first {uk(fh['t'].iloc[0]) if len(fh) else '-'} | last {uk(fh['t'].iloc[-1]) if len(fh) else '-'} UK")
say(f"IEX backup ticks logged:  {len(al):,} | first {uk(al['t'].iloc[0]) if len(al) else '-'} UK")
if len(fh) > 1:
    g = fh["t"].diff().dt.total_seconds()
    say(f"Largest Finnhub gaps (s): {', '.join(f'{x:.0f}' for x in g.nlargest(5))}")
per_min = tl.set_index("t").groupby([pd.Grouper(freq="1min"), "src"]).size().unstack(fill_value=0)
say(" minute(UK) " + "  ".join(f"{c:>8s}" for c in per_min.columns))
for ts, r in per_min.head(25).iterrows():
    say(f"  {ts.tz_convert(UK).strftime('%H:%M')}    " + "  ".join(f"{int(v):8d}" for v in r.values))
sip_per_min = tr.set_index("t").resample("1min").size()
say(f"SIP trades per minute, first 10 min: {', '.join(str(int(x)) for x in sip_per_min.loc[first:].head(10))}")
say("H7: compare 'last Finnhub tick' with the 16:54 banner; if Finnhub stops while SIP volume stays high,"
    " the primary feed stalled (not a quiet market). QQQ freeze at +0.00% says ALL symbols stopped.")

# ---------------------------------------------------------------- H6 / H8 perp
say("\n--- H6 / H8  THE PERP ---")
try:
    hl = hl_candles()
except Exception as ex:
    hl = pd.DataFrame()
    say(f"Hyperliquid candles unavailable ({type(ex).__name__}: {ex}). Using dashboard readings only.")
if not hl.empty:
    hl.to_csv("out/18_perp_1m.csv")
    t1h = first - pd.Timedelta(hours=1)
    p_t1h = hl["c"].asof(t1h)
    p_open = hl["c"].asof(first)
    p = p_t1h / OFFER - 1
    pred_hi, pred_cl = OFFER * (1 + 1.31 * p), OFFER * (1 + 0.83 * p)
    say(f"Perp T-1h ({uk(t1h)} UK) ${p_t1h:.2f} = premium {p:+.1%} | perp at first trade ${p_open:.2f}")
    say(f"Predicted high ${pred_hi:.2f} vs actual ${dayhi:.2f} ({dayhi/pred_hi-1:+.1%}) | "
        f"predicted close ${pred_cl:.2f} vs actual ${close_px:.2f} ({close_px/pred_cl-1:+.1%})")
    say(f"Perp T-1h vs SIP open ${bars['o'].iloc[0]:.2f}: perp {'over' if p_t1h > bars['o'].iloc[0] else 'under'}stated the open by "
        f"{p_t1h/bars['o'].iloc[0]-1:+.1%}")
    ok = abs(dayhi / pred_hi - 1) <= 0.05 and abs(close_px / pred_cl - 1) <= 0.05
    say(f"H6 -> {'PASS' if ok else 'FAIL'}")
    j = pd.DataFrame({"perp": hl["c"], "stock": bars["c"]}).dropna()
    j = j[j.index >= first]
    r = np.log(j).diff().dropna()
    if len(r) > 20:
        for lag in (-2, -1, 0, 1, 2):
            c = r["perp"].corr(r["stock"].shift(-lag))
            say(f"  corr(perp ret t, stock ret t{lag:+d}) = {c:+.3f}   (n={len(r)})")
        say("H8 EXPLORATORY: perp leads if lag +1/+2 correlations clearly exceed lag -1/-2.")
    basis = (j["perp"] / j["stock"] - 1)
    say(f"Basis perp/stock after open: mean {basis.mean():+.2%}, min {basis.min():+.2%}, max {basis.max():+.2%}")

# ---------------------------------------------------------------- save
with open("out/18_postmortem.txt", "w") as f:
    f.write("\n".join(LOG))
say("\nSaved out/18_postmortem.txt.")
