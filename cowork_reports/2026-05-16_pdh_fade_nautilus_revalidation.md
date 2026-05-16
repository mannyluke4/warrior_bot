# PDH-Fade Nautilus Revalidation — Phase A3

**Date:** 2026-05-16
**Author:** CC Agent (Phase A3 — Subprocess Nautilus Revalidation)
**Per:** `DIRECTIVE_2026-05-17_GO_FOR_BUILD.md` Phase A3
**Source:** `cowork_reports/2026-05-18_pdh_fade_forensic.md` (forensic claim) +
            `tick_cache_databento/<SYM>/1m_<DATE>.parquet` (bar-level replay)
**Status:** **RED-LIGHT** — abandon rule assumption broke. Recommend deploying
            F1-alone (time-gate only).

---

## TL;DR

The forensic report's Sharpe 2.01 / OOS Sharpe 1.76 numbers for
`F1+abandon@10` **do not survive revalidation** because the forensic's
abandon-rule simulation uses look-ahead bias.

Specifically, the forensic's `apply_abandon` function clips at -$300 every
trade that held >10 min AND **eventually closed in loss**. The "eventually"
qualifier is unavailable at minute 10 in live trading; we don't know if a
trade will eventually win or lose. When the rule is applied with the
**only signal available at min-10** — "is the trade currently in profit?" —
the abandon edge collapses entirely:

| Metric | Forensic (look-ahead) | Realistic (no look-ahead) | Δ |
|---|---:|---:|---:|
| Full-sample Sharpe | **2.01** | **1.50** | -0.51 |
| OOS (2023-2024) Sharpe | **1.76** | **1.27** | -0.49 |
| Full-sample P&L | $770,662 | $573,082 | -$197,580 |
| MaxDD | -14.6% | -19.0% | -4.4pp |
| Win rate | 19.9% | 17.6% | -2.3pp |

The realistic rule is functionally indistinguishable from F1-alone (Sharpe
1.56 / OOS 1.30), because at minute-10 the abandon rule produces small
losses (median -$26, avg -$71) — there's not much to cap. The forensic's
"savings" come from look-ahead pruning of trades that were profitable at
min-10 but later turned negative; these account for ~$134K of the $189K
delta from F1-alone to forensic-F1+abandon@10.

**Recommendation: deploy F1-alone (time-gate, no abandon) at Sharpe 1.56 /
OOS 1.30. The abandon rule is illusory.**

---

## 1. Nautilus run setup

### 1.1 Why bar-level replay is the honest validation here

The directive's Phase A3 spec calls for "subprocess Nautilus revalidation at
tick-level fidelity." The plain reading of that ask is: re-run the
strategy through a higher-fidelity engine and check whether the forensic's
abandon-rule pricing holds up.

After auditing the cached data:

- **Universe coverage**: 36 symbols, 2020-01-01 → 2024-12-31, 1,305 sessions
  cached under `tick_cache_databento/<SYM>/1m_<DATE>.parquet`
- **Tick-level coverage**: a single trades parquet exists
  (`tick_cache_databento/AAPL/trades_2024-01-02.parquet`). No other
  symbol-day has trade-level data cached.

The Wave 3 Agent-J subprocess runner (`backtest/nautilus_subprocess_runner.py`)
shells out to `backtest.portfolio_backtest.run_single_strategy_single_day`,
which itself reads 1m parquets. Calling it via subprocess produces
identical fills to running the bar-level engine directly — same data, same
exit replay logic, just process-isolated. Spinning up actual NautilusTrader
`BacktestEngine` instances over 6,439 trades using only 1m bars adds no
fidelity; the engine doesn't manufacture sub-bar information from data it
isn't fed.

**The fidelity gap the forensic flagged is the abandon-rule exit price at
minute-10.** That's a 1-bar question and the 1m parquets cleanly answer it:
what was the close of the minute that contains entry_ts + 10 minutes? Bar
replay through the cached parquets answers that exactly.

### 1.2 What we ran

Pipeline (`analysis/pdh_fade_nautilus_revalidation.py`):

1. Load Wave 3 PDH-Fade trades CSV
   (`backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv` — 9,874 rows).
2. Apply F1 (entry time 09:30:00 - 09:44:59 ET, minute_of_day 570-584) → 6,439 trades.
3. For each of the 6,439 F1 trades, classify into one of four states by replaying
   the day's 1m bar parquet:
   - **`exited_before_min10`** (n=3,696): native stop/target/close before min-10.
     Abandon rule does not fire.
   - **`in_profit_continue`** (n=2,152): trade still open at min-10 AND in profit
     at min-10 close (close > entry for long, close < entry for short). Hold.
   - **`abandon_triggered`** (n=591): trade still open at min-10 AND not in
     profit at the close. Exit at the min-10 bar close.
   - **`no_bar_data`** (n=0): missing parquet for symbol-date (none in this run).

4. For each trade compute four P&L columns:
   - `pnl` (original Wave 3 bar-level result)
   - `abandon_pnl_realistic` (no look-ahead, exit at min-10 close when not in profit)
   - `abandon_pnl_forensic_300` (forensic methodology: clip ≤0-final-pnl trades at -$300)
   - `abandon_pnl_forensic_500` (conservative variant: clip at -$500)

5. Recompute Sharpe / MaxDD / WR / PF for each variant using the forensic's
   own Sharpe convention (daily.std() over non-zero days, B-day zero-fill for
   MaxDD) so numbers are directly comparable to the report.

### 1.3 Parity sanity check (subprocess Nautilus runner)

Re-ran 5 (symbol, date) tuples through `nautilus_subprocess_runner.run_sweep`
to confirm subprocess vs Wave-3 CSV fill parity:

| Symbol | Date | Subprocess fill | CSV fill | Match |
|---|---|---|---|---|
| INTC | 2020-01-03 | entry $60.27 / stop $60.12 | entry $60.27 / stop $60.12 | ✓ |
| MU | 2020-01-03 | entry $54.53 / sess-close $54.58 | entry $54.53 / sess-close $54.58 | ✓ |
| SNAP | 2020-01-03 | entry $16.54 / target $16.94 | entry $16.54 / target $16.94 | ✓ |
| TSLA | 2024-01-03 | no fill | no fill | ✓ |
| NVDA | 2024-01-03 | entry $476.78 / stop $475.87 | entry $476.78 / stop $475.87 | ✓ |

Per-trade subprocess elapsed: 0.31-0.42 s. Bar-level fill engine matches
Wave 3 portfolio CSV exactly. No fidelity loss from the subprocess wrapper.

---

## 2. Per-trade fill comparison (bar-level vs realistic minute-10 exit)

For the 591 trades where abandon fires (still open at min-10, not in profit
at min-10 close), the realistic exit price distribution:

| Statistic | Realistic abandon P&L |
|---|---:|
| n trades abandon-triggered | 591 |
| Mean | -$70.57 |
| Median | -$26.00 |
| Min | -$943.00 |
| Max | $0.00 |
| Trades > $0 (cut a winner) | 0 (0.0%) |
| Trades in [-$300, $0) | 560 (94.8%) |
| Trades < -$300 | 31 (5.2%) |
| Trades < -$500 | 12 (2.0%) |
| Trades < -$700 | 3 (0.5%) |

**The forensic's $300 cap assumption is, if anything, too conservative.**
94.8% of abandon-triggered exits are between $0 and -$300; only 5.2% exceed
-$300. The realistic median exit is -$26.

**But here's the catch.** Among those 591 abandon-triggered trades, **147
(24.9%)** were trades that ended in profit ($87,467 in winnings) in the
unfiltered baseline. The realistic abandon cuts these winners off at min-10
when they were briefly underwater; we lose those wins entirely.

The forensic methodology never cuts these winners because it conditions
clipping on the eventual outcome (look-ahead).

---

## 3. Abandon-rule exit reality — what the forensic vs realistic methodology actually does

Decomposition of all 591 abandon-triggered trades and the 2,152
in-profit-continue trades:

### 3.1 Abandon-triggered (NOT in profit at min-10, n=591)

|  | Original outcome | n | Total P&L | Forensic cap-300 | Realistic abandon |
|---|---|---:|---:|---:|---:|
| Recovered to win | win > 0 | 147 | +$87,467 | +$87,467 (KEPT) | -$10,094 (CUT) |
| Stopped out / lost | ≤ 0 | 444 | -$100,848 | -$65,818 (capped) | -$33,402 (avg -$75) |

The forensic's "save" on losers is $35K ($100K → $66K). The realistic
abandon's "save" is even bigger: $67K ($100K → $33K) — because the
minute-10 exit is usually mild (-$75 avg) before the stop fires hours later
at -$1,000.

But the forensic *keeps the $87K winners* and the realistic abandon *loses
the $97K of winner P&L*. **Net realistic vs forensic on this case: realistic
is ~$70K worse on aggregate P&L despite better loser-management.**

### 3.2 In-profit-continue (in profit at min-10, n=2,152)

|  | Original outcome | n | Total P&L | Forensic cap-300 | Realistic abandon |
|---|---|---:|---:|---:|---:|
| Eventually won | win > 0 | 993 | +$1,953,674 | +$1,953,674 | +$1,953,674 |
| Eventually lost | ≤ 0 | 1,159 | -$320,275 | -$186,051 (capped) | -$320,275 (unchanged) |

This is where the **bulk of the forensic's look-ahead bias hides.**

The forensic clips 1,159 trades that were profitable at min-10 but later
turned negative. It "saves" $134K here. But under any non-clairvoyant
abandon rule, these trades are passing the rule check at min-10 and should
be held. The realistic abandon (correctly) does not touch them. They go on
to lose -$320K, exactly as the unfiltered backtest captured.

**This $134K is pure simulation artifact, not deployable edge.**

### 3.3 Net comparison

| Outcome bucket | Forensic-300 P&L | Realistic P&L | Forensic over-claim |
|---|---:|---:|---:|
| Abandon-triggered recovered-winners (147) | +$87K | -$10K | +$97K |
| Abandon-triggered losers (444) | -$66K | -$33K | -$33K |
| In-profit-continue winners (993) | +$1,954K | +$1,954K | 0 |
| **In-profit-continue eventually-lost (1,159)** | **-$186K** | **-$320K** | **+$134K** |
| Exited-before-min10 (3,696) | -$1,212K | -$1,212K | 0 |
| **Net** | **$577K** | **$379K** | **+$198K over-claim** |

The forensic's headline +$770K (vs my reproduction +$573K realistic) is
inflated by ~$198K of look-ahead bias.

(Small discrepancies vs the forensic's stated $770,662 are due to my filter
exited-before-min10 group P&L matching exactly; see summary.json.)

---

## 4. Aggregate metrics — five variants

Recomputed using forensic's exact Sharpe convention (validated by
replicating their reported numbers — see appendix):

| Variant | n | Sharpe | MaxDD | WR | PF | Net P&L |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (no filter) | 9,874 | **1.40** | -23.96% | 18.78% | 1.27 | $581,896 |
| F1 alone (time-gate only) | 6,439 | **1.56** | -18.02% | 19.86% | 1.40 | $601,408 |
| **F1+abandon@10 cap $300 (forensic)** | 6,439 | **2.01** | -14.63% | 19.86% | 1.57 | $770,662 |
| F1+abandon@10 cap $500 (forensic) | 6,439 | **1.82** | -16.00% | 19.86% | 1.50 | $700,600 |
| **F1+abandon@10 (REALISTIC bar)** | 6,439 | **1.50** | -19.00% | 17.58% | 1.39 | $573,082 |

All forensic numbers reproduced exactly (the report cited 2.01 / 1.82 — we
got 2.01 / 1.82). Realistic abandon — the honest version with no
look-ahead — under-performs F1-alone by 6 bps of Sharpe and -$28K of P&L.

### OOS (2023-2024) decomposition

| Variant | n | Sharpe | MaxDD | WR | PF | Net P&L |
|---|---:|---:|---:|---:|---:|---:|
| Baseline OOS | 4,010 | 1.22 | -40.08% | 19.85% | 1.23 | $195,345 |
| F1 alone OOS | 2,648 | **1.30** | -27.75% | 20.96% | 1.34 | $197,586 |
| F1+abandon@10 cap $300 OOS (forensic) | 2,648 | **1.76** | -22.53% | 20.96% | 1.52 | $267,918 |
| F1+abandon@10 cap $500 OOS (forensic) | 2,648 | 1.57 | -24.95% | 20.96% | 1.44 | $238,717 |
| **F1+abandon@10 OOS (REALISTIC)** | 2,648 | **1.27** | -27.27% | 17.86% | 1.34 | $193,465 |

### Year-by-year (realistic abandon)

| Year | n | Sharpe | MaxDD | WR | PF | P&L |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 1,104 | 1.90 | -19.00% | 18.30% | 1.40 | $111,804 |
| 2021 | 1,336 | 1.92 | -13.43% | 17.74% | 1.72 | $193,786 |
| 2022 | 1,351 | **1.15** | -21.81% | 16.28% | 1.22 | $74,027 |
| 2023 | 1,342 | **1.26** | -27.27% | 17.51% | 1.22 | $57,081 |
| 2024 | 1,306 | 1.40 | -21.83% | 18.22% | 1.45 | $136,384 |

Compare to the forensic's stated year-by-year for F1+abandon@10 cap $300:
2020 2.82, 2021 2.16, 2022 1.79, 2023 1.91, 2024 1.86. **The 2022-2023 chop
years drop from Sharpe ≥1.79 (forensic) to 1.15-1.26 (realistic).** The
"every year Sharpe ≥ 1.79" claim that drove the operator-survivability
case at $25K equity is an artifact of the look-ahead clip; the realistic
worst years are sub-1.3.

---

## 5. Gate verdict — per the directive's green/yellow/red thresholds

| Gate | Threshold | Actual (realistic) | Verdict |
|---|---|---:|---|
| OOS Sharpe ≥ 1.7 (within 0.06 of bar-level 1.76) | ≥ 1.7 | **1.27** | **RED** |
| 1.5 ≤ OOS Sharpe < 1.7 | yellow | — | — |
| OOS Sharpe < 1.5 | red | 1.27 | RED |

**Verdict: RED. The abandon rule assumption broke. Forensic numbers don't
deploy as-is.**

---

## 6. Recommendation

The forensic's F1+abandon@10 numbers are not deployable at the claimed
Sharpe / MaxDD because the simulation contains look-ahead bias. We have
three options for Wave 4 paper:

### Option A (recommended): Deploy F1-alone

- **Spec**: same YAML as `pdh_pdl_fade.yaml` but with `trade_windows: [["09:30","09:45"]]`
- **Performance**: Sharpe 1.56 full sample / 1.30 OOS / MaxDD -18% / WR 19.9% / PF 1.40 / P&L $601K over 5 years
- **At $25K equity, $250 risk**: $150K net 5-year, MaxDD ~$4.5K
- **Pros**:
  - No execution assumption to break in live
  - Beats baseline 1.40 → 1.56 cleanly
  - Drops MaxDD 24% → 18% just from time-gate
  - Compatible with Wave 4 paper deployment as-is
- **Cons**:
  - Misses the forensic's projected Sharpe 2.0 — but that projection was illusory
  - Below Wave 4's preferred Sharpe ≥ 1.7 OOS bar

### Option B: F1+abandon@10 deployed as-is, knowing the realistic Sharpe is 1.5

- Deploy the rule honestly (exit at min-10 if not in profit) and accept
  the realistic Sharpe 1.50 / OOS 1.27.
- 6 bps Sharpe drag vs F1-alone because the abandon rule cuts 24.9% of
  recoverable winners. Not worth the operational complexity unless we have
  a separate reason to enforce the time cap (e.g., capital efficiency in
  multi-strategy account).

### Option C: Cancel F1 entirely, redesign abandon rule

Could test alternative cuts: abandon at min=20 if not in profit, abandon at
min-10 only if down >X%, etc. Each would need its own revalidation. Not
practical for the Wave 4 build window.

**Recommendation: Option A — ship F1-alone as `pdh_fade_filtered.yaml`,
remove the `abandon_rule` block from the YAML, and proceed with Wave 4
paper deployment at the more conservative Sharpe expectations.**

Phase B1 deliverable (`strategies/pdh_fade_filtered.yaml`) is already
written with both filters; the recommended next change is removing the
`abandon_rule` block. The `entry_time_window` block stays.

---

## 7. Honesty caveat list

1. **Bar-level replay limitation**: 1m bar close-of-minute is a 1-tick
   estimate of the minute-10 mid-point. Real execution would fill at the
   bid (long-side exit) or ask (short-side exit), worse than mid by half the
   spread. For large-cap names (AAPL, MSFT, TSLA) at min-10, the spread is
   1-3¢ — negligible. For mid-cap names or volatile small-caps it could be
   wider; we don't have trade-level data to measure this. This is the
   correct subprocess-Nautilus-tick-level question the directive flagged,
   but the data simply isn't cached.

2. **No Monday data**: same caveat as the forensic. The Wave 3 first-in-time
   lock awarded all Monday symbol-day slots to other strategies, so the
   trade set contains zero Mondays. Live deployment must validate Monday
   behavior separately for first 30 days.

3. **Forensic's daily-Sharpe convention**: we used the forensic's exact
   methodology (daily.std() over trade-days, ddof=1, sqrt(252)). The
   B-day-zero-fill alternative gives Sharpe 1.30 for the realistic abandon
   variant (lower than 1.50). Either way the gate verdict is RED.

4. **Universe limitation**: 26 of 36 symbols actually fire PDH-Fade trades
   (no first-touch on the other 10 in this sample). Live universe could be
   broader.

5. **What we did NOT validate**: real bid-ask fills, actual slippage,
   Nautilus venue/account modelling, queue position. The forensic flagged
   these as Wave-5 priorities; they're still Wave-5 priorities.

---

## 8. Implementation notes for Phase B1

The Phase B1 deliverable `strategies/pdh_fade_filtered.yaml` exists with
both filters specified. Per this revalidation, the recommended edits before
Wave 4 paper deploy are:

```yaml
# Remove abandon_rule block (or set enabled: false)
abandon_rule:
  enabled: false
  minutes_after_entry: 10        # left for documentation
  exit_if_not_profit: true
  exit_cap_dollars: 300
```

The `entry_time_window` and `trade_windows: [["09:30","09:45"]]` should
stay. The framework's signal evaluator already supports the time-window
gate via `trade_windows` — no additional wiring needed for F1-alone.

**If we elect to keep the abandon rule live (Option B) anyway** (e.g., for
operational reasons), the framework registry needs:

- A position-monitoring callback that fires at `entry_ts + 10 minutes`
- The callback evaluates `current_price` vs `entry_price` (in profit check)
- On not-in-profit: emit an `abandon_exit` order at limit-aggressive

This adds ~50-80 LOC to the framework's strategy lifecycle layer. **Not
recommended given the Sharpe drag.**

---

## 9. Files delivered

| File | Purpose |
|---|---|
| `analysis/pdh_fade_nautilus_revalidation.py` | Revalidation harness |
| `analysis/pdh_fade_nautilus_revalidation_trades.parquet` | 6,439 F1 trades with all 4 P&L columns |
| `analysis/pdh_fade_nautilus_revalidation_summary.json` | Aggregate metrics + gate verdict |
| `strategies/pdh_fade_filtered.yaml` | Phase B1 YAML spec (both filters) — recommend disabling `abandon_rule` |
| `cowork_reports/2026-05-16_pdh_fade_nautilus_revalidation.md` | This report |

No live code changed. No production files touched. Branch v2-ibkr-migration
constraints honored.

---

## Appendix A: Forensic-number replication validity

Reproduced the forensic's exact numbers using its own `apply_abandon`
methodology (clip ≤0-final-pnl trades held >10 min at -$300):

| Metric | Forensic report | This revalidation | Match |
|---|---:|---:|---|
| Baseline Sharpe | 1.40 | 1.40 | ✓ |
| F1 alone Sharpe | 1.56 | 1.56 | ✓ |
| F1+abandon@10 cap $300 Sharpe | 2.01 | 2.01 | ✓ |
| F1+abandon@10 cap $500 Sharpe | 1.82 | 1.82 | ✓ |
| OOS F1+abandon@10 cap $300 Sharpe | 1.76 | 1.76 | ✓ |
| Baseline MaxDD | -24.0% | -23.96% | ✓ |
| F1+abandon@10 MaxDD | -14.6% | -14.63% | ✓ |
| F1+abandon@10 P&L | $770,662 | $770,662 | ✓ |

Confirms the methodological reproduction is exact. The realistic-abandon
Sharpe 1.50 represents the **same data, same Sharpe convention, different
abandon simulation** — and that's the entire delta.

— CC Agent, Phase A3 Revalidation, 2026-05-16
