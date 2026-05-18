# WB v2 — Operationalization Candidates

**Stage:** 0 (research only)
**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Scope:** Enumerate concrete bot-translatable candidates for the three
ambiguous nouns in Manny's spoken setup — "level of support / resistance",
"MACD green near bottom / red near top", and "most active stocks of the
day" — so that Stage 1 backtests can pick from a discrete menu without
re-interpreting the verbal description.

This is a **menu, not a pick**. Stage 1 selects the winning subset.

---

## Executive summary table

| Element | Candidates | Already built (count / where) | New build required? |
|---|---|---|---|
| Level of S/R | 7 | 5 of 7 in `framework/level_sources/` (PDH/PDL, session VWAP, anchored VWAP, round-number, volume profile) | Pivot points + n-bar swing fractals need build |
| MACD operationalizations | 5 | MACD math primitive exists at `macd.py` (custom incremental); zero MACD *level-source / confirmation* plugins in `framework/` | New `framework/indicators/macd.py` + 1 confirmation module |
| Universe selector | 5 | Partial — `bot_v3_hybrid.py:audit_tick_health` emits per-symbol tick counts to daily logs; squeeze scanner emits RVOL; intraday `range_pct` computable from `tick_cache_databento` directly | Mostly aggregation work; no new market-data feed |

**Bottom line:** Stage 1 can run candidate × candidate × candidate across
7 × 5 × 5 = 175 combos using existing `tick_cache_databento` 1-minute
parquet + the squeeze bot's existing tick-audit log stream. **Two level
primitives need building, one indicator module needs building, one log
parser needs building.** Nothing else is missing.

---

## Section 1 — "Level of support / resistance" candidates

The strategy's level layer answers the question *"what reference price is
the wave bouncing off?"* Each candidate produces zero, one, or many
levels per (symbol, session); the WB v2 entry handler picks the nearest
one to current price within a proximity gate (see `framework/arrival.py`).

### 1.1 PDH / PDL — prior-day RTH high and low

- **One-line:** Prior session's regular-hours high and low; classic
  institutional magnet / fade levels.
- **Default parameters:** `max_gap_days=2` (so Monday with Friday data
  emits; Monday-after-Memorial-Day with Thursday data refuses to emit).
- **Where implemented:** `framework/level_sources/pdh_pdl.py` —
  `PDHPDLSource` (full impl, tested through Wave 2 / Agent H).
- **Backtestability:** **Sufficient.** Needs prior-session 1m parquet at
  `tick_cache_databento/<SYM>/1m_<prior_date>.parquet`. Both 2024-12-27
  through 2026-05-15 are cached for the 36-symbol Wave-3 universe and the
  YTD-backfilled small-cap universe.

### 1.2 Intraday VWAP (session, with bands)

- **One-line:** Volume-weighted average price from 09:30 ET, with
  configurable ±N-sigma bands around it.
- **Default parameters:** `band_sigmas=[1.0, 2.0]` (emits `VWAP`,
  `VWAP_UPPER_1`, `VWAP_LOWER_1`, `VWAP_UPPER_2`, `VWAP_LOWER_2`).
- **Where implemented:** `framework/level_sources/vwap.py` —
  `VWAPSource` (Wave 2 / Agent G, with O(1) incremental update and
  built-in slope classifier `vwap_slope_classifier`).
- **Backtestability:** **Sufficient.** Same 1m parquet feed; VWAP is
  reconstructible from `(high+low+close)/3 * volume` per bar. The class
  already does this via `_typical(bar)`.

### 1.3 Anchored VWAP — session-open anchor

- **One-line:** VWAP computed from a configurable anchor event forward
  (gap-day, earnings, FOMC, multi-anchor); same math as session VWAP but
  bounded to bars after the anchor.
- **Default parameters:** `anchor_type='gap_day'`, `lookback_days=30`,
  `gap_threshold_pct=0.02`. **Session-open anchor variant:** NOT a named
  anchor in the current implementation — the existing class supports
  `gap_day | earnings | fomc | earnings_or_gap | multi_anchor`.
  Session-open AVWAP is mathematically identical to `VWAPSource` so it is
  effectively built; if a true "session-open AVWAP as a separate level
  kind" is wanted, it's a 5-line config (re-anchor the source at 09:30
  with no other anchor). Recommend treating §1.2 as the session-open
  AVWAP for WB v2 Stage 1.
- **Where implemented:** `framework/level_sources/anchored_vwap.py` —
  `AnchoredVWAPSource` (Wave 5 / Agent M). Gap-day variant fully wired;
  the session-open variant is degenerate-with-VWAPSource.
- **Backtestability:** **Sufficient** for gap_day. The gap detector
  walks back `lookback_days` sessions of cached 1m bars; that data is in
  hand.

### 1.4 Pivot points (classic / Fibonacci / Camarilla) — **NOT YET BUILT**

- **One-line:** Single-bar daily-pivot formulas that emit a small set of
  support/resistance prices from prior-day OHLC. Three formula families
  in common use; each emits R3/R2/R1/P/S1/S2/S3.
- **Default parameters per formula:**

  **Classic (Floor-trader):**
  - P  = (H + L + C) / 3
  - R1 = 2P − L
  - S1 = 2P − H
  - R2 = P + (H − L)
  - S2 = P − (H − L)
  - R3 = H + 2 (P − L)
  - S3 = L − 2 (H − P)

  **Fibonacci:**
  - P  = (H + L + C) / 3
  - R1 = P + 0.382 (H − L)
  - S1 = P − 0.382 (H − L)
  - R2 = P + 0.618 (H − L)
  - S2 = P − 0.618 (H − L)
  - R3 = P + 1.000 (H − L)
  - S3 = P − 1.000 (H − L)

  **Camarilla:**
  - R4 = C + (H − L) × 1.1/2
  - R3 = C + (H − L) × 1.1/4
  - R2 = C + (H − L) × 1.1/6
  - R1 = C + (H − L) × 1.1/12
  - S1 = C − (H − L) × 1.1/12
  - S2 = C − (H − L) × 1.1/6
  - S3 = C − (H − L) × 1.1/4
  - S4 = C − (H − L) × 1.1/2

  Inputs: prior session RTH high `H`, low `L`, close `C`.

- **Where implemented:** Not yet built. New file expected at
  `framework/level_sources/pivots.py`. Should follow the same pattern as
  `pdh_pdl.py` — scan prior RTH session in `BarHistory`, emit levels at
  `compute_levels()`, no-op `update_intraday()`. Stage 1 build cost: ~150
  LOC + tests.
- **Backtestability:** **Sufficient.** Inputs are identical to PDH/PDL
  (prior session H/L/C). Reuse the helper logic in
  `pdh_pdl.py:_prior_session_date`.

### 1.5 Round-number levels ($1 / $5 / $10 tiered)

- **One-line:** Whole-dollar / $5 / $10 multiples around current price,
  tiered by price band (small-caps get $1; mid-tier gets $5; high-tier
  gets $5+$10).
- **Default parameters:** `window_dollar=5.0`, `increments` per tier:
  - `10_50`:   $1.00 + $5.00
  - `50_150`:  $5.00
  - `150_300`: $5.00 + $10.00
- **Where implemented:** `framework/level_sources/round_number.py` —
  `RoundNumberSource` (Wave 2 / Agent I). Memory note: marked "retired"
  in earlier framework conversations meaning the v1-bot version was
  superseded, but **the framework primitive is alive and registered**;
  pulled into Wave 3 portfolio backtest. WB v2 can use it as-is.
- **Backtestability:** **Sufficient.** No history needed beyond the
  most-recent close; round-number math is pure-arithmetic.

### 1.6 Recent swing highs/lows (n-bar fractals on 1m) — **NOT YET BUILT**

- **One-line:** A "swing high" is a 1m bar whose high is higher than the
  high of the `n` bars immediately before AND after it; mirror for swing
  lows. Fractal-pattern, also called Williams fractals.
- **Default parameters:**
  - `n = 3` (i.e. 3 bars left + 3 bars right; minimum sample for a noisy
    1m chart while still firing within a few minutes).
  - `lookback_minutes = 60` (only keep swings from the last hour as
    active S/R; older ones decay out).
  - `max_levels_per_side = 5` (top 5 most-recent swing highs above
    current price; top 5 most-recent swing lows below).
- **Where implemented:** Not yet built. Existing analogs in the codebase
  worth referencing during build:
  - `analyze_runner_waves.py` — wave detection on past trades (different
    intent but similar pivot logic).
  - `wave_breakout_detector.py` — uses local highs/lows but only for the
    squeeze breakout trigger, not as a general S/R level source.
  Expected new file: `framework/level_sources/swing_fractals.py`.
  Stage-1 build cost: ~200 LOC + tests; design pattern mirrors
  `VWAPSource` for the rolling-buffer update.
- **Backtestability:** **Sufficient.** Inputs: rolling buffer of last
  `lookback_minutes + n` 1m bars. Both `tick_cache_databento` 1m parquet
  and any IBKR-bridged 1m series are sufficient — no tick-level needed.

### 1.7 Volume profile HVN / POC / LVN

- **One-line:** Distribution of cumulative volume across price bins over
  the prior N sessions; emit the bin with the highest cumulative volume
  (POC), bins with > 1.5× mean bin volume (HVN), and bins with < 0.5×
  mean bin volume (LVN).
- **Default parameters:** `lookback_sessions=5`, `bin_pct=0.001` (0.1%
  of reference price), `hvn_multiplier=1.5`, `lvn_multiplier=0.5`,
  `merge_adjacent=True`.
- **Where implemented:** `framework/level_sources/volume_profile.py` —
  `VolumeProfileSource` (Wave 5 / Agent L, with intraday-developing
  profile support via `update_intraday(bar)` and `intraday_snapshot()`).
- **Backtestability:** **Sufficient.** Bar-level (not tick-level)
  approximation is the documented Wave-5 simplification (see module
  docstring lines 38-42). Uses (H+L+C)/3 as bin assignment, volume per
  bar as weight. 5-session lookback is well-served by
  `tick_cache_databento`.

---

## Section 2 — "MACD green / red near top / bottom" candidates

The MACD layer answers *"is momentum confirming the level bounce?"* No
MACD primitives exist in `framework/` today. The repo's `macd.py` is a
custom incremental implementation (12/26/9 hard-coded; rolling 4-bar
history buffer) used by `chop_gate_v3.py` for the squeeze bot — it is
**not under `framework/`** and **does not implement
`LevelSourceProtocol` or any framework confirmation interface.**

**Stage 1 prerequisite:** new module
`framework/indicators/macd.py` exposing a `MACDIndicator` class that
follows the framework's lifecycle (`update(bar) → state`,
`current_state` properties). Stage 1 may also need
`framework/confirmations/macd_confirm.py` to slot into a
`ConfirmationStub` registration (see `framework/registry.py:50`).

**Indicator library decision:** **custom (Python EMA recurrence)** —
matches the existing `macd.py` pattern, avoids the new dep, runs O(1)
per bar tick. No `talib` / `pandas-ta` in the project's
`requirements.txt`; adding either would introduce binary build pain on
the Mac mini target. The MACDState recurrence in `macd.py:7-9`
(`ema_next`) is the reference implementation and should be lifted.

### 2.1 MACD histogram zero-cross (12/26/9)

- **One-line:** Long when histogram crosses from negative to positive;
  short when histogram crosses from positive to negative.
- **Default parameters:** `fast=12`, `slow=26`, `signal=9`. Trigger:
  `prev_hist < 0 and hist >= 0` (long) or mirror.
- **Where implemented:** Math is in `macd.py:MACDState.update`. Cross
  detection: existing `macd_curling_up` (chop_gate_v3.py:248) checks
  histogram shape but not specifically a zero-cross; new wrapper needed.
- **Library:** custom EMA recurrence (no external dep).

### 2.2 MACD line crosses signal line near multi-bar low/high

- **One-line:** Long when MACD line crosses above signal line AND the
  cross happens within K bars of a recent N-bar histogram trough (the
  classical "MACD bottom turn"). Mirror for short.
- **Default parameters:** `fast=12`, `slow=26`, `signal=9`,
  `trough_lookback_bars=5`, `proximity_bars=2`. Histogram trough = `min(hist)`
  over last `trough_lookback_bars`; cross must occur within `proximity_bars`
  of that trough index.
- **Where implemented:** Math available via `MACDState.bearish_cross`
  (macd.py:123). Trough detector + cross-near-trough logic must be added
  in the new `framework/confirmations/macd_confirm.py`.
- **Library:** custom (extends existing `MACDState`).

### 2.3 MACD histogram momentum: consecutive bars of decreasing-magnitude negative, then turn

- **One-line:** Long when histogram is negative, |hist| has been
  shrinking for N consecutive bars, and current bar's hist > prior bar's
  hist (= histogram bottomed). Mirror for short.
- **Default parameters:** `fast=12`, `slow=26`, `signal=9`,
  `consecutive_shrinking_bars=3`.
- **Where implemented:** `chop_gate_v3.py:macd_curling_up` (line 248)
  reads `histogram_at(0/1/2)` — it's a close cousin of this rule
  (currently used to BLOCK long entries when the squeeze MACD is rolling
  the wrong way). The forward-direction version for WB v2 is a 1:1
  inversion-of-veto: same primitive, different sign convention. Should
  be ported to `framework/confirmations/macd_confirm.py` and wired as a
  trigger rather than a veto.
- **Library:** custom (reuses `MACDState` rolling-history buffer at
  `macd.py:79-110`).

### 2.4 Fast MACD (5/13/5) — 1m timeframe sensitivity variant

- **One-line:** Same rules as §2.1-§2.3 but with the EMA periods halved
  to ~5/13/5; gives roughly 2× the trigger frequency on 1m bars, which
  matches Manny's "wave" cadence (a wave on a fluctuating small-cap is
  typically a 5-10 min cycle, not the 20-30 min cycle 12/26 was designed
  for).
- **Default parameters:** `fast=5`, `slow=13`, `signal=5`. Same trigger
  variants as §2.1-§2.3.
- **Where implemented:** Hard-coded `12/26/9` in `macd.py:46-47` —
  needs parameterization. New `framework/indicators/macd.py` should
  expose `MACDIndicator(fast=12, slow=26, signal=9)` so both standard
  and fast variants instantiate from YAML.
- **Library:** custom (parameterized EMA recurrence).

### 2.5 MACD + "near a level" composite gate

- **One-line:** Fire only when MACD trigger (any of §2.1-§2.4) AND price
  is within `proximity_dollar` or `proximity_pct` of an active level
  from Section 1. This is the literal translation of Manny's quote: *"I
  waited for the price to reach a level of support, and added when MACD
  was green near the bottom."* The two conditions are AND-gated.
- **Default parameters:** `proximity_pct=0.005` (within 0.5% of the
  level) OR `proximity_dollar` per tier (0.10 / 0.25 / 0.50 for the
  three round-number tiers). MACD inner-rule defaults to §2.3 (histogram
  bottomed and turned).
- **Where implemented:** Proximity-gate primitive already exists at
  `framework/arrival.py:ArrivalDetector` (consumed by all existing
  framework strategies; see `framework/registry.py:112-128`). The
  composite is a new `framework/confirmations/macd_at_level.py` that
  wraps the proximity check + MACD trigger. Most of the wiring is reuse.
- **Library:** custom (composition; no new indicator deps).

---

## Section 3 — "Most active stocks of the day" candidates

The universe selector answers *"which symbols does WB v2 watch?"*
Manny's verbal version was *"whichever ones had the most ticks in the
squeeze bot's tick audit."* Stage 1 needs a programmatic version of the
same eyeball. Refresh frequency is **per-minute or per-5-minute** —
slow enough to avoid thrash on the symbol list, fast enough to catch
mid-session runners.

### 3.1 Top-N by total dollar volume so far this session

- **One-line:** Cumulative `sum(price × volume)` per symbol from 09:30
  ET to current bar; rank descending; take top-N.
- **Default parameters:** `N=10`, `refresh_minutes=5`, computed at each
  refresh from the running 1m bar stream.
- **Data source:** `tick_cache_databento/<SYM>/1m_<date>.parquet` has
  `open/high/low/close/volume` per minute; dollar volume ≈
  `(open+close)/2 * volume` per bar, summed across bars-so-far. **No
  new data required.** For the small-cap universe also using the squeeze
  scanner's `live_scanner.py` Databento feed (same minute bars).
- **Refresh frequency:** 1-minute (bar-close granularity) is the
  practical ceiling without going to tick-level aggregation. Stage 1
  default 5-minute refresh balances stability vs responsiveness.

### 3.2 Top-N by tick rate (Manny's original eye-ball trigger)

- **One-line:** Number of trades printed per minute, summed across the
  last K minutes; rank descending. This is the literal definition of
  *"the stocks that had the most ticks on the bot's tick audit"*.
- **Default parameters:** `N=10`, `window_minutes=5`,
  `refresh_minutes=1`.
- **Data source:** Live: `bot_v3_hybrid.py:audit_tick_health` (line
  1555-1580) writes `TICK AUDIT: <SYM>: <N> ticks in last 60s, ...` to
  the per-day `logs/<date>_daily.log`. Sampled at 60s intervals across
  the trading day. For 2026-05-15 the file `logs/2026-05-15_daily.log`
  has 10,582 such lines — adequate density for retrospective ranking.
  **No new data required;** Stage 1 builds a one-shot log parser
  (~50 LOC) that yields `(date, ts, symbol, tick_count_60s)` rows.
- **Refresh frequency:** Audit cadence is already 60s; Stage 1 can
  bucket into 5-minute windows for stability.
- **Note:** This is the spec-aligned definition. Tick audit data exists
  only for the symbols the bot was already subscribed to that day —
  it is **conditional on the squeeze scanner's daily watchlist**. For
  WB v2 to broaden the universe beyond what squeeze watched, a parallel
  tick-rate feed sourced from Databento `trades` data (cached at
  `tick_cache_databento/<SYM>/trades_<date>.parquet`) is the upgrade
  path. Current cache only has `trades_2024-*` for the mega-cap subset.

### 3.3 Top-N by RVOL (current volume / 30-day avg at same time-of-day)

- **One-line:** Relative volume — today's cumulative volume to time T,
  divided by the average cumulative volume to time T over the last
  30 trading days; rank descending.
- **Default parameters:** `N=10`, `lookback_days=30`,
  `refresh_minutes=5`, `min_rvol=2.0` (only consider symbols where
  RVOL ≥ 2× average — matches `WB_MIN_REL_VOLUME=2.0` in the project's
  `.env`).
- **Data source:** Live RVOL is already computed by
  `live_scanner.py` and `market_scanner.py` (both read `.env` and write
  to `universe_cache/`; see DIRECTIVE_SCANNER_RVOL_ADV_PARITY.md and the
  parity fix logged 2026-03-24). Historical backtest RVOL is
  reconstructible from `tick_cache_databento` 1m parquet by summing
  bar-volume from session-open through time T for each of the prior 30
  sessions. **No new data required.**
- **Refresh frequency:** 5-minute (RVOL is sticky; bar-by-bar refresh
  is overkill).

### 3.4 Top-N by intraday range (high − low) / open

- **One-line:** Percent intraday range so far this session; ranks the
  most-volatile names. Captures "the price was always fluctuating"
  directly.
- **Default parameters:** `N=10`, `refresh_minutes=5`, `min_range_pct=0.05`
  (only symbols with ≥ 5% range so far).
- **Data source:** `tick_cache_databento/<SYM>/1m_<date>.parquet` —
  running `max(high) − min(low)` from 09:30 to current bar, divided by
  the 09:30 open. **No new data required.**
- **Refresh frequency:** 5-minute.
- **Note:** This is the closest mechanical proxy for Manny's "I watched
  the chart, the price was always fluctuating" — high range = high
  fluctuation amplitude.

### 3.5 Composite score combining 2-3 of the above

- **One-line:** Weighted blend of dollar-volume rank, tick-rate rank,
  RVOL rank, and intraday-range rank. Each input is normalized to
  [0,1] by min-max scaling within the current snapshot's universe; the
  composite is a fixed linear combination.
- **Default parameters:**
  - `weights = {dollar_volume: 0.35, tick_rate: 0.35, rvol: 0.20, range_pct: 0.10}`
    — heavier on the two that best match Manny's spoken trigger
    (dollar-volume and tick-rate are correlated but not identical;
    tick-rate captures "many small prints", dollar-volume captures
    "real money flowing").
  - `N=10` (top-N output).
  - `refresh_minutes=5`.
  - `tie_break = 'rvol'` (when composite ties, RVOL wins).
- **Data source:** Composition of §3.1–§3.4 — same data sources. **No
  new data required.**
- **Refresh frequency:** 5-minute (bounded by the slowest input,
  §3.3 RVOL).

---

## Wiring checklist for Stage 1

For each combination (level × MACD × universe × timeframe), Stage 1's
backtest YAML needs:

1. `level_source.type` — one of `pdh_pdl | vwap | anchored_vwap |
   pivots | round_number | swing_fractals | volume_profile`. **Two are
   not yet built (pivots, swing_fractals).**
2. `confirmation_rule.type` — one of `macd_zero_cross | macd_signal_cross |
   macd_hist_turn | macd_fast | macd_at_level`. **All five require new
   code under `framework/confirmations/macd_*.py` + the indicator
   primitive at `framework/indicators/macd.py`.**
3. Universe selector — a new module
   `framework/universe_selectors.py` (or wired into the existing
   `framework/universe.py`) exposing `top_n_by_dollar_volume`,
   `top_n_by_tick_rate`, `top_n_by_rvol`, `top_n_by_range_pct`,
   `composite_top_n`. **No external feeds needed**; tick-rate selector
   needs the one-shot log parser for the historical leg.
4. `arrival_detector.params.proximity_pct` / `proximity_dollar` — reuse
   `framework/arrival.py` defaults from existing Phase-2 strategies
   (typically `proximity_pct=0.003`–`0.005`).
5. Exit stack — reuse squeeze exits per directive §4; documented in
   `wb_v2/exit_reuse_audit.md` (Deliverable 6, separate file).

**Estimated Stage 1 build cost** (research code only, no live wiring):
~600 LOC new code (pivots + swing_fractals level sources, MACD
indicator module, 5 MACD confirmation rules, universe-selector
aggregator + tick-audit log parser) + tests. All other primitives are
already in `framework/`.

---

## What's explicitly NOT in this menu

- **5m timeframe MACD parameters** — directive §1 calls 1m primary; 5m
  secondary track. Stage 1 can run all five MACD variants on 5m bars
  by changing the bar resampler upstream; no new candidate needed.
- **Multi-timeframe MACD confluence** (1m trigger + 5m direction). Worth
  testing later, but Stage 0 deliberately keeps the menu single-TF to
  bound combinatorics.
- **Volume-weighted MACD or MACD on tick data.** Out of scope for
  Stage 1 — 1m close-based MACD is the canonical version Manny would
  have been watching.
- **Universe selector based on options flow / dark-pool prints.** No
  data feed; not part of Manny's eyeball process.

---

## Notes for Stage 1 directive author

1. **Two level sources need building before the matrix can run end-to-end.**
   `pivots.py` is ~150 LOC, `swing_fractals.py` is ~200 LOC. Both are
   bounded, well-specified, and follow existing patterns.
2. **MACD primitive is the biggest single block of new code** —
   ~250 LOC for indicator + 5 confirmation classes. The math is
   trivial; the work is in the lifecycle wiring and tests.
3. **Universe-selector tick-rate variant is contingent on the squeeze
   bot's daily log files.** Verify with `ls -la logs/*_daily.log | wc
   -l` that the historical coverage Stage 1 wants to backtest is
   actually present. Spot-check: 2026-05-15 has 10,582 TICK AUDIT lines.
4. **No new market-data subscription is required.** Stage 1 runs
   entirely from existing `tick_cache_databento/` parquet + existing
   `logs/*_daily.log` + the framework primitives listed above.
