# Win/Loss Tuning Analysis — 2026-06-08

**Goal:** synthesize the day's research into concrete, gated tweaks that (a) maximize
wins and (b) avoid losses, for both the main squeeze bot and the A/B/C MOVE_STRIKE
sub-bots. All figures are from paper/live-session data (IBKR paper, acct DU…) — see
**Caveats** before acting. Source artifacts: `/tmp/discovery_features_rows.csv`,
`/tmp/live_giveback_rows.csv`, `/tmp/subbot_trades.csv`, today's daily + sub-bot logs.

---

## Executive summary

Two independent levers fell out of the data, and **today's live session demonstrated both at once on a single stock (SUNE, which ran $3 → $9.10 → reversed):**

1. **Avoid losses → gate by time-of-day.** Winners cluster pre-open; essentially all
   damage comes after 09:30 ET. A 09:30 entry cutoff would have avoided **~74% of the
   main bot's** and **~90% of the sub-bots'** losses over the sample. But gating alone
   only reaches *scratch* — it removes the bleed, it does not create edge.
2. **Maximize wins → ride/re-enter the runner.** The main bot's single biggest cost
   today was not a bad trade — it was a **missed** one: shaken out of SUNE at $3.06 by a
   bearish-engulfing exit, then armed on it **5 more times** without re-entering as it
   ran to $9.10. The sub-bots' entire **+$2,647** day was continuation re-entries the
   main bot declined. **This is where the real money is, and no gate addresses it.**

**Headline recommendation:** pursue both, but weight **win-capture (continuation
hold + re-entry on strong runners)** as the higher-value workstream — loss-gating caps
the downside, continuation-capture is what turns the book green.

---

## The data

### A. Today's live session — the SUNE case study (2026-06-08)

| | Day P&L | Trades | Symbols |
|---|---:|---:|---|
| Main bot | **−$123** | 2 | SUNE (scratch), FRSX (−$123) |
| Sub-bot A | +$786 | 6 | SUNE |
| Sub-bot B | +$818 | 5 | SUNE |
| Sub-bot C | +$1,043 | 10 | SUNE |
| **Sub-bots total** | **+$2,647** | 21 | SUNE only |

- SUNE ran **~$3.00 → $9.10 peak (+200%)**, then reversed; bounced; closed mid-range.
- **Main bot:** entered $3.09 (chased $0.09 above the sub-bots' $3.00 fill), shaken out
  at $3.06 by `bearish_engulfing_exit` = scratch. Armed SUNE **5×** afterward, re-entered
  **0×**. Took FRSX (which sub-bots skipped) for −$123. **Missed the entire $3→$9 move.**
- **Sub-bots:** rode continuation in many small bites (HWM trail exits at ~50% drawdown
  from peak). Blemishes: **C top-chased at $9.21 → −$359**, and **two late re-entries
  (19:28+) force-flattened for −$97/−$80.** So both ends of the clock (parabola top,
  into-close) bit even the winners.

**Lesson:** the day's P&L gap was driven by **exit/re-entry quality on a runner**, not by
loss-gating. The main bot's exit was too trigger-happy and its re-entry never fired.

### B. Entry-time edge (live trades, both bots)

Winners are tightly clustered early; losses come after the open.

| Window (ET) | Main WR | Sub WR |
|---|---:|---:|
| before 09:30 | 53% | 57% |
| **after 09:30** | **~17%** | **24%** |
| after 09:30 net P&L | −$5.5k region | **−$20,017** |

- **Every main-bot winner in the risk.json sample entered 06:48–08:32 ET.** After 09:30:
  0-for-14 on that sample.
- Sub-bots **concentrate volume in the dead zone** — 47 of 85 time-matched trades fire
  13:00–15:59 (−$15,810). They don't just lose late, they *live* late.

### C. Entry-cutoff backtest sweep (full available history)

| Cutoff | MAIN kept WR | MAIN avoided | SUB kept WR | SUB avoided |
|---|---:|---:|---:|---:|
| **09:30** | 19%→**32%** | **+$5,491** | 29%→**57%** | **+$20,017** |
| 11:00 | 26% | +$3,130 | 45% | +$19,523 |
| no cutoff | 19% | — | 29% | — |

Cutting after ~09:30 removes most of the loss — **but both bots remain net-negative even
with the cutoff** (−$1,939 main, −$2,249 sub). Gating stops the bleed; it is not edge.

### D. Give-back analysis — "green turned red" (33 main-bot positions)

- **27 of 28 losing trades (96%) touched green before closing red** — sounds alarming…
- …but **median loser only peaked +0.8%** before bleeding to −3.1%. Mostly noise-level
  green. Only ~2 trades got meaningfully green (≥+2%) and gave it all back.
- **Diagnosis: the losers' problem is ENTRY, not exit greed.** They go underwater fast;
  they aren't winners that rotted while waiting for a target. (Confirms the standing
  `pnl_vs_exit_quality` rule: positive unrealized but exit-at-bid is a loss = bad entry.)

### E. Discovery-time discriminators (312 subscribe-discoveries, 55-day pool)

Clean-rip (touches +5% before −5%) base rate **37%**. What separates the rips:

| Feature | Signal |
|---|---|
| **Hour ≤09:00 ET** | ~50% clean-rip vs **>11:00 ET → 23%** |
| **Pre-discovery vol >3%** | 50% clean-rip, +21% median MFE |
| Run-up 15m | barbell: >20% or flat good; **3–8% lukewarm drift = trap** |
| **Float, distance-from-HOD** | **no predictive signal** (counter-intuitive) |

The **G1 gate** (skip hour≥11 AND pre-vol<1.5%) lifts the kept pool 37%→**49%** clean-rip,
cuts 41% of discoveries, and holds across both temporal halves. **Deployed observe-only
2026-06-08** (`discovery_gate.py`, `WB_DISCOVERY_GATE_OBSERVE=1`) — not yet enforcing.

---

## Synthesis: where the money is

| Problem | Driver | Lever | Ceiling |
|---|---|---|---|
| Losing afternoon trades | trades taken in the dead zone | **time/discovery gate** | gets to scratch |
| Bleeding morning entries | poor entry selection | **discovery features** | reduces, not eliminates |
| **Missing the big runner** | shaken out + no re-entry | **continuation hold + re-entry** | **this is the upside** |

The gates are a **floor** (stop losing); continuation-capture is the **ceiling** (start
winning). Today proved the floor is well-understood and the ceiling is wide open: the
main bot left a +200% runner entirely on the table.

---

## Recommended tweaks (prioritized, all gated / observe-first)

### P1 — Win-capture: fix the runner shake-out + re-entry gap (highest value)
The main bot's `bearish_engulfing_exit` cut SUNE at $3.06 before a +200% move, and its
re-entry never fired despite 5 re-arms. Proposed, behind gates, OFF by default:
1. **Suppress the 10-sec bearish-engulfing / topping-wick exits on confirmed strong
   runners** (high RVOL + price extension), letting `WB_CONTINUATION_HOLD_ENABLED`
   carry the position. New gate e.g. `WB_RUNNER_EXIT_SUPPRESS` + RVOL/extension threshold.
2. **Audit the arm-but-no-re-entry path:** why did the main bot arm SUNE 5× and trigger
   0×? (Likely the seed-staleness drop or chase-cap blocking re-entry above the prior
   level — see `WB_SQ_SEED_STALE_GATE`, `WB_ENTRY_MAX_CHASE_PCT`.) This is the single
   biggest opportunity cost found today and deserves a dedicated investigation.

### P2 — Loss-avoidance: tighten the entry-time window
3. **Move `WB_ENTRY_TIME_CUTOFF_ET` from 19:30 → ~11:00** (keeps 07:00–09:30 prime window
   + buffer, kills the 13:00–15:59 dead zone). **Stage observe-only first** (log would-block
   decisions) for a few sessions, since today's losses were *pre*-09:30 and the cutoff
   wouldn't have helped them — confirm it isn't cutting winners before enforcing.
4. **Enforce the discovery G1 gate** — but only after it has logged ≥1 week of live
   *afternoon* decisions (currently ~9 observe records, near-zero afternoon coverage).

### P3 — Sub-bot guards (cap the two failure modes seen today)
5. **Max-extension entry guard:** block MOVE_STRIKE entries more than X% above the move's
   origin / after N× ATR extension — would have prevented C's **−$359 top-chase at $9.21**.
6. **Hard no-new-entry cutoff before EOD flatten** (e.g. no entries after ~15:45 ET for
   sub-bots) — would have prevented the **−$97 / −$80 late re-entries** force-flattened at
   19:28+. Mirrors the P2 time-gate logic on the close side.

### P4 — Entry fill quality
7. The main bot chased SUNE to **$3.09 vs the sub-bots' $3.00** (+$0.09 worse basis on the
   same signal). Review `WB_ENTRY_SLIPPAGE_*` / chase logic — a worse entry basis directly
   widens the give-back and lowers clean-rip odds.

---

## Caveats (read before acting)

- **Paper fills**, both bots (IBKR/Alpaca paper). Pre-market winners especially may flatter
  real-money fills. Direction is trustworthy; magnitude needs real-fill confirmation.
- **Small samples** — 33 main give-back positions, 101 sub trades, 42 main full-history
  trades. Directional, not definitive.
- **Data-quality flags** — today's report tagged `DIRECT_QUERY_WEDGE` (FEBO) + 3
  `HEURISTIC_SUSPECT` symbols; the recurring Tier-2 tick-throttle bug intermittently
  starves the feed (cf. MASTER_TODO MNTS/SUNE). Some "missed" entries may be feed gaps,
  not logic gaps — worth ruling out in the P1 audit.
- **Gating ≠ edge** — every loss-avoidance tweak here caps downside to ~scratch. Only the
  P1 win-capture work changes the sign of the book.
- All tweaks must ship **env-gated, OFF by default, observe-first** per project discipline,
  and pass the VERO/ROLR regression before any live flip.

---

## Next steps
1. **P1 audit** — trace the SUNE arm-but-no-re-entry path in today's daily log (highest ROI).
2. Stage **`WB_ENTRY_TIME_CUTOFF_ET=11:00` observe-only** alongside the discovery gate.
3. Let the **discovery gate** accumulate afternoon observe data through the week, then review.
4. Backtest the **max-extension** and **late-entry-cutoff** sub-bot guards against the
   MOVE_STRIKE history before proposing live.
