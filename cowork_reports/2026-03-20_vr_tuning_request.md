# CC Report: VR Detector Tuning Request for Cowork
## Date: 2026-03-20
## Machine: Mac Mini
## Action Required: Cowork to identify VR test stocks from historical data

---

### What We Know

The VWAP Reclaim detector (Strategy 4) is implemented and compiles cleanly. The state machine works correctly:

```
IDLE → BELOW_VWAP → RECLAIMED → (ARMED → TRIGGERED) or (RESET)
```

But it produced **0 trades** on both test stocks (CHNR 2026-03-19, ARTL 2026-03-18). Both were first-leg momentum plays — not the "dip below VWAP then recover" pattern VR is designed for.

### Why It Didn't Fire

**CHNR 2026-03-19 — 3 reclaim attempts, 0 ARMs:**

| Time | Event | Reason Failed |
|------|-------|---------------|
| 07:22 | RECLAIMED (vol 1.8x) | `reclaim_window_expired` — 3 bars, no new high |
| 07:44 | RECLAIMED (vol 5.1x) | `max_r_exceeded` — R=$1.04 > max $0.50 |
| 08:27 | RECLAIMED (vol 3.1x) | `vwap_lost_after_reclaim` — immediate re-loss |

**ARTL 2026-03-18 — multiple BELOW_VWAP detections, 0 reclaims that stuck:**
- Repeated `severe_vwap_loss` resets (stock dropping too far below VWAP)
- `too_long_below_vwap` resets in afternoon fade
- R values from parabolic volatility exceeded $0.50 cap

### What Cowork Needs To Do

**Task 1: Find 5-10 historical stocks that exhibit the classic VWAP reclaim pattern:**

The ideal VR candidate looks like this:
1. Stock gaps up 10-50% premarket with strong volume
2. Runs in first 30-60 minutes (squeeze/MP territory)
3. **Pulls back BELOW VWAP** — this is the key moment
4. Consolidates below VWAP for 5-30 minutes (not a flash dip)
5. **Reclaims VWAP** with volume confirmation (new 1m bar closes above VWAP)
6. Makes a new high after reclaim → this is the VR entry
7. Continues higher for at least 1-2R

**Where to look:**
- Scanner results exist for Sep 2025 - Mar 2026 (~300 dates)
- `scanner_results/*.json` has all candidates with gap%, RVOL, float, price
- Focus on Profile A stocks (float < 5M) with gap 10-30% — these are most likely to have the run → dip → reclaim pattern
- Stocks that had MULTIPLE trades in the YTD/OOS backtests are good candidates — they likely had enough price action for a VWAP reclaim to occur

**Suggested approach:** For each promising date/stock, check if the stock:
- Had a session high significantly above VWAP (indicating a run)
- Later closed 1m bars below VWAP (indicating a dip)
- Then recovered above VWAP (indicating a reclaim)

This can be checked programmatically by fetching 1m bars and looking for the pattern: `close > VWAP → close < VWAP → close > VWAP` with volume on the reclaim bar.

**Task 2: Suggest threshold adjustments based on findings:**

Current thresholds that may need tuning:

| Parameter | Current | Issue | Suggested Range |
|-----------|---------|-------|-----------------|
| `WB_VR_MAX_R` | $0.50 | Too tight for volatile small-caps | $0.50 - $1.00 |
| `WB_VR_MAX_R_PCT` | 3.0% | May also be too tight | 3.0% - 5.0% |
| `WB_VR_RECLAIM_WINDOW` | 3 bars | Too short for consolidation | 3 - 7 bars |
| `WB_VR_VOL_MULT` | 1.5x | Might need higher for conviction | 1.5x - 3.0x |
| `WB_VR_MAX_BELOW_BARS` | 10 bars | May be too short for real dips | 10 - 30 bars |
| `WB_VR_MAX_LOSS_DOLLARS` | $300 | Seems reasonable, validate | $300 - $500 |

**Task 3: Create a directive with specific backtest commands:**

Once stocks are identified, provide:
```
Stock: XXXX
Date: YYYY-MM-DD
sim_start: HH:MM (from scanner discovery)
Expected behavior: "Stock ran to $X at 07:30, dipped below VWAP at 08:15, reclaimed at 09:00"
```

CC will run the backtests and report results.

### Current VR Env Vars (for reference)

```bash
WB_VR_ENABLED=1
WB_VR_VOL_MULT=1.5          # Reclaim bar volume >= 1.5x avg
WB_VR_MIN_BODY_PCT=0.5      # Min body % for confirmation bar
WB_VR_MAX_BELOW_BARS=10     # Max bars below VWAP before reset
WB_VR_MAX_R=0.50            # Max risk per share
WB_VR_MAX_R_PCT=3.0         # Max R as % of price
WB_VR_MACD_GATE=0           # MACD filter (off)
WB_VR_RECLAIM_WINDOW=3      # Bars after reclaim to confirm new high
WB_VR_MAX_ATTEMPTS=2        # Max attempts per stock
WB_VR_PROBE_SIZE_MULT=0.5   # Half size first attempt
WB_VR_CORE_PCT=75           # Core position %
WB_VR_TARGET_R=1.5          # Core TP
WB_VR_RUNNER_TRAIL_R=2.0    # Runner trail
WB_VR_VWAP_EXIT=1           # Exit if VWAP lost
WB_VR_STALL_BARS=5          # Time stop
WB_VR_TRAIL_R=1.5           # Pre-target trail
WB_VR_MAX_LOSS_DOLLARS=300  # Dollar cap
```

### What CC Has Running

- Full re-scan of ~296 dates with precise discovery timestamps (background, ~2 hours remaining)
- Live bot on ARTL for rest of today's session
- Corrected YTD + OOS backtests queued after re-scan completes (MP + squeeze only, no VR)

### Bottom Line

VR plumbing is solid. We need Cowork to find the right test stocks from historical data so we can validate the detector on actual VWAP reclaim patterns — not gap-and-fade stocks. Once we have 5-10 confirmed candidates with expected behavior, CC will run the backtests and we'll tune thresholds based on real data.
