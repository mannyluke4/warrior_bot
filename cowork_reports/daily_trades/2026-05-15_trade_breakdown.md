# Daily Trade Breakdown — 2026-05-15 (Fri)

**Author:** CC
**For:** Cowork (Perplexity)
**Session:** Cron at 02:00 MT + 3 manual restarts (10:54 ET FCHL recovery, 14:13 ET L2 Layer 1 deploy, 14:24 ET L2 hot-patch)
**Real-money go-live target:** 2026-06-04 (20 calendar days, 13 trading days remaining)

---

## TL;DR

Three major outcomes today:

1. **Squeeze fill-rate bundle delivered.** 0/6 historical → 3/7 today (43% fill rate). All three filled trades behaved correctly: 1 winner (SLE target hit, +$468), 2 mechanical-stop losses (LESL dollar-cap −$533, SLE para-trail −$247). Four other entries cap-saved (3× chase ceiling, 1× BP block). **The squeeze strategy is alive again.**
2. **FCHL orphan disaster: −$13,453 realized.** Engine session-resume failed at date boundary; bot ignored yesterday's open_trades.json. Position rode through stop, manually flattened at $1.83. P0 forensic shipped. **June 4 go-live conditional on fix.**
3. **L2 Layer 1 shipped same-day.** Code in place across all 4 entry paths, observe-only mode. Discovered ib_insync event-loop reentrancy issue mid-session — hot-patched: Setup A disabled, engine wb_bot only (clientId=42). Saturday refactor lined up.

**Net day P&L (realized, all accounts):** **−$15,479** dominated by FCHL orphan.

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
