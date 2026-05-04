# Wave Scalp — Stage 1 Research Report

**Date:** 2026-05-04
**Author:** CC
**Scope:** YTD 2026 (2026-01-02 → 2026-05-04, 84 trading days)
**Per directive:** `DIRECTIVE_WAVE_SCALP_STAGE1_RESEARCH.md`
**Status:** Stage 2 = ❌ DO NOT YET PROCEED — see Section D for blockers and proposed fixes

---

## Headline

The wave-scalp pattern Manny describes **does appear** in our IBKR-tick YTD cache, on **44.6% of (symbol, date) cells**. Mechanical detection produces **15,648 waves** across 84 days. Filtering to score-≥7 setups produces **551 hypothetical trades** with **40.7% WR** and **profit factor 10.04**. However, the headline P&L (+$2.5M) is contaminated by **a single bug-driven trade** (FIGG 2026-02-24, +$2.2M from a 40M-share degenerate position). After removing that trade, the strategy still profits +$318K with PF 2.15 — but **win rate (40.4%) misses the directive's ≥50% acceptance threshold**.

The thesis is *partially* validated. The pattern exists at scale and is profitable in aggregate, but the directive's exit rules (especially the 10-min time stop and the wave-high target) produce a low-WR / high-PF profile rather than the consistent-base-hits Manny is doing on TradingView. Stage 2 should not proceed yet — we need to fix the position-sizing edge case, then either (a) loosen the WR requirement and accept a high-R / lower-WR profile, or (b) tighten exit rules to convert more trades into clean target hits.

---

## Method

**Pipeline:**

1. `wave_detector.py` (new) — pure pattern detection. Identifies waves on closed 1-min bars: ≥0.75% magnitude swing from a local extreme, 3-15 min duration, ≥0.5% reversal in the opposite direction confirms the wave.
2. `scripts/wave_census.py` (new) — replays ticks from `tick_cache/<date>/<sym>.json.gz` through `bars.TradeBarBuilder` (the same module the live bot uses) to produce 1-min bars, feeds bars into `WaveDetector` and a `MACDState` (12/26/9 on closes).
3. For each detected DOWN wave, scores it 0-10 on the directive's seven criteria (prior waves, near recent low, MACD rising, higher low, volume confirm, green bounce, minimal upper wick).
4. For each score-≥7 wave, simulates the long trade: entry = next bar open, target = highest end-price of recent up-wave, stop = bounce-bar low − 0.25%, 10-min time stop, $1,000 risk per trade.
5. `scripts/wave_analysis.py` (new) — reads the three CSVs, computes Section A-D facts, writes `wave_research/ytd_summary.json`.

**Scope:** 84 dates (2026-01-02 → 2026-05-04), 2,593 (sym, date) cells discovered. 5 cells failed (4 corrupt gzips on 2026-04-15: KIDZ, MNTS, MYSE, TSLG; 1 read error). 2,588 cells fully processed in 485 s.

**Outputs (in `wave_research/`):**
- `ytd_wave_census.csv` — 2,588 rows, one per (sym, date)
- `ytd_waves_detail.csv` — 15,648 rows, one per detected wave
- `ytd_hypothetical_trades.csv` — 551 rows, one per simulated trade
- `ytd_summary.json` — aggregated stats from this report

**No existing strategy files were modified.** `wave_detector.py` and `scripts/wave_census.py` / `scripts/wave_analysis.py` are net-new files. The detector consumes the same `bars.Bar` shape the live bot uses; the census driver imports `bars.TradeBarBuilder` and `macd.MACDState` unchanged.

---

## Section A — Wave Frequency

### How often do waves appear?

| Metric | Value |
|---|---:|
| (sym, date) cells in cache | 2,588 |
| Cells with ≥1 wave | 1,154 |
| **% of cells with at least one wave** | **44.6%** |
| Cells with ≥1 score-≥7 setup | 288 |
| % of cells with a tradeable setup | 11.1% |
| Total waves detected | 15,648 |
| Avg waves per active cell | 13.6 |
| Median waves per active cell | 6 |
| Max waves in one (sym, date) cell | 504 |

**Read:** Almost half of the watchlist-day cells in the cache produced at least one wave. That clears the ≥30% acceptance threshold. About 11% of cells produced a high-quality setup — meaningful but not abundant.

### Magnitude distribution (all 15,648 waves)

| Bucket | Count | % |
|---|---:|---:|
| <1% | 1,937 | 12.4% |
| 1-2% | 6,830 | **43.6%** |
| 2-3% | 3,240 | 20.7% |
| 3-5% | 2,188 | 14.0% |
| 5-10% | 930 | 5.9% |
| >10% | 523 | 3.3% |

Median wave magnitude: **1.83%** (P25 1.26%, P75 2.88%). The directive's 0.75% minimum lets through the noise band but the median is well above floor — these are *real* swings, not measurement artifacts. The fat tail (>5% = 9.3% of waves) is dominated by a handful of high-volatility runners.

### Time-of-day buckets (15,648 waves)

| Bucket | Waves | % |
|---|---:|---:|
| Premarket (4:00-9:30 ET) | 4,288 | 27.4% |
| **Morning (9:30-12:00 ET)** | **4,555** | **29.1%** |
| Midday (12:00-15:00 ET) | 2,267 | 14.5% |
| Close (15:00-16:00 ET) | 675 | 4.3% |
| Afterhours (16:00-20:00 ET) | 3,863 | 24.7% |

Morning is the densest block, but premarket and afterhours together account for ~52% of waves — the strategy is NOT a 9:30-12 phenomenon. Premarket waves on these names are real because Manny's universe is gap-up small-caps, which trade actively in pre-market. The afterhours bucket is partially inflated by the YTD backfill capturing post-RTH cleanup runs on the same names.

---

## Section B — Pattern Match Rate

Of 15,648 total waves, **7,873 are down-waves** (the long-entry candidates we score). Score distribution:

| Score | Count | Cumulative ≥ |
|---:|---:|---:|
| 0 | 304 | 7,873 (100.0%) |
| 1 | 532 | 7,569 (96.1%) |
| 2 | 1,005 | 7,037 (89.4%) |
| 3 | 1,741 | 6,032 (76.6%) |
| 4 | 1,151 | 4,291 (54.5%) |
| 5 | 1,624 | 3,140 (39.9%) |
| 6 | 686 | 1,516 (19.3%) |
| **7** | **455** | **830 (10.5%)** |
| 8 | 251 | 375 (4.8%) |
| 9 | 67 | 124 (1.6%) |
| 10 | 57 | 57 (0.7%) |

**10.5% of down-waves clear the ≥7 setup threshold.** That's a useful funnel — strict enough to filter most noise, loose enough to fire 551 trades over 84 days.

### Which scoring criteria are most predictive?

Hit-rate of each criterion across all 7,873 down-waves vs only the top-tier (score ≥7, n=830):

| Criterion | All down-waves | Score ≥7 | Lift |
|---|---:|---:|---:|
| Prior waves observed (≥2) | 86.0% | 99.0% | +13pp |
| Near recent low (≤1%) | 32.1% | **80.8%** | +49pp |
| MACD rising | 24.0% | **66.3%** | +42pp |
| Higher low forming | 38.4% | **78.3%** | +40pp |
| Volume confirm | 47.7% | 63.1% | +15pp |
| Green bounce | 24.1% | **72.4%** | +48pp |
| Minimal upper wick | 46.6% | 81.6% | +35pp |

**Most predictive (high lift):** "near recent low," "green bounce," "MACD rising," and "higher low forming." These are the structural-pattern criteria — they're rare in the general population (24-38%) but nearly always present in the high-score setups (66-81%). The low-lift criteria are "prior waves" (almost always true after a few minutes) and "volume confirm" (binary noise).

**Implication for tuning:** the 7 criteria aren't equally informative. A weighted score (e.g., +3 each for the high-lift criteria, +1 for the rest) might separate signal from noise more cleanly. Defer to Stage 2 design.

---

## Section C — Hypothetical Performance

### Headline numbers (raw, including FIGG bug)

| Metric | Value |
|---|---:|
| Total trades | 551 |
| Win rate | **40.7%** |
| Profit factor | **10.04** |
| Total P&L | **+$2,514,153** |
| Avg win | $12,466 |
| Avg loss | -$851 |
| Max drawdown | $18,979 (0.8% of P&L) |

### The FIGG outlier

A single trade (FIGG 2026-02-24, wave_id=10, score=7) accounts for **+$2,196,000 — 87.3% of total P&L**. The trade row:

```
entry=$2.005, target=$2.0599, stop=$2.005, exit_reason=target_hit
risk_per_share=$0.0 (post-rounding), shares=40,000,000, pnl=$2,196,000
```

**Root cause:** the bounce-bar low and `bounce_bar.low * (1 - 0.0025)` rounded to the same dollar value due to float arithmetic on a $2 stock. `risk_per_share` was computed as a tiny non-zero float (small enough to round-display as 0.0). The position-size formula `shares = int($1000 / risk_per_share)` then produced 40 million shares. Real-world infeasible (would require ~$80M of buying power on a $2 stock), and our `simulate_trade` lacks a notional or share cap.

**This is a sizing-validator bug, not a strategy bug.** Mitigation in Stage 2: enforce `min_risk_per_share = max($0.01, entry * 0.1%)` and `max_shares = max_notional / entry_price`.

### De-FIGG headline numbers

After removing the four FIGG trades (the 2196K winner plus three smaller mixed):

| Metric | Value |
|---|---:|
| Total trades | 547 |
| Win rate | **40.4%** |
| Profit factor | **2.15** |
| Total P&L | **+$318,577** |
| Avg win | $2,696 |
| Avg loss | -$850 |
| Median win | $1,065 |
| Median loss | -$1,000 |

PF still passes the ≥1.4 acceptance threshold by a wide margin. Total over 74 trading days = ~$4,300/day on $1K-risk-per-trade sizing.

### Exit-reason breakdown (ex-FIGG)

| Reason | Trades | % | WR | Avg P&L | Total |
|---|---:|---:|---:|---:|---:|
| target_hit | 115 | 21.0% | 100% | +$2,794 | +$321,313 |
| stop_hit | 219 | 40.0% | 0% | -$1,000 | -$218,995 |
| **time_stop** | **205** | **37.5%** | **50.7%** | **+$1,049** | **+$215,050** |
| session_end | 8 | 1.5% | 25% | +$151 | +$1,209 |

**The single most striking finding in the data:** time-stopped trades are *profitable* on average and have a 50.7% in-trade win rate. The 10-min cap is forcibly closing trades that would otherwise have continued resolving — and the average closure is a small win. This implies extending the time stop (or removing it) would convert some of those 205 trades into clean target/stop resolutions, very likely improving WR.

### R-multiple distribution (ex-FIGG, 547 trades)

| R bucket | Count | % |
|---|---:|---:|
| <-1.5R | 7 | 1.3% |
| -1.5..-0.5R | 254 | 46.4% |
| -0.5..0R | 39 | 7.1% |
| 0..0.5R | 79 | 14.4% |
| 0.5..1R | 48 | 8.8% |
| 1..2R | 42 | 7.7% |
| 2..5R | 44 | 8.0% |
| 5..10R | 26 | 4.8% |
| ≥10R | 8 | 1.5% |

**The shape is a R/R asymmetry trade: lose 1R when stops hit (53% of trades), make small wins or get clipped early on most others, and hit a few big winners (1.5% of trades >10R) that drive most of the profit.** This is a *swing/breakout* return profile, not a *scalp* return profile. Manny's TradingView results suggest he's banking small consistent wins (more like a >50% WR with 1:1 R/R) — the directive's exit rules don't reproduce that.

### Outlier domination (ex-FIGG)

| Metric | All 551 | Ex-FIGG (547) |
|---|---:|---:|
| % of P&L from top-1 trade | 87.3% | ~18% (top is $57,831) |
| % of P&L from top-5 trades | 92.4% | ~44% |
| % of P&L from top-5 days | 95.3% | ~62% |

The directive's "not outlier-dominated" criterion was failing badly with FIGG (95% from 5 days). After removing the FIGG bug, top-5 days carry ~62% — still concentrated, but no longer pathological. With 74 trading days that have at least one trade, the top 5 producing 62% of the P&L is consistent with how breakout-style strategies typically perform.

### Score-threshold sensitivity (ex-FIGG)

| Threshold | Trades | WR | PF | Total | Avg Win | Avg Loss |
|---:|---:|---:|---:|---:|---:|---:|
| ≥7 | 547 | 40.4% | 2.15 | +$318,577 | +$2,696 | -$850 |
| ≥8 | 231 | 44.2% | 2.14 | +$119,143 | +$2,191 | -$809 |
| **≥9** | **85** | **43.5%** | **2.77** | **+$58,963** | **+$2,495** | **-$695** |
| ≥10 | 35 | 25.7% | 0.38 | -$10,092 | +$692 | -$628 |

Lifting the threshold to ≥8 yields a small WR bump (44%) at half the trade count. **Threshold ≥9 has the best PF (2.77) but only 85 trades over 84 days** (~1/day). Threshold ≥10 (perfect score on all 7 criteria) is too restrictive — only 35 trades, dominated by losses. Sweet spot is probably 7-8.

### Universe diversity

| Metric | Value |
|---|---:|
| Unique symbols traded | 174 |
| Trade days (≥1 trade) | 74 of 84 |
| Avg trades/day | 7.4 |
| Median trades/day | 5 |
| Max trades/day | 36 |

Strategy fires on a wide universe (174 distinct symbols), not concentrated on 1-2 names. KIDZ leads with 66 trades — that's a single name across many days, which is normal for a high-volatility runner. Top-5 symbols by P&L (ex-FIGG): CRWG +$61K, KIDZ +$37K, CKX +$31K, SKYQ +$28K, ATPC +$22K.

---

## Section D — Findings & Recommendations

### Acceptance criteria — Stage 2 gate

| # | Criterion | Status | Detail |
|---:|---|:---:|---|
| 1 | Wave-detection correctly identifies oscillations on ≥5 known-good stocks (manual) | ⏳ DEFERRED | Awaiting Manny's manual review of 5 named stocks. Test data ready in `wave_research/ytd_waves_detail.csv` filtered by symbol. |
| 2 | ≥100 hypothetical trades | ✅ PASS | 547 ex-FIGG (or 551 raw) |
| 3 | Hypothetical WR ≥ 50% | ❌ **FAIL** | 40.4% ex-FIGG, 40.7% raw |
| 4 | Hypothetical PF ≥ 1.4 | ✅ PASS | 2.15 ex-FIGG, 10.04 raw (FIGG inflated) |
| 5 | Distribution not dominated by 1-2 outlier days | 🟡 **MARGINAL** | Raw: 95% from top-5 days (FAIL). Ex-FIGG: ~62% from top-5 days (acceptable for breakout-style P&L distribution). |
| 6 | Pattern in ≥30% of watchlist cells | ✅ PASS | 44.6% of cells have ≥1 wave |

**Three of six gates clean-pass. Criterion 1 is awaiting manual verification. Criterion 3 (WR) is the principal blocker. Criterion 5 was failing only because of the FIGG bug.**

### Is the thesis validated?

**Yes, partially.** The pattern is real, frequent, and tradeable — but the directive's exit rules produce a different return profile than Manny's hand-trading. Manny is presumably scalping consistent small wins; the mechanical version produces breakout-style P&L (low WR, high PF, fat right tail).

There are three honest paths:

1. **Accept the profile shift.** A 40% WR / 2.15 PF strategy IS profitable and uncorrelated with squeeze. We could ship it as a "wave breakout" strategy rather than a "wave scalp" strategy — same setups, different return character. PF 2.15 over 74 days on $1K risk = $4,300/day — meaningful contribution.

2. **Re-tune exits to match Manny's TradingView profile.** The data points strongly at this. Specifically:
   - **The 10-min time stop is leaving money on the table.** Time-stopped trades are 50.7% WR with avg +$1,049 — these are the trades that "would have made it" but got cut. Extending time stop to 20-30 min (or removing entirely) is the single highest-leverage change.
   - **The target (= recent up-wave high) is often too close to entry.** Many wins clip the target by pennies. A wider target (e.g., recent up-wave high + 0.5%, or 1.5x ATR) might widen R/R.
   - **The stop (-0.25% below bounce low) might be too tight.** 46% of trades hit -0.5..-1.5R (clean stops at -1R). If pulling stop to -0.5% widens to -0.75R worst case, we might filter out wicks-and-recovers that currently get stopped out.

3. **Tighten entry criteria.** Score ≥9 produces PF 2.77 (best) at 1/day frequency. If Stage 2 builds with score ≥9, fires ~85 trades over 84 days, expected ~$700/day. Not Manny's $37K-in-14-days TradingView pace, but cleanly tradeable.

**Recommended Stage-2 plan:** combine all three. Tighten score to ≥8, widen targets, extend time stop to 20 min. Re-run the census with the new rules and re-evaluate WR before any code goes near the live bot.

### Specific changes for Stage 2 retry

Before any Stage-2 build:

1. **Position-sizer hardening (BLOCKING):**
   - `min_risk_per_share = max($0.01, entry_price * 0.001)` (10 bps minimum)
   - `max_shares = floor(max_notional / entry_price)` where max_notional = $50K (matches main bot's WB_MAX_NOTIONAL)
   - This single fix would have eliminated the FIGG bug at source. It's not even a strategy decision — it's basic input validation.

2. **Census re-run with these rule changes (each compared to the current 547-trade ex-FIGG baseline):**
   - **Variant A:** time stop 20 min (vs 10), score ≥7 — expect higher WR, similar PF
   - **Variant B:** target = max(recent_up_wave_high, entry × 1.015) — expect more time_stops, possibly higher avg_win
   - **Variant C:** score ≥8 only — already evaluated (231 trades, 44.2% WR)
   - **Variant D (combined):** score ≥8, time stop 20 min, target with floor — most likely to achieve ≥50% WR

3. **Manual validation (per criterion 1):** Manny picks 5 known-good wave-scalp days from his TradingView P&L log; we filter `ytd_waves_detail.csv` for those (symbol, date) pairs and confirm the algorithm tagged the swings he saw. If false negatives (real waves missed) → loosen detection thresholds; if false positives (waves where he didn't trade) → tighten.

### What stock filters should activate Wave Scalp?

From the data:
- **Cells with ≥1 wave: 44.6%** — strategy is broadly applicable across the watchlist.
- **Cells with score-≥7 setup: 11.1%** — the high-quality subset.
- **Top performers ex-FIGG:** CRWG, KIDZ, CKX, SKYQ — these are sub-$5 small-caps with high RVOL. Matches Manny's universe.
- **Bottom performers (worst losers):** JLHL -$5,599 (1 trade), SPOG -$4,816 (6), LLYX -$4,071 (9). These are isolated bad-day stocks; no obvious pre-trade filter that would have excluded them.

**Tentative filter logic for activation:**
- Stock must be on the bot's already-qualified watchlist (gap, float, RVOL filters from `live_scanner.py`)
- Must have ≥2 prior waves observed (proves it's oscillating, not trending)
- Suppress during the first 10 minutes of premarket (insufficient bars to establish prior waves)
- Suppress after 11:30 ET if no prior squeeze attempted that day (no "alive" confirmation)

These are starting points; refine in Stage 2.

### What NOT to do in Stage 2

- ❌ Do not ship until the position-sizer is hardened. The FIGG bug would replicate live with potentially catastrophic order rejection or fills.
- ❌ Do not chase the 50% WR by tightening to score ≥10 — that bucket is a 26% WR loser (35 trades, -$10K). Either signal saturates or there's curve-fit.
- ❌ Do not run two full strategies (squeeze + wave scalp) on the same Alpaca account at once until the Wave Scalp passes paper validation alongside squeeze for at least 5 trading days.

---

## Stage 2 go/no-go recommendation

**❌ Do NOT proceed to Stage 2 yet.**

Reason: WR criterion fails (40.4% < 50%). PF and trade-count criteria pass cleanly, but the WR shortfall means the directive's strict acceptance gate is not met.

**Path to GO:** retry the census with the four fixes above (sizing hardening + extended time stop + score ≥8 + target floor) and re-evaluate. Best-case outcome: new WR ≥ 45-50%, PF stays ≥2, trade count ≥100. That would meet the spirit of the gate.

**If retry still under-performs WR:** convene with Manny to decide whether to relax the WR criterion (the data argues a 40% WR / 2.15 PF strategy is an honest profitable trade — high R/R is a legitimate return profile, just different from his hand-scalping style).

---

## Files & artifacts

```
wave_detector.py                                  (new) 230 LOC
scripts/wave_census.py                            (new) 380 LOC
scripts/wave_analysis.py                          (new) 170 LOC
wave_research/
  ytd_wave_census.csv                             2,588 rows
  ytd_waves_detail.csv                            15,648 rows
  ytd_hypothetical_trades.csv                     551 rows
  ytd_summary.json                                aggregated
cowork_reports/2026-05-04_wave_scalp_research.md  (this file)
```

No existing strategy files modified. `bot_v3_hybrid.py` md5 unchanged (verify with `md5sum bot_v3_hybrid.py`).

---

*The wave is real. The scalp is harder than it looks.*
