# Directive: March 27 Morning Backtest
## Priority: URGENT — Validate live bot detection chain
## Date: 2026-03-27

---

## Context

March 27 morning session: bot started at 09:07 ET (late — TWS failed on cron, manual start). Watched ONCO and ARTL. ONCO halted twice (09:32 and 09:38). Zero trades taken. Zero squeeze ARM/TRIGGER events logged.

This is the **third consecutive day** with zero trades on V2. March 25 had FEED (one trade, exit bug). March 26 was volume=0 bug (fixed). March 27 has no known bug — but also no evidence the squeeze detector is even attempting to ARM on live data.

**Manny's concern:** Is the detection chain actually wired correctly end-to-end in the live bot? Or is there another silent bug like volume=0?

---

## Tasks

### Task 1: Backtest March 27 Morning Candidates

Run simulate.py on today's candidates to determine if 0 trades is EXPECTED (no setups) or a BUG (setups exist but bot missed them).

```bash
# ONCO — the primary candidate, halted 2x, sub-1M float
python simulate.py ONCO 2026-03-27 07:00 12:00 --ticks --tick-cache tick_cache/

# ARTL — second candidate, watched from 09:07-09:20 ET
python simulate.py ARTL 2026-03-27 07:00 12:00 --ticks --tick-cache tick_cache/
```

If tick cache doesn't have today's data (likely — tick cache is saved at session end), try bar mode:
```bash
python simulate.py ONCO 2026-03-27 07:00 12:00
python simulate.py ARTL 2026-03-27 07:00 12:00
```

**Key questions to answer:**
1. Does the squeeze detector PRIME on any bars? (volume spike + body criteria)
2. Does it ARM? (level identified within prime window)
3. Does it TRIGGER? (price breaks level)
4. If it ARMs but doesn't trigger — what level was it watching and did price approach it?
5. If it doesn't even PRIME — what was the bar volume vs the min_bar_vol threshold (50K)?

### Task 2: Verbose Detector Logging

If Task 1 shows 0 trades in backtest too (confirming 0 trades is expected), that's fine — just a quiet day.

If Task 1 shows the backtest DOES produce trades but the live bot didn't, we have another bug. In that case:
- Add temporary verbose logging to `bot_ibkr.py`'s squeeze detector callbacks
- Log every `on_bar_close_1m()` call with: symbol, bar volume, body_pct, close vs VWAP, detector state
- Log every `on_trade_price()` call with: price, armed levels, distance to trigger
- Deploy for Monday morning so we can see exactly what the detector is doing on live data

### Task 3: Check Tick Data Flow

The volume=0 bug was fixed (Issue 3, March 26). But verify the fix is actually working on today's session:
- In the morning log, are there any indicators that bars are building with real volume?
- The heartbeat only shows watch count and P&L — it doesn't show bar volume. We have no visibility into whether bars are building correctly.
- **Suggestion:** Add a periodic diagnostic log line (every 5 minutes?) showing last bar's OHLCV for each subscribed symbol. This would have caught the volume=0 bug instantly.

---

## Expected Outcomes

- If ONCO/ARTL backtest = 0 trades → quiet day confirmed, no bug
- If backtest shows trades → live bot has another detection bug, verbose logging needed
- Either way, add diagnostic logging for bar data so we're not blind on Monday
