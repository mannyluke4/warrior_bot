# Morning Report — 2026-04-29

**Mode:** Paper (DUQ143444), squeeze-only
**Bot start:** 09:08 MT (manual relaunch after 2 AM cron failure)
**Window:** 07:00–12:00 ET (missed first 2 hours)
**Live trades:** 0 (none triggered post-seed)
**Status:** Bot running through afternoon for data collection

---

## What happened

### 02:00 cron — first failure (caffeinate fix landed but exposed second bug)

Yesterday's `daily_run_v3.sh` rewrite removed osascript keystroke unlock and replaced with `caffeinate -u`. That fix worked: no more "WARN: keystroke failed". But the rewrite exposed a second bug:

```
=== Waking screen ===
Display wake (caffeinate -u) sent
=== TRAP: cleanup at Wed Apr 29 02:00:05 MDT 2026 ===
daily_run_v3.sh: line 26: CAFFEINE_PID: unbound variable
```

`set -euo pipefail` + `ioreg | grep DevicePowerState | awk` pipeline returns non-zero on a headless Mac mini (no IODisplayWrangler match) → `pipefail` exits the script before `CAFFEINE_PID=$!` is set → cleanup trap dies on undefined variable.

**Fix committed (`735e403`):**
- Init `CAFFEINE_PID=""` alongside other PIDs at top
- Add `|| true` to the ioreg pipeline + default to "unknown"
- Continue gracefully when display state is indeterminate

### 08:16 test cron — fix confirmed for the wake step but gateway hung

One-shot cron at 08:16 fired. Wake step succeeded (`Display state: unknown (continuing)`, `Persistent caffeinate started`). Gateway started but **hung in IBC retry loop** — port 4002 never opened in 360s, daily_run timed out, cleanup ran.

This is a deeper issue: cron-launched IBKR Gateway can't authenticate even paper-mode (no 2FA path) when no GUI session is active. Last night manual launch took 6 seconds; cron-spawned took 6+ minutes and never finished.

**This is what Step A (System Settings) addresses:** auto-login + lock-screen-disabled gives the Mac a persistent logged-in GUI session that cron-launched Java apps can attach to. Without it, Java GUI windows can't be created, IBC never completes login.

### 09:08 manual relaunch — bot ran clean

Killed cron-stuck processes, ran `bash daily_run_v3.sh` from interactive shell. Gateway up in **22 seconds**, bot connected, scanner subscribed to 6 symbols: CRWG, KBSX, RDAC, SAGT, SKYQ, XTLB.

### Primes seen, but all from seed-replay

```
[11:11 ET] SAGT SQ_PRIMED: vol=494.3x avg
[11:13 ET] RDAC SQ_PRIMED: vol=32.2x avg
[11:17 ET] SKYQ SQ_PRIMED: vol=563.4x avg
[11:18 ET] CRWG SQ_PRIMED: vol=66.6x avg
[12:29 ET] XTLB SQ_PRIMED: vol=3.2x avg     (live, not seed)
[13:33 ET] XTLB SQ_PRIMED: vol=2.8x avg     (live)
[13:46 ET] XTLB SQ_PRIMED: vol=3.5x avg     (live)
```

All four 11:11–11:18 primes were emitted **during seed replay** (historical tick replay through detector when symbols were freshly subscribed mid-morning). `begin_seed/end_seed` correctly suppressed entry firing on these. RDAC subsequently ran from $10 → $21+ (+113%), bot sat flat — exactly the "missed opportunity" pattern from a late start.

### Backtest reconstruction of today's morning

Scanner candidates (constructed via reconstructor + IBKR catchup): 9 symbols total.

With **proper sim_start computed via earliest_discoverable** (live-scanner cadence) and **`WB_MIN_REL_VOLUME=0` to match live's permissive rvol-when-unknown logic**:

```
Starting equity: $8,900 (matches live NetLiq)
Cap: $17,800/trade (8.9K × 0.5 × 4 BP × margin)

AKAN  4 cascading entries  +$7,994
─────────────────────────────────
Total: 4 trades, +$7,994 (+89.8%)
$8,900 → $16,894
```

**All P&L came from AKAN.**

---

## Critical finding: scanner coverage gap

**The live bot's `scan_catchup` did NOT include AKAN today.** AKAN gapped +11.3% on 1.2× ADV ($19.46 open, 3.1M shares full day) — should have qualified — but IBKR's scan codes (TOP_PERC_GAIN, HOT_BY_VOLUME, etc.) didn't surface it among the top 5 the bot subscribes.

Backtest captured AKAN only because the reconstructor uses a historical universe that includes it. Live operation today wouldn't have traded AKAN → real morning P&L would have been ~$0, not $8K.

### Why this matters

`live_scanner.py` (Databento-based) ran today at 09:08 — **too late by 2 hours**. Log shows:

```
09:08:31  Fetching 21-day OHLCV (Databento EQUS.SUMMARY ohlcv-1d)
09:08:47  ✓ 12,647 symbols with avg daily volume + prev close  ← Databento works fine
09:08:47  Connecting to Databento live stream (EQUS.MINI tbbo)
09:08:49  authenticated session_id='1777714312'
09:08:49  Stream started, replaying from 04:00 ET
09:08:49  [7_14] No candidates to write.
09:08:49  [FINAL] No candidates to write.
09:08:49  Scanner cutoff reached (9:30 AM ET). Stopping stream.
```

The scanner started, immediately fired all post-7:14 / past-cutoff logic, wrote empty watchlist, exited in 18 seconds. Databento subscription is paid + wired correctly — fetching 12,647 symbols' OHLCV in 16 seconds is real working integration. The issue is purely timing: live_scanner needs to run from 04:00 ET (or earlier) to accumulate the full pre-market session.

**With auto-start working tomorrow, live_scanner will have its full PM session via Databento and would catch broader candidate sets like AKAN naturally.**

---

## Outstanding items

| Item | Owner | Status |
|------|-------|--------|
| Wake step crash (CAFFEINE_PID unbound) | CC | ✓ fixed `735e403` |
| Cron-launched gateway hang | Manny | needs Step A in office tonight |
| Lock screen disabled (Layer 1) | Manny | pending |
| Auto-login (Layer 2) | Manny | pending |
| `pmset -c displaysleep 0` etc. | Manny | pending |
| Scanner coverage (AKAN-class misses) | — | **resolves naturally once 2 AM cron works + live_scanner runs from open** |
| ELPW 04-24 tick fetch hangs | — | IBKR pacing-throttle, low priority |
| `run_ytd_backtest.py` `WB_MIN_REL_VOLUME` mismatch with live | — | align gate to match live's "rvol < threshold AND rvol > 0" semantics |

## What to expect tomorrow

If Step A is done before bed:
- 2 AM cron fires daily_run_v3.sh
- Wake step succeeds (already proven today)
- Auto-login means GUI session exists for Java
- Gateway authenticates paper in seconds (proven last night manually)
- Bot connects + live_scanner.py runs from 04:00 → 09:30
- Databento populates watchlist with real PM gappers
- Bot subscribes to true top candidates (not just IBKR scan_catchup top 5)
- Morning trades fire from real-time primes, not suppressed seed primes

If Step A is NOT done:
- 2 AM cron fires
- Wake succeeds
- Gateway hangs on Java GUI (no logged-in session for Java to attach to)
- Daily_run times out at 360s
- Manual relaunch needed at 7 AM ET (5 AM MT) for any morning trades
