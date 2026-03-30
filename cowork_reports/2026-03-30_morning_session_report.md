# Morning Session Report: 2026-03-30 (Monday)
## Branch: v2-ibkr-migration

---

## Executive Summary

**Bot earned $0 live. Backtest shows +$1,075 was available.** Two compounding issues: Gateway failed to autostart at 2 AM (5th consecutive cron failure), and a mid-session restart at 09:44 to apply a diagnostic fix wiped the bot's state, dropping ASTC from the watchlist right before it squeezed.

**ASTC moved from $2.71 to $6.48 (+139%)** — the biggest mover of the day. The bot had it subscribed from 09:31-09:44, receiving 300+ ticks/min, squeeze detector IDLE (hadn't broken premarket high yet). The restart killed the subscription. ASTC broke its PM high at 10:17 and the backtest shows +$1,209 from two squeeze entries.

---

## What Happened

| Time (ET) | Event |
|-----------|-------|
| 02:00 | Cron fires daily_run.sh |
| 02:00-02:03 | Gateway fails to open port 4002 — 36 retries, 180s timeout, FATAL |
| 09:31 | Manual start — Gateway + bot connect |
| 09:31 | Scanner finds ASTC (gap=117%, vol=345K, rvol=high) |
| 09:31-09:44 | ASTC subscribed, 300+ ticks/min, SQ=IDLE (below PM high $3.88) |
| 09:44 | **Bot restarted** to apply avg_vol diagnostic fix |
| 09:44 | Fresh BotState — scanner returns 0 candidates (ASTC dropped from TOP_PERC_GAIN) |
| 09:44-12:00 | Bot watches nothing. 0 symbols subscribed. |
| 10:17 | **ASTC breaks PM high at $3.90** — squeeze fires in backtest (+$348, +$861) |
| 10:17-11:30 | ASTC continues to $5.32, $5.60, $6.48 — multiple additional arms |
| 12:00 | Morning window closes. $0 earned. |

---

## Backtest: What We Missed (IBKR Ticks)

| Stock | Trades | P&L | Notes |
|-------|--------|-----|-------|
| ASTC | 2 | **+$1,209** | Two SQ target hits at 10:17-10:23. Stock went $2.71→$6.48. |
| ELAB | 3 | +$161 | 1 win (+$562), 2 losses. Mixed. |
| EEIQ | 1 | -$295 | max_loss_hit at $12.90 |
| **Total** | **6** | **+$1,075** | |

ASTC signal flow:
- 07:08: SQ PRIMED (49.4x volume!) but expired — no level break
- 07:11-10:15: Multiple rejects (`not_new_hod` — stock below PM high $3.88)
- 10:16: SQ PRIMED on 4.9x volume, ARMED at PM_HIGH $3.90 (parabolic)
- 10:17: ENTRY at $3.92 → exit $4.05 (para trail, +$348)
- 10:18: ENTRY at $3.92 → exit $4.14 (sq_target_hit, +$861)
- 10:29-10:48: More primes and arms as stock continued to $5.60

**The entries at 10:17 were AFTER our late start time (09:31).** Even starting late, we would have caught these if we hadn't restarted.

---

## ASTC: The Continuation Opportunity

| Price Level | Time | Event |
|------------|------|-------|
| $3.09 | 04:00 | Open |
| $3.88 | pre-market | PM High |
| $3.92 | 10:17 | **SQ Entry 1** → exit $4.05 |
| $3.92 | 10:18 | **SQ Entry 2** → exit $4.14 |
| $4.47 | 10:29 | SQ PRIMED (3.8x vol) — armed but no entry (in trade) |
| $5.32 | 10:45 | SQ PRIMED (3.0x vol) |
| $5.60 | 10:48 | ARMED at $5.60 whole dollar |
| $6.48 | day high | **Stock kept running** |

**SQ captured $3.92→$4.14 (+5.6%). The stock went to $6.48 (+65.6% from entry).** The 2R mechanical exit left $2.34/share on the table. This is exactly the case for CT — after the initial squeeze exits, the stock keeps running and a continuation entry on the first pullback could capture the $4.14→$6.48 leg.

---

## Infrastructure Issues

### 1. Gateway Autostart (5th consecutive failure)
Gateway needs a display context for its login dialog. Cron at 2 AM with screen locked = no window server = no login = timeout. Works perfectly when started manually with an active desktop session.

**Needs:** `launchctl` user agent instead of cron, or VNC/screen session that persists.

### 2. Mid-Session Restart Wipes State
Restarting the bot kills all subscriptions and detectors. The new instance scans, but if the stock has dropped from TOP_PERC_GAIN by then, it's lost.

**Fixed (this session):** Added catchup scan — first scan on startup now runs 3 IBKR scanners (TOP_PERC_GAIN + MOST_ACTIVE + HOT_BY_VOLUME) with HOD-based gap calculation. A stock that gapped at 7 AM is still found even if it's consolidating at 9:30.

### 3. Symbols Pinned for Session
Once subscribed, a stock stays on the watchlist for the entire session window. No more dropping stocks that temporarily fail a rescan filter.

---

## Fixes Deployed Today

| Fix | Commit | Impact |
|-----|--------|--------|
| Catchup scan on startup | e64e112 | 3 scanners, HOD-based gap, finds movers from earlier in day |
| Symbols pinned for session | 793b700 | Never unsubscribe during a window |
| Clean evening reset | 793b700 | Properly clears everything before evening scan |
| avg_vol diagnostic fix | 793b700 | Shows real squeeze detector volume average |

---

## Key Takeaway for CT Strategy

ASTC is today's evidence that CT would add significant value:
- SQ caught the initial breakout: $3.92→$4.14 (+$1,209)
- Stock continued: $4.14→$6.48 (another +56% from SQ exit)
- Multiple SQ PRIMEs and ARMs after the initial trade — the detector SAW the continuation
- But SQ's 2R mechanical exit stopped us out too early

CT's job is to re-enter on the first pullback after the initial SQ exit and ride the continuation with wider targets. On ASTC today, that would have meant catching the $4.14→$5.50+ leg.

**CT regression fix is the priority.** Once VERO/ROLR regressions pass at $0 delta, CT can be validated on ASTC, EEIQ, and other continuation stocks.
