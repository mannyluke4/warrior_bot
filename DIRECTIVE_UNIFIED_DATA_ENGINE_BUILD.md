# DIRECTIVE: Unified Data Engine — Build & Deploy by Monday Open

**Date:** May 9, 2026 (Saturday)  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — paper live by Monday May 11, 04:00 ET  
**Branch target:** new worktree `data-engine-unified` off `v2-ibkr-migration`  
**Predecessors:**
- `cowork_reports/2026-05-09_unified_data_engine_proposal.md` (CC's proposal — read first)
- `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (yesterday's session detail)
- `DIRECTIVE_CORRECTNESS_FIXES_MONDAY.md` (the two correctness fixes already shipped)

---

## What This Is

CC's proposal to replace the dual-bot architecture with a unified data engine + thin strategy bots is **APPROVED**. This directive is the build spec. Goal: have Setup B running paper-live alongside Setup A on Monday May 11 at 04:00 ET, both reading the same `watchlist.txt`, both trading the same windows, with a third Alpaca paper account hosting Setup B's orders.

Three architectural decisions Cowork made vs. CC's proposal:

1. **Setup-driven priority dominates time-of-day.** Time-of-day is the tiebreaker, not the dictator. Open positions and high-confidence setups always pin Tier 1 slots regardless of clock.

2. **Engine runs WITHOUT TBT during A/B period.** Setup A keeps its current TBT allocation (5 slots on the main bot's clientId). Engine subscribes to `reqMktData('233')` only during A/B. This isolates the architecture variable from the data-quality variable. TBT capability is a Phase 3 unlock after Setup B wins the A/B.

3. **Single Alpaca paper account for engine** (the new third account). Cleaner P&L comparison: `Setup A = sum(PA3VP0LB4OID + PA3LXGIPGG8B)` vs `Setup B = PA-NEW`.

---

## Architecture (Final, Approved)

```
                          ┌────────────────────────────────────┐
                          │  IB Gateway (port 4002)           │
                          │  ONE IBKR account (data only)     │
                          │  5 TBT slots — Setup A owns all   │
                          └────────────┬───────────────────────┘
                                       │
                  ┌────────────────────┼────────────────────────────┐
                  │ clientId=1         │ clientId=2          │ clientId=3
                  ▼                    ▼                     ▼
           ┌──────────────┐    ┌──────────────┐      ┌──────────────────┐
           │ Setup A      │    │ Setup A      │      │ Setup B          │
           │ main bot     │    │ sub-bot      │      │ data_engine.py   │
           │ (squeeze)    │    │ (WB)         │      │  (NEW)           │
           │              │    │              │      │                  │
           │ TBT enabled  │    │ TBT disabled │      │ reqMktData('233')│
           │              │    │              │      │ snapshots only   │
           │ →PA3VP0LB4OID│    │ →PA3LXGIPGG8B│      │ during A/B       │
           └──────────────┘    └──────────────┘      └────────┬─────────┘
                                                              │ IPC (Unix socket)
                                                ┌─────────────┴─────────────┐
                                                ▼                           ▼
                                       ┌──────────────────┐       ┌──────────────────┐
                                       │ squeeze_bot.py   │       │ wb_bot.py        │
                                       │ (NEW, logic only)│       │ (NEW, logic only)│
                                       │                  │       │                  │
                                       │ Subscribes to    │       │ Subscribes to    │
                                       │ engine tick feed │       │ engine tick feed │
                                       │ Submits orders   │       │ Submits orders   │
                                       │ to PA-NEW        │       │ to PA-NEW        │
                                       └──────────────────┘       └──────────────────┘
```

**Key invariant:** Setup A is **untouched**. Zero modifications to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, their config, or their cron schedule. Setup B is purely additive code in a new worktree, with its own daily_run script.

---

## File Structure (New Files Only)

```
~/warrior_bot_v2/                       (worktree: data-engine-unified)
├── data_engine.py                      [NEW] The unified data daemon
├── engine_ipc.py                       [NEW] IPC contract + helpers
├── squeeze_bot.py                      [NEW] Logic-only squeeze bot (consumes engine ticks)
├── wb_bot.py                           [NEW] Logic-only WB bot (consumes engine ticks)
├── daily_run_engine.sh                 [NEW] Cron launcher for Setup B (engine + 2 bots)
├── .env.engine                         [NEW] Setup B-specific config (separate from .env)
└── logs/                               (shared with Setup A)
    ├── 2026-05-XX_engine.log           [NEW namespace]
    ├── 2026-05-XX_squeeze_bot.log
    └── 2026-05-XX_wb_bot.log
```

Existing files (`bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `daily_run_v3.sh`, `.env`) are **NOT modified**.

---

## Build Order (4 Phases, Sunday Hammer Session)

### Phase 1: IPC Contract (`engine_ipc.py`)

This is the working contract between engine and strategy bots. Build first; both engine and bots can be built against this independently.

**Message types** (all newline-delimited JSON over Unix socket):

```python
# Engine → bots: every tick
{
  "type": "tick",
  "symbol": "ATRA",
  "ts": "2026-05-08T17:09:30.123456-04:00",  # ISO 8601 with TZ
  "price": 8.65,
  "size": 100,
  "exchange": "ARCA",  # if available
  "tier": "snapshot",  # always "snapshot" during A/B (no TBT)
  "engine_seq": 12345  # monotonic per-symbol sequence number
}

# Engine → bots: bar close events (engine constructs 1m bars from ticks)
{
  "type": "bar",
  "symbol": "ATRA",
  "ts_close": "2026-05-08T17:10:00-04:00",
  "interval": "1m",
  "o": 8.60, "h": 8.65, "l": 8.60, "c": 8.65, "v": 5000,
  "vwap": 8.67,  # computed by engine from session ticks
  "engine_seq": 12346
}

# Engine → bots: subscription state (sent on change)
{
  "type": "subscriptions",
  "watchlist": ["ATRA", "TRAW", "FATN", ...],
  "tier1": [],  # empty during A/B (no TBT)
  "tier2": ["ATRA", "TRAW", "FATN", ...],
  "policy_owner": "wave_breakout"  # which strategy currently has priority
}

# Engine → bots: heartbeat every 5s
{
  "type": "heartbeat",
  "ts": "2026-05-08T17:09:30-04:00",
  "engine_uptime_s": 3600,
  "ibkr_connected": true,
  "tick_rate_5s": 47  # ticks delivered in last 5 seconds
}

# Engine → bots: stream pause (during reconnect)
{
  "type": "stream_paused",
  "reason": "ibkr_disconnect",
  "since": "2026-05-08T17:09:30-04:00"
}

# Engine → bots: stream resumed
{
  "type": "stream_resumed",
  "ts": "2026-05-08T17:09:35-04:00"
}

# Bot → engine: bot identity (sent on connect)
{
  "type": "hello",
  "bot_id": "squeeze_bot" | "wb_bot",
  "version": "1.0"
}

# Bot → engine: subscription request (advisory only — engine still controls actual subs)
{
  "type": "interest",
  "bot_id": "squeeze_bot",
  "symbols": ["ATRA", "TRAW"]  # symbols this bot wants priority on (for setup-driven priority)
}
```

**Connection model:**

- Engine listens on a Unix socket: `/tmp/warrior_engine.sock`
- Each strategy bot connects as a client, sends `hello`, then receives the tick stream
- If a bot disconnects, engine keeps streaming to other clients
- If engine dies, bots receive socket close → trigger fail-CLOSED behavior (refuse new entries, manage existing positions only)

**Versioning:** every message has implicit version via the schema. If we need to break compat later, add `"version": 2` to messages.

### Phase 2: Engine Core (`data_engine.py`)

Single Python process. Owns the IBKR connection. Distributes ticks via IPC.

**Required behaviors:**

1. **Startup:**
   - Connect to IB Gateway on port 4002 with clientId=3
   - Read watchlist from `~/warrior_bot_v2/session_state/<today>/watchlist.json` (same path Setup A uses)
   - Subscribe to `reqMktData('233')` for every watchlist symbol
   - Open Unix socket `/tmp/warrior_engine.sock` and accept bot connections
   - Print startup banner with clientId, ibkr_connected status, watchlist count, IPC socket path

2. **Tick handling:**
   - On every IBKR tick callback, construct a `tick` message and broadcast to all connected IPC clients
   - Maintain per-symbol bar builder (1m bars) — emit `bar` messages on bar close
   - Maintain session VWAP per symbol — include in every `bar` message
   - Write tick stream to `tick_cache_engine/<date>/<symbol>.json` (NEW unified cache, separate from Setup A's `tick_cache/` and `tick_cache_alpaca/`)

3. **Subscription policy (during A/B period: Phase B-2):**
   - Tier 1 (TBT): **NEVER** during A/B period. Engine logs would say `Tier 1: 0 slots used (A/B period — no TBT)`.
   - Tier 2 (snapshot): every watchlist symbol. Auto-resubscribe on watchlist change.

4. **Heartbeat:**
   - Every 5 seconds, broadcast `heartbeat` message
   - If IBKR connection drops, broadcast `stream_paused`, attempt reconnect, then `stream_resumed` when restored

5. **Reconnect:**
   - On IBKR disconnect, retry with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s...)
   - After 5 minutes of failed reconnect, send a final `stream_paused` and exit (let systemd/cron restart the engine)

6. **Logging:**
   - Every state change to its own log file: `logs/<date>_engine.log`
   - Format: `[ENGINE] <timestamp ET> <event> <details>`

7. **Shutdown:**
   - On SIGTERM, broadcast `stream_paused` to all clients, close IPC socket, disconnect from IBKR cleanly
   - Idempotent — safe to call shutdown multiple times

### Phase 3: Strategy Bots (`squeeze_bot.py`, `wb_bot.py`)

Both bots are thin wrappers around the existing detector logic. They become pure consumers of engine output.

**`squeeze_bot.py` requirements:**

1. Connect to engine at `/tmp/warrior_engine.sock`, send `hello` with `bot_id=squeeze_bot`
2. Initialize `SqueezeDetector` (existing class — no changes)
3. Initialize Alpaca client with PA-NEW credentials (read from `.env.engine`)
4. On every `tick` message: feed `detector.on_trade_price(price)` for that symbol's detector instance
5. On every `bar` message: feed `detector.on_bar_close_1m(bar, vwap)`
6. When detector signals entry: place order via Alpaca
7. Manage exits per existing logic
8. Daily P&L tracking, max daily loss enforcement (read from `.env.engine`)
9. Fail-CLOSED on `stream_paused`: refuse new entries, continue managing existing positions
10. Fail-CLOSED on socket disconnect: same as stream_paused

**`wb_bot.py` requirements:** Same shape but uses `WaveBreakoutDetector` and the WB-specific config from `.env.engine`.

**Shared infrastructure** (extract into `engine_bot_common.py` if reuse helps):
- IPC client connection
- Alpaca client wrapper
- Position state management
- Daily P&L tracking
- Logging setup

**What the bots DON'T do:**
- Don't connect to IBKR
- Don't manage subscriptions
- Don't write to `tick_cache_*/`
- Don't run watchdogs
- Don't read `watchlist.txt` directly (subscription state comes via IPC)

### Phase 4: Daily Runner (`daily_run_engine.sh`)

Mirrors `daily_run_v3.sh` but launches the engine + 2 bots instead of the dual bot setup.

**Required behavior:**
1. Wake/unlock dance (copy from `daily_run_v3.sh`)
2. Activate venv
3. Verify IB Gateway is up (assume Setup A's `daily_run_v3.sh` already started it; or start it ourselves if not)
4. Launch `data_engine.py` first; wait for socket file `/tmp/warrior_engine.sock` to appear (max 30s timeout)
5. Launch `squeeze_bot.py` and `wb_bot.py` in parallel
6. Monitor all 3 PIDs; if any dies, log fatal but don't auto-restart (Setup A is the production path during A/B)
7. At session end (20:00 ET): graceful SIGTERM to all 3 processes; ensure positions are flat
8. Log everything to `logs/<date>_engine_run.log`

---

## Configuration (`.env.engine`)

Separate from Setup A's `.env`. Reuses the same env var names so detectors don't need code changes.

```bash
# IBKR data (shared with Setup A — engine uses different clientId)
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=3

# Alpaca execution (THIRD paper account — Manny provisions Sunday)
APCA_API_KEY_ID=<NEW THIRD ACCOUNT KEY>
APCA_API_SECRET_KEY=<NEW THIRD ACCOUNT SECRET>
APCA_API_BASE_URL=https://paper-api.alpaca.markets
APCA_PAPER=1

# IPC
ENGINE_IPC_SOCKET=/tmp/warrior_engine.sock

# Strategy enables
WB_SQUEEZE_ENABLED=1
WB_WB_ENABLED=1

# Detector config — INHERIT from existing .env so Setup A and Setup B detectors behave identically
# Manny will copy the relevant lines from .env to .env.engine on Sunday

# Setup B-specific
WB_ENGINE_AB_PERIOD=1     # When set, engine refuses to subscribe to TBT (A/B mode)
```

---

## Setup-Driven Priority (For When TBT Is Re-Enabled, Phase 3)

This is documented now even though it's not active during A/B. When the engine eventually enables TBT (post-A/B-win), the slot allocation policy is:

```python
def compute_tier1_priority(symbol, state):
    """Higher priority = more likely to hold a Tier 1 slot. Max 5 slots total."""
    
    # Hard pins (any of these → automatic Tier 1)
    if state.has_open_position(symbol):
        return 1000  # Open position always pinned
    if state.detector_armed(symbol, "squeeze"):
        return 800
    if state.detector_armed(symbol, "wave_breakout"):
        return 800
    if state.detector_primed(symbol, "squeeze"):
        return 500
    if state.wb_observing_high_score(symbol):  # WB score >= 7
        return 400
    
    # Soft scoring (time-of-day tiebreaker)
    score = 0
    
    if state.is_squeeze_window():  # 04:00-10:00 ET
        score += state.squeeze_relevance(symbol) * 10  # 0-50 points
    else:  # 10:00-20:00 ET, WB-favored
        score += state.wb_relevance(symbol) * 10  # 0-50 points
    
    # Volume rank as universal fallback
    score += (10 - state.volume_rank(symbol)) * 5  # 0-50 points for top 10 volume
    
    return score

# Engine periodically (every 30s):
# 1. Compute priority for every watchlist symbol
# 2. Take top 5 → those are Tier 1
# 3. Promote/demote as needed (with 5-min cooldown to prevent thrash)
```

Don't implement this during the Sunday build. Just make sure the IPC contract has space for it (`tier1`, `tier2`, `policy_owner` fields in `subscriptions` messages). Future Phase 3 directive will activate it.

---

## A/B Test Protocol

**Same on both sides:**
- `watchlist.txt` (Setup A's `live_scanner.py` writes; both setups consume)
- Trading windows: 04:00-12:00 ET morning, 16:00-20:00 ET evening
- Detector code (squeeze_detector.py, wave_breakout_detector.py — unchanged)
- Detector config (env var values copied from `.env` to `.env.engine`)
- The two correctness fixes from May 8 (pyramid silenced, equity-tied notional cap)

**Different:**
- Setup A: dual bots, each owns its IBKR clientId, separate Alpaca accounts per strategy, main bot has TBT enabled
- Setup B: one engine, two thin bots, single Alpaca account, no TBT during A/B

**Daily comparison report (CC produces every weekday EOD):**

| Metric | Setup A total | Setup B total | Δ |
|---|---|---|---|
| Realized P&L | $X | $Y | $Y-$X |
| Trades fired | N | N | |
| Win rate | XX% | YY% | |
| Avg slippage entry | $X.XX | $X.XX | |
| Avg slippage exit | $X.XX | $X.XX | |
| BP rejections | N | N | |
| Time-to-fill (median) | Xms | Yms | |
| Tick density (avg, all symbols) | X | Y | |

Save to: `cowork_reports/daily_trades/<date>_ab_comparison.md`

---

## Sunday Build Order (Strict Sequence)

1. **First (15 min):** Manny provisions third Alpaca paper account, gets API keys, drops them into `.env.engine` template
2. **Second (15 min):** CC writes `engine_ipc.py` — pure data classes / serialization helpers, no I/O
3. **Third (20 min):** CC writes `data_engine.py` — IBKR connection + IPC server. Test by running it standalone and `nc -U /tmp/warrior_engine.sock` to see ticks flowing.
4. **Fourth (20 min):** CC writes `squeeze_bot.py` and `wb_bot.py`. Test by connecting them to a running engine and verifying detector state transitions match what Setup A would produce on the same ticks.
5. **Fifth (10 min):** CC writes `daily_run_engine.sh`. Test the wake/unlock + launch sequence by running manually.
6. **Sixth (10 min):** Cron entry for Setup B's daily run. Confirm both `daily_run_v3.sh` (Setup A) and `daily_run_engine.sh` (Setup B) fire at 02:00 MT Monday.
7. **Seventh (15 min):** Sunday afternoon dry run. Connect engine to Gateway. Connect bots to engine. Watch ticks flow. Run for 30 minutes. Verify no unhandled exceptions.

**Total estimate: ~2 hours of focused work + Manny's Alpaca account setup time.**

---

## Acceptance Criteria for Monday Morning

| # | Check | How to verify |
|---:|---|---|
| 1 | Setup A runs unchanged at 02:00 MT | `daily_run_v3.sh` log shows normal startup |
| 2 | Setup B runs at 02:00 MT alongside Setup A | `daily_run_engine.sh` log shows engine + 2 bots launched |
| 3 | Engine connects to IBKR and starts streaming | Engine log shows `IBKR connected`, watchlist subscribed, tick rate > 0 |
| 4 | Both bots connect to engine | Engine log shows 2 IPC clients connected, with `bot_id` values |
| 5 | Setup A and Setup B receive same tick events | Compare tick counts in `tick_cache/` vs `tick_cache_engine/` for one symbol — should be within 5% |
| 6 | If Setup B's bots fire entries, orders go to PA-NEW (not PA3VP0LB4OID or PA3LXGIPGG8B) | Alpaca dashboard for PA-NEW shows the orders |
| 7 | Both setups produce daily reports | Setup A → `daily_trades/<date>_trade_breakdown.md`. Setup B → `daily_trades/<date>_engine_trade_breakdown.md`. |
| 8 | A/B comparison report generated EOD | `daily_trades/<date>_ab_comparison.md` summarizes both |

---

## Failure Modes (Acceptable Behavior)

| Failure | Setup A response | Setup B response |
|---|---|---|
| IBKR Gateway dies | Both Setup A bots fail-CLOSED on new entries; existing positions managed | Engine fails-CLOSED → broadcast `stream_paused` → bots fail-CLOSED |
| Engine process crashes | N/A | Setup B bots get socket close → fail-CLOSED. Setup A unaffected. |
| One Setup B bot crashes | N/A | Engine continues. Other bot continues. No auto-restart during A/B (manual investigation). |
| IPC socket fills up (slow consumer) | N/A | Engine drops oldest unread messages with a `[WARN] dropped N messages for <bot_id>` log. Should not happen at our throughput, but if it does, that's a signal to fix. |
| Network partition between engine and Gateway | N/A | Engine reconnects per its policy. Bots see stream_paused/resumed. |

**No auto-restarts in A/B period.** If Setup B has a problem, we want to see it in the data, not paper over it.

---

## What NOT to Do

- ❌ Do NOT modify any Setup A files (`bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `daily_run_v3.sh`, `.env`)
- ❌ Do NOT enable TBT in the engine during A/B period (`WB_ENGINE_AB_PERIOD=1` enforces this)
- ❌ Do NOT add the Setup-Driven Priority logic to the engine yet — IPC contract has the fields, but implementation comes in Phase 3 (post-A/B)
- ❌ Do NOT change detector code (squeeze, WB) — they should be black boxes the bots import
- ❌ Do NOT add new strategies during this build
- ❌ Do NOT modify `live_scanner.py` — both setups read its output unchanged
- ❌ Do NOT touch the chop gate, trailing stops, sizing, or any strategy parameters
- ❌ Do NOT skip the IPC contract phase — the message types in `engine_ipc.py` are the integration spec for the parallel bot dev

---

## Reversal Path

If Setup B causes any issue Monday morning:

```bash
# 1. Disable Setup B's cron entry
crontab -e
# Comment out the daily_run_engine.sh line

# 2. Kill running Setup B processes
pkill -f data_engine.py
pkill -f squeeze_bot.py
pkill -f wb_bot.py

# 3. Setup A continues unaffected — no rollback needed on its side
```

Setup B is purely additive. Setup A's continued operation is the safety net.

---

## Files Touched (Summary)

```
[NEW]    data_engine.py
[NEW]    engine_ipc.py
[NEW]    squeeze_bot.py
[NEW]    wb_bot.py
[NEW]    daily_run_engine.sh
[NEW]    .env.engine
[NEW]    cowork_reports/daily_trades/<date>_engine_trade_breakdown.md   (per session)
[NEW]    cowork_reports/daily_trades/<date>_ab_comparison.md             (per session)

[UNCHANGED] All Setup A files
```

---

*One engine. One IBKR connection. Two thin strategy bots. Third Alpaca account. A/B from Monday open. Setup A is sacred. Strategy tuning still waits for the May 15-16 review.*
