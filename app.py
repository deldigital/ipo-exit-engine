"""
app.py  -  ANT exit dashboard.
  python app.py --check                          engine vs research code on all 20 IPOs
  python app.py --replay SPCX [--speed 0.3]      replay a precedent day through the engine
  python app.py --live --sym ANT --offer 83 --perp xyz:ANT       THURSDAY
  python app.py --live --sym NVDA --offer 180 --perp xyz:NVDA    rehearsal on a live stock
Open http://127.0.0.1:8050 in Chrome.
.env: FINNHUB_KEY=...  optional NTFY_TOPIC=private-topic-name
"""
import argparse
import importlib.util
import logging
import os
import platform
import subprocess
import threading
import time as _time
from datetime import time

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, dcc, html, Input, Output
from dotenv import load_dotenv

from engine import ExitEngine, Rule, ET, UK

OFFER = {"SPCX": 135, "CBRS": 185, "ARM": 51, "FIG": 33, "CRCL": 31, "CRWV": 40, "RDDT": 34,
         "RIVN": 78, "ABNB": 68, "DASH": 102, "SNOW": 120, "UBER": 45, "LYFT": 72, "ZM": 36,
         "PINS": 19, "CAVA": 22, "KVYO": 30, "BIRK": 46, "CHYM": 27, "KLAR": 40}
COLORS = {"WAITING": "#6b7280", "LIVE": "#2563eb", "ARMED": "#16a34a", "WATCH": "#ca8a04",
          "WARNING": "#ea580c", "SELL": "#dc2626"}
LOCK = threading.Lock()
MUTE = False
logging.getLogger("werkzeug").setLevel(logging.ERROR)


def load(sym):
    df = pd.read_csv(f"data/{sym}_d1.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df


def notify(state, msg):
    if MUTE:
        return
    if platform.system() == "Darwin":
        snd = {"WARNING": "Ping", "SELL": "Sosumi"}.get(state)   # WATCH silent: avoids alert fatigue in grace period
        if snd:
            n = 4 if state == "SELL" else 1
            subprocess.Popen(["bash", "-c",
                              f"for i in $(seq {n}); do afplay /System/Library/Sounds/{snd}.aiff; done"])
    topic = os.getenv("NTFY_TOPIC")
    if topic and state in ("WARNING", "SELL"):
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=f"ANT {state}: {msg}".encode(),
                          headers={"Priority": "urgent" if state == "SELL" else "high"}, timeout=3)
        except Exception:
            pass


# ---------------- consistency check vs research code ----------------
def run_engine_on(df, offer, rule):
    eng = ExitEngine(offer, rule)
    bars = list(df.itertuples())
    for i, b in enumerate(bars):
        eng.on_bar(b.Index, b.open, b.high, b.low, b.close)
        if eng.signal:
            fill = b.close if eng.signal["reason"].startswith("CUTOFF") else bars[min(i + 1, len(bars) - 1)].open
            return fill / offer - 1, eng.signal["reason"], eng.signal["ts"].tz_convert(UK).strftime("%H:%M")
    return bars[-1].close / offer - 1, "EOD", "-"


def check():
    spec = importlib.util.spec_from_file_location("r3", "03_confirm_bootstrap.py")
    r3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r3)
    rows = []
    for s, off in OFFER.items():
        df = load(s)
        hold = df[df.index.time <= time(15, 30)]["close"].iloc[-1] / off - 1
        research = r3.simulate(df, off, 0.08, 0.04, 15, 0.10, None, 2) - hold
        r0, why0, t0 = run_engine_on(df, off, Rule(stop=None))
        r1, why1, _ = run_engine_on(df, off, Rule())
        rows.append(dict(sym=s, research=round(research * 100, 1), engine=round((r0 - hold) * 100, 1),
                         diff=round((r0 - hold - research) * 100, 2), why=why0, uk_time=t0,
                         with_stop=round((r1 - hold) * 100, 1), why_stop=why1))
    T = pd.DataFrame(rows).set_index("sym")
    pd.set_option("display.width", 200)
    print("=== RULE v1.1: engine vs research code (vs hold, pts). diff must be 0 ===")
    print(T.to_string())
    print(f"\nmax |diff| = {T['diff'].abs().max():.2f}   mean no-stop = {T['engine'].mean():.2f}"
          f"   mean with-stop = {T['with_stop'].mean():.2f}")


# ---------------- dashboard ----------------
def card(label, value, sub=""):
    return html.Div(style={"background": "#111827", "padding": "10px 14px", "borderRadius": "8px"}, children=[
        html.Div(label, style={"fontSize": "13px", "color": "#9ca3af"}),
        html.Div(value, style={"fontSize": "28px", "fontWeight": "700"}),
        html.Div(sub, style={"fontSize": "13px", "color": "#9ca3af"})])


def make_app(eng, title, feed=None):
    app = Dash(__name__, title=title)
    app.layout = html.Div(
        style={"fontFamily": "Menlo, monospace", "background": "#0b0f14", "color": "#e5e7eb",
               "padding": "16px", "minHeight": "100vh"},
        children=[html.Div(id="banner"),
                  html.Div(id="metrics", style={"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)",
                                                "gap": "8px", "margin": "12px 0"}),
                  dcc.Graph(id="price", style={"height": "430px"}, config={"displayModeBar": False}),
                  dcc.Graph(id="dist", style={"height": "200px"}, config={"displayModeBar": False}),
                  html.Div(id="events", style={"fontSize": "14px", "whiteSpace": "pre", "marginTop": "8px"}),
                  dcc.Interval(id="tick", interval=500)])

    @app.callback(Output("banner", "children"), Output("banner", "style"), Output("metrics", "children"),
                  Output("price", "figure"), Output("dist", "figure"), Output("events", "children"),
                  Input("tick", "n_intervals"))
    def update(_):
        with LOCK:
            s = eng.snapshot()
        fs = dict(feed.state) if feed else {}
        off, r = s["offer"], s["rule"]
        state = s["state"]
        banner = f"{title}  |  {state}  |  {s['msg']}"
        if feed:
            age = _time.time() - fs["tick_ts"] if fs.get("tick_ts") else None
            if fs.get("first_trade") and age is not None and age > 20 and not s["signal"]:
                banner += f"  |  FEED STALE {age:.0f}s: CHECK TRADINGVIEW"
            if fs.get("finnhub") != "connected":
                banner += f"  |  FINNHUB {fs.get('finnhub')}"
            if fs.get("source") == "alpaca":
                banner += "  |  ON IEX BACKUP: CHECK EVERY SIGNAL BY EYE"
        banner_style = {"background": COLORS[state], "padding": "14px 18px", "borderRadius": "8px",
                        "fontSize": "30px", "fontWeight": "800"}

        def pct(x):
            return f"{x/off-1:+.1%}" if x else "-"
        last = fs.get("tick") or s["last"]
        hi = max(s["runmax"], last) if (s["runmax"] and last) else (s["runmax"] or last)
        mins = ((s["last_ts"] - s["first_ts"]).total_seconds() / 60 - 1) if s["first_ts"] is not None else None
        to_floor = f"{last/s['floor']-1:+.1%}" if (s["armed"] and last) else "not armed"
        k_lbl = f"high -{s['k_now']*100:.0f}%"
        metrics = [
            card("LAST" + (" (tick)" if feed else ""), f"${last:.2f}" if last else "-", pct(last) + " vs IPO"),
            card("DAY HIGH", f"${hi:.2f}" if hi else "-", pct(hi)),
            card(f"FLOOR ({k_lbl})", f"${s['floor']:.2f}" if s["armed"] else "-",
                 pct(s["floor"]) if s["armed"] else f"arms at ${off*(1+r.arm):.2f}"),
            card("TO FLOOR", to_floor, f"hard stop ${off*(1+r.stop):.2f}" if r.stop else ""),
            card("SIGNAL", s["signal"]["reason"] if s["signal"] else "none",
                 (f"{s['signal']['ts'].tz_convert(UK):%H:%M} at ${s['signal']['price']:.2f}"
                  if s["signal"] else "")),
            card("UK TIME", (pd.Timestamp.now(tz=UK) if feed else s["last_ts"].tz_convert(UK)).strftime("%H:%M:%S")
                 if (feed or s["last_ts"] is not None) else "-", "cut-off 20:30"),
            card("MINS SINCE FIRST TRADE", f"{mins:.0f}" if mins is not None else "-",
                 "grace trail" if (mins is not None and mins < r.grace_min) else ""),
            card("IPO PRICE", f"${off:.2f}"),
        ]
        if feed:
            ctx, ref = fs.get("ctx"), fs.get("ctx_ref")
            metrics.append(card(f"{feed.ctx_sym} SINCE 1ST TRADE",
                                f"{ctx/ref-1:+.2%}" if (ctx and ref) else (f"${ctx:.2f}" if ctx else "-"),
                                "market context"))
            hn = fs.get("hi_n")
            metrics.append(card("HIGH SUPPORT", f"{hn} trades" if hn else "-",
                                (f"{fs.get('hi_v', 0):,} sh at ${fs.get('hi'):.2f}"
                                 + ("  ONE PRINT: CHECK BY EYE" if hn == 1 else "")) if hn else ""))
            perp = fs.get("perp")
            metrics.append(card(f"PERP {feed.perp or ''}", f"${perp:.2f}" if perp else "-",
                                (f"basis {perp/last-1:+.1%}  hl {fs.get('hl')}" if (perp and last)
                                 else f"hl {fs.get('hl')}")))
        B = pd.DataFrame(s["bars"])
        f1, f2 = go.Figure(), go.Figure()
        for f in (f1, f2):
            f.update_layout(template="plotly_dark", margin=dict(l=40, r=20, t=10, b=30),
                            paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", showlegend=False)
        if not B.empty:
            x = pd.to_datetime(B["ts"]).dt.tz_convert(UK)
            f1.add_scatter(x=x, y=B["close"], line=dict(color="#e5e7eb", width=2))
            f1.add_scatter(x=x, y=B["runmax"], line=dict(color="#16a34a", dash="dot"))
            f1.add_scatter(x=x, y=B["floor"], line=dict(color="#dc2626", width=2, shape="hv"))
            for y, col, name in [(off, "#9ca3af", "IPO"), (off * (1 + r.arm), "#2563eb", "arm")] + \
                    ([(off * (1 + r.stop), "#7f1d1d", "stop")] if r.stop else []):
                f1.add_hline(y=y, line=dict(color=col, dash="dash", width=1),
                             annotation_text=name, annotation_position="left")
            if s["signal"]:
                f1.add_vline(x=s["signal"]["ts"].tz_convert(UK), line=dict(color="#dc2626", width=3))
            d = (B["close"] / B["floor"] - 1) * 100
            f2.add_bar(x=x, y=d, marker_color=["#dc2626" if v < 0 else "#16a34a" for v in d.fillna(0)])
            f2.add_hline(y=0, line=dict(color="#e5e7eb", width=1))
            f2.update_yaxes(title_text="% to floor")
        ev = "\n".join(f"{t.tz_convert(UK):%H:%M}  {st:8s} {m}" for t, st, m in reversed(s["events"][-12:]))
        if feed:
            ev = (f"feed: finnhub {fs.get('finnhub')} | backup alpaca-iex {fs.get('alp')} | "
                  f"source now {fs.get('source')} | trades {fs.get('n_trades')} | backup prints used "
                  f"{fs.get('alp_used')} | filtered (cond/odd lot) {fs.get('filtered')} | rejected jumps "
                  f"{fs.get('rejected')} | level resets {fs.get('resets')} | late prints dropped "
                  f"{feed.builder.late}\n\n") + ev
        return banner, banner_style, metrics, f1, f2, ev

    return app


def replay(eng, df, speed):
    _time.sleep(4)
    for ts, row in df.iterrows():
        with LOCK:
            eng.on_bar(ts, row.open, row.high, row.low, row.close)
        _time.sleep(speed)


def main():
    global MUTE
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--replay", default=None)
    ap.add_argument("--speed", type=float, default=0.3)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--sym", default="ANT")
    ap.add_argument("--offer", type=float, default=83.0)
    ap.add_argument("--ctx", default="QQQ")
    ap.add_argument("--perp", default=None)
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    MUTE = a.mute
    if a.check:
        check()
        return
    if a.live:
        from live import LiveFeeds
        key = os.getenv("FINNHUB_KEY")
        if not key:
            raise SystemExit("FINNHUB_KEY missing in .env")
        eng = ExitEngine(a.offer, Rule(), on_change=None)
        day = pd.Timestamp.now(tz=ET).strftime("%Y%m%d")
        blog = f"logs/bars_{a.sym}_{day}.csv"
        if os.path.exists(blog) and os.path.getsize(blog) > 0:      # crash recovery: rebuild state
            prev = pd.read_csv(blog, header=None, names=["m", "o", "h", "l", "c"])
            for r in prev.itertuples():
                eng.on_bar(pd.Timestamp(r.m).tz_convert(ET), r.o, r.h, r.l, r.c)
            print(f"RESUMED from {blog}: {len(prev)} bars, state {eng.state}, day high {eng.runmax}")
        eng.on_change = notify

        def on_bar(m, o, h, l, c):
            with LOCK:
                eng.on_bar(m, o, h, l, c)
        bk = None if a.no_backup else (os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET"))
        feed = LiveFeeds(a.sym, on_bar, ctx_sym=a.ctx, perp=a.perp,
                         backup_keys=bk if (bk and bk[0]) else None)
        feed.start(key)
        print(f"LIVE {a.sym} offer ${a.offer}. Open http://127.0.0.1:8050")
        make_app(eng, f"LIVE {a.sym}", feed).run(debug=False, port=8050)
        return
    sym = a.replay or "SPCX"
    eng = ExitEngine(OFFER[sym], Rule(), on_change=notify)
    threading.Thread(target=replay, args=(eng, load(sym), a.speed), daemon=True).start()
    print("Open http://127.0.0.1:8050  (replay starts in 4 s)")
    make_app(eng, f"REPLAY {sym}").run(debug=False, port=8050)


if __name__ == "__main__":
    main()
