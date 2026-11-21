"""
live.py  -  live feeds for the exit engine (script 05).
Finnhub WebSocket trades (ANT + QQQ) -> 1-minute bars -> engine.on_bar
Hyperliquid WebSocket trades (xyz:ANT perp) -> context only, never drives decisions.
Every ANT trade and every closed bar is logged to logs/ for the post-mortem.
"""
import asyncio
import json
import os
import threading
import time

import pandas as pd
import websockets

ET = "America/New_York"
# SIP letter exclusions as in the backtest (script 07). Digit codes removed: Finnhub's own encoding is
# unverified and a digit could mean a REGULAR trade in it. Odd lots are removed by size < 100, which was
# verified identical to condition 'I' (script 15 B1). Verify Finnhub's codes with 17_condition_log.py.
BAD_COND = {"Z", "U", "T", "W", "H", "I", "B", "C", "N", "P", "R", "V"}
MIN_SIZE = 100


class BarBuilder:
    """Aggregates trades into 1-minute OHLC bars (ET minutes). Closes a bar when the
    next minute's first trade arrives, or 65 s after the minute started if trading is thin."""

    def __init__(self, on_bar):
        self.on_bar = on_bar
        self.cur = None
        self.late = 0                    # prints for an already-closed minute (dropped, as in backtest)
        self.lock = threading.Lock()

    def add(self, ts_ms, price):
        m = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert(ET).floor("min")
        with self.lock:
            if self.cur is not None and m < self.cur["m"]:
                self.late += 1
                return                               # late print for a closed minute: ignore
            if self.cur is not None and m > self.cur["m"]:
                self._close()
            if self.cur is None:
                self.cur = dict(m=m, o=price, h=price, l=price, c=price)
            else:
                c = self.cur
                c["h"], c["l"], c["c"] = max(c["h"], price), min(c["l"], price), price

    def _close(self):
        c, self.cur = self.cur, None
        self.on_bar(c["m"], c["o"], c["h"], c["l"], c["c"])

    def flush_if_due(self):
        with self.lock:
            if self.cur is not None and pd.Timestamp.now(tz="UTC") >= \
                    self.cur["m"].tz_convert("UTC") + pd.Timedelta(seconds=65):
                self._close()


class LiveFeeds:
    def __init__(self, sym, on_bar, ctx_sym="QQQ", perp=None, max_jump=0.15, backup_keys=None):
        self.backup_keys = backup_keys          # (alpaca_key, alpaca_secret) -> IEX backup feed
        self.sym, self.ctx_sym, self.perp = sym, ctx_sym, perp
        self.max_jump = max_jump
        self.builder = BarBuilder(self._bar)
        self.on_bar_cb = on_bar
        self.state = dict(finnhub="connecting", hl="off" if not perp else "connecting",
                          tick=None, tick_ts=None, n_trades=0, rejected=0,
                          ctx=None, ctx_ref=None, perp=None, perp_ts=None, first_trade=False,
                          fh_ts=None, fh_ant_ts=None, alp="off" if not backup_keys else "connecting",
                          alp_used=0, source="-", filtered=0, resets=0)
        self.pending_jump = []          # consecutive out-of-band prints (possible genuine level shift)
        os.makedirs("logs", exist_ok=True)
        day = pd.Timestamp.now(tz=ET).strftime("%Y%m%d")
        self.tick_log = open(f"logs/ticks_{sym}_{day}.csv", "a", buffering=1)
        self.bar_log = open(f"logs/bars_{sym}_{day}.csv", "a", buffering=1)

    # ---------- handlers ----------
    def _bar(self, m, o, h, l, c):
        self.bar_log.write(f"{m.isoformat()},{o},{h},{l},{c}\n")
        self.on_bar_cb(m, o, h, l, c)

    def _trade(self, s, t_ms, p, src="finnhub", v=None, cond=None):
        st = self.state
        now = time.time()
        if src == "finnhub":
            st["fh_ts"] = now                        # heartbeat = ANY Finnhub trade (QQQ flows all day)
        if s == self.sym:
            if src == "finnhub":
                st["fh_ant_ts"] = now
            elif st["fh_ts"] is not None and now - st["fh_ts"] < 15:
                return                               # primary connection alive: ignore backup prints
            else:
                st["alp_used"] += 1
            cset = {str(x) for x in (cond or [])}
            self.tick_log.write(f"{t_ms},{p},{v},{src},{'|'.join(sorted(cset))}\n")
            if (cset & BAD_COND) or (v is not None and v < MIN_SIZE):
                st["filtered"] += 1                  # same exclusions as the backtest
                return
            last = st["tick"]                        # seeded by the FIRST accepted print, never by the offer
            if last is not None and abs(p / last - 1) > self.max_jump:
                self.pending_jump.append(p)
                pj = self.pending_jump[-3:]
                if len(pj) == 3 and max(pj) / min(pj) - 1 < 0.01:
                    st["resets"] += 1                # 3 consecutive prints agree: genuine level shift
                    self.pending_jump = []
                else:
                    st["rejected"] += 1
                    return
            else:
                self.pending_jump = []
            if not st["first_trade"]:
                st["first_trade"] = True
                st["ctx_ref"] = st["ctx"]            # QQQ level at ANT's first trade
            st["tick"], st["tick_ts"], st["source"] = p, time.time(), src
            hi = st.get("hi")                        # support behind the day high (busted-trade check)
            if hi is None or p > hi:
                st["hi"], st["hi_n"], st["hi_v"] = p, 1, int(v or 0)
            elif p >= hi - 0.01:
                st["hi_n"] += 1
                st["hi_v"] += int(v or 0)
            st["n_trades"] += 1
            self.builder.add(t_ms, p)
        elif s == self.ctx_sym:
            st["ctx"] = p

    # ---------- websocket tasks ----------
    async def _finnhub(self, key):
        url = f"wss://ws.finnhub.io?token={key}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    for s in (self.sym, self.ctx_sym):
                        await ws.send(json.dumps({"type": "subscribe", "symbol": s}))
                    self.state["finnhub"] = "connected"
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "trade":
                            for d in msg.get("data", []):
                                self._trade(d["s"], int(d["t"]), float(d["p"]), "finnhub",
                                            d.get("v"), d.get("c"))
            except Exception as ex:
                self.state["finnhub"] = f"reconnecting ({type(ex).__name__})"
                await asyncio.sleep(2)

    async def _hyperliquid(self):
        url = "wss://api.hyperliquid.xyz/ws"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    await ws.send(json.dumps({"method": "subscribe",
                                              "subscription": {"type": "trades", "coin": self.perp}}))
                    self.state["hl"] = "connected"
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("channel") == "trades":
                            for t in msg.get("data", []):
                                self.state["perp"], self.state["perp_ts"] = float(t["px"]), time.time()
            except Exception as ex:
                self.state["hl"] = f"reconnecting ({type(ex).__name__})"
                await asyncio.sleep(3)

    async def _alpaca(self):
        url = "wss://stream.data.alpaca.markets/v2/iex"
        key, sec = self.backup_keys
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    await ws.recv()
                    await ws.send(json.dumps({"action": "auth", "key": key, "secret": sec}))
                    await ws.recv()
                    await ws.send(json.dumps({"action": "subscribe", "trades": [self.sym]}))
                    self.state["alp"] = "connected"
                    async for raw in ws:
                        for m in json.loads(raw):
                            if m.get("T") == "t":
                                t_ms = pd.Timestamp(m["t"]).value // 1_000_000
                                self._trade(m["S"], t_ms, float(m["p"]), "alpaca", m.get("s"), m.get("c"))
            except Exception as ex:
                self.state["alp"] = f"reconnecting ({type(ex).__name__})"
                await asyncio.sleep(3)

    async def _flusher(self):
        while True:
            self.builder.flush_if_due()
            await asyncio.sleep(1)

    async def _main(self, key):
        tasks = [self._finnhub(key), self._flusher()]
        if self.perp:
            tasks.append(self._hyperliquid())
        if self.backup_keys:
            tasks.append(self._alpaca())
        await asyncio.gather(*tasks)

    def start(self, key):
        threading.Thread(target=lambda: asyncio.run(self._main(key)), daemon=True).start()
