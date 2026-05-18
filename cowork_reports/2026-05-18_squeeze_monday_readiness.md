# Squeeze Monday Readiness — P0 Verification

**Date:** 2026-05-17 (Sunday)
**Author:** CC (read-only verification)
**Per:** `DIRECTIVE_2026-05-18_ENGINE_FRAMEWORK_DEPLOY.md` Track 1
**Scope:** File-by-file PASS/FAIL of Saturday's P0 work for the squeeze strategy in both production paths (Setup A `v2-ibkr-migration` and Setup B engine `data-engine-unified`).

---

## Net assessment

**GREEN — proceed with Monday open.**

All five P0 items pass on a code-evidence basis. The L2 stack is in a deliberate
env-disabled state (code-OK, flag-OFF) per the Saturday 5/17 clarification report;
that is the intended posture, not a regression. The dead-tape gate is wired in
ENFORCE mode rather than observe-only, which (a) matches the original 5/15
directive's acceptance criteria ("ATRA 5/15 must VETO"), and (b) is **not on the
squeeze path** in either bot — it only fires for WB ARMs. Squeeze Monday ships
unchanged.

One documentation-only discrepancy is flagged below (Track 1 framing says
"observe-only"; production is enforce). No code-quality action recommended; this
report records the actual state so Cowork can correct future framing.

---

## Production paths covered

| Strategy | Setup A (Alpaca paper, main bot) | Setup B (engine paper) |
|---|---|---|
| Squeeze | `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py` | `/Users/duffy/warrior_bot_v2_engine/squeeze_bot.py` |
| Wave Breakout | `/Users/duffy/warrior_bot_v2/bot_alpaca_subbot.py` | `/Users/duffy/warrior_bot_v2_engine/wb_bot.py` |
| Common helpers (engine) | n/a | `/Users/duffy/warrior_bot_v2_engine/engine_bot_common.py` |
| Shared modules (both worktrees, identical copies) | `force_exit.py`, `tape_quality.py`, `l2_helper.py`, `l2_signals.py` | same names |

---

## 1. FCHL session-resume fix verified — **PASS**

**Implementation site (Setup B engine):** `/Users/duffy/warrior_bot_v2_engine/engine_bot_common.py:1165-1257`

- `_broker_has_positions(broker)` (line 1165) — safe wrapper, falls back to
  `get_all_positions()` and degrades to `(False, [])` on full failure
- `_lookback_open_trades_path(session, max_lookback_days=7)` (line 1187) — walks
  back day-by-day for most recent non-empty `open_trades.json`
- `decide_boot_mode(session, fresh, resume, broker)` (line 1208) — broker
  source-of-truth check at line 1245 BEFORE marker logic. Returns
  `("resume", "broker_reconcile")` and stashes prior-day path on
  `session._lookback_open_trades_path` (line 1254). The pre-fix `no_marker` cold
  fall-through that produced the FCHL orphan is now unreachable when broker has
  positions.

**Resume rehydrate read path:** `engine_bot_common.py:1074-1104`
`EngineSession.read_open_trades` checks `primary_empty` (today's file ≤ 2 bytes)
and falls back to `_lookback_open_trades_path` when stashed by
`decide_boot_mode`. Emits a `[BOT] ... read_open_trades` log line on the
fallback path.

**Call-site wiring:**

| Path | File | Line |
|---|---|---|
| Engine WB | `wb_bot.py` | 1123-1134 (construct broker before `decide_boot_mode`, pass `broker=_boot_broker`) |
| Engine Squeeze | `squeeze_bot.py` | 1192-1203 (same pattern, prefixed `[SQUEEZE]`) |

**Setup A (V2 worktree):** The V2 bots (`bot_v3_hybrid.py`, `bot_alpaca_subbot.py`)
use a different persistence layer (`wb_persistence.py`, `session_state/`) and a
different resume path. The Saturday FCHL ship targeted the engine bots, which
are where the original 5/14 FCHL orphan event occurred. The V2 worktree's
`WB_SESSION_RESUME_ENABLED=1` confirms resume is on; the V2 resume codepath was
not part of the P0.1 fix and is out of scope for this verification.

**Env gate:** Both `.env` files have `WB_SESSION_RESUME_ENABLED=1`. Without that
flag, `wb_bot.py:1135-1139` and `squeeze_bot.py` will force COLD even when
`decide_boot_mode` returns RESUME. Confirmed ON.

**Verdict:** PASS. The FCHL date-boundary fix is in the production resume path
for the engine bots (where the original incident occurred). The V2 bots are
untouched by this P0 and rely on their existing `wb_persistence` model, which
is not what FCHL exercised.

---

## 2. Force-exit at 19:55 ET (SELL LIMIT chain, no market orders) — **PASS**

**Module:** `/Users/duffy/warrior_bot_v2/force_exit.py` (and identical engine copy
`/Users/duffy/warrior_bot_v2_engine/force_exit.py` — verified by size + mtime).

**Key facts (lines cited from V2 copy):**
- `_ENABLED` default ON (line 32): `os.environ.get("WB_SESSION_END_FORCE_EXIT", "1") == "1"`
- Trigger fires at `_END_TIME_ET − _LEAD_MIN` (20:00 − 5 = 19:55 ET) via
  `should_force_exit_now()` at line 64
- Once-per-day-per-process latch on `_FIRED_DATE` (line 77)
- **`force_exit_position()` uses `broker.submit_limit(...)` ONLY at line 148** with
  `extended_hours=True`; aggressive chase ladder: 1% → 2% → 3% offset,
  10s timeout per attempt, 3 max retries.
- **No market-order path anywhere in `force_exit.py`** — verified by inspection.

**Wiring (all four production paths):**

| Path | File:Line | Pattern |
|---|---|---|
| Setup A main (squeeze + WB) | `bot_v3_hybrid.py:1980-2033`, called from main loop at line 4787 | `_maybe_session_end_force_exit()` iterates `state.open_position` (squeeze) and `state.wb_positions` |
| Setup A subbot (WB only) | `bot_alpaca_subbot.py:2434-` , called at line 4663 | Iterates `state.wb_positions` |
| Engine WB | `wb_bot.py:1057-1091` | Dedicated `_force_exit_watcher` daemon thread, 10s poll, iterates `self.positions` under `_positions_lock` |
| Engine Squeeze | `squeeze_bot.py:1112-1147` | Same pattern as engine WB |

**Cross-file market-order audit:**
- `grep "MarketOrder("` across all four production bots → **0 hits** (no instantiations).
- `from ib_insync import ... MarketOrder, ...` appears as an import in
  `bot_v3_hybrid.py:41` and `bot_alpaca_subbot.py:75` but is not invoked.
- `submit_market` → 0 hits across all four bots.

**Env state (both `.env` files):**
```
WB_SESSION_END_FORCE_EXIT=1
WB_SESSION_END_TIME_ET=20:00
WB_SESSION_END_LEAD_MIN=5      → fires 19:55 ET
WB_SESSION_END_FIRST_OFFSET_PCT=1.0
WB_SESSION_END_RETRY_STEP_PCT=1.0
WB_SESSION_END_MAX_RETRIES=3
WB_SESSION_END_FILL_TIMEOUT_SEC=10
```

**Verdict:** PASS. The SELL LIMIT chain is the only exit primitive at 19:55 ET
across all four bots. No market-order surface exists in the force-exit path.

---

## 3. L2 async refactor merged — **PASS (code in)**; **env DISABLED** (deliberate)

**Module:** `/Users/duffy/warrior_bot_v2/l2_helper.py` (and identical engine copy).

**Architecture (lines from V2 copy):**
- Dedicated background asyncio loop and daemon thread per bot process
  (`_BG_LOOP`, `_BG_THREAD` at lines 58-59)
- `_ensure_bg_ib()` (line 89) lazy-inits the bg loop + IB connection on first
  request, with a `_BG_CONNECT_FAILED` latch (line 61) to prevent reconnect
  storms
- `_bg_fetch_l2_async()` (line 131) is a coroutine on the bg loop. The
  `isSmartDepth=True` parameter has been **dropped** (line 154,
  `ib.reqMktDepth(contract, numRows=num_rows)`) per the Friday hotfix
  `e4a5297` / `a92319d`. Comment at lines 148-153 documents the ib_insync
  IndexError reason.
- `request_l2_snapshot()` (line 198) is the sync wrapper: schedules work via
  `asyncio.run_coroutine_threadsafe(...)` on `_BG_LOOP` (line 212), waits on
  the future. **The bot's main asyncio loop is never touched.**
- `ib_instance` parameter retained but ignored (line 203).

**Per-process clientIds (one per bot):**

| Bot | File:Line | clientId |
|---|---|---|
| `bot_v3_hybrid.py` | line 27 | 42 |
| `bot_alpaca_subbot.py` | line 48 | 43 |
| engine `wb_bot.py` | line 17 | 44 |
| engine `squeeze_bot.py` | line 25 | 45 |

All via `os.environ.setdefault("WB_L2_CLIENT_ID", "NN")` BEFORE first import of
`l2_helper`, exactly as the refactor report specified.

**Env state (both `.env` files):**
```
WB_L2_FILTER_ENABLED=0
WB_SQ_L2_FILTER_ENABLED=0
```

**Both states documented:**
- **Code state:** dedicated bg-thread + per-bot clientId architecture is
  merged and isSmartDepth has been hotfixed out
- **Env state:** all four L2 flags DISABLED, per the Sat 5/17 incident response
  documented in `cowork_reports/2026-05-17_l2_state_clarification.md`. The
  isSmartDepth IndexError flood at ~15:45 ET Friday forced the env disable
  while the code fix was applied; the env stayed at 0 pending Monday-morning
  re-enable smoke test.

**Verdict:** PASS for the code merge. The env state is intentionally OFF and
this is the documented Monday-open posture; squeeze does not require L2 to
ship for Monday (squeeze never imported L2 verdicts as a hard gate, only as
observe-only telemetry). No regression introduced.

---

## 4. Dead-tape gate running observe-only — **PASS-WITH-CAVEAT** (gate is ENFORCE, not observe-only — see note)

**Module:** `/Users/duffy/warrior_bot_v2/tape_quality.py` (identical engine copy).

**Logic (lines from V2 copy):**
- `is_dead_tape(bars_1m)` (line 47) computes `dead_rate` over the last
  `LOOKBACK_MIN=30` bars, returns `(alive=False, reason, telem)` when
  `dead_rate > MAX_DEAD_RATE=0.5` (line 73). `alive=True` path also returns
  full telemetry dict (line 82).
- Env: `WB_DEAD_TAPE_GATE_ENABLED=1` (both .env files).

**Wiring — WB ARM path only:**

| Path | File:Line | Behavior on dead_tape |
|---|---|---|
| Setup A subbot WB | `bot_alpaca_subbot.py:962-981` | Logs `[CHOP_REJECT] {symbol}: dead_tape(...)`, calls `det.mark_entry_failed("dead_tape:...")`, `return` (entry SKIPPED) |
| Engine WB | `wb_bot.py:505-521` | Same pattern (with `now_iso_et()` prefix) |

**Squeeze ARM paths (`bot_v3_hybrid.py` squeeze + engine `squeeze_bot.py`)
do NOT import `tape_quality` or call `is_dead_tape()`.** Verified by grep:
zero hits for `tape_quality` or `is_dead_tape` in either squeeze-side file.

**Caveat — directive framing vs. code reality:**
The Track 1 checklist line says "Dead-tape gate running observe-only — verify
it computes and logs but does not gate entries." The shipped code (in line
with the original 5/15 dead-tape directive, which explicitly required ATRA
5/15 to VETO) is **enforce mode**: on WB ARM, a dead tape returns out of the
handler. The `[DEAD_TAPE_OBSERVE]` log line at `bot_alpaca_subbot.py:977` /
`wb_bot.py:517` is emitted only on the PASS branch (telemetry for
threshold-tuning). On the VETO branch, the log tag is `[CHOP_REJECT]`.

**Impact on squeeze Monday readiness:** None. Squeeze ARM never calls the gate.

**Verdict:** PASS for the squeeze readiness question (gate is wired and does
not touch the squeeze codepath). The "observe-only" framing in the current
directive is a wording mismatch with the actual prod state, which Cowork
should reconcile before relying on dead-tape behavior for WB gating
decisions. This does not block Monday open.

---

## 5. No-overnight constraint enforced — **PASS**

The no-overnight constraint is implemented as the 19:55 ET force-exit
described in §2. Coverage across **all four** production paths is confirmed
(not just one):

| Path | Squeeze force-flat | WB force-flat |
|---|---|---|
| Setup A main (`bot_v3_hybrid.py`) | line 1998-2015 iterates `state.open_position` | line 2017-2032 iterates `state.wb_positions` |
| Setup A subbot (`bot_alpaca_subbot.py`) | n/a (no squeeze in subbot) | line 2434+ iterates `state.wb_positions` |
| Engine `wb_bot.py` | n/a (squeeze runs in `squeeze_bot.py`) | line 1057-1091 daemon thread iterates `self.positions` |
| Engine `squeeze_bot.py` | line 1112-1147 daemon thread iterates `self.positions` | n/a |

All four daemon threads / loop hooks call `force_exit.should_force_exit_now()`
(latch-protected) and then `force_exit_position()` (SELL LIMIT only). No
positions can carry overnight if the bots are running at 19:55 ET.

Combined with the FCHL P0.1 fix, the only known way to carry a position past
session close is if all four bots are stopped before 19:55 ET on a given day.
Even then, the next-morning broker-reconcile at boot time will adopt the
orphan into management with a default 1% stop (per `_resume_rehydrate` orphan-
adoption path documented in the FCHL fix report).

**Verdict:** PASS.

---

## 6. Git log since Friday 5/15 close (~16:00 ET)

Note: the P0 ship commits are dated 15:08-15:49 ET on Friday 5/15 (i.e.,
before the literal 16:00 close cutoff). They are listed here because the
directive's Track 1 framing treats them as "Saturday's P0 ship" — the
`cowork_reports/2026-05-16_*.md` files documenting them are dated 5/16 per
report-naming convention, but the commits themselves landed Friday afternoon.
Confirmed via `git log --pretty=format:"%h|%ad|%s"`.

Two branches in scope: `v2-ibkr-migration` (Setup A) and `data-engine-unified`
(Setup B engine).

| Commit | Date (ET) | Branch | Message | Files touched (key) |
|---|---|---|---|---|
| `1d35c10` | 2026-05-15 15:08 | v2-ibkr-migration | P0.1 + P0.2 + P1.3 (Setup A) | `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `force_exit.py`, `.env` |
| `79d4be7` | 2026-05-15 15:09 | data-engine-unified | engine: P0.1 + P0.2 + P1.3 | `engine_bot_common.py`, `wb_bot.py`, `squeeze_bot.py`, `force_exit.py`, `.env.engine.local` |
| `bd043c3` | 2026-05-15 15:17 | v2-ibkr-migration | P1.2 — Dead-tape gate ship (Setup A WB) | `tape_quality.py`, `bot_alpaca_subbot.py`, `.env` |
| `0f0f729` | 2026-05-15 15:18 | data-engine-unified | P1.2 — Dead-tape gate ship (engine WB) | `tape_quality.py`, `wb_bot.py`, `.env.engine.local` |
| `4e49f35` | 2026-05-15 15:43 | v2-ibkr-migration | P1.1 — L2 async-thread refactor (Setup A) | `l2_helper.py`, `bot_v3_hybrid.py`, `bot_alpaca_subbot.py` |
| `bd0c955` | 2026-05-15 15:43 | data-engine-unified | P1.1 — L2 async-thread refactor (engine) | `l2_helper.py`, `wb_bot.py`, `squeeze_bot.py` |
| `e4a5297` | 2026-05-15 15:49 | v2-ibkr-migration | L2 hotfix — drop isSmartDepth=True | `l2_helper.py`, `ibkr_feed.py`, `.env` (L2 flags 1→0) |
| `a92319d` | 2026-05-15 15:49 | data-engine-unified | L2 hotfix — drop isSmartDepth=True (engine mirror) | `l2_helper.py`, `ibkr_feed.py`, `.env.engine.local` |
| `d0ff678` | 2026-05-15 15:50 | v2-ibkr-migration | cowork_reports: 3 Saturday reports — FCHL fix, L2 async refactor, dead-tape | report MD files |
| `f97e1cb` / `f612c3d` | 2026-05-15 18:00 | v2-ibkr-migration | auto: v3 daily logs 2026-05-15 | logs |
| `b5f5217` | 2026-05-15 18:05 | data-engine-unified | auto: engine daily logs 2026-05-15 | logs |
| `074095c` | 2026-05-15 19:49 | v2-ibkr-migration | cowork_reports: weekly strategy audits | report MD files |
| `ddb9589` | 2026-05-15 20:11 | v2-ibkr-migration | cowork_reports: 2026-05-15 daily breakdown — late-day addendum | report MD files |
| `8431909` | 2026-05-15 20:58 | v2-ibkr-migration | cowork_reports: 4 forensic investigations + synthesis (loser forensic) | report MD files |
| `9e3d1e0` | 2026-05-15 23:26 | v2-ibkr-migration | cowork_reports: L2 state clarification (re-enable→disable timeline) | report MD files |
| `d1d3ca5` | 2026-05-16 01:59 | v2-ibkr-migration | Weekend response — Saturday ships closed, audits processed | directive MD |
| `ba94094` | 2026-05-16 02:40 | v2-ibkr-migration | Loser forensic — 5 diagnostic investigations for next week | directive MD |
| `593689c` | 2026-05-16 02:44 | v2-ibkr-migration | Amend loser forensic — compress timeline | directive MD |
| `9497f87` | 2026-05-16 02:45 | v2-ibkr-migration | Clarification — no overnight holds changes the risk picture | directive MD |
| `945dad7` | 2026-05-16 03:04 | v2-ibkr-migration | Forensic synthesis response — lock in findings, June 15 squeeze-only | directive MD |
| `de6fb39` | 2026-05-16 03:25 | v2-ibkr-migration | Video methodology extraction | directive MD |
| `34e2b0f` | 2026-05-16 03:41 | v2-ibkr-migration | Bot vs human reframe — WB retirement, new roadmap | directive MD |
| `1704018` | 2026-05-16 03:50 | v2-ibkr-migration | Healthy fluctuation framework — the project's actual purpose | directive MD |
| `8c38625` | 2026-05-16 04:21 | v2-ibkr-migration | Planning kickoff — 5 research workstreams running in parallel | directive MD |
| `9a2bc23` | 2026-05-16 04:31 | v2-ibkr-migration | Healthy Fluctuation Framework — unified design doc | docs |
| `c83152c` | 2026-05-16 04:44 | v2-ibkr-migration | Update design doc with Manny review decisions | docs |
| `e7bbd30` | 2026-05-16 04:52 | v2-ibkr-migration | Framework build directive with full context for CC | directive MD |
| `b5352ab` | 2026-05-16 01:11 | v2-ibkr-migration | framework: Wave 1 — backtest infra + protocols + universe + confirmations + sizing | new `framework/` tree, `backtest/`, tests |
| `4fe3687` | 2026-05-16 01:15 | v2-ibkr-migration | fix: date error in Path-1 decision note | doc |
| `3c8d265` | 2026-05-16 01:59 | v2-ibkr-migration | wave 2: 4 strategy backtests on healthy fluctuation framework | `backtest/`, strategies/, tests |
| `808ad52` | 2026-05-16 02:40 | v2-ibkr-migration | wave 3: portfolio backtest + walk-forward + synthesis | `backtest/walk_forward*`, reports |
| `5b9c8fe` | 2026-05-16 03:16 | v2-ibkr-migration | wave 5: phase 2 strategies (volume profile, anchored vwap, l2) | `framework/confirmations/`, `backtest/`, strategies/, tests |
| `a5b5280` | 2026-05-16 15:18 | v2-ibkr-migration | Framework build response — approvals, decisions, Wave 4 held for Manny | directive MD |
| `165e61c` | 2026-05-16 16:46 | v2-ibkr-migration | Detailed PDH-Fade breakdown | doc |
| `320ad8d` | 2026-05-16 16:58 | v2-ibkr-migration | Strategy forensics — 6 parallel investigations | directive MD |
| `a207151` | 2026-05-16 11:19 | v2-ibkr-migration | forensics: 6 parallel investigations on Wave 3 trade data + synthesis | `analysis/`, `forensics_orb/`, `backtest_archive/`, reports |
| `07c014e` | 2026-05-16 17:35 | v2-ibkr-migration | Forensic response — transformed deployment | directive MD |
| `9bd70b3` | 2026-05-16 18:04 | v2-ibkr-migration | Sizing schedule — $300 baseline to $2500 target via 9-tier ladder | directive MD |
| `6b445e0` | 2026-05-16 18:12 | v2-ibkr-migration | Add combined squeeze + framework portfolio backtest directive | directive MD |
| `6c2e493` | 2026-05-16 18:14 | v2-ibkr-migration | GO FOR BUILD: all 8 decisions approved by Manny | directive MD |
| `e623ea0` | 2026-05-16 14:11 | v2-ibkr-migration | GO-FOR-BUILD: 8 approved decisions — Wave 4 pre-deploy build | `.env.framework`, `framework/*`, strategies/, tests, reports |
| `e786d09` | 2026-05-18 05:42 | v2-ibkr-migration | Engine paper -> Framework deploy directive (Wave 4 live) | directive MD |
| `6a71c94` | 2026-05-18 05:45 | v2-ibkr-migration | Amend engine deploy: reuse Setup B Alpaca keys, retire old engine bot | directive MD |

**Production-code commits in this window:** `1d35c10`, `79d4be7`, `bd043c3`,
`0f0f729`, `4e49f35`, `bd0c955`, `e4a5297`, `a92319d` (eight commits, all on
Friday 5/15 15:08-15:49 ET, all explicitly covered by the P0 verification
above). Every other commit in the window is reports, directives, framework
research (no impact on squeeze production), or auto-generated daily logs.

---

## Code-quality concerns found incidentally (no action taken)

These were observed while verifying P0s. None blocks Monday open; all are
flagged here only for future cleanup consideration.

1. **`MarketOrder` import is unused (V2 bots).** `bot_v3_hybrid.py:41` and
   `bot_alpaca_subbot.py:75` import `MarketOrder` from `ib_insync` but never
   instantiate it. Safe to leave (no behavioral impact); removing on a quiet
   day would close the audit surface for "could the bot ever submit a
   market order?".

2. **L2 helper sleep timing.** `l2_helper._bg_fetch_l2_async` uses
   `await asyncio.sleep(0.1)` (line 165) for polling — at 2.0s timeout that's
   up to 20 polls per snapshot, with detector state-build happening every
   iteration even when the book is empty. Not a correctness issue; could
   degrade gracefully if many concurrent ARMs fire. Latency telemetry was
   already flagged as an open item in the Saturday async-refactor report.

3. **Dead-tape gate framing.** As noted in §4, the gate is enforce mode in
   production but described as observe-only in the Track 1 directive.
   Recommend Cowork update the directive language; the code matches the
   original 5/15 dead-tape directive's acceptance criteria.

4. **`v2-ibkr-migration` working tree has uncommitted modifications** in
   `.claude/worktrees/compassionate-zhukovsky` and
   `.claude/worktrees/tender-gauss` (submodule modified-content) plus log
   files and `scanner_results/float_cache.json`. These are operational
   artifacts of the Friday session, not P0 production code. The eight P0
   commits listed in §6 are fully landed and pushed.

---

## Monday-morning re-enable smoke test (carried over from Sat report)

Per `2026-05-17_l2_state_clarification.md`, the planned Monday smoke test for
L2 is:

1. Before 09:30 ET, flip the four `WB_L2_FILTER_*ENABLED` flags from `0` to
   `1` in both `.env` files
2. Watch the first WB or squeeze ARM. Expected log lines:
   - `[L2] bg-thread IB connected (127.0.0.1:4002 clientId=NN)` on first lazy init
   - `[L2] <prefix> <SYM> state=imb=X.XX spread=Y.YY% ... verdict=PASS|VETO reason=...`
3. If 30 minutes of clean ARMs with no `IndexError` / `event loop already
   running` traceback → L2 confirmed back live in observe-only mode
4. If problems → revert env to 0, file the issue, defer to backtest framework

This is **not blocking** for the squeeze Monday open — squeeze ships with L2
env-disabled, which is the current state.

---

## Final P0 checklist

| # | P0 | Verdict | Evidence |
|---|---|---|---|
| 1 | FCHL session-resume fix | PASS | `engine_bot_common.py:1208-1257`, `wb_bot.py:1123-1134`, `squeeze_bot.py:1192-1203`, env `WB_SESSION_RESUME_ENABLED=1` |
| 2 | Force-exit 19:55 ET SELL LIMIT chain | PASS | `force_exit.py:148` (limit-only), wired into all 4 bots, env `WB_SESSION_END_FORCE_EXIT=1` |
| 3 | L2 async refactor merged | PASS (code) / env disabled | `l2_helper.py:56-128, 198-230`, per-bot clientId at `bot_v3_hybrid.py:27`, `bot_alpaca_subbot.py:48`, `wb_bot.py:17`, `squeeze_bot.py:25`. Env `WB_L2_FILTER_ENABLED=0` (intentional) |
| 4 | Dead-tape gate (WB only) | PASS | `tape_quality.py`, wired at `bot_alpaca_subbot.py:962-981` + `wb_bot.py:505-521`. Enforce mode (not observe-only — see §4 caveat). Squeeze unaffected. |
| 5 | No-overnight constraint | PASS | All 4 paths flat by 19:55 ET via force-exit; documented in §5 |

**Overall: GREEN. Squeeze ships Monday 2026-05-18 unchanged.**
