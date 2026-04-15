# Plan — Session Resume (crash-recovery within trading day)

**Author:** CC (Opus)
**Date:** 2026-04-15 afternoon
**Status:** DRAFT — awaiting Manny's OK before implementation

---

## Goal

On restart within the same trading day, the bot resumes within seconds instead of re-running the full boot (scanner wide scan, float lookups, per-symbol `reqHistoricalTicks` seeding). Cold-start only on: first launch of the day, explicit `--fresh`, or corrupted session dir.

Target win: crash at 09:30 → back online by ~09:32 instead of 09:37+.

---

## Approach: Option B (tick-replay, agreed with Manny)

Persist a minimal set of durable facts; reconstruct everything derivable by replaying cached ticks into fresh detectors.

### What gets persisted

```
session_state/YYYY-MM-DD/
  marker.json          # exists iff today's session has run → boot decides resume vs cold
  watchlist.json       # [{"symbol": "FCUV", "subscribed_at": "..."}...]
  risk.json            # daily_pnl, daily_trades, consecutive_losses, closed_trades
  epl_state.json       # epl_watchlist graduated symbols + registry state (best-effort)
tick_cache/YYYY-MM-DD/
  <SYM>.json.gz        # ALREADY EXISTS — append-only tick log from 04:00 ET
```

Everything else (detectors, bar builders, VWAP/HOD, arms, seed state) is **rebuilt by tick replay** — never serialized.

### New: periodic tick-buffer flush

Today `state.tick_buffer` only hits disk at shutdown (line ~2353). Ungraceful shutdown = lost ticks = can't replay the gap. Add a background thread that flushes the buffer to `tick_cache/<today>/<sym>.json.gz` every 30s. Cheap (append, gzip) and bounds crash loss to ≤30s of ticks per symbol.

### Boot decision

```
if --scrub:                       → rm -rf session_state/<today> tick_cache/<today>, then cold
elif --fresh:                     → cold start, overwrites marker
elif session_state/<today>/marker.json exists:
                                  → RESUME mode
else:                             → cold start, writes marker
```

### Resume mode flow

1. Alpaca connect + `reconcile_positions_on_startup()` (unchanged — always runs).
2. IBKR connect (unchanged).
3. Load `session_state/<today>/risk.json` → restore `state.daily_pnl`, counters, `closed_trades`.
4. Load `session_state/<today>/watchlist.json` → list of symbols we were tracking.
5. For each symbol:
   - `qualifyContracts()` (fast)
   - `init_detectors(symbol)` (fresh instances)
   - **Replay path** instead of `seed_symbol()`:
     - Read `tick_cache/<today>/<sym>.json.gz` (all ticks from 04:00 ET through crash time)
     - Split at 07:00 ET → `begin_seed()` → replay seed ticks → `end_seed()` → replay live ticks
     - Skips `reqHistoricalTicks` entirely
   - `reqMktData()` to re-subscribe to live stream
6. Start periodic flush thread.
7. Start Databento poll + scanner rescan on normal cadence.

### Cold mode flow

Unchanged from today, plus:
- Write `session_state/<today>/marker.json` immediately after Alpaca connects.
- Write `watchlist.json` on every `subscribe_symbol()` call.
- Write `risk.json` on every trade exit + every 60s.
- Start periodic flush thread.

---

## Gating

```bash
WB_SESSION_RESUME_ENABLED=0    # master gate, DEFAULT OFF for first ship
WB_SESSION_FLUSH_SEC=30        # tick-buffer flush interval
```

`=0` → current behavior everywhere (no writes to session_state/, no resume attempts, periodic flush still runs if you want crash-safety only on the tick cache — see open question #3).

---

## CLI

```
python bot_v3_hybrid.py              # auto-decides based on marker
python bot_v3_hybrid.py --fresh      # force cold start
python bot_v3_hybrid.py --scrub      # wipe today's session + tick cache, then cold
```

---

## What does NOT change

- `simulate.py` — untouched.
- Detector code — untouched (they're already replay-safe).
- Scanner/watchlist filter logic — untouched.
- Position reconciliation — unchanged (Alpaca is source of truth).
- Evening dead-zone reset (12:00–16:00 ET) — unchanged. On dead-zone exit, bar builders reset and it's effectively a fresh box-session anyway.

---

## Risks & mitigations

1. **Stale tick cache from previous day.** Mitigated: session dir is date-stamped; cold boot on new day regardless.
2. **Partial flush mid-crash corrupts gz.** Mitigated: atomic write (tmpfile + rename) per flush cycle.
3. **Replay produces slightly different detector state if a detector field was added between crash and restart.** Mitigated: detectors reconstruct from tick sequence, not pickled state; any code change is absorbed. Only risk is if a detector's constructor changed behavior — rare, and cold-start is always available via `--fresh`.
4. **EPL watchlist graduation state.** If `epl_state.json` load fails, log a warning and start with empty EPL state. EPL graduation is a 2R-profit feature, not critical for first session.
5. **Box engine state.** Box strategy has its own engine with box_bottom/box_top/trades. Defer — if a crash interrupts an active box setup, accept that it reconstructs from bars on restart. Mark as follow-up.
6. **Open position mid-trade.** Alpaca position reconcile already handles this (line 2100). Works in resume mode too.

---

## Open questions for Manny

1. **Periodic flush without resume?** Should `WB_SESSION_RESUME_ENABLED=0` still run the 30s tick-buffer flush? Arg for yes: you lose nothing on crashes for backtesting data. Arg for no: keep the feature fully isolated behind one gate.
2. **EPL state persistence — best effort or skip for v1?** EPL is already off/opt-in, safe to defer.
3. **Box position persistence — defer?** Box strategy has complex engine state. Simplest v1: box resets on resume, any open box position flattens via reconcile.
4. **`--scrub` scope.** Should it also nuke `float_cache.json`? I'd vote no — float cache is global and 3hr-TTL anyway.
5. **Replay log verbosity.** A resume of 5 symbols with 50k ticks each is ~250k tick replays. I'll log one-liner per symbol on completion ("RESUME SEED: FCUV 42,133 ticks → SQ state=WATCHING, MP state=IDLE, 3 arms"). OK?

---

## Implementation order

1. New module `session_state.py` — write/read helpers, atomic flush, scrub logic.
2. Periodic flush thread (cheapest, most independently-valuable).
3. Boot-time marker + CLI flags.
4. Resume-mode `seed_symbol()` replacement.
5. Risk / watchlist / EPL write points.
6. Local test: start bot in paper, let it seed FCUV or whatever's live, `kill -9`, restart, confirm it picks up without re-seeding.
7. Regression: VERO/ROLR unchanged (sim untouched, should be trivially green).

Estimated diff: ~400 lines. One commit, gated off by default.

---

*Awaiting green light to proceed.*
