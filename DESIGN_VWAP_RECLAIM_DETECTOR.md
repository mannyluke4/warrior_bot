# Strategy 4: VWAP Reclaim Detector — Design Document

## Overview

The VWAP Reclaim detector implements Ross Cameron's "first 1-minute candle to make a new high after price crosses back above VWAP" pattern. This is a fundamentally different setup from both micro-pullback (trend continuation) and squeeze (volume explosion breakout). It catches the moment when a stock that dipped below VWAP recovers and shows renewed buying pressure.

## Evidence From Live Analysis

### CHNR 2026-03-19 (Ross: +$2,506)
- **Trade 1 (VWAP Curl, scratched -$67)**: Price broke below VWAP → curled back above ~$5.15 → entered on reclaim → flushed to $5.00 → scratched. Classic VWAP reclaim that failed.
- **Trade 3 (VWAP + $6 break, +$2,000)**: VWAP reclaim → break through $6.00 whole dollar → rode to $6.60. VWAP reclaim was the LEAD-IN signal.
- 2 of 3 Ross trade sequences on CHNR were VWAP reclaim setups.

### ARTL 2026-03-18 (Ross: +$9,653)
- **08:16**: Ross attempted VWAP reclaim / first candle new high. Failed (-$1,000 loss), but the pattern was correct — he just got the timing wrong.
- **08:22-08:26**: Multiple curl attempts back toward $8.00 area, all VWAP-reclaim-adjacent entries.

### Key Takeaway
Ross uses VWAP reclaim as both a standalone entry AND as a confirmation signal that a stock is ready for the next leg. It's his bread-and-butter re-entry pattern after a pullback.

---

## State Machine: IDLE → BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED

```
IDLE ──────────────────────────────────────────────────────────────────────┐
  │ Price drops below VWAP (close < VWAP)                                 │
  ▼                                                                       │
BELOW_VWAP                                                                │
  │ Price closes above VWAP (close > VWAP) + volume confirmation          │
  ▼                                                                       │
RECLAIMED                                                                 │
  │ Next 1m bar makes new high (high > prior bar high) + body filter      │
  ▼                                                                       │
ARMED (entry = reclaim bar high + $0.02, stop = reclaim bar low)          │
  │ Tick price breaks trigger_high                                        │
  ▼                                                                       │
TRIGGERED → on_signal() → trade opened                                    │
  │                                                                       │
  └── Any reset condition ───────────────────────────────────────────────→─┘
```

---

## Entry Criteria (ALL must be true)

### Phase 1: BELOW_VWAP Detection
1. **Price closes below VWAP** on a 1m bar
2. Must have been above VWAP at some point earlier in the session (prevents triggering on stocks that gapped below VWAP and never recovered)
3. Track: `below_vwap_bars` counter (how many bars spent below)

### Phase 2: RECLAIM Detection (BELOW_VWAP → RECLAIMED)
4. **Price closes above VWAP** on a 1m bar (the reclaim candle)
5. **Volume confirmation**: Reclaim bar volume ≥ 1.5x average of prior 5 bars (shows real buying, not a drift)
6. **Bar is green** (close > open)
7. **Price in valid range**: $2.00 - $20.00
8. **MACD filter** (optional, gated): MACD line > signal line, or MACD histogram positive/rising

### Phase 3: ARMED (RECLAIMED → ARMED)
9. **Next bar makes new high**: On the next 1m bar, high > reclaim bar high (Ross's exact criterion: "first 1-minute candle to make a new high")
10. **Body confirmation**: New-high bar has body ≥ 0.5% of open (not a thin wick fake-out)
11. Entry price = new-high bar high + $0.02 (breakout buffer)
12. Stop = lower of (reclaim bar low, new-high bar low)
13. R = entry - stop (risk per share)

### R Constraints
- MIN_R = $0.03 (same as MP)
- MAX_R = $0.50 (tighter than squeeze — VWAP reclaims are lower-volatility setups)
- If R > 3% of price → reject (too wide for this pattern)

---

## Exit Rules

VWAP Reclaim trades use a BLENDED exit profile between MP and squeeze:

| Exit | Rule | Rationale |
|------|------|-----------|
| **Hard Stop** | stop_low | Same as all strategies |
| **Core TP** | 75% at 1.5R | Slightly wider than MP (1.0R) — reclaims tend to have more room |
| **Runner Trail** | 25% at 2.0R trailing | Catch the continuation if it's a real reclaim |
| **VWAP Loss** | Exit all if price closes below VWAP again | The thesis is dead if VWAP is lost again |
| **Time Stop** | Exit if no progress after 5 bars | Prevent holding dead-cat bounces |
| **Bearish Engulfing** | 10s bar BE detection (existing) | Same as MP |
| **Topping Wicky** | 10s bar TW detection (existing) | Same as MP |

### VWAP Loss Exit (UNIQUE to this strategy)
This is the critical differentiator: if price drops back below VWAP after a reclaim entry, the entire setup thesis is invalidated. Exit immediately regardless of P&L. This is exactly how Ross traded it — he scratched CHNR Trade 1 at -$67 when price flushed back through VWAP.

---

## Reset Conditions (→ IDLE)

| Condition | When |
|-----------|------|
| VWAP lost while BELOW_VWAP | 5+ bars below VWAP without reclaim → give up, stock is weak |
| Price drops >5% below VWAP | Severe weakness — not a dip, it's a dump |
| Reclaim fails (RECLAIMED → IDLE) | 3 bars after reclaim without new high → false reclaim |
| Max attempts reached | 2 attempts per stock per session (lower than squeeze — reclaims either work or they don't) |
| Already in trade | Don't detect new reclaims while a VWAP reclaim trade is open |

---

## Configuration (Env Vars)

All gated by `WB_VR_ENABLED=0` (OFF by default).

```bash
# Master gate
WB_VR_ENABLED=0

# Detection
WB_VR_VOL_MULT=1.5          # Reclaim bar volume >= 1.5x avg of prior 5 bars
WB_VR_MIN_BODY_PCT=0.5      # Min body % for new-high confirmation bar
WB_VR_MAX_BELOW_BARS=10     # Max bars below VWAP before giving up
WB_VR_MAX_R=0.50            # Max R (risk per share)
WB_VR_MAX_R_PCT=3.0         # Max R as % of price
WB_VR_MACD_GATE=0           # Require MACD bullish for reclaim (optional)
WB_VR_RECLAIM_WINDOW=3      # Bars after reclaim to wait for new-high confirmation
WB_VR_MAX_ATTEMPTS=2        # Max reclaim attempts per stock per session

# Sizing
WB_VR_PROBE_SIZE_MULT=0.5   # First attempt = 50% size (probe)
WB_VR_FULL_AFTER_WIN=1      # Full size after first winner

# Exits
WB_VR_CORE_PCT=75           # Core position percentage
WB_VR_TARGET_R=1.5          # Core TP at 1.5R
WB_VR_RUNNER_TRAIL_R=2.0    # Runner trails at 2.0R below peak
WB_VR_VWAP_EXIT=1           # Exit all if price closes below VWAP (CRITICAL)
WB_VR_STALL_BARS=5          # Exit if no progress after N bars
WB_VR_MAX_LOSS_DOLLARS=300  # Absolute dollar cap per VR trade (lower than squeeze)
```

---

## Integration Pattern (follows squeeze_detector.py exactly)

### File: `vwap_reclaim_detector.py`

```python
class VwapReclaimDetector:
    """IDLE → BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED"""

    def __init__(self):
        self.enabled = os.getenv("WB_VR_ENABLED", "0") == "1"
        # ... config from env vars ...

    def seed_bar_close(self, o, h, l, c, v):
        """Warm up indicators — no signals."""

    def on_bar_close_1m(self, bar, vwap=None) -> Optional[str]:
        """Main detection on 1m bar closes. Returns status message."""

    def on_trade_price(self, price, is_premarket=False) -> Optional[str]:
        """Tick trigger check. Returns ENTRY SIGNAL message if triggered."""

    def notify_trade_opened(self):
        self._in_trade = True

    def notify_trade_closed(self, symbol, pnl):
        if pnl > 0: self._has_winner = True
        self._in_trade = False

    def reset(self):
        """Reset for new day/stock."""
```

### In simulate.py (same pattern as squeeze):

```python
# After squeeze detector creation:
from vwap_reclaim_detector import VwapReclaimDetector
vr_det = VwapReclaimDetector()
vr_det.symbol = symbol
vr_enabled = os.getenv("WB_VR_ENABLED", "0") == "1"

# In 1m bar handler (after MP and squeeze):
if vr_enabled and sim_mgr.open_trade is None:
    vr_msg = vr_det.on_bar_close_1m(bar, vwap=vwap)

# In tick handler (priority: squeeze > vwap_reclaim > micro_pullback):
if vr_enabled and vr_det.armed and sim_mgr.open_trade is None:
    vr_trigger = vr_det.on_trade_price(price, is_premarket=is_premarket)
    if vr_trigger and "ENTRY SIGNAL" in vr_trigger:
        trade = sim_mgr.on_signal(..., setup_type="vwap_reclaim", ...)
```

### Entry Priority Order
1. **Squeeze** (highest conviction — volume explosion + level break)
2. **VWAP Reclaim** (medium conviction — structural reclaim with volume)
3. **Micro Pullback** (classic — trend continuation)

If multiple strategies are armed on the same tick, the higher-priority strategy fires.

---

## Test Plan

### Manual Backtests (today — using cached tick data)

| Stock | Date | Discovery Time | Expected Result |
|-------|------|---------------|-----------------|
| CHNR | 2026-03-19 | 07:16 (precise) | Should catch Trade 1 (VWAP curl ~$5.15) and/or Trade 3 ($6 break) |
| ARTL | 2026-03-18 | ~07:41 (news hit) | Should catch 08:16 VWAP reclaim attempt |

For each test:
```bash
# With VR enabled:
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 [full config] \
python simulate.py SYMBOL DATE START 12:00 --ticks -v
```

### Overnight CC Backtests (per-stock precise discovery times)
Queue the full Jan 2025 - Mar 2026 run with VR enabled. CC will:
1. Use existing `scanner_results/*.json` for candidates
2. Use `sim_start` (precise discovery time) for each stock
3. Run with MP + Squeeze + VR all enabled
4. Report per-strategy P&L breakdown

### Regression Check
VERO and ROLR should be UNCHANGED since VR only fires when price drops BELOW VWAP and reclaims. On strong squeeze stocks, price rarely dips below VWAP during the initial run.

---

## Interaction With Existing Strategies

### vs Micro Pullback
- MP requires IMPULSE → PULLBACK → ARM (price stays above VWAP/EMA)
- VR fires when price is BELOW VWAP and comes back → fundamentally different trigger
- No conflict: if price is above VWAP, MP handles it. If below, VR watches for reclaim.

### vs Squeeze
- Squeeze requires volume explosion + key level break + new HOD
- VR doesn't need new HOD or level break — just VWAP cross + new-high confirmation
- They can coexist: squeeze catches the first-leg explosion, VR catches the post-dip recovery
- Entry priority: squeeze > VR if both armed simultaneously

### Portfolio Risk
- VR max loss capped at $300 (vs $500 for squeeze, $1K for MP)
- Max 2 attempts per stock (vs 3 for squeeze)
- Probe sizing on first attempt (50%)
- Independent counters: VR trades don't consume MP or squeeze attempt slots

---

*Design by Cowork (Opus) — 2026-03-20*
*Evidence base: CHNR 2026-03-19, ARTL 2026-03-18 gap analyses*
