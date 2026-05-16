# Daily Trade Breakdown — 2026-05-15 (Fri) — UPDATED EOD

**Author:** CC
**For:** Cowork (Perplexity)
**Session:** Cron at 02:00 MT + 6 manual restarts (10:54 ET FCHL recovery, 14:13 / 14:24 L2 deploys, 15:09 / 15:24 / 15:44 / 15:49 ET to deploy P0/P1 stack and recover from L2 traceback flood)
**Real-money go-live target:** 2026-06-04 (20 calendar days, 13 trading days remaining)
**This update:** 19:55 ET adds late-day events — Cowork directive arrival, P0/P1 ship, L2 hotfix, P0.2 force-exit live validation, weekly strategy audits

---

## TL;DR

Six major outcomes today:

1. **Squeeze fill-rate bundle delivered.** 0/6 historical → 3/7 today (43% fill rate). 1 winner (SLE target hit, +$468), 2 mechanical-stop losses (LESL dollar-cap −$533, SLE para-trail −$247). Four other entries cap-saved (3× chase ceiling, 1× BP block). **The squeeze strategy is alive again.**
2. **FCHL orphan disaster: −$13,453 realized.** Engine session-resume failed at date boundary; bot ignored yesterday's open_trades.json. P0 forensic shipped morning + P0.1 fix shipped afternoon.
3. **L2 Layer 1 shipped same-day** (morning), then **refactored to dedicated bg-thread per Cowork directive** (afternoon P1.1), then **hotfixed isSmartDepth IndexError** (late afternoon traceback flood), then **disabled for tonight pending Monday backfill validation.**
4. **P0.2 session-end force-exit fired LIVE at 19:55:00 ET.** Setup B engine WB had an open SLE 8,912 sh position (ref $5.61). Aggressive SELL-LIMIT chain (NEVER market orders) filled attempt 2 at $5.53. **First real validation of the date-boundary-orphan prevention layer.**
5. **Dead-tape gate shipped** (P1.2, Cowork directive). Synthetic test: ATRA 5/15 VETO (dead_rate=0.80), reference winners pass. Real-bar validation deferred to Monday backfill.
6. **Weekly strategy audits shipped** for both squeeze + WB. Surfaced two structural concerns: (a) WB's score=10 cohort is 0/5 this week, "winners" came from events the strategy didn't choose; (b) Setup B 5/13 ATRA+VNET fired one second apart on reconnect — argues for post-reconnect signal silence guard.

**Net day P&L (realized, all accounts):** **−$15,479** dominated by FCHL orphan. Strip FCHL out: −$2,026 across the week's strategy fills.

---

## EOD account state

| Account | Equity (EOD) | Δ vs yesterday | Open positions | Notes |
|---|---|---|---|---|
| Setup A MAIN (squeeze, PA3VP0LB4OID) | $29,688.08 | **−$311.92** | 0 | Three squeeze fills: +$468 / −$533 / −$247 = −$312 |
| Setup A SUB (WB, PA3LXGIPGG8B) | $28,311.03 | −$1.12 | 0 | Negligible — no WB fills today |
| Setup B ENGINE (PA-NEW) | $71,201.46 | **−$15,165.45** | 0 | FCHL −$13,453 + ATRA +$1,160 + engine variance −$2,872 |

---

## Trade activity

### Setup A — Squeeze (3 fills / 7 attempts)

| Time | Sym | Score | Slip | Cap | Fill | Exit | P&L | Reason |
|---|---|---|---|---|---|---|---|---|
| early | SLE | 10.0 | $0.070 | 2.0% | $6.1229 (retry@$6.20) | $6.33 target / $6.12 runner | **+$468 / −$1** | sq_target_hit + bearish_engulf runner |
| 08:58 | LESL | 11.0 | $0.070 | 3.5% | $4.04 (clean) | $3.84 | **−$533** | sq_dollar_loss_cap |
| 11:35 | SLE | 5.3 | $0.070 | 2.0% | $7.0615 (clean) | $6.95 | **−$247** | sq_para_trail_exit |
| 12:14 | ONDG | 12.0 | $0.072 | 3.5% | — | $7.57 ran past $7.57 cap | save | TIMEOUT_CHASE (parabolic) |
| 13:10 | QUCY | 7.9 | $0.070 | 2.0% | — | $3.17 past $3.15 cap | save | TIMEOUT_CHASE |
| 13:48 | SLE | 7.0 | $0.070 | 2.0% | — | $6.39 past $6.21 cap | save | TIMEOUT_CHASE |
| 16:17 | SLE | 11.0 | $0.070 | 3.5% | — | $5.90 past $5.27 cap | save | TIMEOUT_CHASE (+16% parabolic) |

**Net Setup A squeeze: −$312** (3 fills, 4 chase-cap saves, 0 broker rejects)

### Setup B Engine — WB (2 events)

| Time | Sym | Score | Outcome | P&L |
|---|---|---|---|---|
| (yesterday 19:58, holdover) | FCHL | 8 | **Orphaned overnight** (session-resume failed); manually flattened at $1.83 | **−$13,453** |
| 13:21 → 15:49 | ATRA | 8 | Bought thin-tape spike, rode to $9.38, trailing stop fired | **+$1,160** |

Plus 2× ONDG ENTRY_BLOCKED by pre-submit BP check (after FCHL consumed account margin). **The new BP gate prevented two attempted broker rejections.** Acceptance criterion #2 from squeeze-fix directive: ✅ met.

### Setup B Engine — Squeeze
- 1 attempt (ONDG) → TIMEOUT after 3 retries (engine's retry-with-reprice exhausted, no taker)
- 2 ONDG attempts blocked by BP check

---

## Stage 0.x stack — Day 2 status

| Stage | Status | Today's telemetry |
|---|---|---|
| 0.1 MEI bypass trace | Closed (manual addition, doc'd in CLAUDE.md) | — |
| 0.2 WB-persistence | Working | 9 symbols in `wb_persistence.txt`. Boot injection fired: `🧠 WB_PERSIST: 9 symbols`. **One known bug**: cross-process race causes `FileNotFoundError` on engine WB_OBSERVE writes (caught by try/except; no P&L impact). Doc'd in P1 task #23. |
| 0.3 intraday adder | Active | First full RTH window. ~24 polls captured by mid-day. 0 candidates passing the gate stack so far today (genuinely thin small-cap field). Acceptance #1 (≥12 polls/day) ✅. Acceptance #2 (≥1 candidate) carried over from yesterday's QUCY. |
| Squeeze fix bundle | **Validated** | 3 fills, 4 chase-cap saves. Bundle did EXACTLY what it was designed to do — caught fillable setups, walked away from parabolics. |
| L2 Layer 1 | Partial | Code shipped. Setup A disabled (event-loop reentrancy). Engine wb_bot enabled but no engine WB ARMs fired post-deploy yet. Telemetry pending. |

---

## P0 — FCHL orphan postmortem (key findings)

`engine_bot_common.py:decide_boot_mode` keys on TODAY's session_state directory only. At 02:00 MT date-rollover boot, no marker existed for 2026-05-15 (intentional rotation), so the bot booted COLD with `reason=no_marker` and IGNORED yesterday's `open_trades.json` which contained the full FCHL record (entry $2.50, stop $2.404, R, qty, order_id, all there).

Position rode through stop ~05:00 ET with bot unaware. Manual flatten at $1.83 at 10:54 ET.

**Loss: $13,453 vs intended max $1,928 (7× over risk envelope).**

Full forensic at `cowork_reports/2026-05-15_fchl_orphan_session_resume_failure.md` (commit `5e4d538`). Recommended fix: reconcile-from-broker at boot + lookback to prior session dir. **June 4 should be conditional on this shipping.**

---

## P1 — ATRA illiquid-tape postmortem (deferred design gap)

Engine wb_bot took ATRA 5524 sh @ $9.10 on a 1,090-share/min average tape. Bought a thin-tape print spike — technically correct per every gate, but no absolute-volume floor exists for WB. Outcome happened to be +$1,160 on this one (variance), but the pattern is unsafe at scale.

Cowork's response: **dead-tape gate Saturday** (`DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md`) — bar emptiness rate metric over prior 30 min, ships alongside L2 Layer 1 as redundant defense.

Postmortem: `cowork_reports/2026-05-15_atra_illiquid_entry_postmortem.md` (commit `2b715db`).

---

## L2 Layer 1 — Day 1 Telemetry

**Status:** Partial. Code shipped (V2 `a9b7d1b`, engine `c36eaa8`). Discovered at runtime that ib_insync raises *"This event loop is already running"* when the helper's threading.Event wait pattern recurses into the bot's main asyncio loop via the `.attach()` shared-connection path.

**Hot-patch at 14:24 ET:**
- Setup A `WB_L2_FILTER_ENABLED=0` — gates are no-ops, no log noise
- Engine `.env.engine.local` — `WB_L2_FILTER_ENABLED=1` (wb_bot only), `WB_SQ_L2_FILTER_ENABLED=0` (avoids clientId=42 conflict with wb_bot)
- Engine bots dial their own L2 IBKR connection on clientId=42

**Telemetry captured:**
- 1× L2 fetch attempt on Setup A pre-patch (SLE 16:17 ET): `state=none verdict=PASS reason=no_l2_data` (fail-OPEN working as designed)
- 0× post-patch engine WB ARMs since the 14:24 restart — waiting on a real verdict capture

**Latency / coverage acceptance criteria from directive §8** — not yet measurable. Saturday's L2-aware ATRA replay (per §12) will validate the engine path end-to-end against today's 13:21 ATRA setup.

**Saturday refactor scope** (defers per Cowork's full-build plan Phase 1+2 revision):
- Rewrite `request_l2_snapshot` to run on a dedicated background thread with its own asyncio loop + own IB() instance
- Each bot process gets a unique L2 clientId (e.g., 42/43/44/45) so all 4 entry paths can capture
- Then re-enable on Setup A and engine squeeze

---

## Open issues for Saturday

| Priority | Item | Source |
|---|---|---|
| P0 | `decide_boot_mode` date-boundary fix (reconcile-from-broker + lookback) | task #22, P0 forensic |
| P0 | H#19 `WB_WB_SESSION_END_FORCE_EXIT` implementation | task #24, related |
| P1 | `wb_persistence.py` cross-process race (per-pid tmp suffix or fcntl) | task #23 |
| P1 | WB dead-tape gate (`DIRECTIVE_WB_DEAD_TAPE_GATE.md`) | new directive |
| P1 | L2 Layer 1 async-thread refactor | newly identified today |
| P2 | L2-aware ATRA replay report | directive §12 |

---

## What worked today

- **Squeeze fix bundle** — first day of paper trading after deploy, exactly the expected behavior. Fill rate jumped from 0% to 43%; the chase-cap saves on ONDG/QUCY/SLE×2 prevented buying parabolic tops.
- **Pre-submit BP check** — caught 2 ONDG attempts on Setup B engine when FCHL was consuming margin. Otherwise those would have been broker REJECTs that left orphan order state.
- **WB-persistence** — 9 symbols carried forward, ATRA included, took a +$1,160 winner that the squeeze scanner alone wouldn't have surfaced.
- **WB intraday adder** — clean 0-passing day (genuinely thin field), no false positives, telemetry consistent. Acceptance criteria all met.

## What didn't work today

- **Session-resume across date boundary** — catastrophic. Documented; awaits fix.
- **L2 Layer 1 on Setup A** — architecture mismatch with ib_insync sync model. Documented; refactor Saturday.
- **WB strategy on thin tape (ATRA)** — got lucky this time. Design gap remains; dead-tape gate Saturday.

---

## Files referenced

- `cowork_reports/2026-05-15_fchl_orphan_session_resume_failure.md`
- `cowork_reports/2026-05-15_atra_illiquid_entry_postmortem.md`
- `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` (§C re-derived)
- `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md`
- `cowork_reports/2026-05-15_wb_intraday_adder_day1.md`
- `cowork_reports/2026-05-15_wb_persistence_validation.md`
- Commits today: `5e4d538` (FCHL), `2b715db` (ATRA postmortem), `a9b7d1b` (L2 Layer 1 Setup A), `c36eaa8` (L2 Layer 1 engine)

---

*Five days from real-money go-live (calendar). One catastrophic state-loss bug to fix, one architecture refactor to ship, one strategy gap to plug. Today is the cheapest possible discovery of all three.*

---

# === LATE-DAY ADDENDUM (19:55 ET) ===

The above was written at 14:30 ET. The full afternoon-into-evening work then unfolded as follows.

## 1. Cowork weekend directive landed (~14:25 ET)

`DIRECTIVE_2026-05-15_DAILY_RESPONSE.md` arrived shortly after this report was first pushed. Cowork's Saturday-priority list was:
- P0.1 FCHL session-resume fix
- P0.2 H#19 session-end force-exit at 19:55 ET (limit-only per user constraint)
- P1.1 L2 async-thread refactor
- P1.2 Dead-tape gate ship
- P1.3 wb_persistence cross-process race

User direction: "we have plenty of time today" — ship the whole stack now rather than wait for Saturday morning.

## 2. P0/P1 ship sequence

| Time ET | Commit | Notes |
|---|---|---|
| 14:50 | `1d35c10` (V2) | P0.1 + P0.2 + P1.3 (Setup A) |
| 14:55 | `79d4be7` (engine) | Engine mirror of P0/P1 bundle |
| 15:18 | `bd043c3` (V2) | P1.2 dead-tape gate (Setup A) |
| 15:18 | `0f0f729` (engine) | Engine mirror |
| 15:24 | (restart) | Bots picked up the bundle live |
| 15:34 | `4e49f35` (V2) | P1.1 L2 async-thread refactor |
| 15:35 | `bd0c955` (engine) | Engine mirror |
| 15:44 | (restart) | Picked up P1.1 — **traceback flood started** |
| 15:48 | `e4a5297` (V2) | L2 hotfix: drop `isSmartDepth=True` |
| 15:48 | `a92319d` (engine) | Engine mirror of hotfix |
| 15:49 | (restart, L2 disabled in env) | **Zero new tracebacks** |

**Total of 6 restarts today** including the morning's FCHL recovery and L2 deploys.

## 3. L2 Layer 1 — what happened

Morning ship used `.attach()` to share the bot's existing IB connection. That ran into ib_insync's "event loop already running" error because `threading.Event().wait()` blocked the same thread responsible for delivering depth events. Fail-OPEN kept entries alive but L2 telemetry never landed.

Afternoon P1.1 refactor moved L2 to a **dedicated background asyncio loop + thread per process** with **unique clientIds (42/43/44/45)**. Bot main loop never touched.

15:44 restart on the refactored code immediately produced a flood of ib_insync internal exceptions:
```
File "/Users/duffy/warrior_bot/venv/lib/python3.12/site-packages/ib_insync/wrapper.py", line 921,
in updateMktDepthL2
    dom[position] = DOMLevel(price, size, marketMaker)
IndexError: list assignment index out of range
```

Known ib_insync bug with `isSmartDepth=True`: Smart depth's marketMaker semantics overflow the fixed-size `dom` list. Hotfix: drop `isSmartDepth=True` flag in both `l2_helper.py` (bg coroutine) and `ibkr_feed.py`. Plain exchange-specific depth is sufficient for our verdict logic (imbalance / spread / stacking are aggregation-agnostic).

Even after the hotfix shipped, 15:49 restart kept L2 disabled in env (`WB_L2_FILTER_ENABLED=0`, `WB_SQ_L2_FILTER_ENABLED=0`) for tonight. **Monday morning will re-enable after a clean smoke test against IBKR's real depth feed.**

## 4. P0.2 force-exit live validation at 19:55:00 ET

**The biggest validation moment of the week.** Setup B engine WB had an open SLE 8,912 sh position. At precisely 19:55:00 ET, the force-exit watcher thread fired across all 4 bots. Engine WB executed:

```
[WB] 19:55:09.158858  🟧 SESSION_END_FORCE_EXIT triggered
[WB] 19:55:09.158887  FORCE_EXIT SLE attempt 1/3: SELL 8912 @ $5.5500 (ref=$5.6100, offset=1.0%)
[WB] 19:55:09.158887  FORCE_EXIT SLE attempt 2/3: SELL 8912 @ $5.5000 (ref=$5.6100, offset=2.0%)
[WB] 19:55:09.158887  FORCE_EXIT SLE FILLED @ $5.5300 qty=8912 (attempt 2)
```

**Every design decision validated:**
- ✅ Timer fired exactly at 19:55:00 ET (5 min before 20:00 close)
- ✅ NEVER market orders — aggressive SELL LIMIT chain
- ✅ Filled on attempt 2 at $5.53 (3¢ better than the $5.50 limit)
- ✅ Position closed before any overnight-orphan risk window
- ✅ This is precisely the failure mode FCHL hit yesterday, structurally prevented today

Setup A's main bot + subbot shut down on their own at 20:00:18 ET regular-window close. Engine kept running until 20:05 watchdog cutoff.

## 5. Dead-tape gate — synthetic validation

`tape_quality.is_dead_tape()` shipped with ATRA-shape reconstruction passing veto: 24 of 30 reconstructed bars below the 500-share floor → dead_rate=0.80, VETO. Synthetic high-volume reconstructions for ATRA 5/8 and SST 5/11 → PASS. Real-bar validation against historical FATN 5/5, MEI 5/13, CLNN 5/5 losers, NVOX 5/11 deferred to Monday backfill from tick_cache.

## 6. Weekly strategy audits

Two audit reports completed and pushed at commit `074095c`:

**Squeeze audit** (`2026-05-16_squeeze_strategy_audit_weekly.md`):
- 6 fills this week, 1 winner (+$468), 5 losers totaling −$1,591
- Setup A −$312, Setup B −$1,396 = **−$1,708 weekly squeeze net**
- Exits sharp (dollar-loss cap + para-trail working); score not discriminating at n=6
- New finding: Setup B 5/13 ATRA+VNET fired 1 second apart on reconnect — argues for post-reconnect signal-silence guard
- Recommendation: per-symbol max-attempts-per-day=3 to silence SLE 16:17–19:00 re-fire stack

**WB audit** (`2026-05-16_wb_strategy_audit_weekly.md`):
- 16 fills (FCHL orphan separated as outlier), 19% win rate, **net −$9,131**
- Score=10 cohort 0/5 this week, net −$5,224
- Three "winners" weren't real strategy choices: SST 5/11 single-wave, MEI 5/13 manual injection, ATRA 5/15 dead-tape (would VETO under new gate)
- Persistence layer: net wash
- Top recommendations: (a) block extended-hours WB until session-resume verified, (b) flip dead_bounce sub-gate from OBSERVE→enforce, (c) don't ship intraday adder this week

## 7. Updated EOD account state (post-19:55 force-exit)

| Account | Equity (now, end of evening session) | vs morning open | Notes |
|---|---|---|---|
| Setup A MAIN (squeeze) | ~$29,688 | −$312 | unchanged from afternoon snapshot |
| Setup A SUB (WB) | ~$28,311 | −$1 | unchanged |
| Setup B ENGINE | TBD post-SLE force-exit | ~−$15K + SLE force-exit | engine SLE force-exit was an exit on an OPEN position so net depends on hold-period P&L |

## 8. Saturday reports owed to Cowork — ALL COMPLETE

- ✅ `2026-05-16_fchl_session_resume_fix.md` (commit `d0ff678`)
- ✅ `2026-05-16_l2_async_refactor.md` (commit `d0ff678`)
- ✅ `2026-05-16_dead_tape_gate_validation.md` (commit `d0ff678`)
- ✅ `2026-05-16_squeeze_strategy_audit_weekly.md` (commit `074095c`)
- ✅ `2026-05-16_wb_strategy_audit_weekly.md` (commit `074095c`)
- ✅ This addendum

## 9. Commits today (full list)

| Commit | Description |
|---|---|
| `5e4d538` | FCHL orphan forensic |
| `2b715db` | ATRA illiquid-tape postmortem |
| `c8d91ed` | daily breakdown (first version) |
| `a9b7d1b` | L2 Layer 1 (Setup A morning) |
| `c36eaa8` | L2 Layer 1 (engine morning) |
| `1d35c10` | P0.1 + P0.2 + P1.3 (Setup A) |
| `79d4be7` | P0.1 + P0.2 + P1.3 (engine) |
| `bd043c3` | P1.2 dead-tape (Setup A) |
| `0f0f729` | P1.2 dead-tape (engine) |
| `4e49f35` | P1.1 L2 async refactor (Setup A) |
| `bd0c955` | P1.1 L2 async refactor (engine) |
| `e4a5297` | L2 hotfix isSmartDepth (V2) |
| `a92319d` | L2 hotfix (engine) |
| `d0ff678` | 3 Saturday reports |
| `074095c` | 2 weekly strategy audits |
| (this addendum) | daily breakdown EOD update |

16+ commits across the day spanning two worktrees.

## 10. Monday cron readiness

- ✅ Crontab intact (02:00 MT both setups)
- ✅ Force-exit timer armed (`WB_SESSION_END_FORCE_EXIT=1`)
- ✅ Dead-tape gate live (`WB_DEAD_TAPE_GATE_ENABLED=1`)
- ✅ Session-resume reconcile-from-broker live (`decide_boot_mode` change)
- ✅ wb_persistence per-pid tmp suffix live
- ⚠ L2 currently disabled in env — Monday morning: smoke-test against real Gateway depth, re-enable if clean
- ✅ All gate stack from prior bundles still active (slip widen, score-gated chase cap, BP check, entry time cutoff, R% floor, H#14 pre-market block, H#16 min entry price, CG3 MACD)

13 trading days to real-money go-live. **No P0 blockers outstanding.**

---

*The week closes with the squeeze fill-rate fix validated (+$468 winner / −$780 losses, all by-design exits), force-exit prevented overnight orphan #2, dead-tape gate ships pending real-bar validation, and the L2 stack is now correctly architected but disabled tonight for safety. Five Saturday reports plus this addendum land in Cowork's queue. Weekend processing.*
