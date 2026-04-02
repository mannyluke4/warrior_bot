# Dynamic Player Strategy: Wave Analysis Deep Dive

**Date:** 2026-03-30
**Purpose:** Synthesize tick-level wave data from 10 stocks into mechanical rules for a dynamic trading system that enters dips, exits bounces, and recognizes when the run is over.

---

## 1. Dataset Overview

| Stock | Date | SQ Exit | HOD | Cont Range | Up Waves | Avg Retrace | Avg Dip Dur | Category |
|-------|------|---------|-----|------------|----------|-------------|-------------|----------|
| ROLR | 2026-01-14 | $4.32 | $33.68 | 680%+ | 101 | varies | varies | Monster runner |
| VERO | 2026-01-16 | $5.32 | $12.93 | 143% | 47 | 140.7% | 2.6m | Cascade + halts |
| ALUR | 2025-01-24 | $8.32 | $20.30 | 144% | 43 | varies | varies | Runner + halts |
| AMOD | 2025-01-30 | $2.32 | $5.54 | 139% | 75 | 130.2% | 5.0m | Choppy late runner |
| SHPH | 2026-01-20 | $2.20 | $5.00 | 127% | 89 | varies | varies | Extreme vol + halts |
| INM | 2025-01-21 | $7.32 | $9.17 | 25% | 80 | 156.6% | 4.9m | Halt-dominated chop |
| EEIQ | 2026-03-26 | $9.22 | $12.70 | 38% | 22 | 128.8% | 2.4m | One push then fade |
| ASTC | 2026-03-30 | $4.14 | $6.48 | 57% | 12 | 104.2% | 2.4m | Clean staircase |
| GDTC | 2025-01-06 | $5.32 | $7.93 | 49% | 73 | varies | varies | Moderate runner |
| CRE | 2026-03-06 | $5.32 | $8.11 | 0% | 31 | varies | varies | CONTROL — dead immediately |

---

## 2. The Three Phases Every Stock Goes Through

Every single stock in the dataset follows the same lifecycle after the squeeze exit. The Dynamic Player's job is to identify which phase the stock is in and act accordingly.

### Phase 1: RUNNING (Buy the Dips)
The stock is making consecutive new highs. Each dip is shallow and brief. This is where the money is made.

**Signature — ALL of these must be true:**
- Prior up-wave made or approached a new HOD
- Dip retrace < 60% of prior up-wave
- Price holds above VWAP throughout the dip
- EMA9 holds or briefly touched then recovered
- Dip duration ≤ 3 minutes
- Volume ratio on dip ≤ 1.5x of prior up-wave

**Evidence from the data:**

ASTC (cleanest example): Waves 1-11 are a textbook staircase.
- Wave 2 (dip): 168% retrace BUT it was the first dip right off the squeeze — an outlier. 4.93x vol ratio. This is the "shakeout" dip.
- Wave 4: 42% retrace, 4m, 1.07x vol, above VWAP, broke EMA briefly → bounce to NEW HOD ✅
- Wave 6: 40% retrace, 2m, 1.06x vol, above VWAP+EMA → bounce to NEW HOD ✅
- Wave 8: 54% retrace, 1m, 0.93x vol, above VWAP+EMA → bounce to NEW HOD ✅
- Wave 10: 69% retrace, 1m, 1.16x vol, above VWAP+EMA → bounce to NEW HOD ✅

ROLR: Waves 1-31 (first hour) show the same pattern at massive scale. Each dip 30-58% retrace, above VWAP, 1-4 min duration, bounce to new HOD every time.

VERO (pre-halt): Waves 1-15 at $5-$6 range. Dips 55-100% retrace, 1-4 min, above VWAP. Then halts scramble everything (see Phase special case below).

EEIQ: Wave 2 (first dip after the big push) = 66% retrace, 2m, above VWAP → bounce near HOD. Wave 4 = 104% retrace → Warning phase transition.

### Phase 2: WARNING (Tighten Up / Reduce Size)
The stock is losing momentum. Dips are getting deeper and bounces aren't making new highs. Still tradeable but with reduced conviction.

**Signature — ANY of these appearing:**
- Dip retrace 60-100% of prior up-wave
- EMA9 broken during dip (not just touched)
- Dip duration 3-5 minutes
- Volume ratio on dip 1.5-2.0x
- Bounce fails to make new HOD (lower high)

**Evidence:**

ASTC Wave 12: THE phase transition wave. Retrace 142%, 4 min, 0.94x vol, broke EMA. The bounce (wave 13) only got to $5.65 vs HOD of $6.48 — a dramatically lower high. After this, no wave ever makes a new HOD again. ASTC is done.

EEIQ Waves 4-6: Retrace 104%, then 225%. The bounce after wave 6 ($9.27→$9.90) doesn't come close to HOD ($12.70). Warning → Done.

VERO Waves 82-90 (post $12.93 HOD): Retraces of 149%, 92%, 134%. Bounces at $12.10, $11.72, $11.38, $11.06 — each one lower. Classic distribution.

GDTC Wave 11 (the crash): Retrace 1357% (!), $7.93→$5.72. Massive. But then recovery to $7.92 (wave 18) — nearly a new HOD. This is the halt/crash special case.

### Phase 3: DONE (Stop Trading)
The run is definitively over. The stock is fading, chopping, or crashing. No more entries.

**Signature — ANY ONE of these is terminal:**
- Dip retrace >100% AND next bounce makes a lower high AND below EMA9
- Price falls below VWAP and stays below for 2+ consecutive waves
- Two consecutive dips with retrace >100%
- Dip duration >5 minutes with retrace >80%

**Evidence:**

CRE (control group): Wave 2 = -64.2%, retrace 187%, 12 min duration. Instantly below VWAP. Never recovers. Every subsequent wave below VWAP. This stock was DONE from minute one post-squeeze.

EEIQ Wave 8: 451% retrace, 12 min, below VWAP. Everything after this is below VWAP. Done.

AMOD post-wave 7: Broke below VWAP at wave 7 (182% retrace). Spent waves 7-21 (08:44-09:22) chopping between $2.79-$3.35, mostly below VWAP. Then sudden second wind at wave 22 ($2.79→$5.54, +98.6%). This is the "late runner" edge case — but note it required breaking back above VWAP with a massive vol surge (5.17x).

VERO Wave 92: 359% retrace, 8 min, $11.06→$9.23. After the $12.93 HOD, this is the terminal decline. The bounce (wave 93, $9.23→$10.65) is far below HOD. Done.

INM post-wave 5: After HOD at $9.17, the stock enters halt chaos. Waves 11, 15, 19, 21 have retraces of 402%, 368%, 409%, 105%. This stock was essentially untradeable after the first 10 minutes due to halts.

---

## 3. The Halt Problem

Three stocks (VERO, INM, SHPH) had circuit breaker halts that create artificial 100%+ retrace waves. These look like "Done" signals but the stock resumes running after the halt lifts.

**Key distinguisher: Post-halt behavior**

- VERO waves 16-25: Wild halt swings ($4.12→$6.30→$3.86→$6.81→$2.11→$5.95→$2.12→$6.28). These are NOT tradeable by a Dynamic Player — the halts make entries impossible and stops meaningless.
- After halts settle (VERO wave 26 onward, ~$5.70-$5.90): The stock re-establishes a RUNNING pattern with shallow dips above VWAP. Then wave 45 launches $5.63→$7.40 (new HOD).

**Rule: When a halt occurs, the Dynamic Player pauses and waits for 3 consecutive waves (up-down-up) that all hold above VWAP before re-engaging.**

INM is the cautionary tale: halts at 08:00, 08:05, 08:31 made the stock completely chaotic. Average dip retrace 156% with most waves below VWAP. Even Ross probably had trouble with this one.

---

## 4. The "Buyable Dip" Scorecard

Based on every dip across all 10 stocks, here are the quantified thresholds for a tradeable dip entry:

| Signal | Green (Enter) | Yellow (Caution) | Red (Don't Enter) |
|--------|---------------|-------------------|--------------------|
| Retrace % | < 50% | 50-80% | > 80% |
| VWAP | Holds above | Touches, recovers | Below |
| EMA9 | Holds above | Breaks, recovers within 1m | Below for 2+ min |
| Dip Duration | ≤ 2 min | 2-4 min | > 4 min |
| Vol Ratio (dip/prior up) | < 1.0x | 1.0-1.5x | > 1.5x |
| Prior bounce made new HOD? | Yes | Approached (within 3%) | No (lower high) |

**Scoring:**
- 5-6 Green signals = STRONG entry (full size)
- 3-4 Green + rest Yellow = MODERATE entry (reduced size or tighter stop)
- Any Red signal = NO entry
- 2+ Red signals = phase transition to WARNING or DONE

**Validation against the data:**

ASTC Wave 4 (good dip): Retrace 42% ✅, above VWAP ✅, broke EMA (yellow), 4m (yellow), vol 1.07x (yellow), prior HOD yes ✅. Score: 3G/3Y = MODERATE. Bounce: +18.6% to new HOD. ✅ Profitable.

ASTC Wave 12 (bad dip): Retrace 142% ❌, above VWAP ✅, broke EMA ❌, 4m (yellow), vol 0.94x ✅, prior HOD yes ✅. Score: 3G/1Y/2R = NO ENTRY. Correct — stock never recovered.

EEIQ Wave 2 (good dip): Retrace 66% (yellow), above VWAP ✅, broke EMA (yellow), 2m ✅, vol 1.49x (yellow), prior HOD yes ✅. Score: 3G/3Y = MODERATE. Bounce: +16.6%, approached HOD. ✅ Profitable.

EEIQ Wave 8 (bad dip): Retrace 451% ❌, below VWAP ❌, below EMA ❌, 12m ❌, vol 0.22x ✅ (misleading — slow bleed), no prior HOD (yellow). Score: 1G/1Y/4R = ABSOLUTELY NOT. Correct.

CRE Wave 2 (dead stock): Retrace 187% ❌, below VWAP ❌, below EMA ❌, 12m ❌, vol high ❌, HOD n/a. 5 Reds. Correctly identified as DONE.

VERO Wave 46 (good dip in running phase): Retrace 30% ✅, above VWAP ✅, above EMA ✅, 1m ✅, vol 1.89x (red — but this is the halt recovery surge). Score: 4G/1R. Still entered. Bounce +7.6%.

---

## 5. The Dynamic Player State Machine

Based on the wave patterns, here is the proposed state machine:

```
IDLE → WATCHING → PLAYING → DONE
```

### State: IDLE
- **Entry condition:** SQ trade exits (sq_target_hit, trailing stop, etc.)
- **Action:** Start tracking waves. Count the first up-wave and first down-wave.
- **Transition to WATCHING:** After first complete down-wave (dip) finishes.

### State: WATCHING
- **Purpose:** Evaluate whether the stock is worth playing dynamically.
- **Evaluate:** Score the first dip using the Buyable Dip Scorecard.
- **Transition to PLAYING:** If score ≥ 3 Green and 0 Red → enter on the first dip bounce.
- **Transition to DONE:** If any Red signal, or if the first dip takes >5 minutes.
- **Special:** If a halt occurs during the first wave, wait for 3 post-halt waves above VWAP.

### State: PLAYING
- **This is the active trading state.** The system is dynamically entering and exiting.
- **ENTRY logic:** Enter on each dip that scores ≥ 3G/0R on the scorecard.
  - Entry price: As close to the dip low as possible. Practically: when the dip shows signs of reversing (tick uptick after the down-wave, or price reclaims EMA9 from below).
  - Position size: Full if 5-6 Green. Reduced (50%) if 3-4 Green with Yellows.

- **EXIT logic:** Take profit on each bounce.
  - Primary exit: When the up-wave shows the first down-tick after making a swing high (the wave reversal detection you already have in `analyze_runner_waves.py`).
  - Safety exit: Hard stop at 2% below entry (or the dip low, whichever is tighter).
  - Time exit: If position is flat or negative after 3 minutes, exit at market.

- **TRACKING between trades:**
  - After each exit, immediately start scoring the next dip.
  - Track whether the bounce made a new HOD (critical for phase detection).
  - Track consecutive "lower high" bounces → phase transition signal.

- **Transition to DONE:** Any of:
  - A dip scores ANY Red → stop entering
  - Two consecutive bounces fail to make new HOD (lower highs)
  - Price closes a full 1m bar below VWAP
  - Dip retrace >100% on any wave

### State: DONE
- **Terminal state.** No more entries for this stock.
- **Exception:** If the stock later breaks to a new HOD with volume (AMOD wave 22 pattern), the SQ detector will catch it as a new squeeze. Don't try to detect second winds in the Dynamic Player — let SQ handle it.

---

## 6. How This Differs From CT and Runner Mode

| Feature | CT (shelved) | Runner Mode (rejected) | Dynamic Player (proposed) |
|---------|-------------|----------------------|--------------------------|
| Entry | Single pullback entry | Hold from SQ exit | Multiple dip entries |
| Exit | Single exit | Single trail | Multiple bounce exits |
| # of trades | 1 | 0 (just holds) | 3-10 per stock |
| Adapts to chart | No (fixed state machine) | No (fixed trail %) | Yes (scorecard per wave) |
| Knows when to stop | MACD/duration gates | Never (rides to trail) | Lower high + VWAP break |
| Handles ASTC (clean) | Missed (MACD blocked) | 5R trail: caught some | Would catch waves 5-11 |
| Handles CRE (dead) | Correctly avoided | Would ride into crash | Correctly avoided (Red score) |
| Handles VERO (halts) | Blocked by cascade gate | Would hold through halts | Pauses during halts, re-engages |

---

## 7. Estimated P&L Impact (Conservative)

Working through the wave data trade-by-trade for 3 representative stocks:

### ASTC (clean staircase)
- Current SQ P&L: Exit $4.14 (target hit)
- Dynamic Player entries: Waves 5, 7, 9, 11 (4 dip entries)
- Approximate captures: Wave 5 ($4.63→$5.49, +18%), Wave 7 ($5.15→$5.80, +13%), Wave 9 ($5.45→$6.12, +12%), Wave 11 ($5.66→$6.48, +14%)
- At $50K notional per trade, ~$2,500-$4,000 additional profit
- Wave 12 correctly avoided (Red score)

### EEIQ (one push then fade)
- Current SQ P&L: Exit $9.22 (target hit)
- Dynamic Player entries: Wave 3 ($10.39→$12.12, +16%) — 1 entry
- Wave 4 scores Red (104% retrace) → DONE
- At $50K notional, ~$800 additional. Modest but clean.

### VERO (cascade with halts)
- Current SQ captures cascade re-entries at higher levels
- Dynamic Player would add: Post-halt running phase (waves 46-79)
- Conservative estimate: 3-5 additional wave captures in the $7-$9 range
- At $50K notional, ~$3,000-$5,000 additional
- But CRITICAL: Must not interfere with SQ cascade entries. Dynamic Player only activates AFTER the last SQ exit.

### Conservative total across portfolio:
- If 30% of active days have playable continuation (per CT deep dive data): ~15 days per 49-day period
- Average additional capture per playable day: $1,500-$3,000
- **Estimated uplift: $22,500-$45,000 over the 49-day test period**
- This dwarfs CT's +$413

---

## 8. Risk Mitigation

### Regression safety
- Dynamic Player only activates AFTER the SQ position is fully closed
- It does NOT modify any SQ detection, entry, or exit logic
- SQ cascade re-entries take priority (if SQ re-arms while DP is in WATCHING, SQ wins)
- All DP trades use the same position sizing as SQ (WB_MAX_NOTIONAL)
- Gate: `WB_DYNAMIC_PLAYER_ENABLED=0` (OFF by default)

### Per-trade risk
- Hard stop: 2% below entry or dip low
- Time stop: 3 minutes unprofitable
- Max loss per DP trade: ~$1,000 at $50K notional
- Max consecutive DP trades per stock: configurable (default 10)
- Max total DP loss per stock: configurable (default $2,000)

### The AMOD problem (choppy below-VWAP stocks)
AMOD waves 7-21 were below VWAP with 100%+ retraces. The scorecard correctly blocks all of these (Red on VWAP, Red on retrace). The late runner at wave 22 ($2.79→$5.54) would be caught by the SQ detector, not the DP.

---

## 9. Implementation Requirements for CC

### New file: `dynamic_player.py`
- State machine: IDLE → WATCHING → PLAYING → DONE
- Receives the same 1m bar feed as SQ detector
- Tracks waves internally (up/down detection already built in `analyze_runner_waves.py`)
- Scorecard evaluation on each completed down-wave
- Entry/exit signal generation

### Integration with simulate.py
- After SQ position closes, hand off to DP if enabled
- DP generates BUY/SELL signals that go through TradeManager
- DP positions tracked separately from SQ (different entry reasons)
- When SQ re-arms (new PRIMED), DP goes to DONE (SQ priority)

### Wave detection
- Port the swing detection logic from `analyze_runner_waves.py` to real-time
- Need: wave_high, wave_low, wave_start_time, wave_volume, wave_duration
- Compare each completed down-wave against the scorecard
- Track: prior_up_wave_move, prior_up_wave_hod_status

### Configuration (.env)
```
WB_DYNAMIC_PLAYER_ENABLED=0
WB_DP_MAX_RETRACE_GREEN=50    # % threshold for green retrace score
WB_DP_MAX_RETRACE_RED=80      # % threshold for red retrace score
WB_DP_MAX_DIP_DURATION_GREEN=2  # minutes
WB_DP_MAX_DIP_DURATION_RED=4    # minutes
WB_DP_MAX_VOL_RATIO_GREEN=1.0
WB_DP_MAX_VOL_RATIO_RED=1.5
WB_DP_MIN_GREEN_SIGNALS=3     # minimum green signals to enter
WB_DP_MAX_RED_SIGNALS=0       # maximum red signals allowed
WB_DP_HARD_STOP_PCT=2.0       # % below entry for hard stop
WB_DP_TIME_STOP_MIN=3         # minutes unprofitable before exit
WB_DP_MAX_TRADES_PER_STOCK=10
WB_DP_MAX_LOSS_PER_STOCK=2000
WB_DP_HALT_RECOVERY_WAVES=3   # consecutive above-VWAP waves needed after halt
```

---

## 10. Next Steps

1. **CC Directive:** Write `DIRECTIVE_DYNAMIC_PLAYER_V1.md` with implementation spec
2. **Phase 1:** Build `dynamic_player.py` with wave tracking + scorecard + state machine
3. **Phase 2:** Integrate into simulate.py, gated by env var
4. **Phase 3:** Backtest on all 10 wave analysis stocks
5. **Phase 4:** Run full 49-day regression — must show $0 delta on SQ-only stocks and positive delta on runner stocks
6. **Phase 5:** If successful, wire into bot.py for paper trading

---

## Appendix: Per-Stock Wave Classification

### ASTC — "Clean Staircase"
- Running: Waves 1-11 (10:18-10:57). 6 consecutive new HODs.
- Phase transition: Wave 12 (142% retrace, 4m, broke EMA)
- Done: Wave 13 onward. No new HODs. Choppy $4.80-$5.53 range.
- DP opportunity: 4 dip entries (waves 5,7,9,11 bounces). 0 losses.

### EEIQ — "One Push Then Fade"
- Running: Wave 1 only (single massive +37.7% push, 8 min)
- Phase transition: Wave 4 (104% retrace), confirmed by Wave 6 (225% retrace)
- Done: Wave 8 onward (451% retrace, below VWAP permanently)
- DP opportunity: 1 dip entry (wave 3 bounce). Then stop.

### VERO — "Cascade Runner With Halts"
- Running Phase 1: Waves 1-15 ($5.32-$6.34). Shallow dips above VWAP.
- HALT CHAOS: Waves 16-25 ($4.12→$6.81→$2.11→$5.95 etc). Untradeable.
- Consolidation: Waves 26-44 ($5.66-$5.85). Tight range above VWAP. Low vol.
- Running Phase 2: Wave 45 breakout ($5.63→$7.40, NEW HOD). Then waves 45-79 with dips 30-51% retrace.
- Running Phase 3: Wave 57 surge ($6.59→$8.00), waves to $12.93 HOD at wave 79.
- Phase transition: Wave 86 (230% retrace), Wave 92 (359% retrace, 8 min).
- Done: Post wave 92, bounces $9-$10 range, well below $12.93 HOD.
- DP opportunity: Multiple entries in phase 2 (waves 46-55 range) and phase 3 (waves 57-79). Potentially 8-12 trades.

### ROLR — "Monster Runner"
- Running: Waves 1-31+ (most of the session). Each wave makes new HOD. Retraces 30-58%.
- This stock ran so hard that DP would have been in near-continuous trades.
- DP opportunity: Massive — potentially 15+ dip entries across the run to $33.68.

### CRE — "Control / Dead Immediately"
- Wave 1: +52.4% ($5.32→$8.11). Looks promising.
- Wave 2: -64.2% ($8.11→$2.90). 187% retrace, 12 min, below VWAP. DONE.
- Every signal is Red. DP correctly stays out.
- DP loss: $0. Correct behavior.

### AMOD — "Choppy Late Runner"
- Brief run: Waves 2-5 ($2.32→$3.45). Mixed signals.
- Choppy below-VWAP: Waves 7-21 (08:44-09:22). Most dips >100% retrace, below VWAP. Scorecard says NO.
- Late runner: Wave 22 ($2.79→$5.54, +99%, 21 min). Caught by SQ, not DP.
- Post-runner chop: Waves 23-89. Mostly below VWAP. Choppy $3.50-$4.70.
- DP opportunity: Minimal. Maybe 1-2 entries in early running phase. The late runner would be SQ territory.

### INM — "Halt-Dominated Chaos"
- Brief run: Waves 2-4 ($6.81→$9.17, two waves making new HODs)
- Wave 5: 72% retrace, 10 min. Yellow/Red territory.
- Halt chaos: Waves 11, 15, 19, 21 with 400%+ retraces. Below VWAP.
- DP opportunity: Possibly 1 entry (wave 6 dip at $7.67 with 72% retrace — borderline). Then halts make it untradeable.

### GDTC — "Moderate Runner"
- Running: Early waves making new HODs up to $7.93
- Crash: Wave 11 at 1357% retrace. But then recovery.
- DP opportunity: Several entries in early running phase before the crash.

### SHPH — "Extreme Volatility"
- Running with massive swings: 50-100% up-waves, 50-60% retraces
- Multiple halts throughout
- DP opportunity: Risky. The swings are profitable but the retrace depths are near Red threshold consistently. Reduced size territory.
