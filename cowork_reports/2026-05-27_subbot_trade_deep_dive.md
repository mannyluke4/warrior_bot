# Sub-bot Trade Deep Dive — 2026-05-27 (Day 1, Post-Orphan-Fix)

**Owner:** CC
**Status:** Day-1 analysis. **Sample size is small (4 closed trade cycles × 3 variants = 12 data points). Treat the variant rankings as directional only.**
**Open at session-end:** all 3 variants hold AMSS qty=2000 @ $5.92 (regime_shift entry from 13:32 ET).

---

## TL;DR

- **The big winner everyone took**: ASTC regime_shift @ 08:46 ET — `body=$1.77, ratio=10.41` (body 10× baseline). Entry $7.05-$7.17, partial scale-out at $9.70-$10.05, runner exit at ~$9.94 via HWM. **+$1,100 to +$1,176 across variants.**
- **The losers had a common signature**: both were `REENTRY(GREEN)` with `score=99.0`, taken within 1-3 minutes of a prior exit on the same symbol. Both reversed and stopped out via `move_stop_prox_bail` for ~-1R losses.
- **V1 VWAP fade-gate (Variant B) had a real save today**: it blocked AMSS @ 07:32 (price $12.54 < VWAP $13.64), which would have produced +$45 winner + -$378 loser net -$333 on V_A and V_C. B skipped both, kept just the big ASTC winner + the unavoidable re-entry loser.
- **Today's variant ranking (broker-truth realized): B $688 > C $396 > A $322.** B leads because the fade-gate dodged the AMSS chop trade. **One day is not a verdict.**

---

## Per-variant realized P&L (broker truth)

Computed from Alpaca filled-order pairs. Open AMSS position excluded.

| Variant | Closed P&L | Trades | Fade-gate blocks |
|---|---|---|---|
| A (control, no fade) | **+$322** | 4 closed | 0 |
| B (V1 VWAP fade) | **+$688** | 2 closed | 1 (AMSS @ 07:32) |
| C (V4 BodyCV fade) | **+$396** | 4 closed | 1 (AMSS @ 13:31 — regime_shift entered anyway) |

---

## Closed trades — all variants, side-by-side

Times in ET. Entry/exit prices are broker-truth (average fill from Alpaca).

### Trade 1 — AMSS move_strike @ 07:32 (small winner)

| | A | B | C |
|---|---|---|---|
| Entry | $12.6615 × 357 | **BLOCKED** (vwap fade) | $12.6604 × 357 |
| Exit | $12.79 (HWM dd=25%, hh=1) | n/a | $12.7658 (same) |
| P&L | **+$46** | n/a | **+$38** |
| Score | 11.0 | n/a | 11.0 |

- Initial entry on AMSS's morning ramp. Score 11.0 = standard new-arm score.
- Exit was triggered after a single higher-high then 25% draw-down → small win.
- **V_B's V1 VWAP fade-gate blocked the entry**: log line `MOVE_FADE_GATE_BLOCK AMSS reason=vwap (price=$12.5400 vwap=$13.6357 open=$7.1100)` — price was below VWAP, fade rejected.

### Trade 2 — AMSS REENTRY GREEN @ 07:34 (big loser)

| | A | B | C |
|---|---|---|---|
| Entry | $12.7934 × 320 | **BLOCKED** (vwap fade carries) | $12.8300 × 320 |
| Exit | $11.6100 (stop_prox_bail) | n/a | $11.6100 (same) |
| P&L | **-$379** | n/a | **-$390** |
| Score | 99.0 (re-entry default) | n/a | 99.0 |
| R-multiple | -0.80R | n/a | -0.82R |

- Bot re-entered AMSS 1 minute after the +$46 winner closed. The REENTRY GREEN trigger (green-bar within 30-min watch window) fired, score forced to 99.0 (high-conviction re-entry).
- Price reversed from $12.79 → $11.55 in 4 minutes. Bot exited via `move_stop_prox_bail(low=11.62, stop=11.23, buf=0.390)` — price approached stop within $0.39 of the buffer, bot bailed early to avoid stop slippage.
- V_B was still in the vwap-fade cool-down from 07:32, also skipped this entry.

### Trade 3 — ASTC regime_shift @ 08:46 (big winner — all 3 took it)

| | A | B | C |
|---|---|---|---|
| Entry | $7.17 × 434 | $7.0624 × 434 | $7.05 × 434 |
| Partial out | 391 @ $9.7032 | 391 @ $9.7176 | 391 @ $9.73 |
| Runner exit | 43 @ $9.974 | 43 @ $10.0049 | 43 @ $10.05 |
| P&L | **+$1,110** | **+$1,165** | **+$1,177** |
| Setup | REGIME_SHIFT | REGIME_SHIFT | REGIME_SHIFT |
| body / ratio | $1.77 / **10.41x** | same | same |
| R-multiple | +2.22R | +2.33R | +2.35R |

- **This is the only trade today that hit the regime_shift detector's high-conviction band** (`body=$1.77, ratio=10.41` — current bar's body was 10.41× the rolling baseline body average).
- All 3 variants entered (regime_shift isn't fade-gate-blocked; the gate only applies to MOVE_STRIKE).
- Exit path: 90% scaled out at $9.70-$9.73 (1.5R target hit), runner stopped to break-even-plus per `WB_REGIME_SHIFT_RUNNER_STOP_TO_BE=1`, eventually exited at ~$9.94-$10.05 on HWM drawdown after the move topped at $11.27.
- **B's entry @ $7.0624 was the best fill of the three** (slightly under A and C's $7.17/$7.05). Sub-bots share the engine socket tick stream so the difference is purely Alpaca's per-account fill-side variance.

### Trade 4 — ASTC REENTRY GREEN @ 11:11 (big loser — all 3 took it)

| | A | B | C |
|---|---|---|---|
| Entry | $9.83 × 943 | $9.8856 × 943 | $9.83 × 943 |
| Exit | $9.3482 (stop_prox_bail) | $9.3796 (same) | $9.3755 (same) |
| P&L | **-$454** | **-$477** | **-$429** |
| Score | 99.0 (re-entry) | 99.0 | 99.0 |
| R-multiple | -0.94R | -1.12R | -0.94R |

- Bot re-entered ASTC 3 minutes after the +$1,100+ winner closed. Same REENTRY GREEN cascade pattern as the AMSS loser.
- Price drifted from $9.83 → $9.34 in 1 minute. Same `move_stop_prox_bail(low=9.44, stop=9.31, buf=0.130)` exit pattern — price within $0.13 of stop, bot bailed.
- **Variant B took this trade.** The V1 VWAP fade-gate doesn't fire on REENTRY entries (it gates the *initial* setup; once the prior trade just closed, the re-entry doesn't re-check VWAP). Result: B got the full -$477 loss with no buffer.

---

## What the winners had in common

1. **Initial entry (not REENTRY)** — both winners were the first entry on a new signal. Trade 1 (AMSS) was score=11.0 (standard move_strike score); Trade 3 (ASTC) was regime_shift (no score field — regime_shift uses its own body-ratio gate).
2. **Reasonable entry price relative to setup** — Trade 1 entered at $12.66 with stop $11.23 (R=$1.43, but anomaly was $13.02 so chase gap was modest). Trade 3 entered at $7.17 right at the regime-shift bar's body anomaly.
3. **Direction confirmed by the bar mechanics** — Trade 3's body-to-baseline ratio of 10.41 is the kind of explosive bar that defines regime-shift. The body-ratio gate is doing real signal selection.

## What the losers had in common (this is the actionable pattern)

Both losers were:
- **`REENTRY(GREEN)` re-entries** within 1-3 minutes of a prior exit on the same symbol
- **`score=99.0`** (the artificial high score the re-entry pipeline assigns to force priority through the entry funnel)
- **Exited via `move_stop_prox_bail`** with the low only marginally above stop (buffer 0.13 to 0.39)
- **Negative-R losses around -0.8R to -1.1R** — close to a full stop-out, but bailed early to avoid catastrophic stop slippage

The mechanical pattern: the bot just took a small profit, then immediately re-entered the same symbol because a green continuation bar printed in the post-exit lookback window. Both times, the continuation didn't continue — the green bar was the *exhaustion bar* of the prior move. Re-entry chased into a reversal.

**This is a high-conviction signal that's anti-correlated with what just happened.** If the prior cycle exited via HWM drawdown (the original trend ended), the market is more likely to *continue reversing* than to resume.

### Suggested research direction (not for tonight)

Filter REENTRY GREEN by **time-since-prior-exit** + **size of prior winner**. Today:
- AMSS re-entry came 1 min after a +0.4% trade
- ASTC re-entry came 3 min after a +40% trade

If the prior winner was big enough that the bot's HWM exit is signaling that the move topped, the re-entry is likely chasing a reversal. Maybe a rule: skip REENTRY GREEN if prior cycle's profit was > N% of entry price.

Or stronger: skip REENTRY GREEN entirely if the prior cycle's exit reason was `move_hwm_exit` (a drawdown trigger) rather than something neutral.

Sample is one day — flag as research direction, don't ship a rule yet.

---

## A/B/C variant comparison (Day 1)

### The fade-gate impact, isolated

For trades where the fade-gate differentiated behavior:

| Trade | A took? | B took? | C took? | Best variant on this trade |
|---|---|---|---|---|
| AMSS @ 07:32 (+win) | yes (+$46) | **blocked** | yes (+$38) | A or C (B missed +$42) |
| AMSS @ 07:34 (loser) | yes (-$379) | **blocked** | yes (-$390) | **B** (saved -$384) |
| ASTC @ 08:46 (winner) | yes (+$1,110) | yes (+$1,165) | yes (+$1,177) | tie (engine fanout) |
| ASTC @ 11:11 (loser) | yes (-$454) | yes (-$477) | yes (-$429) | tie (all took it) |

The two trades B differentiated on (AMSS pair) netted V_A and V_C **-$333 / -$352** respectively. B saved that by sitting out the morning AMSS cycle entirely.

The V4 BodyCV gate (Variant C) blocked one trade today: AMSS @ 13:31:00 ET reason=`cv` price=$5.80 vwap=$10.25. But regime_shift on AMSS fired 60 seconds later (at 13:32) and entered anyway — the gate only applies to MOVE_STRIKE entries. Net: V4 fade didn't change C's exposure on AMSS this afternoon.

### Honest read on the variant comparison

- B's lead today is **entirely from one fade-gate save** on a single chop trade (AMSS @ 07:32-07:34 cycle).
- Without that save, B's day would be exactly the ASTC winner + ASTC loser = +$1,165 - $477 = **+$688** — same as observed.
- A and C each took both the small AMSS winner AND the big AMSS loser → net negative on AMSS cycle, partially offsetting the big ASTC winner.
- **The V1 VWAP rule fired exactly once today**, which means the gate is highly conservative. On a quieter morning where AMSS were below VWAP and ramped anyway, V1 would skip plenty of valid entries. We won't know without more sample.

### What the data tells us so far

| Question | Today's answer |
|---|---|
| Does V1 VWAP fade-gate add value? | **Yes today**, +$333 vs no-fade. But sample is 1 fade event. |
| Does V4 BodyCV fade-gate add value? | **No data today** — one trigger but regime_shift overrode it. |
| Does REGIME_SHIFT > MOVE_STRIKE? | **Yes today on conviction trades** — regime_shift caught the +$1,100 ASTC move. MOVE_STRIKE caught a small winner + bigger loser pair. |
| Does REENTRY GREEN add value? | **No today** — 0/2 winners; both -1R losses. |

---

## Open positions context

All 3 variants hold:
- **AMSS qty=2000 @ avg $5.92, regime_shift entry from 13:32 ET, stop=$5.61**
- Current unrealized: +$100 each (current ~$5.97)
- The R is $0.31 per share; current unrealized R-mult = +0.16R

The afternoon regime_shift detected an impulsive bar at AMSS's low. AMSS had crashed from the morning high ($14.43) all day, then printed a body-ratio bar at $5.86 → bot entered. Either continuation back up (= big winner) or reversal back down (= -1R loss). Will be in Wednesday's data.

---

## Recommendations

### Confirm before drawing conclusions

- **3-4 weeks of clean data is the minimum** to draw fade-gate conclusions per the A/B/C directive. Today is day 1.
- Tomorrow's A/B/C report (now with bot-vs-broker comparison from the orphan-fix commit) is the authoritative source for daily P&L.

### Research direction (no code change tonight)

The REENTRY GREEN failure pattern is the most actionable thing in today's data. The next directive could include:
- Replay the past 30 days of REENTRY GREEN entries against actual outcomes
- Stratify by `time_since_prior_exit` + `prior_cycle_pnl_pct`
- If clear failure pattern emerges, propose a gate

### Continued operational monitoring

- Watch for any `move_stop_prox_bail` exits Wednesday and beyond — the buffer values (0.13, 0.39) hint at where stops are placed too tightly for normal noise. May be worth widening the bail buffer on REENTRY trades specifically.

---

## Caveats and disclaimers

- **One day of data.** Today's 12 trade slots (4 cycles × 3 variants) are too few for confidence intervals.
- **Engine-socket fanout means trades are NOT independent across variants.** When A and C take the same setup, that's one underlying market event, not two.
- **Today's market shape (sharp morning ramp + afternoon collapse on AMSS and ASTC) may not reflect typical days.** Both winners and losers came from the same two symbols — a different symbol mix tomorrow could invert today's variant order.

---

*Analysis complete. Standing by for Wednesday's data to extend the comparison.*
