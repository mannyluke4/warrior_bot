# Engine Paper → Framework Deploy (Wave 4 Live)

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Sun 11:41 PM MDT)
**Status:** GO — direct engine paper deploy, no combined backtest gate

---

## What changed from the previous directive

Manny's call (verbatim):
- "We'll do option 3 for squeeze. Leave as is. Keep watching."
- "Don't worry about backtesting the new strat with squeeze. Let's just set it up in engine and watch closely."
- "Let's get CC started on that first. While it's working, I'll explain the new WB setup."

Implications:
- **Squeeze:** no code changes Monday. Sunday-night readiness check still required to confirm Saturday's P0 landed.
- **D3 / combined backtest:** **DROPPED from this round.** No D3a sanity slice, no IBKR-tick-cache adapter, no 5-year reconstruction. Removed from the queue entirely.
- **Engine paper deploy:** runs directly. The framework is its own validation — paper data IS the validation.
- **WB v2:** queued, awaiting Manny's explainer.

---

## Track 1 — Squeeze readiness (no code changes)

Single CC deliverable Sunday night before Monday open:

**`cowork_reports/2026-05-18_squeeze_monday_readiness.md`** — file-by-file PASS/FAIL of Saturday's P0:
- [ ] FCHL session-resume fix verified
- [ ] Force-exit at 19:55 ET (SELL LIMIT chain, no market orders) live in production path
- [ ] L2 async refactor merged
- [ ] Dead-tape gate running observe-only
- [ ] No-overnight constraint enforced
- [ ] `git log --oneline` of everything that landed since Friday close

**If any P0 is FAIL, halt Monday open until resolved.** Otherwise, squeeze ships unchanged.

Also resolve the audit's outstanding hygiene item:

**`cowork_reports/2026-05-18_sle_evening_fill_clarification.md`** — confirm whether any engine SLE fill occurred in extended hours 5/15 (the audit couldn't find it in the engine log). Setup B's 5/15 shutdown shows `daily_pnl=$-445.58, open_positions=0` — only morning SLE fill. Reconcile or correct the record. Not Monday-blocking.

---

## Track 2 — Engine paper goes framework (the main work)

**Account:** Engine paper (the high-equity Alpaca paper account previously used by the engine bot — repurposed)
**clientId:** 51 (separate from squeeze)
**Persistence:** `framework_paper_state/`
**Strategies armed:**
- PDH-Fade-Filtered (F1-alone, abandon@10 OFF — Sharpe 1.56 / OOS 1.30)
- ORB-Aligned-$300+ Mon-skip (post-revalidation)
- PDH-Breakout-F4 (Sharpe 2.81 OOS)

**Sizing:** TieredSizer at Tier 1, locked 60 days (`WB_TIER_LOCK=1`)
**Defaults (`.env.framework`):**
- `WB_FRAMEWORK_SKIP_MONDAYS=1`
- `WB_USE_VIX_REGIME=1`, suppress 25, hysteresis 22
- `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop`
- `WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1`
- `WB_SIZING_MODE=tiered`, `WB_TIER_INITIAL=1`, `WB_TIER_LOCK=1`, `WB_TIER_AUTO_ADVANCE=0`
- `WB_NO_MARKET_ORDERS=1`, `WB_NO_OVERNIGHTS=1`, `WB_NO_BROKER_STOPS=1`
- `WB_FRAMEWORK_IB_CLIENT_ID=51`
- `WB_FRAMEWORK_PAPER_ACCOUNT=framework_paper`

### Pre-launch checklist (CC, in this order)

1. **ORB 36-name parity revalidation** (~30 min) — confirm 2.10 OOS holds on full universe. If it doesn't, halt and report. (B1 ran on slim 12-name; this is the proper full-universe check.)
2. **Engine paper account stand-up** — **REUSE the existing Setup B Alpaca paper keys** (Manny: "same alpaca paper keys that setup b is already using"). No new keys to provision. Wire them into the framework launch via the existing engine credentials. Launch with clientId 51 and the framework persistence file. **Critically: the previous engine-bot strategy on this account is retired — the framework replaces it. Confirm no orphaned engine-bot processes remain on the account before framework goes live.**
3. **Dry-run verification** — start the framework process, confirm it connects to the engine paper account, confirm strategies arm, confirm TieredSizer reads Tier 1 locked, confirm `.env.framework` defaults loaded correctly. **Do NOT take live signals yet.** Just verify wiring.
4. **Monday open soft launch** — strategies live, but the first session runs with extra-verbose logging (every signal, every conflict event, every tier-lock check). CC reviews evening report; if anything is off, freeze before Tuesday.

### Daily reporting

Starting Monday evening:
- Equity (start, end, intraday HWM/LWM)
- Per-strategy P&L (PDH-Fade, ORB, PDH-Breakout)
- Conflict events (`release_on_stop` triggers, lock collisions)
- Tier status (locked at 1, advancement gates would-have-fired count)
- Force-exit events (any positions closed at 19:55)
- Anomalies / surprises

File: `cowork_reports/YYYY-MM-DD_engine_framework_daily.md`

### What's been dropped

- ❌ D3a (IBKR-tick-cache adapter)
- ❌ D3b (2020-2024 universe + tick reconstruction)
- ❌ D3c (combined 5-year backtest)
- ❌ Squeeze framework migration validation runs

All of these can come back later if Manny wants combined-portfolio analysis. For now, paper data IS the validation.

---

## Track 3 — WB v2 (PAUSED pending Manny's explainer)

CC does NOT start any WB v2 work until Manny posts the new WB setup explainer. Then Cowork translates that into a research directive and CC begins Stage 0 (methodology doc + trade intake template + setup taxonomy seed).

The old WB stays at `WB_STRATEGY_ENABLED=0`. No archival yet — wait until WB v2 has its own folder structure decided post-explainer.

---

## Hard constraints (unchanged)

- Setup A is sacred. No modifications to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`.
- Branch: `v2-ibkr-migration` only.
- Alpaca only — no IBKR paper.
- No overnights anywhere — force-exit before close.
- No market orders — SELL LIMIT chains only.
- Squeeze 6/15 real-money cutover unchanged.

---

## CC work queue (priority order)

1. **Sunday night (now):** Squeeze Monday readiness check + SLE evening fill clarification. Halt if P0 FAIL.
2. **Monday pre-open:** ORB 36-name parity revalidation (~30 min).
3. **Monday pre-open:** Engine paper account stand-up using Manny's Alpaca paper keys → `.env.framework.local`.
4. **Monday pre-open:** Dry-run verification (wiring, no live signals).
5. **Monday open:** Framework soft launch on engine paper account, verbose logging.
6. **Monday evening:** First daily report.
7. **PAUSED:** WB v2 (awaiting Manny's explainer).

---

## What Manny needs to provide

1. ~~Engine paper Alpaca API keys~~ — **resolved.** Reuse Setup B's existing Alpaca paper keys. No new credentials needed.
2. **The WB v2 explainer.** No rush — CC is busy with the engine deploy.

## Coordination note (engine bot retirement)

The previous engine-bot strategy that ran on the Setup B Alpaca paper account is being retired in favor of the framework. CC must:
- Confirm the old engine-bot process is stopped before framework launch (no two strategies on one account).
- Decide whether old engine-bot code stays in repo (suggest: yes, with `ENGINE_BOT_ENABLED=0`, same pattern as old WB) or moves to a `_retired/` folder. Cowork suggests gating with env var for now; archive later if Manny wants the cleanup.

---

GO.
