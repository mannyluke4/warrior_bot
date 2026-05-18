# YTD Honest Re-baseline + VERO/ROLR Re-anchor

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 3:44 PM MDT)
**Status:** GO — research / measurement, no production changes

---

## Why this directive exists

CC's regression inventory (`cowork_reports/2026-05-18_regression_inventory.md`) confirmed that VERO/ROLR canonical targets in CLAUDE.md (`+$34,479` and `+$54,654`) have never been re-verified since 2026-04-15. The 2026-04-14 attempt to re-baseline to "realistic fill" numbers (`+$18,516 / +$6,444`) was reverted three minutes later — Manny's call at the time, correctly: *"Backtesting is for strategy against real data only. We figure fill rate stuff out as they present themselves."*

That decision was right. But we never went back and re-anchored the baseline against the un-modified simulator. Five weeks of code changes (chop-gate v2, dead-bounce, chop-gate v3, framework migration, today's bundled deploy) have landed since. **The "honest" number is whatever the current simulator produces with X01 config against real Jan-May 2026 data.** We don't know what it is.

---

## What's been verified before kicking off

Pre-flight done by Cowork (Mon 3:50 PM MDT):

- **`run_backtest_v2.py` X01 config is bit-identical between commit `13d74d3` (2026-04-08) and HEAD.** Same `RISK_PCT=0.035`, `VOL_MULT=2.5`, `MIN_BAR_VOL=50000`, `MIN_BODY_PCT=2.0`, `PRIME_BARS=4`, `PROBE_SIZE_MULT=0.5`, `MAX_ATTEMPTS=5`, `MAX_LOSS_DOLLARS=500`, `TARGET_R=1.5`, `CORE_PCT=90`, `RUNNER_TRAIL_R=2.5`.
- **`simulate.py` fill model is honest** (`fill_price = entry + self.slippage`, deterministic). The 2026-04-14 fill-realism modifications were reverted cleanly. `entry_pricing.py` does not exist in HEAD.
- **Two seed-stale guards survive in simulate.py** (`c8dfbe5` and the cooldown logic from `c6ea469`) — these are correctness fixes for the seed-replay path, not fill-rate prediction. Their commit messages claim VERO is unchanged with the gates on. Worth re-verifying as part of this run, but they are correct and stay on.
- **Live `.env` is gitignored** and only exists on Manny's machine. CC must verify the live config (squeeze paper bot) matches X01 before drawing live-vs-sim conclusions. **For this directive, the backtest harness uses `run_backtest_v2.py` defaults, which IS X01.**

---

## What CC produces

### Deliverable 1 — VERO + ROLR re-anchor

Run both on HEAD:

```bash
WB_BT_RISK_PCT=0.035 simulate.py VERO 2026-01-16 --tick-cache tick_cache/
WB_BT_RISK_PCT=0.035 simulate.py ROLR 2026-01-14 --tick-cache tick_cache/
```

(CC adjusts the exact invocation to match `run_backtest_v2.py`'s X01 batch — the goal is "X01 config, current code, real tick data.")

Capture for each:
- Trade count, per-trade P&L, total P&L
- Run timestamp, commit SHA
- Wall-clock duration

Compare against the historical citations:
- VERO: `+$18,583` (2026-03-19), `+$15,692` (2026-03-27), `+$34,479` (2026-04-08 X01), `+$35,623` (2026-04-15 autopsy), `+$2,268` (2026-05-18 from A3 control)
- ROLR: `+$6,444` (2026-03-19), `+$54,654` (2026-04-08 X01), `+$50,602` (2026-04-15 autopsy), `+$49,775` (2026-05-18 from A3 control)

Note: A3's control numbers (`+$2,268` and `+$49,775`) used the 07:00–12:00 window. The X01 baseline likely used a wider window. **Use the same window the X01 commit used** to make the comparison fair. If unclear, run both windows and report both.

### Deliverable 2 — YTD compounding-equity run (Jan 02 → today)

This is the headline deliverable. Run the full squeeze backtest battery from **2026-01-02 → 2026-05-18** with:

- **Starting equity:** $30,000
- **Sizing mode:** compounding (each day's PnL flows into next day's equity, which drives `RISK_PCT × equity` sizing)
- **Config:** X01 defaults from `run_backtest_v2.py` (RISK_PCT=0.035, etc.)
- **Universe:** whatever the live squeeze scanner would have produced each day. Use `scanner_results/<date>.json` if available; otherwise note the gap and report what it ran on.
- **Tick data:** `tick_cache/` (real, not synthesized)
- **Daily loss scaling:** match whatever the live `.env` has been using through this period (CC checks live `.env` for `WB_BT_DAILY_LOSS_SCALE`). If unsure, run both ON and OFF and report both.

Output:
- `cowork_reports/2026-05-18_ytd_honest_rebaseline.md` — narrative report
- `cowork_reports/2026-05-18_ytd_honest_rebaseline_per_day.csv` — one row per trading day: date, trades, wins, losses, day_pnl, end_of_day_equity, max_drawdown_to_date
- `cowork_reports/2026-05-18_ytd_honest_rebaseline_trades.csv` — one row per trade

The narrative report covers:
- Headline P&L: starting $30K → ending $X. Total return %, total trades, win rate.
- Equity curve description (peak, trough, current)
- Best and worst weeks
- Comparison against the historical 2026-04-14 reverted re-baseline (`+$120,221 / 36 trades / 97% WR / equity $30K → $150K` was the X01 sim-fill figure pre-realistic-fill; `-$2,641 / 26 trades / 20% WR / $30K → $27,359` was the reverted realistic-fill figure for Jan 02 → Apr 14)
- Honest assessment: does the current code, on current data, produce a positive expectancy?

### Deliverable 3 — Five-week code-change impact

Between 2026-04-15 (last documented VERO/ROLR re-run) and today, CC iterates produced (per memory + commit log):
- Chop-gate v2 + dead-bounce retire
- Chop-gate v3
- Framework migration (signal-parity verified, P&L not measured)
- Today's bundled deploy (qty=1 floor, resume-boot, R-floor, broker-mismatch assert)

CC produces a one-page diff narrative: which of these are likely to have moved VERO/ROLR P&L? Specifically:
- Did chop-gate v3 fire on VERO 2026-01-16 in the new run? On any of the YTD trades?
- Did the R-floor gate filter any historical YTD trades? (We expect it to filter ~6-8 low-R trades based on A3's findings.)
- Did the resume-boot gate fire in any historical session?

This contextualizes the YTD number — telling Manny which gates fired on which trades, so the new baseline is interpretable.

### Deliverable 4 — CLAUDE.md update with provenance

Once Deliverables 1-3 land, CC updates CLAUDE.md:
- Replace the standing VERO/ROLR target lines with verified numbers + `(run YYYY-MM-DD, commit XXXXXXX)` provenance
- Add a YTD section: "X01 config, $30K starting equity, compounding, Jan 02 → 2026-05-18: $X final equity, Y total trades, Z% WR. Source: cowork_reports/2026-05-18_ytd_honest_rebaseline.md"
- Flag memory `project_current_state.md`'s `+$21,024 / +$53,979` as stale and unverified

---

## Hard constraints

- No production code changes from this directive. Pure measurement.
- No modifications to `simulate.py` to "fix" fill rates. Manny's call from 2026-04-14 stands: **backtest is strategy-against-real-data, not fill-rate prediction.**
- Branch: `v2-ibkr-migration`.
- If `tick_cache/` has gaps for any day in the Jan 02 → today range, CC reports the gaps and runs the available days. Don't fabricate or interpolate.
- If `scanner_results/` has gaps, same rule — report and skip.

---

## What NOT to do

CC should NOT:
- Re-introduce `entry_pricing.py` or any stale-arm re-pricing logic in simulate.py
- Modify the simulator's fill model (deterministic `entry + slippage` is correct by directive)
- Re-anchor against the realistic-fill reverted numbers (`-$2,641 YTD, +$18,516 VERO`) — those came from a hypothesis that was rejected
- Re-baseline by cherry-picking a "favorable" config — X01 is the standing config because it's what was promoted to canonical on 2026-04-08

---

## Reporting

When all four deliverables land, CC posts a synthesis paragraph in chat with:
- VERO X01 P&L on HEAD (vs the +$34,479 standing target)
- ROLR X01 P&L on HEAD (vs +$54,654)
- YTD final equity (vs $30K starting)
- Whether the new baseline is materially different from the standing CLAUDE.md numbers (drift > 10%? Recommend update.)
- Cowork synthesizes for Manny.

---

## Reminder

Manny: *"Backtesting is for strategy against real data only. We figure fill rate stuff out as they present themselves, like today."*

This directive measures strategy against real data. SBFM-style fill issues are live problems we patch as they appear (and just did, via today's bundled deploy). The simulator stays honest on its own terms.

GO.
