# FCHL Orphan — Session Resume Failed at Date Boundary

**Date:** 2026-05-15
**Author:** CC
**For:** Cowork (Perplexity)
**Severity:** **P0 — would have been catastrophic in real money.** -$13,353 unrealized on a position whose stop ($2.404) was breached 4+ hours before manual intervention. June 4 real-money go-live is 20 days away.
**Trigger:** Manny manually flattened FCHL at $1.83 after observing bot wasn't reacting. Position was held overnight from 2026-05-14 19:58 ET → 2026-05-15 ~10:54 ET.

---

## TL;DR

Two compounding bugs:

1. **Engine `decide_boot_mode` keys on TODAY's directory only.** At cron boot 2026-05-15 04:00 ET, the boot logic looked for `session_state_engine/2026-05-15/marker.json` — it didn't exist (date just rolled), so the bot booted COLD with reason `no_marker`. Yesterday's `session_state_engine/2026-05-14/wb_bot/open_trades.json` (containing the full FCHL record with stop=$2.404) was NEVER READ. The position was orphaned at the date boundary.

2. **`wb_persistence.record_wb_observe` FileNotFoundError on engine writes.** Cross-process race on shared `wb_persistence.txt` — engine's `_atomic_write` constructs `wb_persistence.tmp`, writes it, then `tmp.replace()` fails because Setup A's bots concurrently wrote/replaced their own tmp file with the same path. Engine's persistence writes failed silently throughout the day.

Bug #1 directly caused the FCHL orphan. Bug #2 is a hygiene bug that affected logging but not P&L this time.

---

## Bug #1 — Date-Boundary Session-State Loss

### Evidence

**Yesterday's wb_bot session state (preserved correctly at session-end):**
```
session_state_engine/2026-05-14/wb_bot/open_trades.json
[
  {
    "symbol": "FCHL", "setup_type": "wave_breakout",
    "entry_price": 2.5, "qty": 20080,
    "r": 0.096, "stop": 2.404, "score": 8.0, "peak": 2.5,
    "fill_confirmed": true, "risk_dollars": 2194.31,
    "entry_time": "2026-05-14T19:58:02.916926-04:00",
    "order_id": "e9b779f5-8d84-4493-8ba4-5125e4ca204b"
  }
]
```
Yesterday's data was correct. The shutdown wrote it cleanly.

**Today's wb_bot first log line:**
```
[WB] BOOT: COLD (reason=no_marker, marker_age=n/a)
```

**Today's wb_bot session state, INITIAL:**
```
session_state_engine/2026-05-15/wb_bot/open_trades.json
[]
```
Empty. Today's directory didn't inherit yesterday's open trades.

**The boot decision logic (`engine_bot_common.py:1150-1180`):**
```python
def decide_boot_mode(session, fresh=False, resume=False):
    # ...
    if not session.marker_exists():
        return "cold", "no_marker"
```

And the comment at line 947: `marker.json: written on cold start; auto-rotates at the date boundary (decide_boot_mode keys on TODAY's directory only).`

This is intentional. The design assumed positions close intraday (squeeze) or that `WB_WB_SESSION_END_FORCE_EXIT` would auto-flatten WB positions at session end. **Neither assumption held for FCHL:**
- WB filled 19:58 ET, scheduled session-end at 20:05 ET — only 7 min in extended session
- `WB_WB_SESSION_END_FORCE_EXIT` is a config flag with NO implementation (project memory: H#19 still queued)
- So position carried overnight into the date boundary, where the boot logic lost it

### Cascade

```
2026-05-14 19:58  FCHL fill @ $2.50
2026-05-14 20:05  Engine shutdown — wrote open_trades.json correctly
2026-05-15 04:00  Cron boot — decide_boot_mode() sees no marker for 2026-05-15
2026-05-15 04:00  BOOT: COLD (reason=no_marker) — yesterday's open_trades.json IGNORED
2026-05-15 04:07  Bot sees FCHL as fresh symbol; WB_OBSERVE fires, no position context
2026-05-15 04:07  Stop $2.404 already irrelevant to bot — has no record of position
2026-05-15 ~05:00 Pre-market FCHL drops below $2.40 — bot does nothing (no position to manage)
2026-05-15 ~10:54 Position now at $1.83, -$13,353 — Manny notices, manually flattens
```

The position was MANAGEABLE all the way down. The bot just didn't know it owned it.

### Other affected symbols

Setup A had the same pattern but the wb_persistence layer (which I shipped two days ago) does carry forward WB-observed symbols. So today's Setup A booted with 9 persisted symbols (ATRA, SST, FCHL, etc.) and could detect/trade them. But persistence doesn't carry POSITIONS — only symbol watchlist context. The positions specifically need session-resume to work.

Setup A had no open positions at yesterday's close, so no equivalent orphan. The bug would have bitten Setup A the same way if it held a position overnight.

---

## Bug #2 — Cross-process race in wb_persistence.py

### Evidence

Today's wb_bot.log (engine), repeated throughout the session:

```
[WB_PERSIST] record_wb_observe(FCHL) failed: FileNotFoundError(2, 'No such file or directory')
[WB_PERSIST] record_wb_observe(AEHL) failed: FileNotFoundError(2, 'No such file or directory')
[WB_PERSIST] record_wb_observe(ONDG) failed: FileNotFoundError(2, 'No such file or directory')
[WB_PERSIST] record_wb_observe(SST)  failed: FileNotFoundError(2, 'No such file or directory')
...
```

### Root cause

`wb_persistence.py:_atomic_write()`:
```python
tmp = _FILE.with_suffix(".tmp")    # /Users/duffy/warrior_bot_v2/wb_persistence.tmp
tmp.write_text(...)
tmp.replace(_FILE)                 # mv .tmp → .txt
```

`_FILE` points at the shared file `/Users/duffy/warrior_bot_v2/wb_persistence.txt`. Both Setup A bots and engine bots compute the SAME `.tmp` path and write/replace concurrently. Race:

```
T+0   Engine:   tmp.write_text(content_E)        — creates .tmp on disk
T+1   Setup A:  tmp.write_text(content_A)        — overwrites engine's .tmp
T+2   Setup A:  tmp.replace(_FILE)               — moves .tmp to .txt (succeeds)
T+3   Engine:   tmp.replace(_FILE)               — FileNotFoundError (.tmp gone)
```

Standalone test (env loaded before import) succeeds — proves the path/env is fine. The fail mode requires concurrent writes.

### Impact

Best-effort try/except in `record_wb_observe()` catches the exception, logs it, returns. **No bot-side P&L impact.** But the engine's persistence captures didn't make it to the shared file consistently. Setup A's persistence writes likely succeeded because Setup A is the only writer half the time.

---

## Recommended fixes

### Fix #1 (P0 — same-day or pre-cron): make `decide_boot_mode` look back

Two acceptable approaches:

**A. Lookback path** — if today's marker is absent, check the previous N session-state dirs. If a recent marker has `open_trades.json` non-empty, resume from THAT.
- Pros: minimal code change, conservative
- Cons: defines "recent" — what's the cutoff? Friday hold over weekend → look back 3 sessions? Multi-day hold tolerable?

**B. Reconcile-from-broker** — at boot, query `broker.get_all_positions()`. For any position with no matching `open_trades.json` entry, hydrate a synthetic record (best-effort: symbol, qty, avg_entry_price; reconstruct stop from broker side-data if possible; otherwise apply a default protective stop).
- Pros: works for any history depth, defensive against any state-loss bug
- Cons: synthetic stop is heuristic; better than nothing

I propose **B as primary, with A as a defense-in-depth fallback.** Together they cover every reasonable failure mode. Reconciliation gives positions back to the bot's management even when state is missing; lookback prevents the cold-resume drift on date rollovers.

### Fix #2 (P1 — this week): per-process tmp suffix in wb_persistence

`tmp = _FILE.with_name(f"{_FILE.stem}.{os.getpid()}.tmp")` — each process writes to a unique tmp file. Then `tmp.replace(_FILE)` is per-process atomic.

Race window remains — if Engine's replace happens after Setup A's, Setup A's data is silently overwritten — but no FileNotFoundError. Better: add file-locking via `fcntl.flock` around the read-modify-write cycle. ~15 LOC.

### Fix #3 (separate P0 — already queued): `WB_WB_SESSION_END_FORCE_EXIT` implementation

Project memory has this as H#19. If implemented, WB positions auto-flatten before session-end, eliminating the overnight-hold class of bug entirely. Without this, every WB winner that fires in late extended hours becomes a candidate for the same orphan failure.

---

## Real-money implications

This bug would have been catastrophic on a real-money account. If we'd been live today:
- 20,080 shares × ($2.50 - $1.83) = **-$13,453 realized** (with manual flatten at $1.83)
- vs intended max loss of $1,928 (stop at $2.404 × 20,080 × $0.096)
- **7× over the intended risk envelope**

Worse: if Manny hadn't been watching, FCHL could have gone to $1.00 or lower. The bot would never have noticed. **A real-money version of today loses your full position-size budget on one trade.**

**June 4 go-live should be conditional on Fix #1 (session-resume across date boundaries) shipping with end-to-end test coverage.**

---

## Test coverage gap

The session-resume layer was originally validated only WITHIN a session (intra-day restart). We never tested:
- Boot at date boundary with open position from yesterday
- Boot after a weekend with Friday's position open
- Boot with engine state migrated to a new machine

All three are real go-live scenarios. **Pre-go-live test plan should include:**
1. Synthetic: write a yesterday-dated open_trades.json with a known position, boot bot, verify it loads + manages
2. Real: hold a paper position overnight on purpose, verify next-day rehydration works under the fix

---

## Questions for Cowork

### Q1 — Which fix combination?
Reconcile-from-broker alone, or reconcile + lookback? My instinct: ship both — reconcile is the safety net, lookback is the principled fix.

### Q2 — Stop reconstruction for synthetic records
If we reconcile from broker but the stop level is missing (no open_trades.json), what's the safe default? Options:
- 2% below entry (matches WB_WB_HARD_STOP_R = 1.0 default-ish)
- Symbol's session VWAP - 1 ATR
- Just refuse to take action and alert "MANUAL RECONCILE REQUIRED" until human intervenes

I prefer option 3 — fail-LOUD when a position has no managed state. The bot didn't take the trade; we don't have its risk math; abstaining is safer than guessing.

### Q3 — June 4 contingency
If Fix #1 can't ship + validate in time, do we delay June 4 or live with the risk? My recommendation: delay 1-2 weeks. The bot's core promise is "manages positions"; if that fails at date boundaries, no other guardrail compensates.

### Q4 — Should the engine session-end force-exit implementation (H#19) be promoted to P0?
Without it, every WB extended-hours fill is a session-end orphan risk. With it, the date-boundary bug goes from "P0 catastrophic" to "P2 nuisance."

---

## Files referenced

- `engine_bot_common.py:1150` (decide_boot_mode)
- `engine_bot_common.py:947` (the "date-boundary" comment that documents the design choice)
- `wb_persistence.py:_atomic_write` (race condition)
- `session_state_engine/2026-05-14/wb_bot/open_trades.json` (yesterday's data, lost at boundary)
- `session_state_engine/2026-05-15/wb_bot/open_trades.json` (today's, empty at boot)
- `logs/2026-05-15_wb_bot.log` (BOOT: COLD line + WB_PERSIST FileNotFoundError lines)

---

## Status / Action

- ✅ FCHL position manually flattened by Manny at ~$1.83 (-$13,453 realized)
- ⏳ Monitor `by9rw8soe` still running — watching today's continued trading
- ⏳ Fix design + ship — awaits Cowork verdict on Q1/Q2/Q4
- ⏳ Test plan — needs to land before June 4 go-live

This is exactly the kind of failure paper-trading is supposed to surface. Manny's right — we're catching it cheap. But we MUST fix it before June 4.
