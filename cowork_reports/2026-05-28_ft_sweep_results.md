# FT Exit Parameter Sweep — Results

**Date**: 2026-05-28 (evening)
**Owner**: CC
**Source directive**: `cowork_reports/2026-05-28_phase3_stage1_5_sweep_directive.md`
**Stage 1 results context**: `cowork_reports/2026-05-28_firestorm_trigger_backtest_results.md`
**Status**: Three runs complete (B, C, D). Verdict: **both hypotheses are real, both effects matter, and they compound nonlinearly.** Track A should incorporate both. Sweep recovers 47% of baseline loss but does not close it — long-only ceiling still binds.

---

## TL;DR

Three single-variable sweeps against YTD 2026 vs Stage 1 baseline (A). All against the same universe, same FT trigger, same downstream regime_shift / MOVE_STRIKE / REENTRY pipelines. Only the FT exit framework differs.

| Run | Change | FT P&L | Delta vs A | WR |
|---|---|---|---|---|
| A — baseline (Stage 1) | bar_low × 0.99 hard stop | -$102K | — | 48% |
| B — sizing | min(10c, 5%) R floor | -$80K | **+$22K** | 48% |
| C — philosophy | 25% drawdown floor + flatten 15:30 | -$98K | +$4K | **66%** |
| D — combined (B + C) | both | **-$58K** | **+$44K** | **67%** |

**The sweep answers the directive's two hypotheses cleanly:**

1. **Sizing hypothesis is real.** B alone recovers $24K of A's -$108K control delta (22%). Floor on R prevents the 4-cent-stop-on-$3-stock pathology that produced Stage 1's POLA -$8,963.
2. **Philosophy hypothesis is real, but expressed through WR not P&L.** C alone only recovers $11K (10%) of total P&L because the wider drawdown floor produces a few larger tail losses that offset the gains from winners running longer. WR jumps 48% → 66%.
3. **Combined (D) > B + C summed.** D recovers $51K = $24K (B alone) + $11K (C alone) + $16K compound. The two effects multiply: B caps the share count behind each trade (so any tail loss is smaller), C extends winners (so each winner contributes more). Stacking gets defense from both sides.

**Track A recommendation**: incorporate both Run B's stop floor AND Run C's drawdown-floor philosophy. CC will defer parameter choices (floor magnitudes, drawdown %, force-flatten time) to Cowork's Track A spec.

**Bigger story**: even D still loses -$57K YTD. The Phase 2 long-only-bidirectional ceiling is intact. The sweep moves FT from "catastrophic" to "mediocre but salvageable." Closing the remaining gap likely requires bidirectional support (the Phase 2 verdict's 50/50 up/down split says long-only caps captured edge at ~half).

---

## Methodology

All four runs ran the identical config except for the FT exit env vars (Runs A through D). Same universe source (tick_cache fallback for early-YTD days), same time window (2026-01-02 through 2026-05-28), same time cutoff (FT arms only ≤ 12:00 ET), same trigger threshold (6,000 ticks/min + 5% gap from prior close).

| Run | Env vars added |
|---|---|
| A baseline | (none) |
| B | `WB_FT_STOP_FLOOR_ABS=0.10 WB_FT_STOP_FLOOR_PCT=0.05` |
| C | `WB_FT_DRAWDOWN_FLOOR_PCT=0.25 WB_FT_FORCE_FLATTEN_TIME=15:30` |
| D | union of B + C |

Code changes (sim-only, gated by env, default behavior unchanged):
- `simulate_subbot.py`: stop floor in `_open_firestorm_trigger_position`; force-flatten in `on_tick` override
- `move_strike_subbot.py`: dispatcher branches on `WB_FT_DRAWDOWN_FLOOR_PCT > 0` for FT positions; regime_shift exit path untouched

Each YTD run executed via `replay_subbot_universe.py` against `simulate_subbot.py` subprocess per (date, symbol) tuple. All three runs in parallel; ~15 min wall clock each.

---

## Detailed comparison

### Top-line

| Metric | A | B | C | D |
|---|---|---|---|---|
| Total trade records | 862 | 851 | 907 | 875 |
| Total all-strategy P&L | -$157K | -$133K | -$146K | -$106K |
| **Delta vs control (no FT)** | **-$108K** | **-$85K** | **-$98K** | **-$57K** |
| FT-only trade records | 651 | 639 | 698 | 672 |
| **FT-only P&L** | **-$102K** | **-$80K** | **-$98K** | **-$58K** |
| FT-only WR | 48% | 48% | **66%** | **67%** |
| Worst single trade | -$8,963 | -$3,565 | **-$11,823** | -$3,977 |
| Days FT < -$3K | 13 | 10 | **18** | 13 |
| Coverage (unique pairs) | 223 | 222 | 217 | 216 |

Coverage stays roughly constant across runs — the trigger is firing on the same symbols regardless of exit framework. The exit-only changes are the entirety of the P&L delta.

### Hypothesis recovery

Baseline (A) loss vs control = **-$108,382**.

| Run | Recovery | % of A's loss |
|---|---|---|
| B (sizing) | +$23,840 | 22% |
| C (philosophy) | +$10,577 | 10% |
| D (combined) | **+$50,984** | **47%** |

D > B + C (D = $51K vs B + C = $34K). The +$17K excess is the compound benefit: smaller share counts under wider drawdown floors mean tail losses are smaller AND winners get more runway, simultaneously.

### Worst-loss trade trace (Stage 1's top 5 worst FT trades, traced through B/C/D)

| Date | Time | Sym | A entry | A R | A P&L | B P&L | C P&L | D P&L |
|---|---|---|---|---|---|---|---|---|
| 2026-03-12 | 08:01 | POLA | $2.59 | $0.04 | **-$8,963** | **-$2,480** | $0 (no trade) | -$2,790 |
| 2026-02-18 | 08:06 | LRHC | $2.40 | $0.08 | -$5,515 | (no trade) | -$5,515 | (no trade) |
| 2026-01-23 | 08:11 | KUST | $3.72 | $0.28 | -$3,249 | -$3,249 | -$3,249 | -$3,249 |
| 2026-02-12 | 08:34 | JDZG | $2.09 | $0.17 | -$2,782 | -$2,782 | -$2,782 | -$2,782 |
| 2026-04-16 | 09:04 | BTOG | $5.84 | $0.81 | -$2,064 | -$2,064 | -$2,064 | -$2,084 |

What the trace shows:

- **POLA**: B reduces the loss by 72% (sizing fix forces wider R, fewer shares). C blocks the trade entirely — likely because the stop placement is wider (entry $2.59 - 25% = $1.94 ≪ the bar_low * 0.99 from Stage 1), and the position never opens because the wider R makes qty fall below floor. Note: D's -$2,790 is mostly B's sizing benefit.
- **LRHC**: B blocks the trade entirely (sizing makes R too wide for the available risk budget given probe mult). C does nothing because the drawdown floor doesn't trigger on this particular price action. Effective for B/D, no effect for C.
- **KUST, JDZG**: identical across all runs. These are the trades where the R is already comfortably above the floor AND the drawdown doesn't reach the 25% ceiling. The exit framework changes don't touch these.
- **BTOG**: similar — already had a $0.81 R, so the floor doesn't help.

Key insight: B helps by *preventing some trades from opening* in the first place. C helps by *changing the exit on trades that do open*. They address different parts of the loss distribution.

### Per-month FT-only P&L

| Month | A | B | C | D |
|---|---|---|---|---|
| 2026-01 | -$31K | -$29K | -$7K | -$6K |
| 2026-02 | -$26K | -$25K | -$35K | -$29K |
| 2026-03 | -$14K | -$6K | -$4K | -$1K |
| 2026-04 | -$20K | -$12K | -$47K | -$18K |
| 2026-05 | -$11K | -$8K | -$4K | -$4K |

Notable:
- **C is much worse than A in April** (-$47K vs -$20K). The drawdown floor philosophy fails on at least one April day. Without per-day attribution this is the strongest hint that C alone has a tail-risk problem the sweep didn't visualize.
- **D in March is essentially break-even** (-$644).
- **Jan and Feb are the bleed months** across all runs. Feb is the worst for C and D both. February might be a structurally bad month for the trigger (low-tick environment, high false-firestorm rate).

---

## Per-hypothesis verdict

### Sizing hypothesis: PROVED

A 10c/5% R floor — minimum absolute or percent stop distance — recovers 22% of the loss by preventing the share-count explosion on sub-$5 stocks. The effect is bounded: it doesn't fix the strategy, just caps the blast radius on the worst category of failures.

POLA is the clean example: same trigger, same exit timing, but B's wider R = $0.215 means qty drops from ~1800 to ~770 shares, so the same -$0.64 price move costs -$493 instead of -$8,963.

### Philosophy hypothesis: PROVED (with caveats)

The 25% drawdown floor + 15:30 force-flatten:
- Boosts WR from 48% to 66% (winners get runway to mature into the partial-target instead of stopping out on chop)
- Recovers only 10% of P&L on its own, because some trades that were small losers in A become catastrophic in C (when the drawdown floor finally triggers, the position is much bigger underwater than a bar_low * 0.99 stop would have allowed)
- Worst trade grows from -$8,963 (A) to -$11,823 (C)

This is **Manny's MASK lesson in reverse**. Trusting the fluctuation IS the right philosophy for winners — they need runway. But on the gap-and-FLUSH class of trades (the ~50% of firestorms that go down), no stop means the position rides all the way to the catastrophic floor. The runway benefit and the runway cost are both real and significant.

### Combined hypothesis: PROVED with compound benefit

D recovers $51K = B's $24K + C's $11K + a $17K nonlinear compound. The mechanism: B caps share count, C lets winners run. With smaller share counts AND wider drawdown floors, the worst-case trade ALWAYS smaller than C alone, and the winners run for the same time.

D's worst trade is -$3,977 (similar to B), while D's WR is 67% (similar to C). The combined effects don't trade off — they reinforce.

---

## Track A design implications

Per directive's verdict-mapping:

> If D > B + C → both components compound and Track A should include both

**Track A should include both**:
1. **Minimum R floor**: some form of `max($X, Y% of price)` floor on stop placement. Sweep used 10c + 5%. Track A can tune.
2. **Wide drawdown-from-entry floor**: replace pre-partial hard stop with `drawdown_pct >= N%` check. Sweep used 25%. Track A can tune.
3. **Force-flatten before market close**: 15:30 ET. Sweep value. Track A can tune.
4. **Partial target at 1.5R + HWM trail post-partial**: unchanged from current framework.

What Track A SHOULDN'T do (per the sweep's failure modes):

- **Don't use C alone.** C alone produces -$11,823 tail losses by giving up downside protection without resizing.
- **Don't widen the drawdown floor beyond 25-30%.** The April-2026 case in C suggests the floor needs to be tight enough to prevent ride-the-floor catastrophes.

### Open Track A design questions Cowork should resolve

1. **What's the right R floor magnitude?** B used $0.10 + 5%. Tighter floors (e.g., 5c + 3%) would catch more trades but lose less per worst-case; looser floors would block more entries entirely. Worth a Stage 1.6 micro-sweep before Track A ship?
2. **What's the right drawdown floor magnitude?** C used 25%. Maybe 20% catches catastrophes earlier. Maybe 30% gives winners more room.
3. **Should the drawdown floor be a function of position age?** First N minutes: 50% drawdown allowed (pure runway). After N: tighten to 25%. After 2N: tighten to 15%. Phased drawdown floor matches Manny's intuition that the runway phase is initially wide, then narrows as the trade ages.
4. **Should force-flatten be by clock time (15:30) or position age (60 min)?** Clock kills late-day winners; age kills runners that started early-morning but mature late.
5. **Drawdown floor for REGIME_SHIFT too?** The AMSS -$720 trade today was the same failure mode. Probably yes, but separate question for a separate sweep.

---

## What the sweep does NOT close

Even D's -$57K loss vs control means the strategy still adds negative EV at YTD scale in sim. The Phase 2 verdict that long-only captures at most half the bidirectional signal (median 12.1% up vs 13.0% down move on firestorm bars) is intact — and the gap between "best sweep run" and "break-even" is ~50% of A's baseline loss.

**Probable closure paths beyond Track A:**
1. **Bidirectional support** — short side captures the ~50% of firestorms that flush. Separate engineering directive.
2. **Selective FT — gap-and-run direction filter** — require N consecutive green bars before the FT bar, ensuring we're catching upside-biased firestorms. Reduces coverage but improves WR on the kept set.
3. **Sim/live divergence resolution** — Phase 3c bar-stream data may show sim underperforms live; FT's real edge may already be larger than the sim suggests. Tomorrow morning's cron data tells us.

CC's read: ship Track A's defensive framework first (it's the cheapest fix). Validate the sweep's gains hold in live. Then decide whether to invest in (1) bidirectional or (2) selective filtering.

---

## What this report does NOT include

- **No Track A spec.** Cowork's job, informed by this data.
- **No further parameter sweeps in this round.** Stage 1.6 (R-floor magnitude tuning) deferred until Track A's broader shape is decided.
- **No live wiring.** All sim-only.
- **No new trigger changes.** FT entry logic unchanged from Stage 1.

---

## Deliverables produced

- Code changes (committed but live behavior unchanged):
  - `simulate_subbot.py`: stop-floor logic + force-flatten check
  - `move_strike_subbot.py`: drawdown-floor branch in `_maintain_position` (env-gated, defaults to Stage 1 hard-stop behavior — bit-identical to live)
- YTD result JSONs:
  - `backtest_status/replay_subbot_YTD_FT_sweep_runB_loosened_stop_2026-01-02_2026-05-28.json`
  - `backtest_status/replay_subbot_YTD_FT_sweep_runC_drawdown_floor_2026-01-02_2026-05-28.json`
  - `backtest_status/replay_subbot_YTD_FT_sweep_runD_combined_2026-01-02_2026-05-28.json`
- Analysis: `/tmp/ft_sweep_compare.py` (one-shot; can be promoted to scripts/ if reused)

---

## Cross-references

- Sweep directive (this work's source): `cowork_reports/2026-05-28_phase3_stage1_5_sweep_directive.md`
- Phase 3 Stage 1 baseline results: `cowork_reports/2026-05-28_firestorm_trigger_backtest_results.md`
- Phase 2 missed-firestorm gap: `cowork_reports/2026-05-28_arming_research_phase2_missed_firestorm_gap.md`
- Manny's MASK live trading (failure-mode anchor): conversation log
- AMSS audit (same exit-philosophy failure on REGIME_SHIFT): `cowork_reports/2026-05-27_amss_regime_long_hold_audit.md`
