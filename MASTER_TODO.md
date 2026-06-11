# Warrior Bot — Master Task Tracker
## Last Updated: 2026-06-08 (Cowork session — main bot rebuild directive, sub-bots → discovery research)

This document tracks ALL open work items across every strategy and system. Updated by Cowork after each session. Lives in the repo so nothing gets lost.

---

## 🔥 ACTIVE STACK — as of 2026-06-08

### 🎯 STRATEGIC REDIRECT — Main bot REBUILD (not retirement) for 6/22 real-money

CC's `cowork_reports/2026-06-08_win_loss_tuning_analysis.md` (commit `a118657`) marked the main bot squeeze strategy for retirement (1 net-positive day in 16 sessions, −$7,954 since 5/15). **Manny's call: don't retire — rebuild.** Sub-bots A/B/C remain as continuous discovery research; main bot becomes the production line that absorbs sub-bot findings.

**Rebuild directive**: `cowork_reports/2026-06-08_main_bot_rebuild_directive.md` — in-place refactor of `bot_v3_hybrid.py` replacing squeeze stack with sub-bot strategy stack (MovementStrike + RegimeShiftDetector + FIRESTORM-gate from A + REENTRY-loss-gate from C + Track A exits from B + discovery G1 gate). Keeps main bot's IBKR data feed, engine publisher, AvailableFunds sizing, IBKR execution path. 6 phases (R1-R6) across 8 trading days. Paper-validated by 6/19; **6/22 real-money flip firm if R5 acceptance criteria pass at 6/17 review**.

### 🏆 A/B/C CONDITIONAL GO-LIVE — CLEARED (Day 11 cumulative)

Per Manny's earlier conditional (leading variant ≥ +$1,500 cumulative by 6/15):
- **A (FIRESTORM-gate): +$5,507** — well above threshold; leading variant
- C (REENTRY-loss-gate): +$1,787 — also above threshold
- B (FIRESTORM + Track A): −$2,153 (legacy V1 VWAP burden); +$770 since 6/02 swap

Sub-bots stay running through 6/22 and beyond. Their role: continuous discovery research, daily comparison, failure-mode lookout for the rebuilt main bot.

### 🔬 Today's SUNE case study — the load-bearing insight

SUNE ran $3 → $9.10 (+200%). Three configs handled it differently:
- A (FIRESTORM only): +$786 — defense plus some continuation
- B (FIRESTORM + Track A): +$818 — exit improvements helped
- **C (REENTRY-loss-gate): +$1,043** — best of the three; less restrictive on re-entries → captured more continuation
- Main bot (squeeze): −$123 (scratched out at $3.06 via bearish_engulfing, never re-entered)

**Synthesis from CC's report**: gating gets to scratch; only continuation-capture creates edge. C's REENTRY mechanism is the offensive complement to A's FIRESTORM defense. The rebuild combines both.

### 🛠️ Shipped today (commits)
- `d4c286a` — main bot squeeze retiring official (superseded by rebuild)
- `a118657` — win/loss tuning analysis report
- `588f80d` — discovery-time entry G1 gate (observe-only, accumulating data)
- `3593131` — wall-clock EOD flatten + shutdown backstop (no overnight holds)

### 📋 Open Cowork follow-ups

1. Watch G1 observe-only data through week — evaluate enforce-or-not at 6/15
2. Monitor sub-bot performance during rebuild — surface any divergences
3. 6/17 acceptance review: main_bot_v2 paper validation 6-criterion check
4. Position sizing chart already in place (`position_sizing_chart.md`) — confirms $10k base entry, scaling to $100k by $1M equity via √(equity) × $100

---

## 📦 ARCHIVED ACTIVE STACK — as of 2026-05-26

**Real-money deadline: ~2026-06-22** (unchanged). A/B/C test launches Monday 5/27 per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

### 🎯 LIVE FLIP TONIGHT (2026-05-28 evening) — Track A exit framework for regime_shift

CC's `cowork_reports/2026-05-28_track_a_results.md` (commit `f0dfaee`) passed all 5 acceptance criteria. Combined YTD improvement: **+$106,842** (3.5× threshold). Per-strategy:
- **firestorm_trigger**: 47.7% → 69.6% WR, +$73,630 recovery
- **regime_shift** (the live strategy): 43.6% → 56.2% WR, +$29,262 recovery, **every month improves** (March/May flip positive)
- POLA and LRHC class trades blocked entirely by R floor; AMSS-class hold-to-stop trades catch at drawdown floor instead

**Phase 4b live flip directive**: `cowork_reports/2026-05-28_phase4b_track_a_live_flip_directive.md` — tonight before 02:00 MT cron. Single env var flip in `daily_run_v3.sh` (`WB_EXIT_TRACK_A_ENABLED=1`). FT stays gated off (`WB_FIRESTORM_TRIGGER_ENABLED=0` unchanged) — only regime_shift gets the upgrade this week. A/B/C variant comparison continues (Track A is exit-framework-neutral; applies identically to A/B/C's regime_shift trades). Discontinuity flagged in running totals JSON via new `track_a_enabled` field.

**FT live flip target: 2026-06-04** after one week of regime_shift Track A live validation. Phase 4c directive (Cowork to draft 6/05 after weekly review).

**Today's research journey**: Phase 1 (anatomy) → Phase 2 (missed firestorm signal: 142 missed pairs, P75 33% subsequent move) → Phase 3 Stage 1 (FT prototype validated entry, exits failed -$108K) → Stage 1.5 (sweep proved B+C compound) → Track A (productized, all 5 criteria pass).

**What Track A does NOT solve**: even at +$106K improvement, sim shows -$50K all-strategy YTD residual. Phase 2's long-only ceiling intact. Closing the gap likely needs bidirectional support (Phase 5 / separate engineering directive) or selective gap-and-direction filtering. Track A makes exits stop catastrophically losing; doesn't make the strategy net-profitable in sim.

### 🚨 NEW (2026-05-27 PM) — Sub-bot backtest harness drift discovery

CC's `cowork_reports/2026-05-27_subbot_vs_sim_audit.md` (commit `ee1496b`) revealed that sim (`simulate.py`) and live sub-bot (`move_strike_subbot.py`) are two parallel implementations with three load-bearing drifts:

1. **regime_shift threshold default mismatch**: sim 3.0 vs live 4.0 → sim has been firing regime_shift on weaker signals than live ever would
2. **Exit-decision fallthrough**: sim routes MOVE_STRIKE/REGIME_SHIFT trades through _hwm_exit then FALLS THROUGH to squeeze tick exits (topping_wicky, BE/TW patterns) that live sub-bot doesn't have. Proof: yesterday's ASTC sim exit at $7.85 via topping_wicky for +$262 vs live regime_shift hold to $10.00 for +$1,165.
3. **Universe source**: replay_live_universe.py reads main bot's narrow tracked symbols (4-10) instead of sub-bot's full engine-socket fanout (112 symbols today)

**Implication**: every prior YTD backtest result is invalidated. The **YTD -$17,897 verdict that drove us to live A/B/C was on the wrong code path** — should be re-cited as "YTD result on broken sim harness; re-run pending after harness rebuild." Three strategic re-frames across two days (yesterday: orphan bug + Tier-2 wedge; today: sim drift): we've never had a reliable picture of strategy economics on the backtest side either.

**Phase 3b validation update (2026-05-27 PM, commit `66d6878`)**: harness rebuild Phase 1+2 shipped + validated. AMSS regime_shift matches live exactly (proves decision logic is right). But Variant B regressed catastrophically (-205% delta) — bar-construction divergence cascades into fade-gate evaluating at different price than live saw. 1 of 3 variants passes acceptance criteria. PROBE_SIZE_MULT discovered to be 0.5 in live (sim defaulted to 1.0) → every prior backtest's P&L was overstated by 2×.

**Active directives** (sequenced after Phase 3b):
1. `cowork_reports/2026-05-27_phase3c_bar_construction_investigation_directive.md` — Path A Option 1 cheap investigation. Instrument live's bar callback with bar-stream log, replay one day side-by-side with sim's bars, find divergence point. ~3 hours CC effort. Output: classify divergence as fixable bug OR fundamental timing-edge-case requiring Path A Option 3 (bar-stream recording, ~1-2 day commitment).
2. `cowork_reports/2026-05-27_reentry_hwm_gate_live_directive.md` — Test REENTRY-HWM-gate live by re-purposing Variant C (sacrifices V4 BodyCV evaluation since it had zero effect today). A/B/C clock resets to Day 1 from change ship date. Pairwise variant comparison: A (control) vs C (REENTRY-HWM-gate) isolates gate effect; B (V1 VWAP) vs A isolates fade-gate effect. ~1-2 hours CC effort. **SUPERSEDED 2026-05-27 PM by broadening directive below** — narrow HWM scope misses regime_shift_hard_stop cases.

3. `cowork_reports/2026-05-27_reentry_loss_gate_broaden_directive.md` — **HOT-FIX, must land before 2026-05-28 02:00 MT cron.** AMSS audit (commit `15ba0e7`) showed today's morning gate is too narrow — the 15:16 REENTRY GREEN disaster came after `regime_shift_hard_stop`, not `move_hwm_exit*`. Broadens scope to ALL loss-class prior exits (move_hwm_exit*, move_stop_prox_bail, move_hard_stop, regime_shift_hard_stop). Renames env var + log line. Variant C identity preserved, no A/B/C clock reset. ~1 hour CC effort.

### 🚨 NEW (2026-05-27 PM) — AMSS audit findings

CC's `cowork_reports/2026-05-27_amss_regime_long_hold_audit.md` (commit `15ba0e7`) dissected today's $1,649 AMSS loss across Variant A. Three structural findings:

1. **regime_shift baseline_min too low**: $0.02 default. Consolidation phases collapse baseline → high ratio gate becomes meaningless on any directional bar. Today's 13:32 false-trigger fired on baseline=$0.07 (1.2% of price). **Deferred until Phase 3c data confirms whether the 13:31 trigger bar was real in live or a tick-cache reconstruction artifact.**
2. **No drawdown exit pre-partial for regime_shift**: `move_strike_subbot.py:891` `return  # no trail pre-partial`. Position held 1h 42m waiting for target/stop. **Deferred to separate directive after Phase 3c data lands.**
3. **REENTRY-HWM-gate scope too narrow**: today's miss after `regime_shift_hard_stop`. **Shipped tonight via broadening directive (item 3 above).**

**Phase 4 refactor (extract sub_bot_core.py)**: blocked until harness validates per CC's recommendation. Two implementations side-by-side until then — drift risk requires discipline.

**REENTRY GREEN backtest status**: results from earlier today came from the broken harness, invalidated. Hypothesis remains based on n=2 live A/B/C observations. Now tested live via REENTRY-HWM-gate directive above. Re-run on harness after Phase 3c (and Path A Option 3 if needed) closes.

### 🚨 NEW (2026-05-26 PM) — Orphan position bug (sub-bot AND main bot)

Today's A/B/C launch surfaced a real code bug at `move_strike_subbot.py:1224-1282` `_close_position()`: when `_wait_for_fill` times out / returns partial, the bot unconditionally sets `self.position = None` and computes "approx P&L" on `ref_price` — broker keeps the shares, bot pretends it sold them. 5 orphan positions across A/B/C today, ~$44K of net-long exposure on Variant C before Manny's manual flatten. CC audit: `cowork_reports/2026-05-26_sub_bot_orphan_audit.md` (commit `84a56a0`).

**Same bug class in main bot:** `bot_v3_hybrid.py:740-779` (WB exit) and `bot_v3_hybrid.py:3873-3923` (squeeze exit, structurally worse — clears `state.open_position` optimistically before async `verify_exit_fill` confirms). Now relevant for main bot since commit `2be7efe` moved it to IBKR paper.

**Bot's reported P&L is systematically wrong on volatile days.** Today's variants — bot vs broker truth:
- A: -$1,549 reported vs **+$419 broker** (bot under-reported a profitable variant)
- B: -$2,904 vs -$2,614 (close, B's MNTS held alive correctly)
- C: -$1,762 vs -$2,884 (bot over-reported a loss)

The variant comparison was silently corrupted on Day 1. **Hopeful read**: live operating numbers we've been monitoring for weeks have been bug-corrupted in a non-uniform direction — the YTD backtest (-$17,897) is sim-only and bug-free, but our prior on live strategy economics may improve significantly post-fix.

**Active directive**: `cowork_reports/2026-05-26_sub_bot_orphan_fix_directive.md` — All 3 levers (L1 don't-lie + L2 cancel-replace + L3 periodic reconcile), sub-bot + main bot. Target: Lever 1 ships before tonight's downtime ends so daily_run_v3.sh launches normally at 02:00 MT. Sub-bots held OFF if Lever 1 not in by cron. Main bot continues on IBKR paper either way.

**Today's data treatment**: log broker reconstruction in today's daily report with explicit "DATA CORRUPTED BY ORPHAN BUG" banner, exclude from variant comparison math. Tomorrow becomes effective Day 1 of A/B/C.

### 🚨 NEW TODAY AM (2026-05-26) — IBKR Tier-2 subscription wedge

MNTS ran $7.38 → $15.47 (+110%) today while the bot's `reqMktData` stream delivered ~25 ticks/hour instead of the real ~130K shares/min. Manny made $7k swinging the same name manually. CC audit: `cowork_reports/2026-05-26_ibkr_tier2_subscription_wedge_audit.md` (commit `ce00dd1`). Root cause unproven; 4 hypotheses still live (chronic Tier-2 throttling, IBKR rate-limit downgrade, pre-market half-bootstrap, contract-qualification race). Memory note `project_tick_cache_persistence_gap` (2026-04-16 MYSE event) suggests this is a recurring low-grade bug.

**Implication for A/B/C**: variants all drink from the same engine-socket fanout → comparison is still apples-to-apples even with wedged upstream, but absolute numbers (including the YTD backtest that drove us to A/B/C) become suspect. Hopeful read: strategy might be fine and we've been backtesting against degraded data the whole time.

**Active directive**: `cowork_reports/2026-05-26_subscription_watchdog_directive.md` — ship observability-only watchdog (dual signal: zero-cost heuristic always-on + targeted `reqHistoricalData` verification on top-5 movers/suspects). Audit signal feeds A/B/C daily report. Auto-resubscribe stays OFF until 1-2 days of data inform structural fix. Ship Monday 5/27.

**Tomorrow AM (2026-05-27)**: CC live-monitors during pre-market through first squeeze window. Protocol in directive §"Tomorrow morning ... CC live-monitor protocol".

### Driver context for go-live

YTD backtest revealed strategy is net-negative across 5 months despite Set B's +$3,411 / 10-day positivity. Live A/B/C test on 3 Alpaca paper accounts will settle whether May's positivity is real or variance. Directive: `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`. **Watchdog data quality lens added 2026-05-26 may reframe this entirely** — if MNTS-class wedges turn out to be routine, the YTD result is partly a data artifact, not a strategy failure.

### ✅ SHIPPED 2026-05-22 — commit b4b0b73
Directive: `cowork_reports/2026-05-22_p0_go_live_stack_directive.md`

1. ✅ **Wire `compute_alpaca_aware_limit()`** — main bot calls at 749/3192/4653; sub-bot's own copy called at 714/776. `WB_ALPACA_AWARE_LIMITS=1` in `.env`.
2. ✅ **Sub-bot daily_pnl from actual Alpaca fills** — `SubPosition.fill_entry_price/qty` + `_wait_for_fill()` at 221; logged as `real`/`approx`.
3. ✅ **Sub-bot tick cache seeding** — gated by `WB_SUBBOT_SEED_FROM_CACHE=1`, replays `tick_cache/<today>/<sym>.json.gz` on first symbol encounter.

CC follow-up to Phase 1 parity matrix: `cowork_reports/2026-05-22_cc_followup_to_parity_matrix.md` — surfaces a 6-hour MTVA arm-state silence (04:21→10:28) on 5/22 that sim doesn't reproduce. Leading hypothesis: dropped engine-socket ticks (no `engine_seq` validation). Cowork verified the detector-version-mismatch CC initially raised is NOT real — `.env:377` has `WB_SQUEEZE_VERSION=2` and `simulate.py:30,43` calls `load_dotenv()`.

### Next stack (CC, in order)
1. ✅ **Sub-bot chase-skip arm preservation** — shipped in `1c3ce24`. `move_strike_subbot.py:648 + :662` no longer destroy `det.armed`. Root cause of MTVA 6-hour arm gap and likely a chunk of broader sim/live trade-count divergence. Evidence: `cowork_reports/2026-05-22_mtva_arm_gap_root_cause.md`.
2. ✅ **Re-baseline the 10-day sample** — shipped in `71e4d61`. Result: **+$2,489**. Reframed: bug was sub-bot-only, sim was always correct. The $9 vs cited +$2,498 is from the below-arm 3% filter (`b034a10`), not the chase-skip fix. The fix's actual value will show up on the live side starting Monday. Report: `cowork_reports/2026-05-22_post_fix_10d_baseline.md`.
3. **X01 exits research — closed, all directions killed**:
   - ❌ Direction A killed (`c038c1f`) — bail_timer variants destroyed 10d
   - ❌ Direction B killed (`2887de3`) — Pareto-positive but failed binary PCLA criterion; tight HWM exits push cool-down past the rip
   - ❌ Cool-down variants killed — all 3 fail (`1d4cdd7`). Discovered HWM trail STRUCTURALLY cannot capture vertical-class moves regardless of entry timing
   - **Strategic reframe**: trying to make one exit framework serve two trade patterns (quick movers + vertical explosions) was the wrong shape. Two strategies, not one.

4. **REGIME-SHIFT strategy** — sim Stage 1 shipped (`36ca73d`). Results:
   - Set B (10-day): **+$3,411 vs +$2,489 baseline = +$922** ✅
   - Set A (31 vertical days): −$2,384 total, BUT regime-shift contributed +$6,660 across 9 fires (~$740/fire). The loss is MOVE_STRIKE chain-of-doom on volatile days where regime-shift didn't fire.
   - **Decision**: ship gated ON for Monday cron. Stage 2 directive: `cowork_reports/2026-05-22_regime_shift_stage2_directive.md` — port to sub-bot + enable in `daily_run_v3.sh`.

5. **MOVE_STRIKE fade-environment gate** — Stage 1 surfaced a previously-hidden disaster mode: AVX 2025-09-22 took 19 trades for −$6,268 on a volatile day. Pattern: stock spikes early, fades for hours, MOVE_STRIKE keeps arming + losing. Research at `cowork_reports/2026-05-23_movestrike_fade_gate_directive.md` identified clean discrimination on close_pos_in_range (catch days 0.66-0.99 vs disaster 0.11-0.33) and peak_pct_of_day (catch 0.87-1.0 vs disaster 0.18-0.63). Directive tests 4 real-time signals (VWAP, drawdown-from-open, downtrend, body CV) and combos to gate MOVE_STRIKE entries during fade conditions. ~~Per-symbol cap directive~~ — superseded by this, do not implement.
4. ✅ **Engine_seq tick-drop audit Items 1+2** — shipped in `d171958`. Item 3 (analyze logs after a paper session) becomes a Cowork task once Monday's data lands.

### ✅ SHIPPED 2026-05-22 PM — watchdog freeze fix (`a8a95ec`)
Root cause: `bot_v3_hybrid.py:1585-1589` ran sync IBKR `cancelMktData` + 2s sleep + `reqMktData` per symbol drought on the main thread. 3 freezes today all preceded by TICK DROUGHT resubscribes. Fix: background worker thread with 20s timeout-guarded IBKR calls. Main thread now non-blocking. Validation: Monday's session should show zero `💀 WATCHDOG: main thread frozen` events. Directive: `cowork_reports/2026-05-22_watchdog_freeze_directive.md`.

### P1 — needs scoping before go-live
- **Tick cache EOD truncation** — task #25 per directive. PCLA 5/21 was the catastrophic case.
- **Dead-symbol pruning** — `cowork_reports/2026-05-22_over_subscription_audit.md`. 158 symbols subscribed today, 5 ever armed, 1 traded. 3,039 TICK DROUGHT events (top 10 symbols accounted for 2,018 of them). `bot_v3_hybrid.py:2078` explicitly says "We NEVER unsubscribe symbols during a session." Not blocking 6/04 (watchdog fix made symptom non-fatal), but worth adding a prune pass for load/quality. Suggested heuristic in the audit report.

### Cowork-side follow-ups (parking, not blocking 6/04)
- **Parity audit Phase 2-4** — baseline recalibration of the +$2,498 11-day sample using realistic fill assumptions; prioritized fix list; continuous parity monitoring design. Source: `cowork_reports/2026-05-22_sim_live_parity_audit_directive.md`. Phase 1 complete: `cowork_reports/2026-05-22_sim_live_parity_matrix.md`.

### Pacing
**Paper account is the test.** No "let it bake for N days" gates. Ship → observe in tomorrow's session → fix what breaks.

---

## 🟢 COMPLETED — Jan 2025 Missed Stocks Backtest

**Result: Scanner is confirmed as the #1 bottleneck.** If the scanner had found all of Ross's January stocks, the bot would have made **+$42,818** vs ~$5,543 actual — a **7.7x multiplier**.

Key findings: 88% stock-level profitability, SQ is the only strategy that fires, 18-22% capture rate on Ross's P&L, bot beats Ross on all 3 of his losses. 10 tickers had no Databento data (likely OTC). 6 had data but 0 trades (large float, MACD gate, no ARM).

**Report:** `cowork_reports/2025-01_missed_stocks_backtest_results.md`

---

## 🟢 COMPLETED — Ross Exit V3 CUC Fix

CC implemented both CUC gates and ran the 4-config YTD comparison. **Result: CUC tuning alone cannot close the gap.** Best config (MinBars=5) improved V2 by +$2,049 but still -$8,750 vs baseline. The sq_target_hit architecture issue dominates (-$12,832).

**Code changes (merged):** `WB_ROSS_CUC_FLOOR_R` and `WB_ROSS_CUC_MIN_TRADE_BARS` in ross_exit.py
**Report:** `cowork_reports/2026-03-23_v3_cuc_comparison.md`
**Decision:** Phase 2 signal-at-level partials deferred. Focus shifts to scanner coverage (missed stocks backtest).

---

## 🔴 #1 PRIORITY — Scanner Coverage Improvement

The January 2025 missed stocks backtest proved the scanner is the highest-leverage fix. The bot found 7.4% of Ross's tickers (5/68) and left ~$37K on the table in one month. The bot IS profitable on these stocks — it just never sees them.

**Root causes of scanner misses (29 missed opportunities, Jan 2025):**

| Category | Count | % | Fix Approach |
|----------|-------|---|-------------|
| Scanner never found stock | 13 | 45% | Broader criteria, continuous rescan, news feed |
| Found but bot didn't trade | 5 | 17% | Already mostly fixed by SQ V2 (post-Jan addition) |
| Found AND traded (exit gap) | 3 | 10% | Ross exit refinement (in progress) |
| Sympathy/thematic plays | 3 | 10% | Sector momentum tracking (hard to automate) |
| Mid-morning discovery | 2 | 7% | Continuous intraday rescan |
| Unknown float (no float data) | 2 | 7% | Float data fallback / allow unknown-float with gates |
| Scanner timing (pre-7:15 move) | 1 | 3% | Earlier first scan or streaming mode |

**Scanner Gap Analysis COMPLETED (2026-03-23):**
Per-stock analysis of every profitable missed stock. 5 root cause categories: float too high (4 stocks, +$1,379), unknown float (4 stocks, +$12,178), not in data universe (10 stocks, no data), failed scanner gates (13 stocks, +$13,445), structural (3 stocks, $0).
**Report:** `cowork_reports/2026-03-23_scanner_gap_analysis.md`

**Phase 1 tasks (scanner architecture):**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Analyze WHY 13 stocks weren't found | **COMPLETED** | **P0** | Report: `cowork_reports/2026-03-23_scanner_gap_analysis.md` |
| Enable unknown-float stock trading | **COMPLETED** | **P0** | Done 2026-03-23. WB_ALLOW_UNKNOWN_FLOAT=1 in .env; gate logic in run_ytd_v2_backtest.py |
| Fix continuous rescan (0 finds in Jan) | **✅ COMPLETED** | **P0** | Commit `6a91afe`. Cumulative 4AM→checkpoint volume, RVOL inline calc, gap 5% for RVOL≥10x. |
| Rename "unknown-float" terminology (was "Profile X") | **COMPLETED** | **P0** | Done 2026-03-23. All Python files, .env, docs updated. |
| Research: alt data feeds + float sources | **✅ COMPLETED** | **P1** | Perplexity deep dive done 2026-03-23. See findings below. |
| Add SEC EDGAR as Tier 5 float fallback | **✅ COMPLETED** | **P1** | Commit `6a91afe`. In both live_scanner.py and scanner_sim.py. CIK map + XBRL API. |
| Add float cache invalidation (clear stale Nones) | **✅ COMPLETED** | **P1** | Commit `6a91afe`. Clears None entries on load, forces re-lookup through full chain. |
| Add Alpha Vantage free tier as Tier 6 float | **✅ COMPLETED** | **P2** | Commit `6a91afe`. `WB_ALPHA_VANTAGE_API_KEY` env var (empty = disabled). 25 calls/day. |
| **Jan 2025 vs Jan 2026 comparison** | **DIRECTIVE WRITTEN** | **P0** | `DIRECTIVE_JAN_COMPARISON_V1.md`. Re-run scanner_sim for Jan 2025 with fixes, then backtest both months side-by-side. Validates all scanner + exit changes. |
| OTC coverage (Polygon + IBKR) | **DEFERRED** | **P3** | Polygon $199/mo + IBKR $18/mo. Manny declined for now. Would cover ~10 missing OTC tickers. Revisit after free-tier improvements are maximized. |
| News feed integration (catalyst detection) | **NOT STARTED** | **P2** | Ross's edge: news at 7:00 AM → scanner alert. Bot: gap-only |
| Sector/sympathy tracking | **NOT STARTED** | **P3** | EVAC (GLP-1 sympathy), BTCT (crypto theme) — hard to automate |

**Perplexity Research Findings (2026-03-23):**
- **Trade Ideas**: No programmatic API — browser-only. Not viable.
- **IEX Cloud**: Permanently shut down Aug 2024.
- **Polygon.io**: $199/mo covers OTC + real-time. Best option for OTC but cost deferred.
- **SEC EDGAR**: Free XBRL API, 10 req/s, `EntityCommonStockSharesOutstanding`. Covers ~80% of unknown-float failures. **ADOPTED → Item 4.**
- **Alpha Vantage**: Free tier 25 calls/day, has true `SharesFloat` field. **ADOPTED → Item 6.**
- **Float cache invalidation**: Clearing stale None entries prevents permanent lookup failures. **ADOPTED → Item 5.**
- **OTC stocks**: ~28% of Jan 2025 misses are OTC/pink sheet. Would need Polygon + IBKR ($217/mo). **DEFERRED** — Manny declined.
- **Alpaca cannot trade OTC stocks.** Databento EQUS.MINI = NMS only. Both are structural limitations.
- **Report:** `scanner_deep_dive_report.md` (Perplexity output)

**Free-tier recovery model:** Unknown-float gate ($8,035, done) + SEC EDGAR ($4,143 est) + rescan fix ($3-5K est) + cache invalidation (prevents future misses) = **+$15-17K/month potential** at zero additional cost.

**Key evidence:**
- `cowork_reports/2026-03-23_scanner_gap_analysis.md` — per-stock rejection analysis + recommendations
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — full backtest results
- `cowork_reports/missed_stocks_backtest_plan.md` — per-stock miss analysis
- `cowork_reports/ross_vs_bot_jan_2025.md` — January comparison summary
- `scanner_deep_dive_report.md` — Perplexity data feed + float source research

---

## 🔴 #2 PRIORITY — Execution Gap: Scaling & Multi-Leg Extraction

**The Problem:** On EEIQ (March 26), Ross made $37,860 while the bot's best-case estimate is $1,500–$3,000 — a **12–25x gap** on the same stock, same day. The bot correctly identified the stock (Profile A, 158% gap, 29.5x RVOL, sub-1M float) but can only capture ~5–8% of what a skilled discretionary trader extracts from a big runner.

**Root Cause:** Single-entry, single-exit architecture vs Ross's multi-leg, scaling, cushion-based approach. Ross made 5+ entries across $5.95–$8.80, pressing to 30K shares on conviction. The bot takes 1 entry at fixed risk and rides to 2R target.

**Report:** `cowork_reports/2026-03-27_eeiq_ross_vs_bot_comparison.md`

| Task | Status | Priority | Est. Impact | Notes |
|------|--------|----------|-------------|-------|
| **Scaling in/out** | **NOT STARTED** | **P0** | **3–5x per-trade P&L** | Initial entry at probe size (50%), confirmation add at +0.5R held 2 bars, strength add on new level break. Requires multi-position tracking per symbol. Single biggest multiplier. |
| **Post-halt re-entry** | **NOT STARTED** | **P1** | **2–3x on halt stocks** | On halt resume, if price dips then reclaims pre-halt high within 3 bars, enter fresh. Pre-halt level as stop. Already tracking halts (ONCO halt/resume working 2026-03-27). |
| **Continuation pattern detection** | **NOT STARTED** | **P1** | **2x additional legs** | Inverted H&S, VWAP reclaim, curls — exactly the patterns Ross used for his $24K EEIQ trade. See Strategy 4 and 5 sections below. |
| **Dynamic session risk sizing** | **NOT STARTED** | **P2** | **1.5–2x on conviction** | When bot is up $X on the day, allow larger position size on high-conviction setups. Ross's "cushion press" turned $4.5K scalp into $37K day. |

**Realistic ceiling with all improvements:** ~$8K–$15K on a stock like EEIQ (~40% of Ross). Remaining gap is discretionary judgment that's extremely hard to automate.

---

## 🟢 RESOLVED — V3 Hybrid Bot Live (Replaces V2 IBKR-only)

**V2 pure-IBKR bot never took a trade** in 8 live sessions (March 25 → April 1). Root cause: PRIMED→ARMED gap — volume explosion and level break happen on the SAME bar on fast movers, but V1/V2 require them on SEPARATE bars.

**Solution: V3 Hybrid** (`bot_v3_hybrid.py`, 1576 lines) — IBKR for data (scanner, ticks, RTVolume) + Alpaca for execution (orders, paper account). First live session April 2: 0 trades (correct outcome, 100% backtest match), infrastructure stable 6 hours.

**V1 phantom position bug also fixed:** VOR April 1 had cancel-replace race condition. V3 has: startup position reconciliation, fill verification (no cancel-replace), 60s heartbeat sync, exit verification with market fallback, graceful shutdown check.

### Remaining Infrastructure Issues

| Issue | Status | Notes |
|-------|--------|-------|
| Mac Mini pmset sleep prevention | **NOT APPLIED** | `sudo pmset -a sleep 0 displaysleep 0` + `caffeinate -dims`. Cron 4 AM fails daily. |
| Scanner-move paradox | **KNOWN LIMITATION** | Volume spike that creates opportunity = spike that triggers scanner discovery. Accept catching 2nd move. |
| IBKR STK.US.MAJOR misses micro-caps | **KNOWN** | Databento bridge helps (KIDZ found via watchlist.txt) |

### Session-resume follow-ups (v2 — v1 shipped 2026-04-15)

Session-resume v1 is live (gated OFF by default via `WB_SESSION_RESUME_ENABLED`). v2 items deferred from the first ship:

| Item | Why deferred | Notes |
|------|-------------|-------|
| Box strategy state persistence | Box engine has complex state (box_bottom/top, trades, RSI/VWAP cache). v1 flattens any open box position as orphan on resume. | Directive: persist `state.box_engine` fields + `state.box_position` to a `box_state.json`, rehydrate mirror of momentum path. Touches `_exit_box_trade`, `_enter_box_trade`, `box_bar_builder_1m`. |
| OCO/bracket protection | Separate architectural shift, not bundled into session-resume. | Today's exits are reactive (`manage_exit` → `exit_trade`). OCO would make each entry a bracket order + trail-update via order modification. Removes the "crash reopens naked position briefly" window. |
| EPL state round-trip validation | v1 loads best-effort, warns on failure. | Manually confirm graduation state survives resume once EPL sees meaningful use again. |

**Reports:** `cowork_reports/2026-04-02_morning_progress.md`, `cowork_reports/2026-04-01_v1_investigation.md`

---

## 🟢 COMPLETED — Live Bot Migration to V3 Hybrid

Mac Mini now runs `bot_v3_hybrid.py` via `daily_run_v3.sh`. V1 Alpaca websocket issues and V2 zero-trade problem both resolved by V3 architecture. Cron at 4 AM MT (2 AM was old schedule).

**Remaining:** pmset sleep prevention not yet applied — Gateway requires active display session. Manual startup still needed daily.

---

## 🟡 Scanner Alignment (Mostly Complete)

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Phase 1-4: Scanner code alignment | **✅ DONE** | CC | Commit `e9cbb88` |
| Phase 5: Validate with new data | **✅ DONE** | CC | YTD runner uses aligned scanner |
| Connect `live_scanner.py` to `daily_run.sh` | **NOT STARTED** | CC MM | Blocked by Databento cost verification |
| Verify Databento streaming costs | **NOT STARTED** | Manny | Usage-based pricing |
| Faster rescan for news-driven movers | **NOT STARTED** | HIGH | CHNR 44 min late |

---

## 🔴 Strategy 1: Micro Pullback — REDESIGNED as Post-Squeeze Re-Entry (MP V2)

### Standalone MP: SCRAPPED (-$8,066 over 15 months, 24% WR)
- `WB_MP_ENABLED=0` — keep OFF permanently
- 34 max_loss_hit trades at 0% WR (-$19,122) — entries during pre-squeeze noise
- Big MP winners (AIFF, LSE, ROLR) were all squeeze stocks — SQ catches them better
- March 27: SQ-only=$0, SQ+MP=-$2,499. MP turns quiet days into losses.
- **Report:** `cowork_reports/2026-03-27_mp_deep_dive.md`

### MP V2: Post-Squeeze Re-Entry — IMPLEMENTED + SQ-PRIORITY GATE DONE
Redesign MP as a re-entry module that only activates AFTER the squeeze detector has confirmed a stock is a legitimate mover. Core implementation (7c9d302) + SQ-priority gate fix (a474005) both done.

**Design Doc:** `STRATEGY_MP_V2_REENTRY_DESIGN.md`
**Implementation Commits:** 7c9d302 (core MP V2), a474005 (SQ-priority gate + per-re-entry cooldown)
**Directive:** `DIRECTIVE_MP_V2_SQ_PRIORITY_GATE.md`

**Key design decisions:**
1. MP stays DORMANT until SQ fires a trade on the symbol (win or loss)
2. 3-bar cooldown after SQ exit before MP starts looking
3. Skip impulse detection (squeeze WAS the impulse) — go straight to pullback monitoring
4. MACD gate relaxed (bearish MACD during post-squeeze pullback is the dip we want to buy)
5. Exits via SQ V1 mechanical system (not MP 10s bar exits)
6. Up to 3 re-entries per symbol per session
7. Probe sizing (50%) on first re-entry, full size on confirmation adds
8. SQ has unconditional priority — MP V2 defers when SQ is PRIMED/ARMED/in-trade (DONE)

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| ~~Implement MP V2 DORMANT/COOLDOWN/ACTIVE state machine~~ | **DONE** | **P0** | Commit 7c9d302 |
| ~~Route MP V2 trades through SQ exit system~~ | **DONE** | **P0** | `setup_type="mp_reentry"` routes to SQ V1 exits |
| ~~Add SQ-priority gate~~ | **DONE** | **P0** | Commit a474005. MP V2 defers when `sq_det._state != "IDLE"` |
| ~~Add per-re-entry cooldown~~ | **DONE** | **P0** | `notify_reentry_closed()` method in commit a474005 |
| **Validate: VERO holds at +$15,692 with V2 ON** | **NOT STARTED** | **P0** | Baseline shifted from +$18,583 due to system-wide optimization (portfolio +$5.5K→+$19.8K). +$15,692 is the correct current target. |
| **Validate: EEIQ shows MP V2 value-add** | **NOT STARTED** | **P0** | SQ-only vs SQ+V2 on EEIQ 2026-03-26. Proof that re-entries capture extra legs |
| **Full YTD backtest (SQ + MP V2)** | **NOT STARTED** | **P1** | 15-month IBKR dataset. Key check: 0 trades on days where SQ didn't fire |
| **Live paper observation (1 week)** | **NOT STARTED** | **P2** | Deploy alongside SQ, monitor for P&L add vs drag |

### Prior MP Fixes (Historical — Applied to Standalone MP, May Carry Over)
- [x] Fix 1: Direction-aware continuation hold (+$317) — `WB_CONT_HOLD_DIRECTION_CHECK=1`
- [x] Fix 2: Float-tiered max loss cap (+$937) — `WB_MAX_LOSS_R_TIERED=1`
- [x] Fix 3: max_loss_hit triggers cooldown (+$916) — `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1`
- [x] Fix 4: No re-entry after loss (+$1,315) — `WB_NO_REENTRY_ENABLED=1`
- [x] Fix 5: TW profit gate at 1.5R (+$12,619) — `WB_TW_MIN_PROFIT_R=1.5`

---

## 🟢 Strategy 2: Squeeze / Breakout — V2 Detector Built + Feature Tested

Squeeze is the primary strategy. V1 detector in `squeeze_detector.py` (FROZEN). V2 detector in `squeeze_detector_v2.py` (714 lines, separate module). V3 hybrid bot uses V2 detector with rolling HOD gate live.

**Files**: `squeeze_detector.py` (V1, ~420 lines, FROZEN), `squeeze_detector_v2.py` (V2, 714 lines), `bot_v3_hybrid.py` (live bot)
**Import switch**: `WB_SQUEEZE_VERSION=1|2`

### SQ V2 Feature Test Results (63-Day Backtest, April 1 2026)

| Config | P&L | Trades | WR | Delta vs V1 |
|--------|-----|--------|-----|------------|
| V1 baseline | +$154,849 | 26 | 73% | — |
| **V2 rolling HOD only** | **+$169,227** | **29** | **67%** | **+$14,378** |
| V2 all features ON | +$167,556 | 29 | 67% | +$12,707 |
| V2 base, rolling HOD OFF | +$131,657 | — | — | **-$23,192 (REGRESSION)** |

**Rolling HOD is the single improvement that matters.** V1's `_session_hod` never expires; V2's `max(bars[-49:])` lets stale premarket highs age out. Named features (COC, exhaustion gate, intra-bar ARM) had ~$0 impact individually. Candle exits cost $1,671 — OFF for now.

### Current Live Config (V3 bot)
- `WB_SQUEEZE_VERSION=2` with rolling HOD ON, candle exits OFF
- All other V2 features available but currently OFF

### Open Tasks

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| All V1/V2 core implementation | **✅ DONE** | — | Both detectors working, V3 bot live |
| Feature testing (63-day backtest) | **✅ DONE** | — | Rolling HOD = +$14,378, everything else ~$0 |
| **V2 base code regression audit** | **NOT STARTED** | **P1** | V2 without rolling HOD is -$23K worse than V1. Unexplained code path differences need audit. |
| **Candle exit tuning** | **NOT STARTED** | **P2** | Currently OFF (cost $1,671). Need higher profit gates or min time-in-trade. |
| Run full 55-day YTD with squeeze V2 | **NOT STARTED** | **HIGH** | The definitive test across full dataset |
| Port squeeze exits to trade_manager.py | **✅ DONE** | — | V3 hybrid bot handles this directly |

### Squeeze V2 Env Vars (all gated, defaults = OFF or conservative)
```
WB_SQUEEZE_ENABLED=1           # Master gate (OFF by default)
WB_SQ_VOL_MULT=3.0             # Min volume multiple to trigger PRIMED
WB_SQ_MIN_BAR_VOL=50000        # Absolute min bar volume
WB_SQ_MIN_BODY_PCT=1.5         # Min candle body % for squeeze bar
WB_SQ_PRIME_BARS=3             # Bars to wait for level break after PRIMED
WB_SQ_MAX_R=0.80               # Max R for consolidation-based stop
WB_SQ_LEVEL_PRIORITY=pm_high,whole_dollar,pdh
WB_SQ_PROBE_SIZE_MULT=0.5      # Half size on first attempt
WB_SQ_MAX_ATTEMPTS=3           # Per-symbol squeeze attempt limit
WB_SQ_PARA_ENABLED=1           # Parabolic mode (level-based stop fallback)
WB_SQ_PARA_STOP_OFFSET=0.10    # Stop = breakout_level - offset
WB_SQ_PARA_TRAIL_R=1.0         # Tighter trail for parabolic (vs 1.5R normal)
WB_SQ_NEW_HOD_REQUIRED=1       # Bar must be at/making new session HOD
WB_SQ_MAX_LOSS_DOLLARS=500     # Absolute dollar cap on squeeze losses
WB_SQ_TARGET_R=2.0             # Core exit target
WB_SQ_CORE_PCT=75              # Core vs runner split
WB_SQ_RUNNER_TRAIL_R=2.5       # Runner trail distance
WB_SQ_STALL_BARS=5             # Time stop (bars without progress)
WB_SQ_VWAP_EXIT=1              # Exit on VWAP loss
WB_SQ_PM_CONFIDENCE=1          # PM bull flag adds to score
```

---

## 🟡 Strategy 3: Dip-Buy Into Support (NEW — Not Yet Built)

Ross bought ARTL's dip from $8.20 to $5.63 at $6.73 and rode the bounce to $7.60 (+$5,000). This is a countertrend buy — fundamentally different from pullback-on-trend.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define dip-buy entry criteria | **NOT STARTED** | MEDIUM | Manny to provide breakdown. Key elements: sharp pullback after squeeze, support level (VWAP, whole dollar), bounce confirmation |
| Design dip-buy detector module | **NOT STARTED** | MEDIUM | Needs concept of "support" — VWAP, prior day close, whole/half dollars |
| Define dip-buy exit rules | **NOT STARTED** | MEDIUM | Likely tighter stops than pullback trades |
| Implement and backtest | **NOT STARTED** | — | After design approved |

---

## 🟡 Strategy 4: VWAP Reclaim (NEW — Not Yet Built) ⬆️ PRIORITY UPGRADED

Ross trades "the first 1-minute candle to make a new high" after price crosses back above VWAP. This is a specific entry signal the bot doesn't have. **CHNR analysis (2026-03-19) shows this was Ross's bread-and-butter pattern — 2 of his 3 actual trade sequences were VWAP reclaim setups.**

**Evidence across two live-day analyses:**
- **CHNR 2026-03-19**: VWAP curl trade (scratched -$67) + VWAP break into $6.00 (+$2k). Ross's primary setup.
- **ARTL 2026-03-18**: VWAP reclaim was part of Ross's re-entry sequence after the initial squeeze.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define VWAP reclaim criteria | **NOT STARTED** | **HIGH** | Key: price crosses above VWAP from below, first candle makes new high, volume confirmation. MACD filter (Ross skipped CHNR longs when MACD negative). |
| Design VWAP reclaim module | **NOT STARTED** | **HIGH** | May be simpler than squeeze — specific trigger condition. Entry on VWAP reclaim, exit at prior resistance/whole dollar. |
| Define exit rules | **NOT STARTED** | MEDIUM | |
| Implement and backtest | **NOT STARTED** | — | After design approved |

---

## 🟡 Strategy 5: Curl / Extension (NEW — Not Yet Built) ⬆️ PRIORITY UPGRADED

Rounded bottom approach toward prior HOD. Ross uses this for continuation trades later in the session. **CHNR analysis (2026-03-19) confirms this is Ross's biggest winner pattern — his +$2,000 curl from $5.00 support was the day's best trade.**

**Evidence across two live-day analyses:**
- **CHNR 2026-03-19**: Curl from $5.00 support after deep pullback → squeeze to $6.00 (+$2k). His best actual trade.
- **ARTL 2026-03-18**: Ross's best ARTL trade was also a curl pattern (gradual recovery into prior HOD).

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define curl entry criteria | **NOT STARTED** | **HIGH** | Key elements: gradual rounded-bottom recovery after pullback, approaching prior support/resistance zone. Needs concept of "support" (VWAP, whole dollar, prior consolidation) |
| Design and implement | **NOT STARTED** | **HIGH** | More complex than VWAP reclaim — needs multi-bar pattern recognition for rounded bottom shape |

---

## 🔵 Architecture: Strategy Profile System

The framework that allows multiple strategy modules to coexist without conflicting.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Design strategy profile architecture | **NOT STARTED** | HIGH | Each module: own state machine, own entry/exit rules, own reset logic. A TW reset in pullback doesn't affect squeeze module. Trade manager routes to correct module's exit rules. |
| Define trade manager routing logic | **NOT STARTED** | HIGH | When 2 modules want to enter same stock, who wins? When in a position, which module's exits apply? |
| Define shared vs module-specific settings | **NOT STARTED** | MEDIUM | Some settings (risk, notional cap) are global. Some (TW grace, R thresholds) are per-strategy. |
| Implement framework | **NOT STARTED** | — | After design approved, before adding new strategies |

---

## 🔵 Architecture: Detector Reset Tuning

The "extended candles" reset and TW resets during pullback phase are too aggressive on squeeze stocks. 9 resets in 45 minutes on ARTL.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Review "extended candles" reset threshold | **NOT STARTED** | MEDIUM | Currently resets after 5-6 green candles. On a squeeze, that IS the move. May need to be RVOL-aware (disable for >10x RVOL stocks). |
| Review TW resets during PULLBACK phase | **NOT STARTED** | MEDIUM | TW killed 4 potential ARM formations on ARTL during 08:19-08:26. Should TW reset be softer during active pullback detection? |
| This may be resolved by strategy profiles | **NOTED** | — | If squeeze module ignores these resets, the problem goes away for squeeze stocks. Pullback detector may still benefit from softer resets. |

---

## 🟢 Infrastructure / Ops

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Sync tick cache to Mac Mini | **PARTIAL** | MEDIUM | 49-day backtest ran, but not all pairs may be cached. Rsync full `tick_cache/` to Mac Mini for complete deterministic replay. |
| ~~Update CLAUDE.md with new regression targets~~ | **✅ DONE** | LOW | VERO now +$15,692 (was +$18,583, shifted by system-wide optimization). ROLR +$6,444 unchanged. Updated 2026-03-27. |
| Update COWORK_HANDOFF.md with today's work | **NOT STARTED** | LOW | Current state, new fixes, new architecture direction. |
| Ross Cameron video analysis | **NOTED** | WHEN POSSIBLE | Manny wants to compare bot entries vs Ross's recaps. Can't watch videos — Manny would need to provide timestamps/summaries for key trades. |

---

## 📊 Current Performance Baseline

| Metric | Value | Date |
|--------|-------|------|
| SQ V1 (63-day backtest) | **+$154,849** (26 trades, 73% WR) | 2026-04-01 |
| SQ V2 rolling HOD (63-day backtest) | **+$169,227** (29 trades, 67% WR) | 2026-04-01 |
| Jan 2025 missed stocks potential | **+$42,818** (7.7x vs actual $5,543) | 2026-03-23 |
| VERO regression | **+$15,692** (requires `WB_MP_ENABLED=1`) | 2026-03-27 |
| ROLR regression | **+$6,444** (requires `WB_MP_ENABLED=1`) | 2026-03-18 |
| V1 live (April 1) | **4 trades, -$671** + VOR phantom | 2026-04-01 |
| V3 live (April 2) | **0 trades, $0** (correct — 100% backtest match) | 2026-04-02 |

---

*This file is the single source of truth for all open work. Updated by Cowork after each session.*
