# Live Bot vs Backtest Audit — 2026-03-24

**Author**: Cowork (Opus)
**Purpose**: Identify every place where the live bot (bot.py + trade_manager.py) diverges from the backtesting engine (simulate.py) to ensure what we're backtesting is what we're trading.

---

## CRITICAL GAPS (Will Cause Different Results)

### 1. NO SQUEEZE DETECTOR IN LIVE BOT

**Severity: CRITICAL**

| Component | simulate.py | bot.py |
|-----------|------------|--------|
| SqueezeDetector import | Yes (line 1723) | **NO** |
| WB_SQUEEZE_ENABLED read | Yes | **NO** |
| Squeeze ARM/trigger logic | Full state machine | **Missing entirely** |
| sq_target_hit exit | Full implementation | **Missing entirely** |
| Squeeze trailing stop | Full implementation | **Missing entirely** |

The backtest produces trades via `SqueezeDetector` (the primary strategy per megatest data: 70% WR, +$118K). The live bot has **zero squeeze code**. It only runs `MicroPullbackDetector`, which is currently gated OFF (`WB_MP_ENABLED=0`).

**Impact**: The bot literally cannot take the trades that backtesting shows are profitable. With MP off and no squeeze, the live bot is trading nothing.

**Fix**: Import and wire `SqueezeDetector` into bot.py with the same entry/exit flow as simulate.py. This is the #1 priority.

---

### 2. NO SQUEEZE EXIT LOGIC IN trade_manager.py

**Severity: CRITICAL**

simulate.py has a dedicated `_squeeze_tick_exits()` method (line 608) that handles:
- Pre-target squeeze trailing stop (protect gains before 2R hit)
- `sq_target_hit` at 2R (core exit, partial or full)
- Post-target runner detection and trailing
- Squeeze-specific stop ratcheting

trade_manager.py has **none of this**. The `_manage_exits()` method only handles:
- Signal mode: trail + hard stop
- Classic mode: TP/runner/chandelier
- Ross exit signals (on 1m bars)

Even if squeeze entries were wired in, the exit logic would use signal-mode trailing (wrong for squeeze) instead of the dedicated squeeze exit flow.

**Fix**: Port `_squeeze_tick_exits()` from SimTradeManager to PaperTradeManager, or refactor to share the code.

---

### 3. BAIL TIMER: LIVE ONLY (Not in Backtest)

**Severity: MODERATE**

trade_manager.py has bail timer (exit unprofitable trades after N minutes):
```python
self.bail_timer_enabled = True  # WB_BAIL_TIMER_ENABLED=1
self.bail_timer_minutes = 5     # WB_BAIL_TIMER_MINUTES=5
```

simulate.py has **no bail timer**. The comment on line 2266 mentions it ("Keeps: bail timer...") but there's no actual implementation. Bail timer only exists in trade_manager.py's `_manage_exits()` (line 2956).

**Impact**: Backtest may show trades that linger unprofitably for 10+ minutes and eventually recover. Live bot would have exited them at 5 minutes. This can go either way — bail timer prevents some losers from getting worse, but also kills trades that would have recovered.

**Fix**: Add bail timer to SimTradeManager.on_tick() so backtest results reflect what the live bot actually does.

---

### 4. CLASSIFIER: LIVE CONFIG ENABLED BUT UNUSED IN BACKTEST

**Severity: MODERATE**

.env has `WB_CLASSIFIER_ENABLED=1` (live default per CLAUDE.md). But:
- bot.py has **no classifier import** — the env var is read by nobody in the live bot
- simulate.py has no classifier integration either
- classifier.py exists but is only used by validate_classifier.py (research)

The classifier was designed to categorize stocks and adjust exit thresholds. It's configured ON but not actually wired into anything. This isn't a divergence per se (both ignore it), but it means the config is misleading.

**Fix**: Either wire classifier into both bot.py and simulate.py, or set `WB_CLASSIFIER_ENABLED=0` in .env to reflect reality.

---

## MODERATE GAPS (May Cause Edge-Case Differences)

### 5. VWAP RECLAIM DETECTOR: BACKTEST ONLY

simulate.py imports and runs `VwapReclaimDetector` (when `WB_VR_ENABLED=1`). bot.py does not. Currently VR is disabled in .env so this doesn't matter today, but if someone enables it, it'll only work in backtests.

### 6. BID QUALITY VALIDATION: LIVE ONLY

trade_manager.py's `_manage_exits()` checks:
- Stale bid guard (>10s without update → skip exit check)
- Phantom bid rejection (bid deviates >N% from last trade)
- Wide spread rejection

simulate.py uses price directly with no bid/ask validation. This is expected (backtest has no order book), but means live exits may fire at slightly different prices than backtest exits.

### 7. HALT-THROUGH LOGIC: LIVE ONLY (Partially in Backtest)

trade_manager.py has full halt-through support:
- Feed silence detection (`WB_HALT_DETECT_SEC=30`)
- Frozen bail timer during halts
- Resume grace period
- Max duration safety

simulate.py only has halt detection for squeeze/VR trades, not for the main MP/signal-mode flow. Since halt-through is currently OFF (`WB_HALT_THROUGH_ENABLED=0`), this doesn't matter today.

### 8. QUOTE-AWARE ENTRY LIMITS: LIVE ONLY

trade_manager.py uses live bid/ask for entry pricing:
- Ask chase guard (skip if ask moved >5% above signal)
- Phantom bid gate
- Wide spread gate
- Dynamic limit padding based on current spread

simulate.py uses `entry + slippage` (fixed $0.02 default). This means backtest entries are slightly optimistic — they always fill at trigger + $0.02, while live entries may miss fast moves or get worse fills on wide spreads.

### 9. PILLAR GATES: DIFFERENT IMPLEMENTATION LOCATIONS

Both have pillar gates, but:
- simulate.py: Checks pillar gates inline in the main loop (lines 2573, 2786)
- bot.py: Delegates to `trade_manager._check_pillar_gates()` (line 1170)

The actual logic reads the same env vars, but the bot checks pillars in `on_signal()` while the sim checks them before calling `on_signal()`. Functionally equivalent, but any future change to one could miss the other.

### 10. 10s BAR EXIT PATTERN DETECTION

Both have TW/BE exit detection on 10s bars, but the implementation differs:
- bot.py: `on_bar_close_10s()` checks `det.last_patterns` for TOPPING_WICKY, then calls `trade_manager.on_bar_close()` which internally handles BE
- simulate.py: `on_10s_close()` callback checks the same patterns with identical grace/profit gates

These should produce the same results, but the code is duplicated rather than shared, so any fix to one must be manually applied to the other.

---

## ALIGNED (Working the Same)

| Feature | Status |
|---------|--------|
| MicroPullbackDetector state machine | Same code, same class |
| Stale stock filter | In detector, shared |
| Exhaustion filter + dynamic scaling | In detector, shared |
| MACD hard gate | In detector, shared |
| Score calculation | In detector, shared |
| Signal mode trailing stop logic | Equivalent in both |
| Hard stop / max_loss_hit | Equivalent in both |
| Float-tiered max loss cap | Both read same env vars |
| Re-entry cooldown | Both implement per-symbol tracking |
| No-reentry after loss (Gate 5) | Both implement |
| Ross Exit system | Both use RossExitManager from ross_exit.py |
| Continuation hold | Both read same env vars |
| R-multiple trailing stop on 10s bar | Both implement |
| Position sizing (risk/$, notional cap) | Equivalent |

---

## PRIORITY ACTION ITEMS

| # | Action | Severity | Effort |
|---|--------|----------|--------|
| 1 | **Wire SqueezeDetector into bot.py** | CRITICAL | 2-3 hours |
| 2 | **Port squeeze exit logic to trade_manager.py** | CRITICAL | 2-3 hours |
| 3 | **Add bail timer to simulate.py** | MODERATE | 30 min |
| 4 | **Clean up WB_CLASSIFIER_ENABLED** | LOW | 5 min |
| 5 | Port VwapReclaimDetector to bot.py (when ready) | LOW | 1-2 hours |

**Items 1 and 2 must be done before the bot can trade what we're backtesting.** Without squeeze in the live bot, our backtests are science fiction — they show what the bot *could* do, not what it *will* do.

---

## SUMMARY

The live bot is fundamentally misaligned with the backtesting engine. The backtester's primary strategy (Squeeze, 70% WR, +$118K) doesn't exist in the live bot. The live bot's only strategy (Micro Pullback) is gated OFF. The net result: **the live bot currently cannot take any trades**.

This was fine during the study phase, but if we're moving toward live trading with squeeze as the primary strategy, wiring SqueezeDetector + squeeze exit logic into the live bot is the single most important piece of work remaining.
