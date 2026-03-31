# Morning Progress Report: 2026-03-31 (Tuesday)
## Branch: v2-ibkr-migration

---

## Executive Summary

**First live session with a healthy bot and confirmed quiet market.** After 5 consecutive mornings lost to bugs, today we ran real-time integrity checks during the session and proved the bot is working correctly — the market is genuinely quiet, not the bot failing silently.

---

## Timeline

| Time (ET) | Event |
|-----------|-------|
| 02:00 | Cron fired daily_run.sh |
| 02:04 | Wake sequence: display wake ✅, keystroke FAILED (accessibility), desktop ACTIVE ✅ |
| 02:04-02:07 | Gateway launched but **failed to open port 4002** (180s timeout) — 6th consecutive autostart failure |
| ~06:50 | Manny woke up, alerted CC |
| 06:56 | Manual Gateway start — UP in 15s, bot connected |
| 07:00 | **CATCHUP SCAN fired** — 3 scanners found 96 unique symbols |
| 07:00-07:04 | Catchup scan **HUNG** — compute_adv() blocking on historical data requests for each of 96 symbols |
| 07:04 | Restarted bot, catchup hung again (44 symbols this time) |
| 07:08 | **FIX DEPLOYED**: Removed ADV/RVOL computation from catchup scan, use absolute volume + gap% only |
| 07:10 | Restart #3 — catchup processed 46/46 symbols in ~2 minutes ✅ |
| 07:10 | **POLA found** via catchup scan (+18% gap, 94K volume, 1.8M float) |
| 07:17 | POLA subscribed, seeded (198 bars), ticks flowing |
| 07:18 | Tick drought detected → auto-resubscription → 166 ticks/min ✅ |
| 07:19+ | Bot running, POLA watched, SQ=IDLE (no volume explosion) |
| 09:10 | **Integrity scan #1**: Live snapshot — 20 stocks, all fail RVOL. Quiet morning confirmed. |
| 09:15 | **Integrity scan #2**: Historical full-morning check — every stock's price = HOD (no spikes and pullbacks). No missed opportunities. |
| 09:15+ | Bot continues running, 0 trades — correct behavior |

---

## Bugs Found & Fixed This Session

### 1. Catchup Scan Hangs on ADV Computation (CRITICAL)
**Problem:** `scan_catchup()` called `compute_adv()` for each of 96 symbols. Each call makes a `reqHistoricalData(30 days)` request. One symbol hung indefinitely (no timeout), blocking the entire bot.

**Fix:** Skip ADV/RVOL in catchup scan. Use absolute volume + gap% as filters. RVOL is checked on the next normal 5-min scan. Catchup now processes 46 symbols in ~2 minutes.

**Impact:** Bot was stuck for 4+ minutes on first two restart attempts. Third restart with fix worked immediately.

### 2. Catchup Scan numberOfRows Too High
**Problem:** 50 results per scanner × 3 scanners = up to 150 symbols to evaluate.

**Fix:** Reduced to 20 per scanner. Still casts a wide net (60 unique max) but more manageable.

### 3. Progress Logging Added
**Fix:** Catchup scan now prints `"processing X/Y — SYMBOL..."` for each candidate. No more blind waits.

---

## Autostart Investigation

The wake/unlock sequence partially worked:
- `caffeinate -u` (display wake): ✅
- `osascript keystroke` (password): **FAILED** — "keystroke failed — check Accessibility permissions"
- Desktop session: **ACTIVE** (auto-login may have already unlocked it)

Even with desktop reported as ACTIVE, Gateway's Java AWT still couldn't render the login dialog. The issue is deeper than screen lock — it's the cron execution context. Java AWT needs a specific type of display session that cron doesn't provide.

**Status:** Still unsolved after 6 attempts. Next approaches to try:
1. `launchd` user agent instead of cron (runs in user's login session)
2. VNC session that persists 24/7
3. Schedule `pmset` to wake the Mac before cron fires

---

## Integrity Verification

### Live Scan (09:13 ET)
Ran standalone scanner on separate IBKR connection (clientId=98). Checked all 20 TOP_PERC_GAIN stocks with full RVOL computation.

**Result:** 0 candidates pass all filters. Every stock fails on RVOL (all below 1.0x). Best candidate: KIDZ +79% gap but only 0.9x RVOL with 352K volume.

### Historical Morning Check (09:15 ET)
Checked TOP_PERC_GAIN + HOT_BY_VOLUME for stocks that may have moved earlier and pulled back.

**Result:** Every stock's current price = HOD (High of Day). No stock spiked and pulled back this morning. Prices have been drifting, not squeezing.

### Conclusion
**Quiet morning confirmed with two independent verification methods.** The bot is not missing anything.

---

## Bot Health at Time of Report

```
[09:13 ET] ACTIVE | flat | daily=$+0 (0t) | conn=OK | ticks=833 | POLA:5t/IDLE
POLA CHART: O=$2.28 H=$2.29 L=$2.27 C=$2.28 V=7,379 | EMA9=2.29 VWAP=2.31 | sq=IDLE
```

- Connection: OK ✅
- Ticks: Flowing (39-87/min for POLA) ✅
- Scanner: Running every 5 min (25 snapshots so far) ✅
- Squeeze detector: IDLE (no volume explosion) ✅
- Caffeinate: Active (Mac won't sleep) ✅

---

## Changes Deployed During Session

| Change | File | Commit Status |
|--------|------|--------------|
| Skip ADV in catchup scan | ibkr_scanner.py | Uncommitted — needs push |
| Reduce catchup numberOfRows 50→20 | ibkr_scanner.py | Uncommitted |
| Add catchup progress logging | ibkr_scanner.py | Uncommitted |
| Re-enable catchup (was disabled) | bot_ibkr.py | Uncommitted |

---

## What We Still Need

1. **Autostart fix** — 6/6 mornings failed. This is the #1 infrastructure priority.
2. **Catchup scan ADV** — currently skipped. Could add a timeout (15s per symbol) so it tries but doesn't hang.
3. **Stress test during live session** — Cowork/Perplexity designing a scrutiny directive. The live session is the only time we can find bugs the backtest doesn't expose.
4. **Evening session** — bot will auto-transition to dead zone at 12:00, resume at 16:00. Catchup scan will fire again for evening.
