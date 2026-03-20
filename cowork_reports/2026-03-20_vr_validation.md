# CC Report: VWAP Reclaim (Strategy 4) Validation
## Date: 2026-03-20
## Machine: Mac Mini

### Phase 1: Regression — PASS
- VERO: +$18,583 (target: +$18,583)
- ROLR: +$6,444 (target: +$6,444)
- VR code compiles cleanly, no impact on existing strategies when VR OFF

### Phase 2: CHNR 2026-03-19 Results

| Config | Trades | P&L | Setup Types | Notes |
|--------|--------|-----|-------------|-------|
| MP+SQ only | 2 | +$429 | 2 squeeze | Baseline |
| MP+SQ+VR | 2 | +$429 | 2 squeeze | VR detected reclaims but never armed |

**VR did not produce any trades on CHNR.** The detector was active and went through state transitions:

Key VR events:
```
[07:22] VR_RECLAIMED: close=5.07 > VWAP=4.97, vol=1.8x → reclaim_window_expired (3 bars, no new high)
[07:44] VR_RECLAIMED: close=5.43 > VWAP=5.00, vol=5.1x → VR_NO_ARM: max_r_exceeded R=1.04 > max=0.50
[08:27] VR_RECLAIMED: close=5.38 > VWAP=5.37, vol=3.1x → vwap_lost_after_reclaim (immediate re-loss)
```

**Analysis**: CHNR reclaimed VWAP 3 times but:
1. First reclaim: no new high within 3 bars (stock stalling)
2. Second reclaim: R too wide ($1.04 > $0.50 max) — parabolic volatility
3. Third reclaim: VWAP immediately lost again — weak bounce

This is actually correct behavior — CHNR was a gap-and-fade stock. The VR detector correctly avoided entering what would have been losing trades.

### Phase 3: ARTL 2026-03-18 Results

| Config | Trades | P&L | Setup Types | Notes |
|--------|--------|-----|-------------|-------|
| MP+SQ only | 2 | -$1,689 | 1 squeeze (-$2,611), 1 MP (+$922) | Baseline |
| MP+SQ+VR | 2 | -$1,689 | 1 squeeze (-$2,611), 1 MP (+$922) | VR detected activity but no trades |

**VR did not produce any trades on ARTL either.** The detector saw VWAP loss/reclaim cycles but:
- Multiple `VR_BELOW_VWAP` detections followed by `severe_vwap_loss` resets
- Stock's large range created R values exceeding the $0.50 cap
- Repeated `too_long_below_vwap` resets in the afternoon fade

**Note**: ARTL's sim_start here is 08:00 (checkpoint timing). With precise discovery or 07:00 start, the squeeze would have caught the first leg (+$6,963). The late start is what makes this a losing session.

### Summary

| Metric | Result |
|--------|--------|
| Regression | PASS (VERO +$18,583, ROLR +$6,444) |
| CHNR delta (VR ON vs OFF) | $0 (no VR trades) |
| ARTL delta (VR ON vs OFF) | $0 (no VR trades) |
| VR state machine | Working correctly — IDLE → BELOW_VWAP → RECLAIMED → (RESET or NO_ARM) |
| VR trades produced | 0 across both stocks |

### Key Observations

1. **The VR detector is working correctly** — it transitions through all states and logs detailed reasons for resets and no-arms. The code is sound.

2. **Neither test stock produced a VR trade.** CHNR was a gap-and-fade (weak reclaims), ARTL had too-wide R values from parabolic volatility. Both are arguably correct no-trade decisions.

3. **The R-cap ($0.50) may be too tight for VWAP reclaim setups.** At 07:44 CHNR had a legitimate reclaim with 5.1x volume but R was $1.04 — double the cap. VWAP reclaims on volatile stocks naturally have wider stops. Consider `WB_VR_MAX_R=0.80` (matching squeeze) or using a percentage-based cap.

4. **The reclaim window (3 bars) may be too short.** The 07:22 reclaim on CHNR was genuine but the stock needed more than 3 minutes to set up a new high. Consider `WB_VR_RECLAIM_WINDOW=5`.

5. **These two stocks may not be ideal VR candidates.** Both were first-leg momentum plays (squeeze territory). VR is designed for second-leg entries after a dip — stocks that gap up, pull back below VWAP, then recover. We need to test on stocks that had strong morning runs, dipped below VWAP mid-morning, then recovered (e.g., a stock that runs 7-8 AM, dips 8-9 AM, then reclaims at 9:30).

6. **Recommend NOT running full YTD yet.** The detector works but produced 0 trades on 2 test stocks. We should first identify 2-3 known VWAP reclaim stocks from the historical data and validate on those before committing to a 55-day run.

### Files Changed
- `cowork_reports/2026-03-20_vr_validation.md` (this file)
