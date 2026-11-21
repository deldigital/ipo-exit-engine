# IPO day-one exit engine

A rules-based decision-support system for selling an IPO allocation on its first day of trading. It watches live trades, keeps a trailing floor under the day's high and signals when to sell. I built it for a UK retail allocation in the Anthropic IPO (Nasdaq: ANT, 19 November 2026, offer price $83). Selling was manual, because the broker (AJ Bell) does not offer limit or stop orders on US shares.

The rule was designed and validated overnight on 18 to 19 November 2026, frozen at 15:00 UK on the day, and run live that afternoon. For every formal test, including the post-trade review, the hypotheses and pass criteria were written in the script header before the script was run.

> Research and educational project. Not investment advice.

---

## 1. Outcome on the day

| Item | Detail |
|---|---|
| Allocation | 34 shares at $83 (GBP 2,148.79) |
| Opening cross | 11:48:24 ET, 108,086,607 shares at $111.50 (+34.3% on the offer) |
| Day high | $115.10, a 125-share print one second after the cross |
| SELL signal | 12:01 ET, second consecutive 1-minute close below the 8% grace floor |
| Fill | $105.03 (+26.5%) |
| Net result | GBP 550 after dealing charge and FX |
| Close | $97.17 (+17.1%); day low $92.72 |

| Exit | Price | Net P&L (GBP) |
|---|---|---|
| Rule v1.1 (as executed) | $105.03 | 550 |
| Hold to the 15:30 ET cut-off | $95.09 | 294 |
| Hold to the official close | $97.17 | 348 |
| First obtainable quote, 1 / 2 / 3 minutes after the cross | $111.67 / $110.94 / $107.47 | 721 / 702 / 613 |
| Day high (hindsight only) | $115.10 | 810 |

The rule kept 68.6% of the move from the offer price to the day high and beat holding. It lost to selling at the first obtainable quote, because the stock peaked within seconds of the cross: it traded at $113 or above for only 47 seconds in total.

Expectation written before the open, after the allocation was known: a mean outcome of about GBP 355 and about a 5% chance of a loss.

---

## 2. Problem

| Item | Detail |
|---|---|
| Position | UK retail IPO allocation, 34 shares at $83 |
| Objective | One exit, as close as possible to the day's peak, with robustness preferred to in-sample performance |
| Broker constraints | Manual sterling quotes valid for about 15 seconds; no limit or stop orders on US shares; online dealing 14:30 to 21:00 UK; GBP 5 per deal plus 0.75% FX |
| Execution delay | 10 to 40 seconds from signal to fill |
| Horizon | First trading day, hard exit 15:30 ET (20:30 UK) |

The engine therefore does not trade. It produces WATCH, WARNING and SELL signals, and the holder executes.

---

## 3. The rule (v1.1, frozen 19 November 2026)

All decisions are taken on completed 1-minute bars built from trades.

| Element | Specification |
|---|---|
| Arming | The trail activates once the day's high is at least offer x 1.10 ($91.30) |
| Floor | Running high x 0.92 for the first 15 minutes after the first trade, then x 0.96. The floor only moves up |
| WATCH | Close below running high x 0.98 (silent, information only) |
| WARNING | First 1-minute close below the floor: open the broker's sell screen |
| SELL | Second consecutive 1-minute close below the floor: sell everything |
| Hard stop | Two consecutive 1-minute closes below offer x 0.95 ($78.85), after the first 5 minutes |
| Cut-off | Sell any remaining position at 15:30 ET |
| Halts | Empty minutes are not closes; SELL needs two completed bars that contain trades |

SELL latches: once it fires, the engine makes no further decisions. If the open is modest, the trail may never arm, and the rule reduces to holding to 15:30 ET unless the hard stop fires.

**Why a stopping rule can add value at all.** If the price is a martingale, the optional stopping theorem says no stopping rule beats holding in expectation. A rule can still change the shape of the outcome, and it can raise the mean only if there is predictable structure, such as uncertainty about the sign of the drift or reversal after a peak (du Toit and Peskir, 2009; Shiryaev, Xu and Zhou, 2008; Ekström and Vaicenavicius, 2016; Kaminski and Lo, 2014). I treat v1.1 as an insurance rule rather than a source of excess return.

---

## 4. Data

| Dataset | Source | Use |
|---|---|---|
| Day-one 1-minute consolidated (SIP) bars, 20 IPOs, 2019 to 2026 | Alpaca market data, free plan | Rule search and validation |
| Raw trades for SPCX, CBRS, ARM and RIVN (11.7m trades) | Alpaca trades endpoint | Tick-level validation, 1-second bars |
| QQQ 1-minute bars on the same days | Alpaca | Market-context test |
| Six direct listings (SPOT, WORK, PLTR, ASAN, RBLX, COIN) | Alpaca | Holdout for heavy day-one insider supply |
| Pre-IPO perpetual futures (xyz:SPCX, xyz:CBRS, xyz:ANT) | Hyperliquid public API | Calibrating the open, high and close |

The 20 IPOs: SPCX, CBRS, ARM, FIG, CRCL, CRWV, RDDT, RIVN, ABNB, DASH, SNOW, UBER, LYFT, ZM, PINS, CAVA, KVYO, BIRK, CHYM, KLAR. Three closed below their offer price. For ANT, mega deals (SPCX, ARM, RIVN, UBER, CRWV) were weighted x3 and modest-pop deals x2. The weights were set by judgement after seeing the data; the effective sample size is 16.6.

Trades are filtered on SIP condition codes (Z, U, T, 4, 7, W, H, I, B, C, N, P, R, V). Live, trades under 100 shares are also excluded. On 200,000 raw SpaceX trades this matched the odd-lot condition exactly, and minute highs rebuilt from the filtered trades matched the vendor bars in every minute.

Market data is not included in this repository; the scripts download it.

---

## 5. Research before the trade (scripts 01 to 16)

| Script | Question | Result |
|---|---|---|
| 01 | Shape of day one | First trade 113 to 268 minutes after 09:30 ET. Time to peak is bimodal: 14 of 20 peaked within 15 minutes, but the largest deals peaked late (SPCX at 84 minutes, ARM at 227). Pullbacks before the peak 4 to 16% |
| 02 | Rule search (864 variants) | Flat plateau for 4% to 8% trails. A 2-minute lag beat a 1-minute lag, so breaches partly reverse: confirmation is needed |
| 03 | Confirmation and weighted bootstrap | 4% trail, armed at +10%, two confirming closes. Selling half at +25% cost 1.7 points and was dropped |
| 03b | Grace period | An 8% trail for the first 15 minutes passed every pre-set test. A 30-minute version, which would have helped SpaceX, failed them |
| 06 | Nested leave-one-out cross-validation of the whole selection | The same rule was chosen in 17 to 19 of 20 folds. Out-of-sample gain over holding +5.8 to +6.7 points (in-sample 7.0); 11 wins, 7 losses (sign test p = 0.24). On the five largest deals only +0.1 to +1.2 points |
| 07, 08 | Tick-level validation | Bars rebuilt from ticks match vendor bars exactly. Dips are no deeper at 1-second resolution. Decision bars of 30 and 15 seconds did worse than 1-minute bars |
| 09 | Market context (IPO return minus beta x QQQ) | Rejected: no out-of-sample gain. The opening chop is stock-specific |
| 10 | Chop versus top: session VWAP, Bayesian online changepoint detection | Rejected: every variant did worse than v1.1 |
| 11 | Perpetual futures against the actual day | The open relative to the perp premium was unpredictable (0.47 and 1.05); the high (1.31x and 1.28x) and close (0.83x and 0.81x) were consistent, on two deals |
| 12 | Monte Carlo of the GBP outcome | Block bootstrap run through the live engine code. A description of the distribution, not an independent test: it resamples the deals the rule was chosen on |
| 13 | Live-code tests | +20% open, odd lots, out-of-sequence prints, level shift, feed failover, 15-minute switch: all pass |
| 14 | Direct listings | All six peaked within 30 minutes; the rule beat holding on five of six |
| 15 | Halts and filter consistency | Halt handling and the odd-lot filter verified on the live code: all pass |
| 16 | Remaining ideas, with the adoption test fixed in advance | All nine rejected (section 6) |

### Ideas tested and rejected

| Idea | Why it was rejected |
|---|---|
| Volatility-scaled trail | Lost to fixed-percentage trails at 1-minute resolution |
| Selling half at a fixed target | Lower variance but 1.7 points worse on average |
| Faster decision bars (30 s, 15 s) | More noise, lower capture |
| Market context (QQQ beta) | No out-of-sample gain |
| Session VWAP filter | Worse than the baseline in sample |
| Bayesian online changepoint detection | Worse than the baseline |
| Two of the last three closes below the floor | Never selected out of sample |
| Smooth taper instead of the minute-15 switch | Worse on SpaceX and on the direct listings |
| Instant sale on one deep breach | Worse: deep breaches also reverse |
| Bayesian drift-learning overlay | Practically identical to v1.1 |

With price, volume, VWAP, market and changepoint features on 20 IPOs, I could not separate opening chop from a genuine top on the largest deals.

---

## 6. Live system

```
Finnhub WebSocket (ANT, QQQ trades) ──┐
Alpaca IEX WebSocket (backup) ────────┼─> filters ─> 1-minute bar builder ─> ExitEngine (rule v1.1) ─> Dash dashboard
Hyperliquid WebSocket (xyz:ANT perp) ─┘                                                               sounds, phone push,
                                                                                                      tick and bar logs
```

| Component | Detail |
|---|---|
| Primary feed | Finnhub trade WebSocket |
| Backup feed | Alpaca IEX WebSocket |
| Filters | Condition codes, odd lots, and a 15% jump filter that resets after three agreeing prints |
| Bar builder | Closes a bar on the next minute's first trade, or 65 seconds after the minute starts |
| Context only | QQQ since the first trade; Hyperliquid perp price and basis. Never used for decisions |
| Dashboard | State banner, last price, day high, floor, distance to floor, minutes since the first trade, trades supporting the day high, chart with high, floor, offer, arming and stop lines, event log |
| Alerts | WARNING and SELL trigger a laptop sound and a phone push |
| Resilience | Automatic reconnection, crash recovery from the bar log, stale-feed and backup-feed banners |

`RUNBOOK.md` is the operating procedure used on the day, including the override policy written before the open.

---

## 7. Post-trade review (scripts 18 to 22)

| Script | Question | Result |
|---|---|---|
| 18 | ANT post-mortem | Capture 68.6% of the offer-to-high move. The rule beat holding to 15:30 ET and to the close, and lost to the first obtainable quote. The perp calibration predicted the high and close within 4% but understated the open by 6.6%. After the open the perp moved with the stock in the same minute (correlation 0.98), with no lead |
| 18 | Feeds | Finnhub delivered no ANT trades all day; the IEX backup carried the whole session. IEX 1-minute closes were within 0.13% of consolidated closes, and the engine replayed on consolidated bars fired SELL in the same minute |
| 19 | 27 deals (20 IPOs, 6 direct listings, ANT): rule against selling 2 minutes after the open | A tie: +0.12 points on average, better in 13 of 27. Both beat holding by about 7.5 points. Which one wins depends on when the day's high comes (rank correlation +0.44), which is not known at the open |
| 20 | Risk comparison | All early exits beat holding (90% interval +3.4 to +10 points). A 50/50 split had the lowest maximum regret |
| 21 | Average exit value by fixed sale minute | Rises to minutes 4 to 6, then declines through the session. One-minute changes in the first minutes are 3.1 times as variable as in minutes 15 to 30 |
| 22 | Sensitivity to execution delay | The rule is delay-sensitive: a 1, 2 or 3-minute delay after the signal costs 1.4, 2.2 and 3.4 points on average, because it fires inside a decline. A fixed sale at minute 5 shows no systematic delay cost. On ANT the fill came within 5 cents of the signal price |

---

## 8. What I would do differently

1. **Check every symbol for silence, not just the connection.** The primary feed sent nothing for ANT all day. The backup saved the trade, but a staleness check per symbol, once the listing is confirmed elsewhere, would have caught it at once.
2. **Decide how the day high is defined.** On ANT the high was a 125-share trade one second after the cross. The backup feed saw $114.98 and the consolidated tape $115.10, and both gave a SELL in the same minute. A high that requires minimum volume would guard against bad prints, but here it would have set a lower floor and a later, lower exit. This is a trade-off to settle and test in advance, not a free fix.
3. **Start from a defined sample.** The 20 IPOs were chosen by hand, and memorable deals tend to be heavily traded ones. In a follow-up study on a rule-based sample of 236 US IPOs with proceeds of at least $500m (2016 to 2026), the drift from minute 5 to 15:30 ET was much smaller (median -0.85%) and not statistically significant. The 7.5-point advantage of early exits over holding in this repository is a property of these deals, not of IPOs in general.

---

## 9. Limitations

- Effective sample: 20 IPO peaks, of which five are large deals. The perp calibration rests on two observations.
- Signals use the last trade, not the national best bid, and the broker's quote spread is not modelled.
- The grace-period family was designed after watching the SpaceX replay. The nested cross-validation covers choices within the grid, not the decision to add that family.
- No correction was made for multiple testing across the full search.
- Cancelled or busted trades are not handled live; the dashboard shows how many trades support the day high instead.

---

## 10. Repository layout

| File | Purpose |
|---|---|
| `engine.py` | Exit engine (rule v1.1); the same code runs in research, replay and live |
| `live.py` | Live feeds, filters, bar builder, logging |
| `app.py` | Dashboard; modes `--check`, `--replay SYM`, `--live` |
| `01` to `16` | Research before the trade (section 5) |
| `17_condition_log.py` | Checks the trade-condition codes the live feed actually sends |
| `18` to `22` | Post-trade review (section 7) |
| `RUNBOOK.md` | Operating procedure used on the day |
| `.env.example` | Names of the required API keys |

`data/`, `out/` and `logs/` are created by the scripts and are not tracked.

---

## 11. Reproduce

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # then add your own keys
python 01_fetch_and_profile.py        # download day-one bars
python 03_confirm_bootstrap.py        # rule selection
python 06_nested_cv.py                # out-of-sample validation
python app.py --check                 # engine matches research code
python 13_live_open_test.py && python 15_halt_and_filter_check.py   # live-code tests
python app.py --replay SPCX           # replay a precedent day
python app.py --live --sym ANT --offer 83 --perp xyz:ANT
python 18_postmortem.py               # post-trade review (needs the day's logs)
```

Scripts 19 to 22 read the files written by 01, 14 and 18. The Alpaca free plan serves historical consolidated data only for requests ending at least 15 minutes in the past.

---

## References

- Adams, R. P. and MacKay, D. J. C. (2007). Bayesian online changepoint detection. arXiv:0710.3742.
- du Toit, J. and Peskir, G. (2009). Selling a stock at the ultimate maximum. *Annals of Applied Probability*, 19(3), 983-1014.
- Ekström, E. and Vaicenavicius, J. (2016). Optimal liquidation of an asset under drift uncertainty. *SIAM Journal on Financial Mathematics*, 7.
- Kaminski, K. M. and Lo, A. W. (2014). When do stop-loss rules stop losses? *Journal of Financial Markets*, 18, 234-254.
- Shiryaev, A., Xu, Z. and Zhou, X. Y. (2008). Thou shalt buy and hold. *Quantitative Finance*, 8(8), 765-776.
