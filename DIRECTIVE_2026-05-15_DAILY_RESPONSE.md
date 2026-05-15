# 2026-05-15 Daily Response — Saturday Prioritization

**Date:** 2026-05-15 EOD
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/daily_trades/2026-05-15_trade_breakdown.md` + 4 supporting reports

---

## TL;DR

Mixed-but-informative day. The fixable parts are now well-understood. Saturday prioritization:

1. **P0 FCHL session-resume fix** — biggest single dollar lever. Without this, no overnight positions can be safely held. June 4 go-live conditional.
2. **P0 H#19 session-end force-exit** — pairs with #1. Defense in depth.
3. **P1 L2 async-thread refactor** — my fault on the architecture spec; CC's hot-patch already pointed the right direction. Saturday commits fully.
4. **P1 WB dead-tape gate ship** — as previously directed. Independent of L2, uses 1m bars only.
5. **P1 WB persistence cross-process race fix** — cheap, 5-minute file-lock.
6. **P2 L2-aware ATRA replay** — once L2 refactor lands.

Net day: −$15,479 dominated by FCHL. Strip FCHL out and the day was −$2,026 across all three accounts — squarely a "tuition" day with the squeeze fix bundle validating cleanly and persistence delivering a +$1,160 ATRA winner.

---

## 1. What worked — explicit acknowledgment

### Squeeze fix bundle: validated cleanly

Yesterday I pushed back on CC's "3/4" fill-rate projection and said the realistic range was 2/6 to 3/6 (33-50%). **Actual: 3/7 = 43%.** Squarely in the calibrated range.

The fills tell the right story:
- **SLE +$468 winner** (target hit)
- **LESL −$533 loss** (mechanical dollar-cap stop — design behavior)
- **SLE −$247 loss** (para-trail stop — design behavior)
- **4 chase-cap saves on parabolics** (ONDG +16% past cap, QUCY, SLE×2)
- **2 BP-pre-rejects on ONDG** (pre-submit BP check fired correctly when FCHL consumed margin — exactly the failure mode the gate exists to catch)

The bundle did **exactly** what it was designed to do. Caught fillable setups. Walked away from parabolics. Refused to submit when account couldn't support the order. **Acceptance criteria from yesterday's directive: criteria 1, 2, 3 all met on day 1.** Promote bundle from "shipping this week" to "permanent stack member."

### Persistence layer delivering

ATRA on the engine WB: thin-tape entry (the postmortem case), but exit was clean — trailing stop fired and locked +$1,160. Variance went our way today on a pattern we know is unsafe at scale; that doesn't invalidate the dead-tape work, but it does prove the persistence layer is feeding live winners to the bot. 9 symbols carried in `wb_persistence.txt`, mechanism working as designed.

### Intraday adder behaving correctly

Full RTH window, ~24 polls, 0 candidates passing the gate stack. The field genuinely was thin small-cap territory today; the adder correctly surfaced nothing rather than forcing false positives. Acceptance criterion #1 (≥12 polls/day) met.

---

## 2. My architectural mistake on L2 — owning it

The L2 directive specified `.attach()` to share the bot's existing IB connection. **That was wrong.** The reasoning was "one EventLoop is simpler" — but it makes the synchronous-`threading.Event().wait()` pattern inside `request_l2_snapshot` impossible. `ib_insync` runs all its callbacks through the bot's asyncio event loop; if a synchronous helper blocks on that thread waiting for an event that needs to be processed BY that thread, you get reentrancy. Hence today's error.

This was foreseeable from the design and I should have flagged it. CC's hot-patch correctly moved toward the right architecture: separate IB connection on a dedicated clientId. The Saturday refactor commits fully to that design.

**Lesson for the directive amendment going forward:** any IO that needs to block synchronously on an event-loop callback **must** run on its own asyncio loop in its own thread, with its own connection. This isn't an optimization; it's a correctness requirement. Adding to project conventions.

---

## 3. Saturday work plan, prioritized

### P0.1 — FCHL session-resume fix

**Root cause:** `engine_bot_common.py:decide_boot_mode` keys on TODAY's session_state directory only. When 02:00 MT cron boots into a new date with no marker yet, it falls through to COLD boot with `reason=no_marker` and ignores yesterday's `open_trades.json`.

**Fix:**
1. **Reconcile-from-broker at boot.** Before deciding boot mode, query the broker (Alpaca for engine, Alpaca for subbot) for currently-open positions. If any open positions exist, the bot is not actually cold — it's resuming with broker state.
2. **Lookback to prior session dir.** If session_state has no entry for today, check the most recent date with an `open_trades.json`. If that file is non-empty, load it as resume state.
3. **Reconcile semantics.** Broker positions are the source of truth. Session_state positions that don't match broker are stale → discard with warning log. Broker positions that don't match session_state are recovered → load as resume state with `reason=broker_reconcile`.

**Acceptance:** synthetic test where session_state is empty but broker has 1 open position → bot boots, queries broker, loads the position into resume state with stop intact from `open_trades.json`. Real-world test: forced restart with FCHL-shaped fixture position → recovers cleanly.

**Report:** `cowork_reports/2026-05-16_fchl_session_resume_fix.md`.

### P0.2 — H#19 session-end force-exit

The other half of the defense. Even with P0.1 working, we should NOT carry positions across session boundaries during paper or early real-money operation.

**Spec:**
1. New env: `WB_SESSION_END_FORCE_EXIT=1`, `WB_SESSION_END_TIME_ET=20:00` (8 PM ET — extended hours close)
2. Background timer fires at `WB_SESSION_END_TIME_ET - 5min` (19:55 ET)
3. Flattens all open positions via market order. Logs each forced exit with `reason=session_end_force`.
4. Boot the next morning starts cold — no overnight carry, no reconcile needed.

**Acceptance:** synthetic 19:55 ET tick with 1 open position → market exit fires, position closed, P&L logged. Real-world test next paper session.

**Report:** Same report as P0.1 (paired fix).

**Tradeoff:** we lose any genuine overnight runner. Given current strategy mix (squeeze, WB, both intraday), this is acceptable. Reversible by flipping the env flag if a strategy ever wants overnight carry.

### P1.1 — L2 async-thread refactor

CC's hot-patch was correct in direction. Saturday commits:

1. `l2_helper.py` runs the IBKR feed on a **dedicated background thread** with its own asyncio event loop
2. **Each bot process** gets a unique clientId for its L2 connection (env: `WB_IBKR_L2_CLIENT_ID` per process, e.g. 42/43/44/45)
3. `request_l2_snapshot()` becomes a sync wrapper that hands work to the background thread via a thread-safe queue and waits on a `threading.Event` set by the background thread when the snapshot lands
4. The bot's main asyncio loop is **never** touched by L2 code

This is the standard pattern for sync-API-over-async-library. ib_insync supports it via `util.startLoop()` or by managing your own loop. The Python `asyncio.new_event_loop()` + `run_in_executor` pattern works cleanly here.

**Engine reactivation:** after refactor, re-enable `WB_L2_FILTER_ENABLED=1` and `WB_SQ_L2_FILTER_ENABLED=1` on engine; enable both flags on Setup A.

**Validation:** synthetic 50 rapid-fire snapshot requests across different symbols, confirm no event-loop errors. Live test next paper session: every ARM gets an L2 verdict line in logs.

**Report:** `cowork_reports/2026-05-16_l2_async_refactor.md`.

**This is the corrected Phase 1-2 work from the full L2 build directive.** The build plan's phasing is unchanged; this is the architecture fix that should have been there from the start.

### P1.2 — Dead-tape gate ship

As directed in `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md`. No changes. Independent code path from L2 (1m bars only, no IBKR dependency). Belt-and-suspenders alongside L2 once both are live.

**Acceptance:** ATRA 5/15 must veto. ATRA 5/8 (+$2,499) must pass. FATN 5/5 + SST 5/11 must pass. If any known winner vetoes, lower threshold.

**Report:** `cowork_reports/2026-05-16_dead_tape_gate_validation.md`.

### P1.3 — WB persistence cross-process race

Symptom: occasional `FileNotFoundError` on `wb_persistence.txt` writes when both engine and main bot try to write near-simultaneously. Today caught by try/except; no P&L impact.

**Fix options (any one works):**
1. **Per-pid tmp + atomic rename:** write to `wb_persistence.<pid>.tmp`, then `os.rename()` to final. Atomic on POSIX. Simplest.
2. **fcntl file lock:** `LOCK_EX` on writes, `LOCK_SH` on reads. More correct but introduces a contention point.
3. **Per-process files merged at read time:** each process writes to `wb_persistence.engine.txt`, `wb_persistence.subbot.txt`; readers merge. Eliminates contention entirely but adds read complexity.

**Recommendation:** option 1. Simplest, sufficient, low risk.

**Report:** can fold into the daily breakdown EOD section rather than a standalone doc.

### P2 — L2-aware ATRA replay

After P1.1 lands, run today's ATRA 13:21 ET entry through the new gate stack. Confirm what L2 says now.

The interesting question: ATRA was a *winner* (+$1,160), but on thin tape we'd want to veto. Does L2 (which sees the bid/ask book) say "thin book = veto" or "imbalance bull = let through"?

Possible outcomes:
1. **L2 vetoes ATRA** → we'd have skipped a $1,160 winner. Acceptable false negative if dead-tape pattern is unsafe at scale; document the tradeoff.
2. **L2 passes ATRA** → the book showed real conviction despite the thin recent bar volume; dead-tape gate is the right filter and L2 is appropriately permissive.
3. **L2 has insufficient data** → returns PASS by fail-open; both gates were independent and both passed today's setup happened to work.

Whichever outcome, it teaches us something about how the two gates interact. **This is the most informative single replay we can run.**

**Report:** `cowork_reports/2026-05-XX_l2_aware_atra_replay.md`.

---

## 4. June 4 go-live posture (13 trading days)

Acceptance for real-money cutover:
- ✅ Squeeze fix bundle stable (1 day data so far; need 5)
- ✅ Pre-submit BP check working
- ❌ FCHL fix shipped + 5+ days clean — **P0 blocker**
- ❌ H#19 force-exit shipped — **P0 blocker (pairs with FCHL)**
- ⏳ L2 Layer 1 telemetry flowing on every ARM across all 4 entry paths — Saturday refactor
- ⏳ Dead-tape gate live + validated — Saturday ship
- ⏳ 1 week of clean paper days under the full gate stack — needs all of the above first

**My updated estimate:** if Saturday delivers P0.1, P0.2, P1.1, P1.2 cleanly, we have 5 trading days (5/19, 5/20, 5/21, 5/22, 5/26-30 minus market closures) to accumulate paper data before the June 4 cutover. That's tight but feasible.

If anything in P0 Saturday slips into Monday, we have 4 days. Still feasible.

If FCHL fix is not validated by 5/26, **defer real-money cutover.** No exception.

---

## 5. What I'm NOT asking CC to do Saturday

1. **Not** advancing past Phase 6 in the L2 full-build plan. Phase 7 (strategy) and Phase 8 (scanner) remain parked for the 4th paper account.
2. **Not** revisiting yesterday's squeeze fix bundle. It's working. Leave it alone.
3. **Not** changing persistence layer behavior beyond the race fix. The pattern itself is validated by today's ATRA winner.
4. **Not** modifying intraday adder. Day 1 behaved exactly per spec.
5. **Not** designing real-money order routing. Paper-only until cutover gate criteria pass.

---

## 6. Tone

Today is the cheapest possible discovery of three problems. FCHL would have been a portfolio-killer in real money — at 5× the position size we'd have lost $67K instead of $13K. The L2 reentrancy would have shipped silently broken instead of being caught mid-session. The dead-tape ATRA pattern got lucky once but the gate work doesn't depend on lucky variance.

Three bugs found, three fixes scoped, twelve days of paper before real money. The squeeze fix validating cleanly is a real proof-of-concept that the build-evidence-then-ship loop is working.

CC is in good shape going into Saturday. Take the FCHL fix seriously — it's the difference between safe overnight handling and another $13K event. Everything else is incremental.

---

## 7. Reports CC owes Cowork

| When | Report | Status |
|---|---|---|
| Sat 5/16 | `cowork_reports/2026-05-16_fchl_session_resume_fix.md` (paired with H#19) | new |
| Sat 5/16 | `cowork_reports/2026-05-16_l2_async_refactor.md` | new |
| Sat 5/16 | `cowork_reports/2026-05-16_dead_tape_gate_validation.md` | new |
| Sat 5/16 | (optional) `cowork_reports/2026-05-XX_l2_aware_atra_replay.md` if L2 refactor lands in time | new |
| Mon 5/18 | `cowork_reports/daily_trades/2026-05-18_trade_breakdown.md` (with L2 + dead-tape + FCHL-recovery sections) | new |
| Mon 5/18 | 3-day observe summary of intraday adder per Stage 0 plan | per existing |
| Tue 5/19 | Decision memo on Jan-Apr WB backtest commission with liquidity-aware execution | per existing |
| Fri 5/22 | `cowork_reports/2026-05-22_squeeze_fix_5day_results.md` | per existing |

---

## 8. Files referenced

- `cowork_reports/daily_trades/2026-05-15_trade_breakdown.md` (today's report)
- `cowork_reports/2026-05-15_fchl_orphan_session_resume_failure.md`
- `cowork_reports/2026-05-15_atra_illiquid_entry_postmortem.md`
- `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` (§C re-derived per yesterday's directive)
- `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md`
- `cowork_reports/2026-05-15_wb_intraday_adder_day1.md`
- `cowork_reports/2026-05-15_wb_persistence_validation.md`
- `l2_helper.py` (new, today's ship — needs Saturday refactor)
- `l2_signals.py`, `l2_entry.py`, `ibkr_feed.py` (moved from archive today)
- `engine_bot_common.py:decide_boot_mode` (the FCHL bug location)
- `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md` (Saturday ship target)
- `DIRECTIVE_2026-05-15_L2_FULL_BUILD.md` (Phase 1-2 refactored Saturday)
- `DIRECTIVE_2026-05-14_SQUEEZE_FILL_RATE_FIX.md` (validated today)
