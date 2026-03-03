# EDSA Live Trade Report — March 3, 2026

**Position**: 7,293 shares @ $3.03 entry | Stop $2.92 | Entered 10:45 ET
**Exit**: Manually closed @ $3.55 avg fill (~2:00 PM ET)
**Peak**: +$7,418 at 11:57 ET (price $4.047)
**Duration**: Open ~3.5 hours | Bot blind to position entire time (reconcile bug)

---

## Complete Timeline

### Pre-Entry Signals (rejected)

| Time ET | Event | Price | Outcome |
|---------|-------|-------|---------|
| 9:29 | ARMED @ $2.42, score 10.3 | $2.42 | ❌ Wide spread 5.1% (bid $2.30 / ask $2.42) |
| 10:39 | ARMED @ $2.90, 11,111 shares | $2.90 | ❌ Insufficient buying power ($28,695 vs $32,222 needed) |
| 10:43 | ARMED @ $3.00, score 10.5 | $3.00 | ✅ Filled 6,666 shares |
| 10:44 | Bearish engulfing exit | $2.97 | 6,666 shares sold @ $2.96 → **-$267** |
| 10:45 | Re-armed @ $3.06, score 12.5 | $3.06 | ✅ Filled 7,293 shares @ $3.03 (actual) |

### Position P&L Timeline (7,293 shares @ $3.03)

| Time ET | Close | Unrealized P&L | Event |
|---------|-------|---------------|-------|
| 10:45 | $3.057 | +$198 | Entry bar — immediately ticked up |
| 10:46 | $3.190 | **+$1,166** | First big green bar |
| 10:47–10:57 | $3.12–3.27 | +$730–$1,386 | Choppy consolidation |
| **10:10** | **$3.000** | **-$219** | **First dip below entry** |
| **10:13** | **$2.940** | **-$656** | Dropped below stop territory |
| **10:15** | **$2.910** | **-$875** | **Below $2.92 stop** |
| **10:19** | **$2.880** | **-$1,094** | |
| **10:21** | **$2.840** | **-$1,386** | |
| **10:26** | **$2.774** | **-$1,864** | **SESSION LOW — deepest loss** |
| 10:30–10:42 | $2.90–$3.01 | -$948 to -$145 | Slow recovery |
| 10:43–10:46 | $3.03–$3.10 | +$0 to +$474 | Back above entry |
| 10:47–10:57 | $3.09–$3.17 | +$439–$1,021 | More chop |
| 11:41 | $3.292 | +$1,907 | Second impulse begins |
| 11:42 | $3.410 | +$2,771 | Ripping |
| 11:43 | $3.515 | +$3,537 | |
| 11:44 | $3.628 | +$4,365 | |
| 11:46 | $3.780 | +$5,470 | |
| 11:48 | $3.900 | +$6,345 | |
| 11:50 | $3.945 | +$6,673 | |
| **11:51** | **$4.010** | **+$7,147** | |
| **11:57** | **$4.047** | **+$7,418** | **PEAK UNREALIZED P&L** |
| 11:58–12:00 | $3.95–$3.92 | +$6,700–$6,491 | Topping wicky + bearish reset on 1m |
| 12:01+ | $3.57–$3.74 | +$3,959–$5,173 | Floating, no exit |
| ~1:30 PM | ~$3.65 | ~+$4,800 | Current |

---

## Critical Findings

### Finding 1: The Bot Is NOT Managing This Position (BUG)

**Root cause**: Reconcile mismatch at entry wiped the position from bot tracking.

At 10:45:12 ET — 12 seconds after fill — the reconcile check ran and found:
```
alp_qty: 0  (Alpaca's API showed 0 shares — propagation delay)
bot_qty: 7293  (bot's internal state had the position)
```

Alpaca's paper trading API has a ~10-30 second propagation delay before new positions appear. The bot's reconcile logic saw this mismatch and almost certainly cleared the internal `trade_manager.open["EDSA"]` entry (treating 0 Alpaca shares as truth). From that point:

- **Stop monitoring stopped** → explains why price hit $2.774 at 10:26 ET without triggering the $2.92 stop
- **Bearish engulfing exit checks stopped** → explains 3+ hours with no exit signals despite large pullbacks
- **No 10-second bar exit events** in the log for EDSA at any point in the session

The position survived and became hugely profitable despite the bot dropping it — pure luck that EDSA came back from -$1,864 to +$7,418 without hitting a firm Alpaca stop order.

**Evidence**:
- Only 1 reconcile_position event for EDSA (at entry), never again
- Zero exit_signal events after 10:45 ET
- Stop at $2.92 never triggered despite price hitting $2.774 on 10:26 close (10:26 low was even lower)
- 0 ten-second bar exit events for any symbol in the session log (10s bars not logged, but exit_signal events would still appear — they don't)

### Finding 2: No Runner Stop / Profit Protection

Even IF the bot were managing the position normally, it has no mechanism to:
- Raise the stop as the position gains
- Lock in profits above a threshold (e.g., move stop to breakeven at 2R, to 1R at 5R)
- Trail a stop below recent swing lows

The bot held through a dip from +$7,418 to +$3,959 (-$3,459 giveback) with no protective action. The exit signal mechanism (bearish engulfing on 10-second bars) is a good entry-style tool but is NOT designed for runner profit protection on a position that's already up 4.4R.

---

## What Should Have Happened

### Ideal scenario with functioning stop management:
1. **10:26 ET**: Stop at $2.92 fires when price hits $2.774 → exit @ ~$2.90 → **-$948 loss**
2. Position closed. EDSA runs to $4.06 without us → missed +$7,500 move.

That would be the "correct" but painful outcome. The stop existed to prevent exactly this scenario — a large adverse move.

### But EDSA recovered — so what if we had a trailing stop instead?
If the stop had been raised as the position gained:
- At +2R (~$3.30): raise stop to breakeven ($3.03) → survives the dip, holds through the run
- At +5R (~$3.72): raise stop to +2R ($3.30) → minimum guaranteed ~$1,970 profit
- At +7R (~$3.97): trail stop to ~$3.60 → captures ~$4,179 on exit

A trailing stop mechanism would have:
1. Protected against the early drawdown (breakeven stop at $3.03 triggers on dip → small loss, not -$1,864)
2. Protected the runner gains at the peak
3. Likely exited around $3.60-$3.70 → ~+$4,200-$4,900

---

## Two Bugs to Fix

### Bug 1: Reconcile Clears Position on Alpaca Propagation Delay (CRITICAL for live)

**Current behavior**: If `alp_qty == 0` and `bot_qty > 0` within seconds of a fill, the reconcile logic drops the position.

**Fix**: Add a grace period. Any position entered in the last 60 seconds should NOT be cleared by the reconcile even if Alpaca shows 0 shares. Trust the `entry_filled` event for the first 60 seconds.

```python
# In reconcile logic:
ENTRY_GRACE_SECONDS = 60
if bot_qty > 0 and alp_qty == 0:
    seconds_since_entry = (now - trade.entry_time).total_seconds()
    if seconds_since_entry < ENTRY_GRACE_SECONDS:
        # Alpaca propagation delay — keep position, skip reconcile
        continue
```

**Priority**: CRITICAL before any live real-money trading. In paper mode this lost us position management; in live mode this would leave a real position completely unprotected.

### Bug 2 (Feature): Trailing Stop / Profit Lock for Runners

**Proposed logic** (env-gated, OFF by default):

| Unrealized Gain | Stop Action |
|----------------|-------------|
| ≥ 2R | Raise stop to breakeven ($entry) |
| ≥ 4R | Raise stop to +1R |
| ≥ 6R | Raise stop to +3R (trailing) |
| ≥ 8R | Trail stop $0.15 below 10-bar highest close |

EDSA R = $0.11 (entry $3.03, stop $2.92).
- 2R = $3.25 → hit at 10:46 ET. Stop would move to $3.03.
- 4R = $3.47 → stop to $3.14. Dip to $2.77 → exits at $3.03 → ~+$0 (breakeven, much better than -$1,864)
- 6R = $3.69 → stop to $3.36
- 8R = $3.91 → trailing $0.15 below recent highs → stop ~$3.75

On the actual EDSA move, a trailing stop would have:
- Protected against the early -$1,864 drawdown (exits at breakeven)
- Then let the runner go to $4.06
- Trailed stop up to ~$3.75 as price peaked
- Likely exited ~$3.75-$3.80 → **+$5,100-$5,470**

---

## Final Result

| Event | Shares | Entry | Exit | P&L |
|-------|--------|-------|------|-----|
| Trade 1 (bearish engulfing exit) | 6,666 | $3.00 | $2.96 | -$267 |
| Trade 2 (manually closed) | 7,293 | $3.03 | $3.55 | **+$3,792** |
| **Net EDSA session** | | | | **+$3,525** |

**Peak unrealized**: +$7,418 at 11:57 ET ($4.047) — gave back ~$3,900 from peak due to no runner protection.

**What a trailing stop would have captured** (estimated):
- Stop raised to breakeven at 2R ($3.25, hit at 10:46 ET) → survives early dip, holds runner
- Trail raised to ~$3.75 as price peaked at $4.05 → exit ~$3.75-$3.80 → **+$5,100-$5,470**
- vs actual manually-closed result: **+$3,525**
- Trailing stop improvement estimate: **+$1,575-$1,945**

---

## Recommended Next Steps

1. **Fix reconcile grace period first** — before any live trading session
2. **Investigate: does the reconcile actually clear the position, or does it just log and move on?** Need to read `_reconcile_all_positions()` in `trade_manager.py` carefully
3. **Design trailing stop system** — propose config, backtest on known runners (VERO, GWAV, APVO) to verify it helps rather than exits too early
4. **Investigate the first -$267 trade**: the bearish engulfing exit fired 1 minute after entry at $2.97 when price quickly recovered to $3.19 on the very next bar. This suggests the bearish engulfing on 10s bars may be too sensitive for initial position entries.

---

*Report generated: March 3, 2026*
*Position still open at time of writing*
