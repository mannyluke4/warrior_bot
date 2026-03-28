# Forensic Report: ONCO/ARTL — $0 Bot vs $20,869 Ross
## Date: 2026-03-27
## Investigator: Cowork (Opus)

---

## Executive Summary

Ross Cameron made +$20,869 on ONCO (+$6,800) and ARTL (bulk of remainder). Our bot found both stocks, subscribed to both, ran for 2+ hours with heartbeats — and generated zero trades, zero SQ signals, zero bar close events. The entire morning log is just heartbeats and scanner runs.

**Root causes identified: 3 compounding failures, any ONE of which killed the session.**

---

## Failure 1: FATAL — Late Start (09:07 ET vs 07:00 ET)

| Event | Time | Impact |
|-------|------|--------|
| Cron job fires | 02:00 MT (04:00 ET) | ✅ On time |
| TWS startup | 04:00-04:03 ET | ❌ 36 retries, AppleEvent timeout, ABORTED |
| Manual start #1 | 09:07 ET | 2 hours 7 minutes late |
| Manual start #2 | 09:20 ET | Restart |
| Manual start #3 (Gateway port 4002) | 09:29 ET | Final session |

**Ross entered ONCO at ~07:00 ET** on the premarket spike ($3→$7.50→selloff→$5.25 entry). By 09:07 ET, ONCO had already made its primary move, halted twice, and was trading sideways around $4-$5. The bot missed the entire premarket and first 2 hours of the session.

**ARTL started moving at ~08:30 ET** from $4.40, was at $5.80 by the time Ross entered ($6.34), and halted above $12 before the bot's third restart at 09:29 ET. By then ARTL had already dropped from the scanner.

**Impact: 100% of Ross's $20,869 was earned before 09:30 ET.** The bot didn't exist during any of the profitable price action.

---

## Failure 2: CRITICAL — Near-Zero Tick Data

Even after subscribing at 09:07-09:29 ET, the bot received almost no trade ticks:

| Stock | Ticks Received (Morning) | Expected (2h session) | Deficit |
|-------|-------------------------|----------------------|---------|
| ONCO | 12 | ~5,000-20,000 | 99.9% |
| ARTL | 61 | ~5,000-20,000 | 99.7% |

**Tick cache forensics:**
- ONCO: All 12 ticks at 15:12:21 UTC (11:12 ET) — $4.05-$4.07 range. One single second of data.
- ARTL: 147 total (61 morning + 86 evening). First morning ticks at 15:12 UTC (11:12 ET) — $12.41.

**The bot was subscribed from 09:07-11:09 ET but received essentially zero ticks until 11:12 ET** — just before the morning session ended. This means:
- The `on_ticker_update` callback was NOT firing during the session
- The bar builder never built any 1-minute bars
- The squeeze detector never got any data to process
- The trigger check never ran

This is the same class of bug as March 26's volume=0 issue, but possibly worse — the ticks aren't even arriving at all.

**Possible causes:**
1. **IBKR subscription not actually active** — `reqMktData` may return success but IBKR may not be streaming if the connection is unstable
2. **Competing session** — March 26 had an Error 10197 (mobile app wiped subscriptions). No explicit 10197 today, but the same pattern (subscribe → silence → nothing) matches
3. **Port 7497 vs 4002 confusion** — sessions #1 and #2 used port 7497 (TWS), session #3 used port 4002 (Gateway). If both were running, they might have conflicted
4. **Bar builder not wiring callback** — the `on_bar_close_1m` function exists but may not be connected to the bar builder's event

---

## Failure 3: ARTL Dropped From Scanner

| Scan Time | ONCO | ARTL | Notes |
|-----------|------|------|-------|
| 09:07 ET | ✅ Found | ✅ Found | Both subscribed |
| 09:12 ET | ✅ Found | ✅ Found | Still watching |
| 09:20 ET (restart) | ✅ Found | ✅ Found | Re-seeded |
| 09:29 ET (restart, port 4002) | ✅ Found | ❌ **DROPPED** | Only ONCO subscribed |
| 09:34+ ET | 0 new | — | Scanner returning 0 candidates |

ARTL dropped from the scanner between 09:20 and 09:29 ET. By 09:29, ARTL had already run from $4.40 to $12+, halted multiple times, and was showing extreme post-halt volatility. The scanner may have filtered it on:
- **Price gate:** ARTL at $12+ exceeds `WB_MAX_PRICE=20.00`... no, still under. But the IBKR scanner snapshot price may have been the halt price or a stale quote.
- **Gap calculation:** If IBKR returned a different previous close, the gap% calculation might have pushed ARTL outside the 10-500% gate.
- **Scanner API returning stale data** after the halt series.

**The scanner_results/2026-03-27.json file is EMPTY (`[]`).** This means the final scanner save overwrote all previous results with an empty array. We have no record of what the scanner actually found at any checkpoint.

---

## Failure 4 (Evening Bug): Diagnostic Print Crash

Starting at 16:05 ET, every tick for ARTL/SST triggers:
```
ValueError: Invalid format specifier '.2f if vwap else 0:.2f' for object of type 'float'
```

This is in `bot_ibkr.py` line 278 — the diagnostic bar logging CC added. The f-string has a syntax error (ternary inside format spec without proper braces). This crashes the entire `on_ticker_update → on_trade → on_bar_close → on_bar_close_1m` chain. **Every tick that triggers a bar close kills the entire processing pipeline for that tick.**

However, this is evening-only (the diagnostic logging was committed in the afternoon). The morning session ran on older code without this print statement, so this bug didn't cause the morning failure.

---

## Timeline vs Ross

| Time (ET) | Ross | Bot |
|-----------|------|-----|
| 04:00 | Watching ONCO gap up PM | Cron fires, TWS fails to start |
| 07:00 | Enters ONCO at $5.25 (micro pullback) | TWS still dead after 36 retries |
| 07:00-08:30 | Multiple ONCO trades (+$6,800 net) | Bot doesn't exist |
| 08:30-09:00 | Watching ARTL prove itself at $4.40→$5.80 | Bot doesn't exist |
| 09:07 | ARTL breaking $6.80 | Manual start #1 — subscribes ONCO+ARTL |
| 09:07-09:17 | Trades ARTL through $7→$8.60→$9.50 | Bot has heartbeats but 0 ticks received |
| 09:20 | | Manual start #2 — re-subscribes ONCO+ARTL |
| 09:29 | ARTL halted above $12 | Manual start #3 — ARTL dropped from scanner |
| 09:30-11:00 | Walking away with $20,869 | Watching ONCO with 0 SQ signals, 12 total ticks |
| 11:12 | Done for the day | First actual ticks arrive (too late) |

---

## Recommendations

### P0: Gateway Headless Switch (Monday)
Already directives. Eliminates the 2-hour startup delay that killed 4 consecutive mornings.

### P0: Tick Data Debugging
The near-zero tick count is the deeper problem. Even when the bot was running and subscribed, it received almost nothing. CC needs to add:
1. **Tick counter per symbol** — log every 60s: `"{symbol}: {tick_count} ticks in last 60s"`
2. **Subscription verification** — after `reqMktData`, check that `ticker.ticks` is actually populating within 10 seconds
3. **Heartbeat with tick audit** — the 1-minute heartbeat should include tick counts per symbol, not just watch count

### P0: Scanner Results Preservation
`scanner_results/2026-03-27.json` is empty because each scanner run overwrites the file. Change to **append mode** or save per-checkpoint snapshots so we don't lose the evidence.

### P1: Pre-Open Scanner (04:00-07:00 ET)
Ross found ONCO at 4 AM because he monitors the premarket gap scanner before the session. The bot's first scan at 09:07 missed 5 hours of premarket activity. The live_scanner.py (Databento) is designed for this but isn't wired into the bot's startup flow yet.

### P1: Investigate Competing Sessions
Three manual restarts on two different ports (7497 and 4002) may have left zombie connections that confused IBKR's data routing. CC should add explicit `ib.disconnect()` and subscription cleanup on restart.

---

## Key Insight

Even if the bot had been running from 04:00 ET with perfect tick data, the current squeeze detector likely wouldn't have caught Ross's ONCO trades. Ross entered at $5.25 on a micro-pullback off the 10-second chart at 7 AM — that's exactly the MP V2 scenario (not a squeeze). The squeeze on ONCO was the initial gap from $3→$7.50 in premarket, which the bot can't trade.

ARTL is the real missed opportunity. It squeezed from $5.80 through $6.80, $7, $8.60, $9, $9.50, and halted at $12+. That's a textbook squeeze cascade — multiple breakouts through whole dollar levels with volume. If the bot had been running from 08:00 with working tick data, the SQ detector should have fired on the $6.80 or $7.00 level break.

**The gap isn't strategy. The gap is infrastructure.** Fix Gateway autostart + tick data delivery, and the strategy can finally be tested live.
