# ANT day-one runbook (Thursday 19 November 2026, UK times)

The operating procedure as used on the day, kept unchanged apart from formatting.

RULE v1.1 is FROZEN. No code or parameter changes after 15:00.

## POSITION (AJ Bell contract note, 19/11/26 08:00)
- 34 shares ANT at GBP 63.199574 (= $83 at GBP/USD 1.3133). Cost GBP 2,148.79, no dealing charge.
- Settlement 20/11/26. Refund of unused cash about GBP 101.
- Break-even after sale costs (GBP 5 + 0.75% FX): about $83.82 (+1.0%), if GBP/USD stays ~1.313.
- AJ Bell sell quantity to type in: 34.

## Morning
- 07:00  Check xyz:ANT perp (trade.xyz) and the Trump-Xi readouts.
- 08:00  RING AJ BELL (0345 54 32 600): will ANT be sellable online the moment it trades,
         before settlement? If not, the model is moot; ask what time shares appear.
         Also ask: app/web session timeout length, and any online size limit for a new US listing.
- 08:15  python 13_live_open_test.py and python 15_halt_and_filter_check.py -> every line PASS.
- 08:00-12:00  AJ Bell allocation email: shares, GBP used, refund.
               Update SHARES in 12_ant_monte_carlo.py and rerun for the final GBP numbers.
- 09:00  Rehearsal 1 (US pre-market):
         python app.py --live --sym NVDA --offer <NVDA price x 0.9> --perp xyz:NVDA
         Check: trades counting up, bars appearing each minute, source = finnhub,
         backup alpaca-iex = connected.
- 14:30  Rehearsal 2 (US open), 15 min. Check sounds and phone push (ntfy) fire.
- 14:00  OPERATIONAL CHECKS
  1. Feed vs SIP: from 14:30 run  python app.py --live --sym QQQ --offer <QQQ x 0.95>  for ~20 min.
     Compare several 1-min highs/closes (dashboard or logs/bars_QQQ_*.csv) with TradingView NASDAQ:QQQ 1-min:
     must match within a cent or two. Feed line must say "source now finnhub". Stop it before 16:00 (port 8050).
     Post-halt 3-print reset already tested offline (15, A3 PASS); live, watch "level resets" after any halt.
     At ~14:50 run  python 17_condition_log.py QQQ  -> confirms Finnhub's condition-code encoding and that
     the filter removes only a few % of normal-size trades. Then stop the QQQ app.
     ONE Finnhub connection per key: never run two live apps, a notebook or any other script with FINNHUB_KEY.
  0. Clock:  sudo sntp -sS time.apple.com  (bars use exchange timestamps; the 65 s fallback uses the laptop clock).
  2. Mac and phone: run  caffeinate -dimsu &  before starting the ANT app; charger in, lid open.
     Pause macOS updates. Phone hotspot ready in case Wi-Fi drops.
     NTFY_TOPIC must be a long random string (a public topic name could be used to push a fake SELL).
     Test push:  curl -d "test" ntfy.sh/<NTFY_TOPIC>  and confirm it arrives through iOS Focus:
     Settings > Focus > (each Focus) > Apps > allow ntfy; enable Time Sensitive for ntfy. macOS Focus off.
- 15:00  FREEZE.

## Afternoon set-up (16:00)
1. Terminal:  python app.py --live --sym ANT --offer 83 --perp xyz:ANT
2. Chrome tab 1: http://127.0.0.1:8050   tab 2: TradingView NASDAQ:ANT (1-min)
3. Phone: AJ Bell app, logged in, ANT sell screen, quantity = all shares typed in.
4. Mac on charger, sleep disabled, sound on.

## Expected (perp +18.5% calibration, 2 precedents)
- First trade 16:45-18:30. Open +9% to +19% ($90-99).
- Day high about +24% (~$103). 20:30 price about +15% (~$95.50).
- Monte Carlo (35 sh): rule mean ~GBP 300, P(loss) ~5%, worst-5% about breakeven.

## Rule v1.1 (what the dashboard does)
- Arms once day high >= $91.30.
- Floor = day high x 0.92 for first 15 min after first trade, then x 0.96. Floor only moves up.
- WATCH: 2% below high (yellow banner, SILENT: during the first 15 min this is normal noise).  WARNING: one 1-min close below floor -> open AJ Bell quote screen.
- SELL: second consecutive 1-min close below floor -> SELL ALL, accept quote within 30 s.
- HARD STOP: two 1-min closes below $78.85 (after first 5 min) -> SELL ALL.
- CUT-OFF: 20:30 sell everything still held (AJ Bell online US dealing ends 21:00).

## At the first trade
- Feed line must say: source now finnhub. If it says alpaca, cross-check TradingView.
- Supply wall: insiders can sell up to ~316m shares today; expect selling at round numbers,
  especially $100. Context only, NOT an input to the rule.

## AJ Bell session (session timeout risk)
- Log in to the AJ Bell APP fresh when ANT's first trade prints, and tap inside it every 10 minutes.
- Re-open the ANT sell screen at every WARNING. Keep the 2FA device next to you.

## Trading halts (LULD pauses)
- During a halt there are no trades and NO bars; empty minutes never count as closes.
- SELL still needs two completed bars WITH trades below the floor (tested: 15_halt_and_filter_check.py).
- The reopening auction print is accepted even if it gaps more than 15% (3 agreeing prints).
- AJ Bell will not quote during a halt. If WARNING fired before a halt, expect to sell after the reopen.

## Override policy (written 02:10, before the open). Act outside the rule ONLY if:
1. AJ Bell will not quote (then retry, then phone 0345 54 32 600);
2. the feed is plainly wrong when checked by eye against TradingView;
3. the hard stop fires.
A feeling that ANT is strong or weak is NOT a reason.

## Live definition (for the post-mortem)
- Bars from Finnhub trades excluding SIP conditions Z,U,T,4,7,W,H,I,B,C,N,P,R,V and size < 100.
- Equivalent to the backtest's exclusion of odd-lot condition I while the round lot is 100 (price < $250).

## Pre-registered expectation (02:10, before the open)
- Central estimate about GBP 195 on 35 shares, about 15% chance of a loss
  (40% grey-market / 30% weak-open / 30% perp-calibrated scenarios).
- Day high within 30 min of first trade: about 55%. Close below $83: about 12%.
- UPDATE 10:50, 34 shares, after the morning sweep (grey market +20-26%, perp ~$102.5):
  Monte Carlo (12, --shares 34): grey-market-today scenario rule mean GBP 486 vs hold 465, P(loss) 0% vs 2.6%,
  P5 +242 vs +87, capture 0.77 (model slightly optimistic on the close: sim +22% vs perp-implied ~+19%).
  Blend 50% grey-today / 25% perp-calibrated / 15% SpaceX-like weak open / 10% FT +4% block:
  PRE-REGISTERED: mean about GBP 355, P(loss) about 5%. Central exit $96-100 -> GBP 310-415.

## More rules decided in advance (02:45)
- SELL fired but cannot execute: keep requesting quotes and sell at the FIRST quote you get, whatever the
  price has done since. The engine no longer protects you after SELL. No second thoughts.
- Banner says ON IEX BACKUP: every WARNING/SELL is checked by eye against TradingView before acting.
- HIGH SUPPORT card says ONE PRINT: the day high may be a bad or busted print -> check by eye (override 2).
- First trade after 20:00 UK (15:00 ET): do NOT use the engine (untested). Sell only if the hard stop
  fires; otherwise hold overnight and re-plan on Friday morning.
- Small allocation (e.g. under 10 shares): the GBP 5 fee is >1% of the position and the rule's money edge
  is near zero. Run it anyway: it becomes a research test, not a profit decision.

## If something breaks
- Banner FEED STALE: read price from TradingView; backup feed should take over in 15 s.
- Dashboard crashes: rerun the same command; it RESUMES from logs/bars_ANT_<date>.csv.
- Everything down: apply rule by hand. Floor = day high x 0.92 (first 15 min) then x 0.96.
- AJ Bell "quote unavailable": retry once, then phone 0345 54 32 600 (GBP 25).
- Never sell in the first minutes because of nerves; never hold past 20:45.

## After
- Keep logs/ticks_ANT_*.csv and logs/bars_ANT_*.csv for the post-mortem (script 18).
