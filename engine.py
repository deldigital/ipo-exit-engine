"""
engine.py  -  ANT exit engine, RULE v1.1 (19 Nov 00:55: 8% grace trail for first 15 min). Same code runs in replay and live.
Decisions are taken only on 1-minute bar closes, exactly as in research scripts 02/03.
"""
from dataclasses import dataclass
from datetime import time

ET = "America/New_York"
UK = "Europe/London"


@dataclass
class Rule:
    arm: float = 0.10          # arm trail once day high >= offer * 1.10
    trail: float = 0.04        # floor = day high * 0.96 after the grace period
    grace_trail: float | None = 0.08  # first 15 min after first trade: floor = high * 0.92
    grace_min: float = 15
    watch: float = 0.02        # WATCH below day high * 0.98
    confirm: int = 2           # consecutive 1-min closes below floor -> SELL
    stop: float | None = -0.05 # hard stop vs offer (None = off)
    stop_after_min: float = 5
    cutoff_et: time = time(15, 30)


class ExitEngine:
    def __init__(self, offer, rule=None, on_change=None, bar_sec=60):
        self.bar_sec = bar_sec
        self.offer = float(offer)
        self.r = rule or Rule()
        self.on_change = on_change
        self.first_ts = None
        self.runmax = None
        self.armed = False
        self.below = 0
        self.stop_below = 0
        self.state = "WAITING"
        self.msg = "Waiting for first trade"
        self.signal = None
        self.last = None
        self.last_ts = None
        self.bars = []
        self.events = []
        self.k_now = self.r.grace_trail if self.r.grace_trail is not None else self.r.trail

    @property
    def floor(self):
        return self.runmax * (1 - self.k_now) if self.runmax else None

    def _set(self, state, ts, msg):
        self.msg = msg
        if state != self.state:
            self.state = state
            self.events.append((ts, state, msg))
            if self.on_change:
                self.on_change(state, msg)

    def _fire(self, ts, price, reason):
        self.signal = dict(ts=ts, price=price, reason=reason)
        self._set("SELL", ts, f"{reason}: SELL ALL NOW (last close ${price:.2f})")

    def on_bar(self, ts, o, h, l, c):
        """ts = bar start (tz-aware). Called once per completed 1-minute bar."""
        import pandas as pd
        ts_close = ts + pd.Timedelta(seconds=self.bar_sec)
        self.last, self.last_ts = c, ts_close
        if self.signal is None:
            if self.first_ts is None:
                self.first_ts = ts
                self._set("LIVE", ts_close, f"First trade. Open ${o:.2f} ({o/self.offer-1:+.1%})")
            mins = (ts - self.first_ts).total_seconds() / 60
            self.k_now = (self.r.grace_trail if (self.r.grace_trail is not None and mins < self.r.grace_min)
                          else self.r.trail)
            if ts.tz_convert(ET).time() >= self.r.cutoff_et:
                self._fire(ts_close, c, "CUTOFF 20:30 UK")
            else:
                self.runmax = h if self.runmax is None else max(self.runmax, h)
                if not self.armed and self.runmax >= self.offer * (1 + self.r.arm):
                    self.armed = True
                fl = self.floor
                self.below = self.below + 1 if (self.armed and c < fl) else 0
                stop_px = self.offer * (1 + self.r.stop) if self.r.stop is not None else None
                self.stop_below = (self.stop_below + 1
                                   if (stop_px and mins >= self.r.stop_after_min and c < stop_px) else 0)
                if self.below >= self.r.confirm:
                    self._fire(ts_close, c, "TRAIL BREACH CONFIRMED")
                elif self.stop_below >= self.r.confirm:
                    self._fire(ts_close, c, "HARD STOP CONFIRMED")
                elif self.below >= 1:
                    self._set("WARNING", ts_close, f"Close ${c:.2f} below floor ${fl:.2f}. Open AJ Bell sell screen")
                elif self.stop_below >= 1:
                    self._set("WARNING", ts_close, f"Close ${c:.2f} below hard stop ${stop_px:.2f}")
                elif self.armed and c < self.runmax * (1 - self.r.watch):
                    self._set("WATCH", ts_close, f"Pulling back: {c/self.runmax-1:+.1%} from high")
                elif self.armed:
                    self._set("ARMED", ts_close, f"Trail armed. Floor ${fl:.2f}")
                else:
                    self._set("LIVE", ts_close, f"Not armed until ${self.offer*(1+self.r.arm):.2f}")
        self.bars.append(dict(ts=ts_close, close=c, high=h, runmax=self.runmax,
                              floor=self.floor if self.armed else None, state=self.state))

    def snapshot(self):
        return dict(state=self.state, msg=self.msg, last=self.last, last_ts=self.last_ts,
                    runmax=self.runmax, floor=self.floor, armed=self.armed, offer=self.offer,
                    first_ts=self.first_ts, signal=dict(self.signal) if self.signal else None,
                    bars=list(self.bars), events=list(self.events), rule=self.r, k_now=self.k_now)
