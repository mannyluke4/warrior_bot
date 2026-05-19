# Track 2 — Stop Redesign Research (gap-up R:R repair)

**Date:** 2026-05-19
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Tue 12:39 PM MDT)
**Status:** GO — research / backtest, no live deploy until candidate is validated

---

## Why this directive exists

Commit `633ee56` ("Live entry-limit fix: use max(arm, live_tape) for basis") shipped this morning and is now live. It fixes the MTVA/RUBI missed-fills failure mode by anchoring the entry limit to the current tape on gap-up triggers instead of the arm price.

**It does not fix the resulting R:R asymmetry.** Stop logic is still mechanical `stop = entry - R` where `entry` is the arm price. When the bot fills at a gap-up basis (say arm $2.02, basis $2.17), the real risk-per-share from the actual fill is `R + (basis - arm)` — R is structurally inflated, target at 1.5R is degraded to ~1.05R, and the stop may sit below the recent structural support level which means we eat the gap-fill round-trip on retracements that wouldn't have stopped a properly-placed stop.

CC explicitly carved this out in the commit message:

> "Stop logic remains mechanical (entry - R) until swing-low redesign is built + validated in simulate.py against full YTD. R:R math on gap-fills will be worse than designed until that lands."

This is Track 2.

---

## Hard methodology

**Backtest decides.** Not intuition, not theoretical purity, not "what discretionary traders do." We test candidates against the YTD honest baseline and let the data pick.

**Same playbook as the framework strategy forensics:**

1. Implement each candidate in `simulate.py` behind a flag (no live changes)
2. Run YTD backtest (Jan 02 → today) on each candidate with X01 config, $30K compounding equity
3. Compare against the YTD honest baseline (`+$290,502 / 75% WR / 55 trades` from yesterday's `2026-05-18_ytd_honest_rebaseline.md`)
4. Walk-forward / anti-overfit checks
5. Report all candidates' results, recommend one, get Manny sign-off
6. Only then implement in live (`bot_v3_hybrid.py` + sibling files)

---

## The five candidates

CC implements all five behind env flags in `simulate.py`. Each is its own backtest run; results compared head-to-head.

### Candidate A — Basis-anchored mechanical stop

`stop = basis - R`

Where `basis = max(arm, live_tape_at_signal_time)` (mirrors the live entry-limit fix).

- **Implementation:** trivial. Replace `entry` with `basis` in stop calc.
- **Hypothesis:** preserves the original R-distance, just shifted upward by the gap. Position sizing unchanged. Stop sits above the original support level, which on big gap-ups may stop out too tight (a normal pullback retraces past where the trigger fired).
- **Risk:** more whipsaws on volatile gap-ups; could systematically reduce winrate without commensurate target gain.

### Candidate B — Swing-low anchored stop

`stop = max_swing_low_in_lookback_window - buffer`

Where:
- `lookback_window` = configurable, candidates: last 5 / 10 / 15 1-min bars before signal
- `buffer` = `max($0.05, basis × 0.5%)` — same shape as the existing `_entry_slippage_for()`
- `R = basis - stop`
- `qty = floor(tier_risk_dollars / R)` (sizing flexes with R)

CC implements as one candidate but tests three lookback windows (B-5, B-10, B-15) inside that candidate's harness — three sub-runs.

- **Implementation:** new `swing_low_finder()` helper in `simulate.py`; reads from existing 1-min bar cache that the simulator already maintains. Live equivalent: read from `state.intraday_bars_1m[symbol]`.
- **Hypothesis:** structural stops behave more like discretionary traders' actual placement; R varies trade-to-trade but max-risk-per-trade stays bounded by sizing.
- **Risk:** noisy swing-low definition could create degenerate stops on choppy bars; small windows may produce stops too tight, large windows too loose.

### Candidate C — Premarket VWAP / opening-range anchor

`stop = max(premarket_vwap, opening_range_low) - buffer`

Where:
- `premarket_vwap` is computed from premarket trades only (already available — scanner uses it)
- `opening_range_low` is the low of the first 5 minutes after 09:30 ET (only applicable post-open)
- `R = basis - stop`
- `qty = floor(tier_risk_dollars / R)`

- **Implementation:** premarket VWAP is in scanner data already; opening-range low needs a session-time guard. Both are clean computations.
- **Hypothesis:** for premarket / open gap-ups, VWAP and opening range are the levels actual market participants are trading off. Stops below them hold the structural narrative.
- **Risk:** doesn't handle intraday gap-ups (a midday spike has no relevant premarket VWAP). Need a fallback rule for after-open trades.

### Candidate D — Hybrid (tightest of the three)

`stop = max(basis - R_mechanical, swing_low_with_buffer, vwap_with_buffer)`

Pick the **tightest** (highest) of the three candidates' stops. R becomes `basis - stop`. Sizing flexes.

- **Implementation:** combine A + B + C, pick max of the three stop prices. Most code, most flexibility.
- **Hypothesis:** "the bot never picks a stop looser than mechanical R, and tightens whenever structural levels are tighter." Gives the most natural stop placement across regimes.
- **Risk:** complexity. More moving parts means more edge cases. May overfit to historical regime if not walk-forward tested.

### Candidate E — Refuse gap-ups beyond threshold

If `basis - arm > X% of arm` (candidates: 2%, 5%, 10%), skip the trade entirely. No stop redesign — just decline the regime.

- **Implementation:** trivial — early-skip in `enter_trade()`.
- **Hypothesis:** gap-ups beyond N% are statistically worse than fading a gap entirely; better to wait for the next clean trigger than to enter at a degraded R:R.
- **Risk:** the data may show exactly the opposite — the biggest gap-ups today (MTVA +7%, RUBI +5%) might be the highest-EV signals when filled correctly. Refusing them costs the upside.

---

## What CC produces

### Deliverable 1 — `simulate.py` flag-gated implementations

Five candidates, all behind env flags. Live code untouched.

```
WB_BT_STOP_MODE=mechanical | basis | swing_low | vwap | hybrid | refuse_gap
WB_BT_SWING_LOW_LOOKBACK=10  # for swing_low / hybrid
WB_BT_GAP_REFUSE_PCT=5.0     # for refuse_gap
```

Default: `mechanical` (current behavior — exactly preserves the YTD baseline).

`bot_v3_hybrid.py` and `bot_alpaca_subbot.py` are NOT modified in this directive. Live still runs mechanical-stop. Backtest is where we test.

### Deliverable 2 — YTD comparison report

Run YTD backtest (2026-01-02 → 2026-05-19, X01 config, $30K compounding equity) for each candidate. Plus three sub-runs of B (5/10/15 lookback) and three sub-runs of E (2%/5%/10% threshold).

Output: `cowork_reports/2026-05-19_track2_stop_redesign_ytd.md` plus per-candidate CSVs.

For each candidate, report:
- Total P&L
- Trade count
- Win rate
- Average winner / average loser
- Max drawdown
- Sharpe ratio (if computable on this trade count)
- Per-trade R:R distribution (the stat that matters most for this redesign)
- Number of gap-up trades (basis > arm by >0.5%)
- Per-trade comparison to mechanical baseline: which trades changed outcome, by how much

### Deliverable 3 — Walk-forward / anti-overfit check

For the top 2-3 candidates from Deliverable 2:
- Train on Jan-Mar 2026, test on Apr-May 2026
- Train on Apr-May 2026, test on Jan-Mar 2026
- Confirm test-period Sharpe ≥ train-period Sharpe (anti-overfit gate)
- Confirm parameter selection (e.g., B's lookback window) holds across train/test boundaries

### Deliverable 4 — Gap-up specific analysis

The MTVA + RUBI today were both gap-up triggers. The whole point of this redesign is improving gap-up trade outcomes. Filter all candidates' results to **only the trades where basis > arm by >0.5%** and report:

- For each candidate vs mechanical baseline: how many gap-up trades, how did they perform?
- Which candidate produces the best gap-up R:R distribution?
- Does the chosen candidate degrade non-gap-up performance? (We don't want to fix gap-ups by hurting clean triggers.)

### Deliverable 5 — Synthesis report and recommendation

`cowork_reports/2026-05-19_track2_synthesis.md` with:
- Headline numbers per candidate vs YTD baseline
- Recommended candidate with rationale
- Risk discussion: what could go wrong with the recommended candidate, what would falsify it in live
- Live-deploy proposal (which env flags, which sibling files, what regression suite)
- Manny decision required

---

## Hard constraints

- **`bot_v3_hybrid.py` and `bot_alpaca_subbot.py` are not modified by this directive.** Track 2 is research-only. Live still runs the mechanical-stop logic with today's `max(arm, live_tape)` entry-limit fix in place.
- **No `simulate.py` modifications outside the flag-gated stop logic.** Don't touch fill model, don't touch tick-cache reading, don't reintroduce fill-realism. Manny's 2026-04-14 directive stands.
- **`mechanical` default preserves the YTD baseline.** We must be able to verify that running with `WB_BT_STOP_MODE=mechanical` produces $+290,502 YTD bit-identical to yesterday's report. If it doesn't, the implementation is wrong, not the data.
- **Position sizing flexes with R, not max_risk.** `tier_risk_dollars` stays constant ($300 at Tier 1); `R` varies per trade based on stop placement; `qty = floor(tier_risk_dollars / R)` is the formula across all candidates.
- Branch: `v2-ibkr-migration` only.

---

## Live monitoring during this work

Today's `633ee56` is live. While CC works on Track 2 in the backtest harness, we want live data on the new entry-limit behavior. CC adds (or confirms exists) per-entry logging:

- `arm_price`, `basis`, `live_tape_at_signal`, `gap_pct = (basis - arm) / arm`
- `original_limit`, `fill_price` (when filled), `chase_cap_aborts` count
- Realized R:R from fill: `(fill - stop) → R`; `(exit - fill) / R → realized_R_multiple`

This data feeds into the eventual Track 2 live deploy validation. CC doesn't need to build a new monitoring pipeline — extend the existing daily report with a "gap-up trades" section.

Output: `cowork_reports/YYYY-MM-DD_gap_up_trades.md` daily, starting tomorrow.

---

## Out of scope

Not addressed by this directive:
- Squeeze 6/15 real-money cutover — stays on current mechanical-stop logic; Track 2 ships post-cutover at earliest
- Engine framework Wave 4 paper deploy — independent
- WB v2 Stage 0 research — independent
- Databento subbot A/B — independent (already in flight)
- Broker latency investigation — independent
- ANY redesign of `entry`, `R`, or `target_R` semantics — Track 2 is stop placement only; if the work surfaces that target should also flex with structural levels, that's Track 3, separate directive.

---

## What's the bar for picking a candidate

Single test: **does the recommended candidate beat mechanical baseline on YTD compounding P&L AND on per-trade R:R distribution AND on max drawdown?**

If yes on all three → ship it.
If yes on P&L but worse on drawdown → discuss with Manny; may not be worth the risk.
If yes on R:R but worse on P&L → discuss; this is the "fix the math but lose money" outcome and the math fix isn't worth losing money for.
If no on P&L → reject; mechanical stays.

**No candidate is shipped just because it's "more principled." We ship what makes more money or doesn't lose meaningful money while improving robustness.**

---

## Reminder

The fix shipped today catches the move. Track 2 makes catching the move profitable. Both halves matter; neither alone is the win.

GO.
