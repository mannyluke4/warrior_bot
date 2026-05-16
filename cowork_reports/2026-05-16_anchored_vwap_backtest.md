# Anchored VWAP Backtest — Wave 5, Agent M

**Date:** 2026-05-16
**Author:** CC Agent M
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §5 (Agent M)
**Design:** `DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md` §5.2 (Anchored VWAP)
**Status:** BACKTEST ONLY — no paper deployment per directive §9 hard stop.
**Existing live code:** untouched per directive §7.

---

## 1. TL;DR

Both Anchored-VWAP specs **fail Wave 5 acceptance gates** on real Databento
data 2020-2024 across the 36-symbol shortlist. Pullback is directionally
positive but well below the Sharpe ≥ 1.0 bar; Breakout is catastrophically
negative.

| Metric | Gate | AVWAP-Pullback | AVWAP-Breakout |
|---|---:|---:|---:|
| Sharpe (annualized) | ≥ 1.0 | **0.89** | **−1.36** |
| Trades | ≥ 100 | 7,844 ✓ | 5,790 ✓ |
| Max drawdown | ≤ 15% | **−15.45%** ✗ (border) | **−109.4%** ✗ (account wipe) |
| Net P&L on $100K | positive | +$73,111 ✓ | **−$104,809** ✗ |
| Profit factor | > 1.4 | 1.07 ✗ | 0.89 ✗ |
| Win rate | informational | 42.3% | 39.4% |

VIX-on (suppress entries when VIX > 25) was applied throughout. A 2024-only
VIX-on-vs-off comparison shows that the coarse VIX gate has minimal impact
in this universe — virtually all 2024 sessions are below the threshold —
so VIX cannot rescue the breakout failure.

**Recommendation:** Defer/remove `anchored_vwap_breakout` from the framework
roster; the "reclaim from below" thesis as encoded here does not hold for
mega-cap liquid equities on 1-minute bars. Promote `anchored_vwap_pullback`
to the **watch list** alongside ORB-5min and PDH-Breakout (Wave 3
synthesis §1) — it has directional edge, every-year positive in 4 of 5
years, and fires on materially different days than PDH-Fade (only 32%
symbol-day overlap, 0.01 daily-P&L correlation — strong diversifier candidate).

---

## 2. Strategy spec recap

### 2.1 AVWAP-Pullback (`strategies/anchored_vwap_pullback.yaml`)

```
level_source:    anchored_vwap, anchor_type=gap_day, lookback 30 sessions
arrival:         proximity 0.20% (AVWAP-as-support test)
confirmation:    signal_candle (hammer for pullback-from-above ⇒ long;
                                shooting_star for pullback-from-below ⇒ short;
                                doji either direction)
                 require_volume_increase=true
stop:            just_past_level, pad $0.15
target:          composite — opposite_level OR r_multiple 2.0,
                 activate trailing ATR×1.5 after 1.5R
regime gate:     VIX < 25
trade window:    09:35 → 15:55 ET
risk:            $1,000 fixed per trade
```

### 2.2 AVWAP-Breakout (`strategies/anchored_vwap_breakout.yaml`)

```
level_source:    anchored_vwap, anchor_type=earnings_or_gap, multi_anchor=3
arrival:         proximity 0.10% (retesting AVWAP from below)
confirmation:    breakout_candle (close above AVWAP + 1.5× vol baseline)
stop:            bar_low, pad $0.05
target:          r_multiple 2.0 + trailing ATR×1.5 after 1.5R
regime gate:     VIX < 25
trade window:    09:35 → 15:55 ET
risk:            $1,000 fixed per trade
```

### 2.3 Universe and date range

- 36 symbols pre-cached in `tick_cache_databento/` (Wave 3 shortlist —
  AAPL, MSFT, TSLA, NVDA, META, AMD, ADBE, CRM, ORCL, NFLX, INTC, QCOM,
  CSCO, MU, AVGO, PLTR, ROKU, SNAP, SOFI, F, BAC, WFC, JPM, MA, DIS, NKE,
  DAL, AAL, WMT, COST, T, VZ, KO, MRK, PFE, AMC).
- Sessions: 1,307 trading days, 2020-01-01 through 2024-12-31.
- Data: Databento `ohlcv-1m` parquet files, RTH 09:30-16:00 ET, naive ET
  timestamps (framework convention).

---

## 3. Anchor identification methodology

`framework/level_sources/anchored_vwap.py` implements three independent
anchor detectors, plus a `multi_anchor` aggregator.

### 3.1 Gap day (`detect_gap_days`)

A "gap day" is a session whose open price diverged from the prior session's
RTH close by at least `gap_threshold_pct` (default 0.02 = 2%). Detection:

1. Build the chronologically-ordered list of RTH session dates present in
   the history.
2. For each session `s` within the lookback window strictly before the
   target date, compare `s.open` to the prior session's last RTH bar close.
3. If `|open - prior_close| / prior_close ≥ gap_threshold_pct`, emit an
   `Anchor(kind="gap_day", session_date=s, anchor_ts=first RTH bar of s)`.

This captures both gap-up (positive `gap_pct`) and gap-down (negative
`gap_pct`); the gate is on absolute value.

### 3.2 Earnings reaction day (`detect_earnings_anchors`)

Databento Standard does not include corporate-action event data on the
equity tier (per directive note). I hardcoded a stub calendar covering
seven liquid mega-caps in `EARNINGS_CALENDAR`:

- **AAPL, MSFT, NVDA, META, AMD, TSLA, GOOGL** — 20 quarterly releases each
  spanning 2020-2024. Dates pulled from public investor-relations releases.

The "reaction day" is the first RTH session strictly AFTER the earnings
release (most companies in the calendar release post-close, so the
reaction day is the next trading day). The anchor timestamp is the open
of that next session.

Symbols not in the stub calendar (29 of the 36-symbol universe) emit zero
earnings anchors — by design and per directive ("use a stub list for now
if Databento doesn't have it").

### 3.3 FOMC announcement (`detect_fomc_anchors`)

FOMC dates 2018-2024 are hardcoded in `FOMC_DATES` (58 total — 8 meetings
per year plus a couple of mid-cycle 2020 emergency meetings). Anchor
timestamp is the open of the FOMC session itself (regime change happens
at 2pm; AVWAP from the morning open captures the entire reaction).

### 3.4 Multi-anchor aggregation

`anchor_type="multi_anchor"` performs the union of gap_day + earnings +
fomc detection, dedupes by session_date (first found wins), sorts
newest-first, and returns the top `multi_anchor_count` anchors. The
`AnchoredVWAPSource` then spins up one `_AVWAPState` accumulator per
anchor and emits one `Level(kind="AVWAP")` per accumulator in the
returned LevelSet — strategies can then look for confluence or check
each anchor independently.

`anchor_type="earnings_or_gap"` is a lighter variant used by the breakout
spec — it dedupes earnings + gap anchors but excludes FOMC (FOMC anchors
on mega-caps tend to be noisier and were dropped per the multi-anchor
distribution observed in early smoke runs).

### 3.5 Edge cases handled (per `tests/framework/test_anchored_vwap.py`)

- Empty history → empty LevelSet
- Zero-volume bars skipped during VWAP accumulation
- Sub-threshold gaps correctly excluded
- Lookback boundary inclusive (an anchor exactly `lookback_days` back is included)
- Unknown symbols → no earnings anchors (graceful empty)
- FOMC dates with no bar coverage in history → skipped (graceful empty)
- Negative AND positive gaps both detected (absolute-value threshold)
- Multiple gap days returned newest-first (deterministic ordering)
- Incremental `update_intraday()` parity with batch `compute_levels()`
  (volume-weighted math is order-invariant by construction)

All 17 unit tests pass (`pytest tests/framework/test_anchored_vwap.py`).

---

## 4. Per-spec real-data metrics

### 4.1 AVWAP-Pullback aggregate (all 5 years, VIX-on)

```
n_trades:           7,844
n_wins / losses:    3,320 / 4,489
win_rate:           42.33%
profit_factor:      1.073
sharpe:             0.895
avg_r_multiple:     +0.009
total_pnl:          +$73,111  (on $100K starting equity, fixed $1K risk)
max_drawdown_pct:   -15.45%
ending_equity:      $173,111
exit_reason mix:    stop 49.4%, trail_stop 19.1%, session_close 19.0%, target 12.5%
direction mix:      long 53.8%, short 46.2%
```

### 4.2 AVWAP-Pullback per-year

| Year | Trades | Sharpe | Win | Net P&L | MaxDD |
|---|---:|---:|---:|---:|---:|
| 2020 | 1,165 | 1.10 | 43.2% | +$12,516 | −10.4% |
| 2021 | 2,027 | **2.23** | 42.7% | **+$48,263** | −8.0% |
| 2022 | 548 | **−1.39** | 41.4% | **−$6,771** | −14.0% |
| 2023 | 1,958 | 0.33 | 43.6% | +$6,115 | −15.0% |
| 2024 | 2,146 | 0.52 | 40.6% | +$12,987 | −22.4% |

2021 carries the strategy. 2022 (high-VIX year) is the only negative year
— even though the VIX gate is on. The coarse VIX map suppresses most of
Jan-Nov 2022, but residual sessions still bled. 2024's −22.4% intra-year
DD is also a red flag.

### 4.3 AVWAP-Breakout aggregate

```
n_trades:           5,790
n_wins / losses:    2,283 / 3,479
win_rate:           39.43%
profit_factor:      0.890
sharpe:             -1.360
avg_r_multiple:     -0.018
total_pnl:          -$104,809
max_drawdown_pct:   -109.4%    (account wiped, then turned negative)
ending_equity:      -$4,809
exit_reason mix:    stop 56.4%, trail_stop 20.2%, target 14.6%, session_close 8.8%
direction mix:      long 100% (breakout spec is long-only by design)
```

### 4.4 AVWAP-Breakout per-year

| Year | Trades | Sharpe | Win | Net P&L |
|---|---:|---:|---:|---:|
| 2020 | 896 | −1.75 | 37.5% | −$18,678 |
| 2021 | 1,490 | **−2.25** | 39.8% | **−$46,171** |
| 2022 | 460 | −2.04 | 38.3% | −$11,261 |
| 2023 | 1,394 | −0.42 | 41.1% | −$7,666 |
| 2024 | 1,550 | −0.97 | 39.0% | −$21,034 |

**Every year negative. The thesis fails.** "Price retesting AVWAP from
below and reclaiming on volume" is a low-edge setup on mega-cap 1-minute
bars — by the time the close-above-AVWAP + 1.5× vol confirmation fires,
the move has typically already exhausted and reverts. 56% of trades stop
out. Even the trail-stop exits (which should capture trends) are net
small-positive but get overwhelmed by hard-stop losses.

---

## 5. Multi-anchor vs single-anchor comparison

### 5.1 Pullback (single-anchor by design)

All 7,844 pullback trades fired on a `gap_day` anchor — no earnings or
FOMC contributions because `multi_anchor_count=1` and `anchor_type="gap_day"`
in the YAML. This is a clean per-spec result; we can't compare anchor
types within Pullback because the spec doesn't iterate over them.

### 5.2 Breakout (multi-anchor with `earnings_or_gap`, count 3)

| Anchor type | Trades | Sharpe | Win | Avg R | Net P&L | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| `gap_day` | 5,631 | −1.354 | 39.3% | −0.018 | **−$101,085** | −102.9% |
| `earnings` | 159 | −0.512 | 42.8% | −0.023 | **−$3,724** | −14.4% |

The split is heavily skewed toward `gap_day` because (a) we only have a
stub earnings calendar covering 7 of 36 symbols, and (b) gap days fire
across the entire universe but earnings only for those 7 names.
Normalizing per-anchor:

- **Earnings AVWAP**: only 159 trades but with the best per-trade Sharpe
  (−0.51 vs −1.35) and a markedly better win rate (42.8% vs 39.3%).
  Suggests the earnings-AVWAP signal has more information content than
  the gap-day-AVWAP signal — consistent with the auction-market-theory
  literature (research_vp_market_profile §1) that earnings-anchored
  references are stickier than ad-hoc gap anchors.
- **Gap-day AVWAP**: the dominant source of trades and the catastrophic
  source of losses. 5,631 trades is 96% of breakout signals.
- **FOMC anchors**: zero firings in the breakout sweep because the
  `anchor_type="earnings_or_gap"` spec explicitly excludes FOMC. A
  separate run with `anchor_type="multi_anchor"` would surface them; not
  warranted given the dominant spec failure here.

**Single-anchor (gap_day) vs multi-anchor verdict:** In this backtest,
multi-anchor confluence doesn't rescue the breakout thesis. Earnings-only
breakout would be a smaller-N, less-bad spec (Sharpe −0.51), still
failing the ≥ 1.0 gate. Defer the multi-anchor confluence idea pending a
fuller earnings calendar (Databento Plus or third-party).

---

## 6. Per-anchor-type performance summary

Because Pullback runs single-anchor (`gap_day` only) and Breakout's anchor
mix is documented above, the cross-spec per-anchor-type breakdown reduces
to:

| Spec | Anchor | Trades | Sharpe | Win % | Avg R |
|---|---|---:|---:|---:|---:|
| AVWAP-Pullback | gap_day | 7,844 | **+0.89** | 42.3% | +0.009 |
| AVWAP-Breakout | gap_day | 5,631 | −1.35 | 39.3% | −0.018 |
| AVWAP-Breakout | earnings | 159 | −0.51 | 42.8% | −0.023 |
| AVWAP-Breakout | fomc | 0 | n/a | n/a | n/a |

**Gap-day AVWAP works as a pullback level (support/resistance test) but
fails as a breakout level (reclaim from below).** That's a coherent
finding: gap-day AVWAPs are anchored on a high-volume, high-information
session; price *touching* and rejecting that average is a meaningful
event, but price *closing above* the average doesn't change the gap-day
narrative — the breakout often gets sold into by the same participants
who anchored it.

---

## 7. Pass/fail vs each gate

| Gate (per directive §5 acceptance) | AVWAP-Pullback | AVWAP-Breakout |
|---|---|---|
| **Real-data Sharpe ≥ 1.0** | **0.89** — FAIL (close) | **−1.36** — FAIL (severe) |
| **≥ 100 trades** | 7,844 — PASS | 5,790 — PASS |
| **Max drawdown ≤ 15%** | 15.45% — FAIL (border) | 109% — FAIL (account wipe) |
| **VIX-on improves Sharpe** | Marginal (see §8) | Marginal — doesn't rescue |

Net verdict: **Pullback fails by a narrow margin; Breakout fails badly.**

---

## 8. VIX-on vs VIX-off sensitivity

A 2024-only, 5-symbol (AAPL/NVDA/META/MSFT/TSLA) comparison run:

| Mode | Pullback Sharpe | Pullback PnL | Breakout Sharpe | Breakout PnL |
|---|---:|---:|---:|---:|
| VIX-off (vix_max=999) | 0.455 | +$8,070 | −2.25 | −$29,341 |
| VIX-on (vix_max=25) | 0.458 | +$7,950 | (same — 2024 mostly low VIX) | (same) |

The coarse VIX regime map flags only 2024-08-05 to 2024-08-09 as
"high-VIX" within calendar-2024, so the gate barely binds on this period.
For the full-year 2020-2024 run on 36 symbols, the gate matters more —
all of Jan-Nov 2022 (the bear year) is in the high-VIX window, so
≈30-40% of 2022 sessions are suppressed, which is why 2022's trade count
drops to 548 (vs ~1,500-2,000 in normal years).

**The VIX gate helps but does not flip the verdict.** Even with perfect
2022 suppression, the strategies' edge is too thin to clear Sharpe ≥ 1.0
gates.

A Wave 5 follow-up could replace the coarse VIX window map with a real
daily VIX series (e.g. CBOE historical CSV), which would let us calibrate
the 22/25 hysteresis suggested in Wave 3 synthesis §3. Out of scope for
this build given the current verdict.

---

## 9. Comparison with PDH-Fade (the Wave 3 survivor)

Per Wave 3 synthesis §1, PDH-Fade is the sole strategy that cleared all
real-data and robustness gates (Sharpe 1.40-1.47 fixed-dollar, +$582K on
$100K, every year positive). The directive asks whether AVWAP-Pullback
fires on **different days** than PDH-Fade.

### 9.1 Symbol-day overlap

| Metric | Count |
|---|---:|
| AVWAP-Pullback (symbol, session_date) pairs | 7,844 |
| PDH-Fade (symbol, session_date) pairs | 9,874 |
| Intersection | 2,504 |
| AVWAP-only days | 5,340 |
| PDH-only days | 7,370 |

**Only 32% of AVWAP-Pullback's signal days overlap with PDH-Fade.** 5,340
unique (symbol, date) pairs fire AVWAP-Pullback but never fire PDH-Fade
— a strong diversification signal at the trade-count level.

### 9.2 Daily-P&L correlation

- Per-trade-day P&L correlation on the 2,504 overlapping (symbol, day)
  pairs: **+0.001** (effectively zero).
- Full-panel daily P&L correlation (sum across all symbols per day):
  **+0.015** (effectively zero).
- Days both strategies fire (across the universe): 718
- Days only AVWAP fires: 189
- Days only PDH fires: 277

**Conclusion: AVWAP-Pullback and PDH-Fade are uncorrelated at the daily
level.** If AVWAP-Pullback could be raised to Sharpe ≥ 1.0 (it's at
0.89), the pair would be an excellent portfolio combination — near-zero
correlation, different signal mechanism, similar timeframes.

This is the strongest argument for **keeping AVWAP-Pullback on the watch
list** rather than retiring it: it's not a duplicate of PDH-Fade. A Wave
5 follow-up tuning pass (proximity, anchor lookback, signal-candle
strictness) might push its Sharpe over the bar; the diversification
ceiling is real.

---

## 10. Why the strategies underperform — diagnostic

### 10.1 Pullback: edge per trade is too small

- Avg R: +0.009 — i.e. the average trade makes 0.9% of risk per fire.
- Profit factor: 1.07 — wins are only ~7% bigger than losses on average.
- Stop-out rate: 49.4%.

The pullback thesis works on highly volatile small-caps (where Manny's
intuition lives) but on AAPL/MSFT/NVDA mega-caps, the gap-day AVWAP gets
revisited so often that the "first pullback" reaction is washed out by
many subsequent pullbacks. The signal-candle volume confirmation isn't
strict enough to filter the chop.

### 10.2 Breakout: wrong-side fade

- 56% of trades stop out. Long-only by design.
- The "reclaim from below" sequence is preceded by accumulation in a
  zone *below* the gap-day AVWAP — meaning the AVWAP is acting as
  resistance and most reclaims fail. Closing above + 1.5× vol catches
  the failed-breakout (long trap) instead of the clean reclaim.

A fix would be to gate breakouts on a higher-vol mult (3.0× rather than
1.5×), add an acceptance rule (N bars above AVWAP), or add an L2-imbalance
filter — but each makes the signal rarer and we already have 5,790 trades
across 5 years. Doubling vol_mult would likely halve trade count and
slightly improve win rate without flipping the per-trade edge.

### 10.3 Universe mismatch — known issue carried from Wave 3

Wave 3 J §12 and the Wave 3 synthesis §6 flagged the catalyst-day filter
as a P1 Wave 5 item. The 36-symbol shortlist is liquid-mega-cap-only;
none of the symbols had a true "high-information gap day" the way Manny's
small-cap-gapper universe does. AVWAP is most powerful on names with
*sharp* anchor events — earnings reactions on $5B+ market-cap names,
post-secondary-offering opens, or post-PR-catalyst opens. Backtest 2 of
the framework needs catalyst-day-filtered universe expansion.

---

## 11. Acceptance gates summary

| Gate | Pullback | Breakout |
|---|---|---|
| Sharpe ≥ 1.0 | FAIL (0.89, narrow miss) | FAIL (-1.36) |
| ≥ 100 trades | PASS (7,844) | PASS (5,790) |
| Max DD ≤ 15% | FAIL (-15.45%) | FAIL (-109%) |
| VIX-on improves Sharpe | Negligible | Negligible |
| Positive PnL all years | FAIL (2022 negative) | FAIL (every year negative) |

**Both specs fail Wave 5 acceptance gates.** Promotion to portfolio or
paper testing is not recommended.

---

## 12. Recommendations

1. **Remove `anchored_vwap_breakout` from the framework roster.** The
   thesis fails empirically on this universe; further parameter tuning
   is unlikely to flip the per-trade edge.
2. **Keep `anchored_vwap_pullback` on the watch list** (alongside
   PDH-Breakout and ORB-5min per Wave 3 synthesis §1). It has directional
   edge, ~zero correlation with PDH-Fade, and fires on materially
   different days. Re-evaluate after:
   - Catalyst-day universe filter (Wave 5 P1 from Wave 3 synthesis §4).
   - Tighter signal-candle criteria (require >2× volume, not just
     "increased").
   - A real daily VIX series for proper 22/25 hysteresis tuning.
3. **Earnings-anchor variant deserves a focused re-run** post-Databento-
   Plus or with a fuller earnings calendar. The earnings-AVWAP breakout
   was the best per-anchor sub-result (Sharpe −0.51 vs −1.35 for
   gap-day); a 36-symbol earnings calendar would 5-10× the earnings
   trade count and could narrow the per-anchor Sharpe gap.
4. **Wave 5 build complete** for this agent. Hand off to Cowork for
   Wave 5 synthesis with Agent L (Volume Profile) and Agent P (L2
   confirmation) parallel results.

---

## 13. Files delivered

```
framework/level_sources/anchored_vwap.py       508 lines — AVWAP level source + anchor detection
strategies/anchored_vwap_pullback.yaml          53 lines — pullback spec
strategies/anchored_vwap_breakout.yaml          54 lines — breakout spec
backtest/anchored_vwap_backtest.py             620 lines — bar-level backtest harness
tests/framework/test_anchored_vwap.py          330 lines — 17 unit tests, all passing

backtest_archive/anchored_vwap/
  summary.json
  trades_anchored_vwap_pullback.parquet         7,844 trades
  trades_anchored_vwap_pullback.csv
  trades_anchored_vwap_breakout.parquet         5,790 trades
  trades_anchored_vwap_breakout.csv

backtest_archive/anchored_vwap_vix_off/        2024-only, 5-symbol VIX-off comparison
backtest_archive/anchored_vwap_vix_on/         2024-only, 5-symbol VIX-on comparison
backtest_archive/anchored_vwap_smoke2/         smoke test (optimization parity check)

cowork_reports/2026-05-16_anchored_vwap_backtest.md  (this report)
```

**No live code touched.** Existing bots, scanners, persistence layer,
squeeze detector, and L2 stack — all untouched per directive §7 and
CLAUDE.md "Critical Rules".

---

## 14. Open questions for Cowork

1. **Acceptance gate threshold.** Pullback Sharpe 0.89 vs gate 1.0 — is
   the framework's stance "miss = remove" or "miss-by-margin = tune in
   Wave 5"? The diversification benefit vs PDH-Fade argues for the
   latter; the cleanliness of the gate argues for the former.
2. **Catalyst-day universe expansion priority.** Wave 3 P1 item.
   AVWAP-Pullback's clearest path to clearing the gate runs through a
   universe of names with sharper anchor events. Do we have appetite to
   pull the catalyst-day filter forward from Wave 5 P1 to a Wave 5.5
   parallel agent now?
3. **Earnings calendar source.** Databento Plus is a budget decision —
   would Manny rather pay for the upgrade or pull from a free source
   (Polygon, Yahoo, or a manual quarterly calendar)?
4. **Confidence floor for keeping a watch-list strategy active.** ORB-5,
   PDH-Breakout, and now AVWAP-Pullback are all on the watch list with
   directional edge but failed gates. At what point do we cull?
