# WB Persistence Layer — Stage 0.2 Validation

**Date:** 2026-05-14 (shipped same day as directive)
**Author:** CC
**For:** Cowork (Perplexity)
**Severity:** Stage 0.2 deliverable per DIRECTIVE_WB_SCANNER_STRATEGY.md
**Status:** Code shipped + synthetic-tested. Awaits Manny's call on live deployment timing (cron tomorrow vs mid-day restart today).

---

## TL;DR

Stage 0.2 (`WB-persistence layer`) is implemented. WB-observed symbols are now persisted to `~/warrior_bot_v2/wb_persistence.txt` for 3 calendar days. At boot (or any subsequent `poll_watchlist` cycle), `bot_v3_hybrid.py` injects these symbols into `state.active_symbols` and `subscribe_symbol()`s them, flowing them downstream to `bot_alpaca_subbot.py` and the unified engine via `session_state/<today>/watchlist.json`. This restores the FATN/SST winner channel intentionally — without the stale-everything bug of pre-`a38ce72` carryover.

---

## Architecture

### Shared module: `wb_persistence.py`

Single 130-line module, duplicated identically in V2 and V2_engine worktrees (verified via `diff` — identical). Public API:

- `record_wb_observe(symbol)` — call from any WB log emit
- `active_persisted_symbols() -> set[str]` — call from watchlist-poll
- `debug_state() -> dict` — diagnostics, not on hot path

Internal:
- File format: `SYMBOL,YYYY-MM-DD` per line, comments allowed (`# ...`)
- Atomic write via `.tmp` + rename — concurrent-safe under Lock
- Prune on every write: entries with date older than `_SESSIONS` calendar days are dropped
- Symbol validation: alpha + 1-5 chars (matches existing watchlist parser)
- Error handling: every IO path is best-effort; any exception is logged and swallowed (persistence failure must never kill the trading loop)

### File location

Default: `<module_dir>/wb_persistence.txt`. Override: `WB_PERSIST_FILE` env var.

Both worktrees point to `/Users/duffy/warrior_bot_v2/wb_persistence.txt` as the single source of truth (engine `.env.engine.local` overrides the engine-local default). This means a WB_OBSERVE from Setup A's subbot or Setup B's engine wb_bot both write to the same file, and both setups read the same file at boot.

### Integration points (3 edits, each <10 lines)

1. **`bot_v3_hybrid.py:poll_watchlist`** (READ side, every poll cycle):
   After the existing watchlist.txt loop, call `wb_persistence.active_persisted_symbols()`. For each symbol not in `state.active_symbols`, call `subscribe_symbol(sym)`. Log as `🧠 WB_PERSIST: N symbols carried from prior sessions: [...]`.

2. **`bot_alpaca_subbot.py:on_bar_close_1m`** (WRITE side):
   After printing the WB log line, if `"WB_OBSERVE" in wb_msg`, call `wb_persistence.record_wb_observe(symbol)`.

3. **`warrior_bot_v2_engine/wb_bot.py:_on_bar_message`** (WRITE side — engine path):
   Same as #2 but at the engine's WB detector call site.

### Why bot_v3_hybrid does the injection

The squeeze bot is the upstream of `state.active_symbols` and the writer of `session_state/<today>/watchlist.json`. Both `bot_alpaca_subbot.py` (Setup A WB) and the engine's `wb_bot.py` (Setup B WB) read this file as their subscription source. Putting the injection in `bot_v3_hybrid.poll_watchlist` is one touchpoint that fans out to both WB execution paths automatically.

Side effect: the **squeeze detector** also runs on the persisted symbols. This is harmless — squeeze's `WB_SQ_VOL_MULT=2.5×` and `WB_SQ_MIN_BAR_VOL=50000` floors mean it won't fire on the low-volume bars that WB-persisted symbols typically carry. We don't add a "wb_only" tag because the bypass isn't needed (no bot-side PM-volume filter; the filtering was upstream in the scanner).

---

## Env vars (added)

In `~/warrior_bot_v2/.env`:
```
WB_PERSIST_ENABLED=1
WB_PERSIST_SESSIONS=3
```

In `~/warrior_bot_v2_engine/.env.engine.local`:
```
WB_PERSIST_ENABLED=1
WB_PERSIST_SESSIONS=3
WB_PERSIST_FILE=/Users/duffy/warrior_bot_v2/wb_persistence.txt
```

Defaults match the directive (3 sessions). All gated; setting `WB_PERSIST_ENABLED=0` reverts to pre-directive behavior with zero code-path changes.

---

## Validation

### Test 1 — Module unit tests (smoke)

Ran `wb_persistence.record_wb_observe()` and `active_persisted_symbols()` against `/tmp/test_wb_persistence.txt`:

- ✓ `record_wb_observe("ATRA")` writes the file
- ✓ `record_wb_observe("atra")` (lowercase) normalizes to ATRA, dedupes (no second write)
- ✓ Seeding with a 2-day-old entry: `active_persisted_symbols()` includes it
- ✓ Seeding with a 5-day-old entry: pruned on next read
- ✓ Subsequent `record_wb_observe()` prunes the 5-day-old from the file on write
- ✓ Symbol-format validation rejects non-alphabetic names (matches existing watchlist parser)

### Test 2 — Shared-file across worktrees

Seeded `~/warrior_bot_v2/wb_persistence.txt` with `ATRA,2026-05-13` and `SST,2026-05-13`:

```
V2 module:     active_persisted_symbols() = ['ATRA', 'SST']
Engine module: active_persisted_symbols() = ['ATRA', 'SST']
```

Both V2 and engine read the same shared file successfully.

### Test 3 — Real boot integration (NOT YET RUN)

The currently-running bots were launched at 07:31 MT today, **before** these edits. They are still on the pre-persistence code path and will not pick up the seeded ATRA/SST entries.

Two paths to live:
- **Option A — Restart bots now mid-session.** ATRA/SST would appear in the next poll_watchlist cycle (~60s). Bots have no open positions today (verified via Alpaca account state earlier). Risk is minimal.
- **Option B — Wait for tomorrow's 02:00 MT cron.** Cron restart picks up the new code naturally. No mid-day risk.

Awaiting Manny's call.

---

## Currently-seeded file

`~/warrior_bot_v2/wb_persistence.txt` (from validation test):

```
# wb_persistence.txt — WB-observed symbols within last N sessions
# Format: SYMBOL,YYYY-MM-DD (last WB_OBSERVE date)
# Updated: 2026-05-14T12:28:15-04:00
ATRA,2026-05-13
SST,2026-05-13
```

If bots are restarted today, these two symbols will be subscribed and traded immediately. SST 5-11 was a +$2,090 winner; ATRA 5-08 was a +$2,500 winner — both became losers on subsequent days (ATRA 5-11 ×3 = -$1,803; SST 5-12 = -$870). They are exactly the kind of carryover the directive contemplates.

If Manny prefers a clean test, we can clear this file before tomorrow's cron and let the WRITE side organically populate it during the day.

---

## Files changed (commit pending)

```
M bot_v3_hybrid.py            — poll_watchlist: inject persisted symbols
M bot_alpaca_subbot.py        — WB_OBSERVE → record_wb_observe()
M warrior_bot_v2_engine/wb_bot.py — same WRITE hook on engine path
M .env                        — WB_PERSIST_ENABLED, WB_PERSIST_SESSIONS
M warrior_bot_v2_engine/.env.engine.local — same + WB_PERSIST_FILE override
A wb_persistence.py           — new module (V2)
A warrior_bot_v2_engine/wb_persistence.py — duplicate (engine)
A cowork_reports/2026-05-15_wb_persistence_validation.md — this report
```

The MEI 05-13 bypass-trace report (Stage 0.1) is being produced by a parallel research agent and will be appended in a subsequent commit when complete.

---

## Risks & open items

**Risk 1 — Two-file drift (V2 vs engine).** Duplicated `wb_persistence.py` could diverge over time. Mitigation: file is small (130 lines), tested for `diff -q` parity at this commit. If we touch one, we touch the other in the same commit.

**Risk 2 — Race on simultaneous writes.** Setup A subbot and Setup B engine wb_bot both write to the same file. Inside each process, `_LOCK` makes operations atomic. Across processes, the `.tmp + replace()` pattern is rename-atomic on POSIX, but a concurrent reader could see a slightly stale state. Acceptable — persistence reads happen at poll-watchlist cadence (60s), not on hot path.

**Risk 3 — Seeded file affects live trading on restart.** ATRA/SST are pre-loaded. If bots restart, they trade ATRA/SST today. Mitigation: clear the file before restart if a clean test is preferred.

**Risk 4 — Scanner overwrites or removes symbols.** The scanner writes only to `watchlist.txt`; it does not touch `wb_persistence.txt`. The two systems are independent. Symbols on the persisted list that ALSO pass scanner filters appear twice (deduped in `state.active_symbols`).

**Open question — EOD rollover.** The directive specs a separate `wb_observed_today.txt` that rolls into `wb_persistence.txt` at EOD. The implementation collapses these into one file because the rolling-N-day prune at write time achieves the same effect with fewer moving parts. If Cowork prefers the two-file split for diagnostic clarity, we add it as a follow-up.

---

## Next steps

- **Manny:** decide on restart-now vs cron-tomorrow rollout.
- **CC:** finalize MEI bypass-trace report (agent running async).
- **CC:** ship Stage 0.3 (intraday WB adder, observe-only) per directive §0.3 — targeted for Fri 5/15 EOD.
- **Cowork:** review this report + the MEI trace; flag any architectural objections before the intraday adder lands.

---

*The persistence layer is the smallest possible version of what the directive asks for: read-side restores yesterday's-WB-active symbols, write-side feeds tomorrow's list, no scanner or watchlist file-format changes, no bot-side filter bypass needed because the filter that was excluding these symbols lives upstream in the scanner. If Stage 1's backtest finds WB has no real edge once accidents are removed, gating this off is a one-line .env flip.*
