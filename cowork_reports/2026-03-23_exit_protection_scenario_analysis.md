# Ross Exit V2 — Intra-Bar Protection: 5 Scenario Analysis

## Date: 2026-03-23
## Context

V2 exit signals work correctly on runners (ALUR +$5,589 improvement, ROLR +$17,747). The gap is **intra-bar spike-reversals** — INM spiked +5.6R then crashed to -0.9R within the 07:33 bar. Ross exit only evaluates on 1m bar close, so it never saw the spike.

CC recommended re-enabling `sq_target_hit` (hard take-profit). We rejected this — it would fix INM but destroy the ALUR/ROLR gains that validate V2.

Below: 5 alternative protection approaches, modeled against actual tick data from the targeted backtests.

---

## Stocks Used for Modeling

| Stock | Date | V2 Result | Key Price Action |
|-------|------|-----------|-----------------|
| **ALUR** | 01-24 | +$7,578 | $8.04 → $10.61 clean 17-min run, doji partial at 18R |
| **INM** | 01-21 | -$799 | $7.04 → $7.83 → $6.92 spike-reverse in same 1m bar |
| **ROLR** | 01-14 | +$24,191 | $4.04 → $6.68 (T1), $7.04 → $16.94 (T2), monster parabolic |
| **VMAR** | 01-10 | -$500 | $3.73 → ~$3.76 → $3.59, immediate reversal, never ran |
| **SLXN** | 01-29 | +$466 | Already improved in V2, mild runner |

**ROLR intra-bar pullbacks observed in tick data** (from TW_SUPPRESSED log):
- 08:29: $12.90 → $11.95 (–$0.95)
- 08:30: $13.60 → $12.47 (–$1.13)
- 08:31: $13.28 → $12.52 (–$0.76)
- 08:33→08:39: $17.76 → $15.29 (–$2.47, after V2's shooting star exit)

These pullbacks are normal for parabolic runners. Any protection mechanism must survive them.

---

## Variation A: Simple BE Floor at 3R (Tick-Level)

**Rule**: If unrealized reaches 3R on any tick, move hard stop to entry price. One-time ratchet. No exit signal — just adjusts where the stop lives.

| Stock | Hit 3R? | Stop Moves To | Effect on V2 Result |
|-------|---------|--------------|-------------------|
| ALUR T1 | Yes ($8.46, quickly) | $8.04 | None — doji fires at $10.61 long before stop tested. **+$7,850** |
| INM T1 | Yes ($7.46, during spike) | $7.04 | Price reverses to $6.92 but stop now at $7.04. Exits BE. **$0** (was -$426) |
| INM T2 | No (hit loss first) | — | No change. **-$373** |
| ROLR T1 | Yes (immediately) | $4.04 | None — VWAP break at $6.68 fires. **+$9,427** |
| ROLR T2 | Yes (immediately) | $7.04 | None — runner pullbacks ($11.95 low) are WAY above $7.04. **+$14,929** |
| ROLR T3 | No (quick loss) | — | No change. **-$166** |
| VMAR | No (never moved +3R) | — | No change. **-$500** |

**V2 + A Total**: +$426 improvement (INM T1: -$426 → $0)
**Runner risk**: **ZERO**. Stop at entry is so far below any runner's operating range that it never interferes.
**Complexity**: Trivial — 3 lines of code.

---

## Variation B: Stepped R-Floor (Tick-Level)

**Rules**:
- At 3R: stop → entry + 0.5R
- At 6R: stop → entry + 2R
- At 10R: stop → entry + 5R
- At 20R: stop → entry + 10R

Ratchet only — never lowers.

| Stock | Peak R | Stop Ratchets To | Effect |
|-------|--------|-----------------|--------|
| ALUR T1 | 18R (doji) | entry+10R = $9.44 | Doji at $10.61 fires first. Runner: shooting star at $10.43 > $9.44. **No change.** |
| INM T1 | 5.6R ($7.83) | 3R step: $7.11 (entry+0.5R). Never hits 6R ($7.88). | Price crashes, exits at $7.11. **+$249** (was -$426) |
| ROLR T2 runner | 70R+ ($16.94) | At 20R: stop at $9.84. | Pullback low: $11.95 (08:29). $11.95 > $9.84. **No interference.** |
|                |              | At peak: stop at ~$10.84 (extrapolating steps) | Still below all pullback lows. **Safe.** |
| VMAR | 0.2R | Never activates. | **No change.** |

**V2 + B Total**: +$675 improvement (INM T1: -$426 → +$249)
**Runner risk**: **NEAR ZERO**. Even at 20R, the floor is only at 10R — half the peak. ROLR's pullback to $11.95 (from $7.04 entry = 35R) is still 28R above the 10R floor.
**Complexity**: Moderate — lookup table, ~15 lines.

---

## Variation C: Peak Drawdown Partial (Tick-Level)

**Rules**:
- Track peak unrealized on every tick
- If price retraces 50% of peak-to-entry range: fire partial_50
- If price retraces 75% of peak-to-entry range: fire full_100
- Only activates above 3R unrealized

| Stock | Peak | 50% DD Level | 75% DD Level | Effect |
|-------|------|-------------|-------------|--------|
| INM T1 | $7.83 (5.6R) | $7.44 | $7.24 | Partial at $7.44: +$712 (1776 sh). Full at $7.24: +$355 (1775 sh). **Total: +$1,067** (was -$426) |
| ROLR T2 runner | $17.76 | $12.40 | $9.72 | Pullback at 08:29 hits $11.95 — below $12.40! **Partial fires at ~$12.40.** Runner cut from 888→444 shares. Lost ~$2,013 vs V2's full runner. |
| ALUR T1 | $10.61 | $9.33 | $8.47 | Price runs cleanly to $10.61 (doji). No 50% retracement visible. **Probably safe**, but 17 minutes of running may have hidden dips. |

**V2 + C Total**: INM +$1,493 improvement, but **ROLR loses ~$2,013** on premature runner partial.
**Net: WORSE than current V2 by ~$500.**
**Runner risk**: **HIGH**. The 50% DD threshold is too tight for parabolic runners with healthy pullbacks. ROLR's $12.90→$11.95 pullback is normal — only 18% of entry-to-peak range, but the peak keeps moving so the percentage calculation shifts. A runner that goes $7→$13→$12→$17 gets partially exited during the healthy $13→$12 dip.
**Verdict**: **REJECTED** — mechanically penalizes the exact behavior we want (runners with pullbacks).

---

## Variation D: 10s Structural Stop Above 5R

**Rule**: Below 5R, normal 1m structural stop. Above 5R, structural stop = low of last completed green 10s bar.

| Stock | Effect (estimated from tick data) |
|-------|----------------------------------|
| INM T1 | Above 5R at $7.74. Last green 10s bar low before reversal: ~$7.65. Stop fires at ~$7.65. **~+$2,166** (was -$426) — great result. |
| ROLR T2 runner | Above 5R from the start. During 08:29 pullback ($12.90→$11.95): last green 10s bar low before dip: ~$12.50. Price hits $11.95. **Stop fires at ~$12.50.** Runner portion: ($12.50-$7.04)×888 = **$4,849** instead of **$8,791**. Lost $3,942 on runner. |
| ALUR T1 | Above 5R from ~$8.74. Over 17 minutes of running, any red 10s cluster would update the structural stop. High risk of premature exit during minor pullbacks. **Estimated loss: $1,000-$3,000** depending on specific 10s bar action. |

**V2 + D Total**: INM gains ~$2,592 but ROLR loses ~$3,942, ALUR loses ~$1,000-$3,000.
**Net: SIGNIFICANTLY WORSE — estimated -$2,000 to -$4,000 vs current V2.**
**Runner risk**: **VERY HIGH**. 10s bars are too noisy for continuous structural stop updates on parabolic runners. Normal pullbacks of $0.50-$1.00 during a $10 move are 5-10% retracements — totally healthy, but the 10s structural stop would fire on every one.
**Verdict**: **REJECTED** — systematically kills runners, which is the opposite of what V2 is designed to do.

---

## Variation E: 10s Emergency Brake (Conservative Hybrid)

**Rule**: Fire a one-time protective exit ONLY if ALL conditions are met simultaneously:
1. Unrealized is currently **above 3R** (meaningful profit at risk)
2. Price has dropped from **intra-bar peak** by more than **50% of peak-to-entry range** (major reversal, not a pullback)
3. At least **3 consecutive red 10s bars** (confirmed momentum shift, not a blip)
4. Fires as **partial_50** (not full exit — leaves room if it's a deep pullback before continuation)

| Stock | Triggers? | Effect |
|-------|-----------|--------|
| INM T1 | Peak $7.83, entry $7.04, range=$0.79. 50% DD = $7.44. Price drops through $7.44 during reversal. 3 red 10s bars during crash: YES. **Partial fires at ~$7.30-$7.40.** Remaining shares hit stop at $6.92. Partial: ($7.35-$7.04)×1776 = +$550. Full loss: ($6.92-$7.04)×1775 = -$213. **Total: +$337** (was -$426) |
| ROLR T2 runner | Runner at $9.35+. Peak at $12.90 during 08:29 bar. Range from runner start: $12.90-$7.04 = $5.86. 50% DD = $10.97. Pullback low: $11.95. $11.95 > $10.97. **Does NOT trigger** — pullback isn't severe enough. Even the $13.60→$12.47 pullback: 50% DD from $13.60 peak = $10.32. $12.47 > $10.32. **Still doesn't trigger.** |
| ROLR T2 (later) | $17.76 peak. 50% DD = $12.40. Post-SS pullback to $15.29: $15.29 > $12.40. **Doesn't trigger.** (V2 already exited at SS $16.94 anyway.) |
| ALUR T1 | Clean 17-min run. Peak continuously rising. Would only trigger if a within-run dip lost 50%+ of gains. Highly unlikely on a clean squeeze. **Almost certainly no trigger.** |
| VMAR | Never above 3R. **Doesn't activate.** |

**V2 + E Total**: INM improves by +$763 (-$426 → +$337). All runners untouched.
**Runner risk**: **LOW**. The 50% intra-bar DD + 3 consecutive red 10s bars is a very high bar. Normal pullbacks ($0.95 on a $5.86 range = 16%) don't come close to 50%. Only true spike-reversals (like INM) trigger it.
**Complexity**: Moderate — requires 10s bar tracking and peak tracking, ~30 lines.
**Open question**: Needs CC to test with actual 10s bar reconstruction to confirm the 3-red-bar filter works. My estimates are based on tick price direction, not actual 10s OHLC.

---

## Comparison Matrix

| Variation | INM T1 | ROLR Runner | ALUR | Net vs V2 | Runner Risk | Complexity |
|-----------|--------|-------------|------|-----------|-------------|------------|
| **Current V2** | -$426 | +$8,791 | +$7,850 | baseline | none | — |
| **A: BE at 3R** | $0 | +$8,791 | +$7,850 | **+$426** | zero | trivial |
| **B: Stepped floor** | +$249 | +$8,791 | +$7,850 | **+$675** | near zero | low |
| **C: Peak DD partial** | +$1,067 | ~+$6,778 | risk | **~-$500** | HIGH | moderate |
| **D: 10s structural** | +$2,166 | ~+$4,849 | risk | **~-$3,000** | VERY HIGH | moderate |
| **E: 10s emergency** | +$337 | +$8,791 | +$7,850 | **+$763** | low | moderate |

---

## Recommendation

**Implement B + E together.** They're not mutually exclusive — they solve different problems at different speeds.

**B (stepped R-floor)** provides a guaranteed tick-level safety net. It's deterministic, trivial to test, and has mathematically zero risk to runners because the floor is always far below the operating range of a healthy trade. It catches INM-type reversals at the bottom end — you don't capture the spike, but you don't give back the farm either.

**E (10s emergency brake)** adds a faster-reacting layer for severe intra-bar reversals. The 3-red-10s + 50%-DD double filter means it only fires on true crashes, not normal pullbacks. It catches more of INM's spike than B alone ($337 vs $249) and would scale better to more extreme spike-reversal scenarios.

**Combined B+E**: The stepped floor catches moderate reversals; the emergency brake catches severe ones. Neither touches runners.

**What this does NOT solve**: VMAR (-$500). That trade was a dud from entry — price barely moved above entry before reversing. No exit mechanism can save a trade that never runs. That's a $500 cost-of-doing-business that gets dwarfed by ALUR/ROLR gains.

---

## What CC Needs To Test

1. Implement B (stepped floor) first — it's deterministic and testable immediately
2. Implement E (emergency brake) with the 10s bar data — needs actual 10s OHLC reconstruction
3. Run the same 5-stock targeted test matrix (ALUR, INM, ROLR, VMAR, SLXN)
4. Confirm ROLR runner is NOT affected by either mechanism
5. Confirm VERO/ROLR regression passes
6. Then YTD

---

*Analysis by Cowork — 2026-03-23*
*Based on tick-level price data extracted from verbose backtest logs*
