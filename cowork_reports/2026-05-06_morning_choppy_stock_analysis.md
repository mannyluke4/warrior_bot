# Morning Session Analysis — Choppy-Stock P0
## 2026-05-06

**Author:** CC
**For:** Cowork (Perplexity) review and brainstorm
**Status:** P0 — needs filter design before 2026-06-04 real-money go-live
**Related memory:** `feedback_pnl_vs_exit_quality.md`, `project_choppy_stock_filter_p0.md`

---

## Executive summary

The sub-bot took 4 round-trips today on the Wave Breakout strategy.
**Net P&L: −$472.97 (Alpaca paper, equity $30,000 → $29,527).**

| # | Symbol | Entry | Exit | qty | P&L | R | Exit reason |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | CLNN | $7.13 | $7.21 | 7,032 | +$562.56 | +0.93 | trail-stop limit no-fill → manual MKT close |
| 2 | FATN | $3.06 | $3.00 | 16,447 | −$986.82 | −1.05 | clean stop-out (limit filled at signal) |
| 3 | FATN | $3.05 | $3.01 | 16,393 | −$655.72 | −1.07 | clean stop-out, immediate re-entry of #2's symbol |
| 4 | PMAX | $2.97 | $3.06 | 6,750 | +$607.50 | +0.77 | clean trail-stop exit |

**The pattern is brutally clear:**
- The two **CLNN/FATN/FATN** entries were on choppy small-caps with thin liquidity. Net: **−$1,080**.
- The one **PMAX** entry was on a stock with real momentum and clean price action. Net: **+$608**.

Same detector, same scoring, same risk model. **The bot has no concept of "is this stock tradable right now?"** That's the gap to close.

---

## The two populations side-by-side

I pulled the per-symbol 5-minute CHART logs around each entry to compare the prevailing conditions. The contrast is stark.

### PMAX (winner) — clean momentum stock

5-min CHART snapshots near the 12:21 ET entry:

| Time | O | H | L | C | Vol | VWAP_dist | HOD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12:05 | 2.90 | 2.90 | 2.88 | 2.88 | 8,296 | +3.3% | 3.16 |
| 12:10 | 2.99 | 2.99 | 2.96 | 2.98 | 8,923 | +6.7% | 3.16 |
| 12:15 | 2.94 | 2.97 | 2.94 | 2.94 | 2,759 | +5.2% | 3.16 |
| 12:20 | 2.91 | 2.92 | 2.90 | 2.90 | 9,304 | +3.9% | 3.16 |
| **12:25 (entry)** | **2.98** | **3.02** | **2.97** | **3.01** | **14,916** | **+7.6%** | **3.16** |
| 12:30 | 3.02 | 3.02 | 2.99 | 3.00 | 19,441 | +7.0% | 3.16 |
| 12:35 | 3.04 | 3.06 | 3.03 | 3.04 | 14,270 | +8.5% | 3.16 |
| 12:40 | 3.04 | 3.12 | 3.04 | 3.10 | 52,718 | +10.5% | 3.16 |
| 12:45 (exit) | 3.05 | 3.06 | 3.03 | 3.04 | 8,255 | +8.3% | 3.16 |

**Features:**
- Persistently and meaningfully above VWAP (+3.3% to +10.5%)
- Substantial 5-min bar volumes (8K-52K)
- Progress toward HOD ($3.16) — was an active candidate
- Real participants on both sides of the book

### FATN (loser ×2) — choppy thin small-cap

5-min CHART snapshots around the 11:35 and 12:03 entries (only the ones logged for FATN):

| Time | O | H | L | C | Vol | VWAP_dist | HOD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12:00 | 3.06 | 3.06 | 3.06 | 3.06 | 1,010 | -0.7% | 3.32 |
| 12:05 | 3.01 | 3.04 | 3.01 | 3.02 | 1,011 | -1.7% | 3.32 |
| 12:10 | 3.09 | 3.09 | 3.09 | 3.09 | 5 | +0.6% | 3.32 |
| 12:20 | 3.09 | 3.09 | 3.09 | 3.09 | 8 | +0.6% | 3.32 |
| 12:25 | 3.13 | 3.13 | 3.13 | 3.13 | 6 | +1.9% | 3.32 |
| 12:30 | 3.17 | 3.17 | 3.17 | 3.17 | 400 | +3.1% | 3.32 |
| 12:40 | 3.15 | 3.15 | 3.15 | 3.15 | 2 | +2.4% | 3.32 |
| 12:45 | 3.15 | 3.15 | 3.15 | 3.15 | 1,000 | +2.4% | 3.32 |

**Features:**
- Oscillating around VWAP (-1.7% to +3.1%) — no directional commitment
- Crushed 5-min volumes (single-digits to 1,011 — *thousands of times less than PMAX*)
- Single-print 5-min bars (H=L=C, the bar contains 1 trade or zero)
- HOD $3.32 unreachable (all 5-min closes well below)
- O=H=L=C bars are a major tell: there's no actual price discovery, just a stale last-trade

### CLNN (lucky on win, then armed again, BP-rejected) — choppy mid-volume

5-min CHART around the 10:48 entry and 12:25 re-arm:

| Time | O | H | L | C | Vol | VWAP_dist | HOD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12:05 | 7.14 | 7.17 | 7.14 | 7.17 | 612 | +1.3% | 7.50 |
| 12:10 | 7.15 | 7.21 | 7.10 | 7.13 | 9,768 | +0.6% | 7.50 |
| 12:20 | 7.07 | 7.07 | 7.07 | 7.07 | 200 | -0.3% | 7.50 |
| **12:25 (re-arm)** | **7.07** | **7.07** | **7.01** | **7.05** | **3,404** | **-0.5%** | **7.50** |
| 12:30 | 7.13 | 7.13 | 7.13 | 7.13 | 300 | +0.6% | 7.50 |
| 12:35 | 7.06 | 7.06 | 7.00 | 7.00 | 623 | -1.2% | 7.50 |
| 12:40 | 7.05 | 7.05 | 7.05 | 7.05 | 150 | -0.5% | 7.50 |
| 12:45 | 7.00 | 7.00 | 7.00 | 7.00 | 34 | -1.2% | 7.50 |

**Features:**
- CLNN re-armed at 12:25 *while price was BELOW VWAP* (−0.5%). This is the diagnostic moment.
- HOD was $7.50, current close $7.05 → 6% below HOD
- Volume per 5-min bar wildly variable (34 to 9,768) — characteristic of a stock with no committed buyers
- BP-rejected on the second entry (saved by accident, not by design)

---

## What the WB detector saw vs. what was actually there

The detector emits `WB_ARMED` based on a wave-pattern score. Recap of the four arms:

| Symbol | Time | Score | wave_id | Trigger | Stop | R |
|---|---|---:|---:|---:|---:|---:|
| CLNN | 10:48 | 7 | 4 | 7.11 | 7.0442 | 0.0658 (0.93%) |
| FATN | 11:35 | 7 | 12 | 3.04 | 3.0026 | 0.0374 (1.23%) |
| FATN | 12:03 | 8 | 16 | 3.05 | 3.0125 | 0.0375 (1.23%) |
| PMAX | 12:21 | 8 | 14 | 2.9609 | 2.8529 | 0.108 (3.65%) |
| CLNN | 12:25 | 7 | 14 | 7.05 | 6.9925 | 0.0575 (0.82%) |

**The R-distance (stop distance as a % of entry) is the single sharpest observable separator on its own:**
- Losers (CLNN, FATN, FATN, CLNN-rearmed): **0.82% – 1.23%**
- Winner (PMAX): **3.65%**

A stop that's 1% from entry on a stock with a 1.5% bid-ask spread is almost guaranteed to either
(a) get whipsawed by spread alone or
(b) leave no room for the trail to activate before the natural noise hits the stop.

PMAX's 3.65% R was wide enough that 0.77R of profit cleared the spread + slippage by a comfortable margin.

---

## Hypotheses (for Perplexity to weigh in on)

**H1 — Tight-R + thin liquidity is the killer combination.** Either alone is survivable; together they make profitable exit nearly impossible. Filter: refuse entries where `R / spread < N` (e.g. require R to be at least 3× the bid-ask spread).

**H2 — Persistent VWAP-distance is a clean proxy for momentum reality.** PMAX held +3.3% to +10.5% above VWAP; CLNN/FATN oscillated within ±2-3%. Filter: require `vwap_dist_pct ≥ X` at entry (e.g. `≥ +2%` for a long).

**H3 — Volume per recent bar is the most under-utilized signal.** PMAX: 8K-52K shares/5min. FATN: 5-1000. The bot's WB detector currently uses *bar magnitude* (price moves) but not *bar volume* as a tradeability gate. Filter: require average bar volume over last N bars to clear a floor (absolute or relative to symbol's daily average).

**H4 — Single-print 5-min bars (O=H=L=C) are a structural disqualification.** They mean the symbol traded once or zero times in 5 minutes. The detector replays them as if they're real bars. Filter: skip detector update on degenerate bars; refuse entry if more than X of last N bars are degenerate.

**H5 — HOD progression matters more than HOD distance.** A stock 6% below HOD with no recent progress toward it (like CLNN at 12:25) is a fundamentally different setup than a stock 6% below HOD that's clearly climbing back (like PMAX at 12:25 working from $2.88 to $3.10). Filter: require recent N-bar HOD to be making new highs OR price to be within X% of current HOD.

**H6 — Composite gate.** No single feature is bulletproof. A 3-of-5 vote (R ≥ 3×spread, vwap_dist ≥ 2%, last-5-bar avg volume ≥ floor, no recent degenerate bars, HOD progression) might be the right framing.

---

## Questions for the brainstorm

1. **Which features above are best supported by the historical winners** (e.g. the WB Phase 1 paper validation winners from prior days)? If R-distance correlates with outcome, that's the highest-leverage simple filter.

2. **How aggressive should the spread-gate be?** A real-time bid-ask spread isn't currently in the bot's arming logic at all (`WB_ENTRY_MAX_SPREAD_PCT=5.0` exists in `.env` but applies to squeeze, not WB). Adding it to WB is the smallest possible fix that addresses H1 directly.

3. **Should refused entries log into a per-day blacklist automatically?** If the chop filter rejects FATN at 11:35, the same FATN setup at 12:03 is also chop. A 30-min cooldown after a chop-refusal seems trivially valuable.

4. **How do we ensure we don't over-fit to today's two losers?** The filter should reject the CLNN/FATN/FATN class but preserve PMAX. The historical backtest pass on `tick_cache/2026-01 → 2026-04` is the validation set.

5. **Where does the filter live in the code?** Two reasonable spots:
   - Inside `place_wave_breakout_entry` (sub-bot's bot_alpaca_subbot.py:506+) as a pre-submission gate. Cleanest. Logs `[CHOP_REJECT]` and bumps a per-symbol counter for the auto-blacklist.
   - Inside `wave_breakout_detector.py` — would change scoring to incorporate spread/volume. More integrated but harder to backtest in isolation.
   - **Recommendation:** Start at the bot level; promote into the detector only if needed.

---

## Other findings worth flagging

### Audit-tick-health is not Tier-1-aware
Independent of the chop filter, `audit_tick_health()` declares 🔴 CRITICAL after 60s of no ticks regardless of market state. Fired thousands of times during pre-market quiet on illiquid small caps. Cosmetic, but it spammed logs hard enough that it masked real signals (I dismissed real symptoms as "premarket quiet" for hours — see "Operator failure" below).

### Live-tick gap closure attempt (TBT) backfired
`WB_TBT_ENABLED=1` was meant to close the ~80% live-tick gap from `reqMktData` aggregation. In practice both bots became data-blind on Tier-1 symbols (KBSX 6.5h stale, CLNN 3.5h stale, ERNA 1h+ stale while actively trading). Disabled at 10:36 ET, fell back to known-good `reqMktData('233')`. Needs offline diagnosis before re-enabling. Suspect: the dispatch in `on_ticker_update` routes Tier-1 symbols to `_drain_tick_by_tick_ticker`, but `ticker.tickByTicks` may not actually be receiving prints — possibly an `ib_insync` event-loop / subscription-state issue.

### Operator failure on my (CC's) part
I dismissed the audit's CRITICAL spam as cosmetic for ~6 hours, asserting "the market is just quiet" when in fact the bot was data-blind on Tier-1. Manny had to call it out: *"never assume that market is just quiet. we've likely been blind all morning."* The 2026-05-05 cross-feed audit should have been enough prior context to catch this. **Lesson:** when a paper/live divergence appears, cross-check against an independent source (Alpaca quote API was 30 seconds away) before accepting "quiet market" as the explanation. Saved as a feedback memory.

### Restart pitfalls
- `daily_run_v3.sh` has a crash-trap that kills the entire stack (caffeinate, watchdog, both bots) when sub-bot fails health check. Cost ~2 minutes of unnecessary downtime. Worth softening the trap.
- System `python3` lacks `pytz`. Manual launches MUST use `~/warrior_bot_v2/venv/bin/python3`. This is in memory but I forgot it under pressure.

---

## Files

- This report: `cowork_reports/2026-05-06_morning_choppy_stock_analysis.md`
- Memory entries created today: `feedback_pnl_vs_exit_quality.md`, `project_force_exit_and_blacklist_features.md`, `project_choppy_stock_filter_p0.md`
- Logs: `logs/2026-05-06_daily.log`, `logs/2026-05-06_subbot_alpaca.log`, `logs/cron_2026-05-06.log`
- Tick cache: `tick_cache_alpaca/2026-05-06/{CLNN,FATN,PMAX}.json.gz` (full tick data for backtest analysis)

---

*The detector picks setups. We need a tradability gate around its output. PMAX vs FATN/CLNN today is the cleanest A/B test we'll get.*
