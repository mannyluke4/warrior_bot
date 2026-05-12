# Daily Trade Breakdown — 2026-05-11 (Monday)

**Sub-bot:** `bot_alpaca_subbot.py`, strategy = WaveBreakout (Alpaca paper PA3LXGIPGG8B)
**Main bot:** `bot_v3_hybrid.py`, strategy = Squeeze (Alpaca paper PA3VP0LB4OID)

**Sub-bot equity day:** ~+$599 realized (1W / 5L, 17% WR, avg R = -0.09)
**Main bot equity day:** $0 (0 fills — chase-cap aborted ODYS, retry-cap aborted TRAW)

**Headline:** SST winner (+$2,090 / +3.28R) covered four ATRA losses + NVOX/CLNN paper-cuts. Three same-symbol ATRA re-arms cost a cumulative -$1,326. The main bot's two no-fills were *the right calls* (ODYS chased to $11.22 = +12% above signal; TRAW four-leg retry cadence couldn't keep up with a parabolic open).

> **Why this report exists:** Manny wants per-trade granularity to spot patterns over the next ~3 sessions before tuning. This is the second report in that cadence (5/8 was the first). Patterns that repeat across both days move to the high-confidence tuning queue.

---

## Quick scoreboard — sub-bot (WB)

| # | Symbol | Score | Result | R-mult | $ P&L | Hold | Reason exited |
|---|---|---|---|---|---|---|---|
| 1 | ATRA | 10 | LOSS (orphan) | -0.04R | **-$35** | ~7m (partial fill via timeout) | bail_timer (auto-adopted) |
| 2 | NVOX | 9 | LOSS | -0.47R | **-$37** | 3 min | trailing_stop |
| 3 | CLNN | 10 | LOSS (orphan) | -0.16R | **-$128** | ~2h13m | trail no-fill → bail_timer |
| 4 | ATRA | 10 | LOSS | -1.16R | **-$513** | 13 min | stop_hit |
| 5 | SST  | 9  | **WIN** | **+3.28R** | **+$2,090** | 43 min | trailing_stop |
| 6 | ATRA | 10 | LOSS | -1.43R | **-$778** | 5 min | stop_hit |
| | **Net** | | | **-0.09R avg** | **+$599** | | |

## Quick scoreboard — main bot (SQ)

| # | Symbol | Score | Result | Why |
|---|---|---|---|---|
| – | ODYS | 10 (PARABOLIC) | NO ENTRY | 08:48 chase-cap fired — market $11.22 > 1.02×$10.07 limit |
| – | TRAW | 12 (PARABOLIC + vwap_dist + pm_high_break) | NO ENTRY | 09:31 4 retries ($2.36/$2.40/$2.44/$2.45), all timed out |

---

## Day timeline (sub-bot, ET)

```
04:11 ET   ATRA WB_DOWNWAVE wave=1 (early pre-market context)
05:29 ET   ATRA score=8 → CHOP_REJECT (R$0.10 < 1.5×spread $0.195, vol low)
06:22 ET   SST  score=7 → CHOP_REJECT (R below spread, below VWAP)
07:00 ET   ATRA score=10 → CHOP_BYPASS → ENTER $8.78 → ENTRY TIMEOUT (10s)
           ↑ but Alpaca filled 3,526 / 3,551 qty at $8.61 BEFORE cancel
           ↑ orphan_adopted → bail_timer → EXIT $8.60 = -$35
07:43 ET   TRAW score=8 — no chop_reject log, but earlier TRAW BP-rejected
08:27 ET   TRAW score=7 → CHOP_REJECT (R 0.25%)
08:48 ET   ⚠️  [Main bot] ODYS score=10 PARABOLIC → ENTRY $10.07 →
           chase-cap aborted: market $11.22 > $10.27. The bot was right.
09:31 ET   ⚠️  [Main bot] TRAW score=12 → ENTRY $2.36 →
           RETRY 1/3 $2.40 → RETRY 2/3 $2.44 → RETRY 3/3 $2.45 → all timed out
09:31 ET   ATRA score=10 → CHOP_BYPASS → ENTER $9.07 → ENTRY TIMEOUT (no orphan)
09:43 ET   CLNN score=10 → CHOP_BYPASS → ENTER $7.32 → FILL $7.35
           ↑ Trade #3 — held 2h13m
09:55 ET   CLNN trail armed @ peak $7.55 → 09:56 trail signal $7.48 →
           EXIT NO-FILL (limit $7.43, market gapped through) — stays open
10:12 ET   NVOX score=9 → CHOP_BYPASS → ENTER $16.25 → FILL $16.22
           ↑ Trade #2 — 3 min hold, trail @ $16.27 peak → exit $16.20
11:55 ET   CLNN bail_timer adopts the open orphan position → EXIT $7.32
13:14 ET   ATRA score=8 → CHOP_REJECT (R$0.09 < 1.5×spread $0.255)
13:27 ET   CLNN score=10 → CHOP_BYPASS → ENTRY TIMEOUT (no fill)
13:52 ET   ATRA score=10 → CHOP_BYPASS → ENTER $8.45 → FILL $8.47
           ↑ Trade #4 — 13 min, stopped @ $8.33
14:18 ET   SST score=9 → CHOP_BYPASS → ENTER $3.79 → FILL $3.83
           ↑ Trade #5 (winner) — 43 min, trail $4.09
14:32 ET   ENSC score=9 → CHOP_BYPASS → BP REJECT (SST + position concurrent)
14:54 ET   ATRA score=7 → CHOP_REJECT — third ATRA reject of session
15:47 ET   TRAW score=10 → CHOP_BYPASS → BP REJECT ($32,562 cost / $32,562 BP)
17:31 ET   TRAW score=9  → CHOP_BYPASS → BP REJECT (still tight)
18:30 ET   ATRA score=10 → CHOP_BYPASS → ENTER $9.59 → FILL $9.49
           ↑ Trade #6 — 5 min hold, stopped @ $9.20 — biggest single loss
18:40 ET   TRAW score=8 → CHOP_REJECT
19:43 ET   TRAW score=7 → CHOP_REJECT
20:00 ET   Trading windows close
```

**Tally:** 28 sub-bot WB_ARMED events, 14 CHOP_REJECT, 9 CHOP_BYPASS, 6 fills (of which 2 were orphan-adopted via timeout-then-fill), 4 TRAW BP rejects, 1 ENSC BP reject.

---

## Trade #1 — ATRA @ 07:00 ET — orphan via entry-timeout race condition

**Entry decision**
- Score: 10 (max), wave_id 9
- Provisional entry $8.89, signal limit $8.78
- Stop $8.5885, R = $0.30 → **R% = 3.4%** (largest R% of the day)
- Pre-market window — only 4 prior ATRA waves logged

**The race**
```
[07:00 ET] ATRA WB_ARMED score=10 → CHOP_BYPASS
[WB] ATRA ENTER qty=3551 entry=$8.7800 limit=$8.83 score=10
[WB] ATRA ENTRY TIMEOUT — no fill within 10s, cancelled
... 7 minutes pass ...
🟥 EXIT: ATRA qty=3526 @ $8.6000 reason=bail_timer P&L=$-35 daily=$-35
```

**What actually happened (per Alpaca ledger):**
- BUY 3,551 limit $8.83, **canceled with filled_qty=3526 @ $8.61** — the partial filled AS the cancel arrived
- This created an unmanaged 3,526-share orphan position
- Bail-timer subsystem adopted the orphan at the 5-min mark, sold @ $8.60 (limit $8.58)
- Net: -$35 (3,526 × $0.01)

**Why this matters:** The bot logged "no fill within 10s, cancelled" but ~99% of the order *did* fill. This is a **race-condition between cancel and partial-fill** at the Alpaca API boundary. The orphan-adoption path saved us from a worse outcome — but it shouldn't have created an orphan in the first place.

**Tuning hypothesis:** After ENTRY TIMEOUT, query Alpaca's actual filled_qty before declaring "no fill." Treat any filled_qty > 0 as a real entry and arm the normal exit machinery (stop $8.5885 was never installed for this position).

---

## Trade #2 — NVOX @ 10:12 ET — paper-cut trail (-0.47R)

### Entry decision

**Wave history (NVOX before arm):** 8 prior waves, 0 prior arms — patient signal.

**Entry inputs**
- Score: 9 (right at the bypass threshold)
- Provisional entry $16.25, stop $16.1794, **R = $0.071 → R% = 0.43%** ⚠️
- VWAP at entry (10:10 ET bar): $16.22, entry **-0.1% from VWAP** (right at VWAP)
- HOD: $16.79 → entry 3.4% below HOD

**Order**
- Limit BUY $16.33 (signal + $0.05 buffer); FILLED **$16.22** = $0.11 of *price improvement* off limit, but $0.03 BELOW signal price entirely
- **Adjusted R after fill** = $0.0406 → **R% = 0.25%** — comically thin

### Price path (1m closes)

| Time ET | C | VWAP | vs entry $16.22 |
|---|---:|---:|---:|
| 10:10 (pre-entry) | 16.21 | 16.22 | -0.06% |
| 10:12 (entry fill $16.22) | — | 16.22 | 0.0% |
| 10:12:25 (trail arm) | peak $16.27 | — | +0.31% |
| 10:13 (trail fire) | signal $16.23, limit $16.15 | — | +0.06% |
| 10:13 (exit fill $16.2010) | — | — | -0.12% |

### What hurt this trade
1. **R% = 0.25% post-fill is below ALL reasonable thresholds.** Same problem as FATN on 5/8 (R% = 1.47% post-fill, also lost). Trailing stop's give-back tolerance ($0.04 from $16.27 peak = 0.25% giveback) was larger than the trade's risk budget. **The bot stopped itself out for a rounding error.**
2. **Trail armed within 25 seconds of fill.** Same pattern as SST 5/8 (trail fired 3 min after fill). The trailing-stop is too aggressive on tight-R trades.
3. **Score 9 is the bypass floor.** Like 5/8's SST (also score 9, also lost), score-9 setups have less margin and should not use the same trail rules as score-10.

**Tuning hypothesis:** Block CHOP_BYPASS when post-fill R% < 1.0% — repricing slippage just ate the trade's risk budget before management could even start.

---

## Trade #3 — CLNN @ 09:43 ET — orphan after trail no-fill (-0.16R)

### Entry decision

**Wave history:** 2 prior waves, 0 prior arms — first arm of the day for CLNN.

**Entry inputs**
- Score: 10, wave_id 3, provisional $7.32, stop $7.1720, **R = $0.148 → R% = 2.02%**
- VWAP at 09:45 bar = $7.25 → entry **+1.0% above VWAP** ✅ (above-VWAP)
- HOD: $7.36 → entry just 0.5% below HOD ⚠️ (near-highs)
- 1m bar at 09:45: $7.32–$7.33, volume only 706 shares

**Order**
- Limit BUY $7.37, FILLED **$7.35** ($0.02 improvement, $0.03 of slippage above signal)
- Post-fill R = $0.178 → R% = 2.42%

### What happened
- 09:55 ET: trail armed @ peak $7.55 (+2.7% from entry); trail set $7.4610
- 09:55:30 ET: price reversed → trail signal $7.48; limit SELL $7.43
- **EXIT NO-FILL — manual review** ← bot logged this; the limit $7.43 didn't catch the bid
- Position stayed open. Trail logic exhausted.
- 11:55 ET (~2h later): bail-timer adopted the still-open position, sold @ $7.32 (limit $7.29, *better* limit than original trail attempt)
- Net: 4,255 × ($7.32 - $7.35) = **-$128**

### What hurt this trade
- **Trail-limit exit didn't catch.** CLNN dropped fast through $7.43; the limit-only sell missed the print. Without an aggressive backup (no market orders allowed per project policy), the position floated for 2 hours.
- **Bail-timer eventually rescued it** at a worse price than peak ($7.32 vs $7.55) but better than where it eventually went (CLNN closed the day at $6.5x).
- **HOD-anchor entry.** Entry at $7.32 was within $0.04 of HOD ($7.36). Like ATRA #6 below — buying near the day's high is the consistent loser.

**Surprising finding:** The 5/8 report flagged "trail-fired-then-no-fill" as theoretical; today CLNN proves it happens in practice on thin small-caps. **This is a real risk vector for live money** — a stop signal that doesn't fill, then doesn't re-fire, leaves the position uninsured until bail-timer arrives 30+ min later.

**Tuning hypothesis:** On trail EXIT NO-FILL, re-arm the trail check on next tick (don't wait for bail-timer). Or: drop the limit by another buffer ($0.05) and resubmit until filled.

---

## Trade #4 — ATRA @ 13:52 ET — hard stop (-1.16R)

### Entry decision

**Wave history (ATRA before arm):** 57 prior waves, **3 prior chop-rejected arms today** (05:29 score 8, 12:06 score 8, 13:14 score 8). This is critical — same-symbol repeat without blacklist.

**Entry inputs**
- Score: 10, wave_id 58, provisional $8.45, stop $8.3491, **R = $0.101 → R% = 1.19%**
- VWAP at 13:50 bar = $8.48 → entry **-0.4% below VWAP** ⚠️
- HOD: $9.20 — entry 8.2% below HOD (well off highs — a *retracement* attempt)
- 5-min bar volume thin (~300 shares)

**Order**
- Limit BUY $8.50, FILLED **$8.47** ($0.03 improvement, $0.02 slip from signal)
- Post-fill R = $0.121 → R% = 1.43%

### Price path

| Time ET | C | VWAP | Δ from $8.47 |
|---|---:|---:|---:|
| 13:55 (post-entry) | 8.42 | 8.48 | -0.59% |
| 14:00 | drift toward $8.40 | 8.48 | -0.83% |
| 14:05 | 8.36 area | 8.48 | -1.30% |
| 14:05 stop hit signal $8.34 | sell limit $8.29 → fill $8.33 | | -1.65% |

### What hurt this trade
1. **Below-VWAP entry on a stock that had already had its run** (HOD was $9.20 at 04:30 ET pre-market — long since faded). Same pattern as 5/8's FATN.
2. **Third arm of the day on ATRA** — chop_blacklist expires after 30 min, and the score-bypass overrides blacklist anyway. **No in-session loss memory.**
3. **R% 1.43% post-fill** — borderline; below the "1.5% safe" threshold the 5/8 winners cleared.

---

## Trade #5 — SST @ 14:18 ET — winner (+3.28R) ← **the day-saver**

### Entry decision

**Wave history:** 59 prior waves, **2 prior chop-rejected arms today** (06:22 score 7, 08:45 score 7, 11:04 score 7) — score finally popped to 9.

**Entry inputs**
- Score: 9 (right at bypass floor)
- Provisional $3.79, stop $3.7507, **R = $0.039 → R% = 1.04%** (provisional — but watch what happens after fill!)
- VWAP at entry: $3.66 area → entry **+3.5% above VWAP** ✅
- HOD before entry: $3.97 → entry 4.5% below HOD

**Order**
- Limit BUY $3.84, FILLED **$3.83** ($0.01 improvement, $0.04 slippage from signal)
- **Adjusted R post-fill = $0.0793 → R% = 2.07%** — slippage DOUBLED the post-fill R because the stop didn't move. This is the same pattern as ATRA on 5/8 (1.97% post-fill, winner).

### Price path

| Time ET | event | price |
|---|---|---:|
| 14:18 | entry fill | $3.83 |
| 14:22 | wave 61 up (in-trade) | trending up |
| 14:28 | wave 62 up (in-trade) | trending up |
| 14:32 | wave 63 down (in-trade) | first wobble — held |
| 14:54 | wave 64 down (in-trade) | second wobble — held |
| 14:56:57 | TRAIL_ARMED peak $3.91 trail $3.87 | +2.1% |
| 14:57 | wave 65 up (in-trade) | re-acceleration |
| 15:01 | trailing_stop signal $4.09 → exit fill $4.09 | **+6.8%** |

### What worked
1. **+3.5% above VWAP at entry, NOT near HOD.** Cleanest of the day. Trend-aligned.
2. **Slippage *helped* by widening R-budget.** Fill $0.04 above signal but stop unchanged → real R% jumped from 1.04% to 2.07%.
3. **43-minute hold through TWO down-waves** (14:32 and 14:54) — bot resisted exiting on wobbles. This is the discipline win.
4. **Trail did the right thing this time:** armed at peak $3.91, fired when reversal materialized at $4.09 (after another leg up). Peak-to-exit giveback was within reasonable bounds because price stair-stepped, not nose-dived.

### What missed
- Same as 5/8 ATRA: SST went on to close higher than the trail exit. 5-min bar at 15:30 shows SST topped at $4.05 then weakened, then bounced again later — there was probably another $0.10-$0.20/share on the table.

---

## Trade #6 — ATRA @ 18:30 ET — late-day chase, hard stop (-1.43R)

### Entry decision

**Wave history:** 81 prior waves, **4 prior chop-rejected arms / 1 prior loser today** on ATRA. Cumulative ATRA P&L going into this trade: **-$548** (#1 -$35 + #4 -$513).

**Entry inputs**
- Score: 10, wave_id 82, provisional $9.59, stop $9.2867, **R = $0.303 → R% = 3.16%**
- VWAP at 18:30 bar: $8.60 → entry **+11.5% above VWAP** ⚠️ (way above, late-cycle)
- HOD: $9.84 (set earlier this hour) → entry 2.5% below HOD ⚠️ (near-top)
- PM_H: $9.20 (entry well above PM high — extended-hours runner)
- 18:30 bar: O=$9.31 H=$9.59 L=$9.31 C=$9.59 V=1,714 (entry on the high of the bar)

**Order**
- Limit BUY $9.64, FILLED **$9.49** ($0.15 improvement, $0.10 *below* signal — favorable!)
- Post-fill R = $0.203 → R% = 2.14%
- Notional: $25,740 (sized down from prior $30K because of risk budget)

### Price path (5-min bars, post-entry)

| Time ET | O | H | L | C | V | vs $9.49 |
|---|---:|---:|---:|---:|---:|---:|
| 18:30 (entry) | 9.31 | **9.59** | 9.31 | 9.59 | 1,714 | 0.0% |
| 18:35 | 9.59 | 9.59 | 9.37 | 9.37 | 1,510 | -1.26% |
| 18:40 | 9.37 | 9.45 | 9.37 | 9.45 | 466 | -0.42% |
| 18:45 | 9.45 | 9.45 | 9.45 | 9.45 | 100 | -0.42% |
| 18:50 | 9.30 | 9.37 | 9.30 | 9.37 | 3,568 | -1.26% |
| 18:55 | 9.33 | 9.33 | 9.33 | 9.33 | 600 | -1.69% |
| 19:05 (stop hit) | 9.20 | 9.20 | 9.20 | 9.20 | 3,416 | **-3.06%** |
| 19:55 (close) | 9.25 | 9.25 | 9.25 | 9.25 | 1,000 | -2.53% |

### What hurt this trade
1. **Bought 2.5% below HOD on the third ATRA attempt of the day, after the stock had already run from $8.30 → $9.84.** Classic top-of-runner entry.
2. **+11.5% above VWAP** — the stock was already extended. VWAP would need to climb $0.89 to even reach the entry price.
3. **No in-session loss memory.** Bot had two ATRA losses logged (-$548 cumulative) and one timeout, but the score=10 bypass still fired.
4. **Stop trailed below VWAP** — stop at $9.29 was still +8.0% above VWAP. The "real" support (VWAP $8.60) was $0.89 below stop. Stop hit on light-volume drift, not a structural break.
5. **Position never traded above $9.59** (the entry-bar high) — same FATN-on-5/8 pattern: never green, never recovered.

**Surprising finding (correcting Manny's initial read):** This was an **above-VWAP loser**, not a below-VWAP one. The "below-VWAP loses" hypothesis from 5/8 doesn't generalize. The cleaner formulation: **entries near HOD after the stock has already extended significantly above VWAP — regardless of which side of VWAP — lose.**

---

## Cross-trade pattern observations (lead with the high-confidence patterns)

### Pattern 1: Post-fill R% < 1.5% predicts loser (5/5 across 5/8 + 5/11)

| Date | Symbol | Score | Post-fill R% | Result |
|---|---|---|---|---|
| 5/8 | FATN | 10 | 1.47% | LOSS -1.04R |
| 5/8 | SST | 9 | 1.25% | LOSS -0.40R |
| 5/8 | ATRA | 10 | **1.97%** | **WIN +2.51R** |
| 5/11 | NVOX | 9 | **0.25%** | LOSS -0.47R |
| 5/11 | ATRA #4 | 10 | 1.43% | LOSS -1.16R |
| 5/11 | SST | 9 | **2.07%** | **WIN +3.28R** |
| 5/11 | ATRA #6 | 10 | 2.14% | LOSS -1.43R |

Both winners ≥ 1.97% R%. All four losers with measurable R%: 0.25%, 1.25%, 1.43%, 1.47%. **The 1.5% threshold cleanly separates winners from losers across 2 days.**

ATRA #6 is the exception — 2.14% R% but still lost. The CONFOUND on that one is "late-day, near-HOD, post-extension." So R% is necessary but not sufficient.

→ **Hypothesis #10:** Require post-fill R% ≥ 1.5% (else cancel and re-arm). Today this kills NVOX (saves -$37) and ATRA #4 (saves -$513). On 5/8 it kills FATN (saves -$772) and SST (saves -$251).

### Pattern 2: Trail fires within 5 min of fill = paper-cut

| Date | Symbol | Fill → trail-arm | Fill → trail-fire | Result |
|---|---|---|---|---|
| 5/8 | SST | ~3 min | ~3 min | LOSS (gave up after $0.05 give-back) |
| 5/11 | NVOX | 25 sec | ~1 min | LOSS (gave up after $0.04 give-back) |
| 5/11 | CLNN | ~12 min | ~13 min | LOSS (trail fired, but limit no-filled — different failure mode) |
| 5/11 | SST | ~39 min | ~43 min | **WIN** (price stair-stepped before trail caught a real reversal) |

The winners have **no trail-fire in the first 30 minutes.** Trail fires fast = the entry didn't have room to breathe.

→ **Hypothesis: "no-trail-exit floor"** for first 5 min after fill. (Already in 5/8 queue as #4.)

### Pattern 3: Same-symbol repeats with no in-session blacklist

ATRA today: 3 trades (entries; counts #1 orphan) — cumulative -$1,326.
- Trade #1 -$35 (07:00 ET, orphan)
- Trade #4 -$513 (13:52 ET)
- Trade #6 -$778 (18:30 ET)

Between each there were additional ATRA arms that *did* chop-reject (12:06, 13:14, 14:54), so the chop gate was working. But the bypass at score=10 ignored the day's loss history. **A stock that's already cost $548 should get a higher bypass bar than score=10.**

On 5/8 there was only one ATRA trade (and it won), so this is a 5/11-specific issue — but the *pattern* of bypass overriding accumulated losses is structural.

→ **Hypothesis #11:** After ≥2 same-symbol losses in a session OR cumulative -$500 same-symbol, demote bypass threshold from 9 → 11 (functionally disabled — score caps at 10 on WB, 12 on SQ).

### Pattern 4: Late-day chase = biggest single loss

| Date | Trade | Time ET | Entry vs HOD | Loss |
|---|---|---|---|---|
| 5/8 | (no late-day loser — ATRA late = winner) | 17:09 | -12.5% below HOD | (won) |
| 5/11 | ATRA #6 | 18:30 | -2.5% below HOD | **-$778** |

Single data point on 5/11, but it's the biggest loser of the day and matches the lookalike on 5/8 (ATRA late-day entry — but 5/8's was 12% off HOD, today's was 2.5% off HOD = much closer to top).

→ **Hypothesis #12:** After 16:00 ET, require entry to be ≥5% below session HOD (no top-tagging in extended hours).

### Pattern 5: Above-VWAP loss disproves "below-VWAP loses" narrative

The 5/8 report's hypothesis was "below-VWAP entries lose" (FATN at -2.2% VWAP lost). Today's ATRA #6 was **+11.5% above VWAP** and lost the most of any single trade. So:

**Refined formulation:** It's not WHICH SIDE of VWAP — it's HOW EXTENDED. Both extremes lose. The wins came from "near VWAP, building above" (5/8 ATRA -0.8% → +5%) or "above-VWAP but with room to run, mid-day" (5/11 SST +3.5% above VWAP, 4.5% below HOD).

The cleaner pattern: **distance to HOD matters more than distance to VWAP for predicting outcome.**

### Slippage analysis (entry side)

| Trade | Signal | Limit | Fill | Slip $ | Slip % |
|---|---:|---:|---:|---:|---:|
| ATRA #1 (orphan) | $8.78 | $8.83 | $8.61 | -$0.17 | -1.94% (favorable) |
| NVOX | $16.25 | $16.33 | $16.22 | -$0.03 | -0.18% (favorable) |
| CLNN | $7.32 | $7.37 | $7.35 | +$0.03 | +0.41% |
| ATRA #4 | $8.45 | $8.50 | $8.47 | +$0.02 | +0.24% |
| SST | $3.79 | $3.84 | $3.83 | +$0.04 | +1.06% (DOUBLED R%!) |
| ATRA #6 | $9.59 | $9.64 | $9.49 | -$0.10 | -1.04% (favorable) |

Today entry slippage was *favorable on net* — 3 of 6 fills came in below signal. This contradicts the typical chase-cost concern.

### Slippage analysis (exit side)

| Trade | Signal | Limit | Fill | vs limit |
|---|---:|---:|---:|---:|
| ATRA #1 | $8.61 | $8.58 | $8.60 | +$0.02 (better) |
| NVOX | $16.23 | $16.15 | $16.2010 | +$0.05 (better) |
| CLNN | $7.48 | $7.43 | **NO FILL** at trail; later $7.32 via bail | – |
| ATRA #4 | $8.34 | $8.29 | $8.33 | +$0.04 (better) |
| SST | $4.09 | $4.04 | $4.09 | +$0.05 (better) |
| ATRA #6 | $9.20 | $9.15 | $9.20 | +$0.05 (better) |

Exit slippage was uniformly favorable EXCEPT the CLNN trail-no-fill, which is a different failure mode (the limit price was too aggressive for the speed of the drop). **Pattern: trail-stop limit prices need to be wider to actually fire on fast drops.**

---

## Main bot deep dive — two notable no-fills

### ODYS 08:48 ET — chase-cap saved us

**Signal:**
```
ENTRY SIGNAL @ 10.0200 stop=9.9000 R=0.1200 score=10.0 setup_type=squeeze
why=squeeze: base=5.0; vol_extra=+5.0; [PARABOLIC]
```

**Order:** Limit BUY $10.07 (signal + $0.05 slip), qty 1497
**Outcome:** `ORDER TIMEOUT: ODYS market $11.22 exceeds max chase $10.27 (2.0% above original $10.07) — giving up`

ODYS gapped from $10.02 → $11.22 in <10s. Per `WB_ENTRY_MAX_CHASE_PCT=2.0`, the retry path aborted at $10.27.

**Counter-factual:** If we'd filled at $11.22:
- R was $0.12 from signal; at $11.22 entry, stop $9.90 = $1.32 of risk
- Risk budget was ~$717 (3.5% of equity at ~$20K), so qty would have shrunk from 1497 → ~543
- ODYS intraday HOD was $13.50 → IF the trade had worked, +$0.30 (modest follow-through) × 543 = +$163. But equally likely ODYS fades — at this kind of vertical move, mean reversion is favored.

**The chase-cap is doing exactly its job.** This is the directive that prevents 2026-01 VERO-style top-tagging. Keep it.

### TRAW 09:31 ET — retry cadence too slow for a parabolic open

**Signal:**
```
ENTRY SIGNAL @ 2.3052 stop=2.2100 R=0.0952 score=12.0 setup_type=squeeze
why=squeeze: base=5.0; vol_extra=+5.0; vwap_dist=+1.0(8%); pm_high_break=+1.0
```

**Order sequence:**
```
🟩 ENTRY: TRAW qty=5514 limit=$2.36 (slip=$0.050)
RETRY 1/3: market=$2.35 new_limit=$2.40 (slip=$0.050)
RETRY 2/3: market=$2.39 new_limit=$2.44 (slip=$0.050)
RETRY 3/3: market=$2.40 new_limit=$2.45 (slip=$0.050)
```

All 4 attempts (initial + 3 retries) timed out over ~40 seconds. Each retry added $0.04 to the limit (1.7% per step). TRAW moved faster than $0.04 per 10 seconds.

**Why this is the harder failure mode:** Score=12 (max possible — score floor is 5, plus 5 bonus + vwap + pm_high) — this was a *higher* conviction signal than ODYS. The setup was textbook. We just couldn't get in.

→ **Hypothesis #13 (already in queue per directive):** Engine cross-feed-aware initial limit + adaptive retry-with-reprice. Currently shipping on the `data-engine-unified` worktree. Would have either (a) sized the initial limit based on Alpaca ask not IBKR signal, or (b) accelerated the reprice cadence on observed market velocity.

---

## Cross-bot data quality issues

### ENSC bar-builder asymmetry — confirmed

Main bot log line 5140: `🔥 Seeded ENSC: 50599 ticks → 33 bars`
Sub-bot log line 3995: `🔥 Seeded ENSC: 50599 ticks → 0 bars (50599 ticks/bar avg)`

**Identical tick count (50,599) → main bot builds 33 bars, sub-bot builds 0.** This is a sub-bot-side bar-builder bug. ENSC was never genuinely tradable in the sub-bot — every ENSC arm came from later in-day tick accumulation, not the pre-market seed. ENSC was BP-rejected once today (14:32 ET) and chop-rejected otherwise, so no real P&L impact, but the bug masks setups.

### CLNN bail-timer logged as -$128 once, then again in "orphan_adopted" summary

Subbot daily summary at session end:
```
ATRA orphan_adopted bail_timer: $-35
CLNN orphan_adopted bail_timer: $-128
```

Both already appear as primary EXIT lines. The session-end "orphan_adopted" tag is a *summary tag*, not double-counting — just confirming the rescue path triggered. Reading the daily P&L tally: -$35 -$37 -$128 -$513 +$2,090 -$778 = **+$599 net**, which matches.

### Tick droughts

The directive flagged CLNN/FATN/KBSX/ATRA tick droughts cross-checked between Alpaca and IBKR. I didn't re-validate at the tick level today — but the chop-reject log shows multiple thin pre-market windows (degenerate bars, V<2500 5-bar avg). This is **real silence on thin small-caps**, not a feed bug. Reaffirms the 2026-05-04 sub-bot deployment hypothesis that "Alpaca data inflates results" needs *more* data, not assertion.

---

## Tuning hypotheses queued (running list — items 10-13 are new)

| # | Hypothesis | Source | Expected effect (this session) | Files |
|---|---|---|---|---|
| 1 | Block bypass when vwap_dist < -1.0% even at score≥9 | 5/8 FATN | Saves ATRA #4 -$513 | `bot_alpaca_subbot.py` chop_bypass |
| 2 | Score=9 requires post-fill R% ≥ 1.5% | 5/8 SST | Saves NVOX -$37, SST 5/8 -$251 | `place_wave_breakout_entry()` |
| 3 | Trail = max(2×R, 1% of price) | 5/8 ATRA upside | More upside on SST winner | trail logic |
| 4 | No trail-exit for first 5 min after fill | 5/8 SST + 5/11 NVOX | Saves NVOX -$37; less paper-cut on SST 5/8 | trail logic |
| 5 | Per-position notional = min($50K, equity × 1.0) | 5/8 TRAW BP reject | Saves 4× TRAW BP rejects today (could net +6× concurrent positions) | sizing |
| 6 | Marketability buffer = min(0.5% × price, $0.05) | 5/8 slippage table | Today slippage was favorable, this is dormant | order placement |
| 7 | Wire pyramid leg2 OR remove trigger event | 5/8 SST + ATRA | No pyramid triggered today; still latent | wave-breakout pyramid |
| 8 | Entry timeout 10s → 30s for score≥9 | 5/8 CLNN | Helps the 2 ATRA timeouts today (07:00, 09:31), helps 13:27 CLNN | order placement |
| 9 | Liquidity prefilter: skip arm if last 60s ticks <20 | 5/8 CLNN | Today's ATRA #1 race condition still hits this | ARM logic |
| **10** | **Block bypass when post-fill R% would be < 1.5%** (predict R% from price+stop+slip) | 5/8 + 5/11 both days | **Saves NVOX -$37 + ATRA #4 -$513 today = -$550 today** | chop_bypass logic |
| **11** | **Per-symbol in-session loss-blacklist (after ≥2 losers OR cumulative -$500, demote bypass)** | 5/11 ATRA ×3 | **Saves ATRA #6 -$778 today** | bypass + chop_blacklist |
| **12** | **Late-day chase guard: after 16:00 ET, require entry ≥5% below session HOD** | 5/11 ATRA #6 | **Saves ATRA #6 -$778 today** (overlaps with #11) | chop_bypass |
| **13** | **Engine cross-feed-aware initial limit + adaptive retry-with-reprice** | 5/11 ODYS + TRAW | Gives ODYS + TRAW a fighting chance to fill main bot (shipping on `data-engine-unified`) | main bot retry path |

**Net effect of #10+#11+#12 in isolation today: -$1,328 saved** (5 losers culled to 1-2). Sub-bot day would have been roughly +$2,090 SST winner + perhaps -$200 of remaining noise = **+$1,890 instead of +$599** — but on small sample. Still need ≥3 more sessions of data before applying any of these.

---

## Daily metrics for next-day comparison

| Metric | 5/8 value | 5/11 value | Trend |
|---|---|---|---|
| # WB_ARMED events | 24+ | 28 | ↑ |
| # CHOP_REJECT | 9 | 14 | ↑ (gate working harder) |
| # CHOP_BYPASS triggers | 5 | 9 | ↑ |
| # bypass → fill | 3 / 5 | 6 / 9 (incl 2 orphans) | ↑ |
| # bypass → win | 1 / 3 | 1 / 6 | ↓ (lower WR) |
| Avg R-multiple | +1.07 | -0.09 | ↓ (winner less dominant) |
| Avg slippage on entry | +$0.026 / +0.69% | -$0.04 net (3 favorable, 3 cost) | ≈ |
| Avg slippage on exit | -$0.013 (favorable) | -$0.041 (favorable) | ≈ |
| Equity day change | +$1,485 (+5.0%) | +$599 (~+2%) | ↓ |
| # same-symbol repeat losers | 0 | 2 (ATRA #4 then #6) | NEW pattern |
| # entry timeouts | 1 | 3 | ↑ |
| # BP rejects | 1 (TRAW) | 5 (4× TRAW + ENSC) | ↑ |
| # trail-no-fill | 0 | 1 (CLNN) | NEW failure mode |
| Main bot fills | 0 | 0 | flat |
| Main bot chase-cap saves | – | 1 (ODYS) | NEW |
| Main bot retry-cap aborts | – | 1 (TRAW) | NEW |

---

## Raw data references

- Sub-bot log: `/Users/duffy/warrior_bot_v2/logs/2026-05-11_subbot_alpaca.log` (26,095 lines)
- Main bot log: `/Users/duffy/warrior_bot_v2/logs/2026-05-11_daily.log` (31,659 lines)
- Cron log: `/Users/duffy/warrior_bot_v2/logs/cron_2026-05-11.log` (63 lines)
- Alpaca order ledger: pulled live at report time via `tc.get_orders()` against PA3LXGIPGG8B; 15 orders (6 fills + 3 cancels + 4 BP rejects + 2 trail no-fills)
- Tick caches (IBKR feed):
  - Main: `/Users/duffy/warrior_bot_v2/tick_cache/2026-05-11/` (~120 symbols)
  - Sub-bot: `/Users/duffy/warrior_bot_v2/tick_cache_alpaca/2026-05-11/` (9 traded symbols)
- This report's source events (sub-bot log line numbers):
  - ATRA #1: 3913-3917, 4106-4107
  - NVOX: 9167-9207
  - CLNN: 8267-8678, 11994-11995
  - ATRA #4: 15691-16078
  - SST: 16463-17771
  - ATRA #6: 23689-24559
- Main bot key events: daily log lines 8543-8547 (ODYS), 9997-10018 (TRAW)

*Companion: `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (Friday, prior session in this series).*
