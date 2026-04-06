# Bug Report: Live Bot Seed Bar Parity Issue

**Date:** April 6, 2026
**Author:** CC (Claude Code)
**Priority:** P0 — this affects whether the live bot can actually take the trades the backtest finds
**Discovered:** First live day with full monitoring

---

## The Problem

The live bot missed +$808 in trades that the backtest finds on the exact same date (April 6, 2026) using the exact same tick data (tick_cache). The squeeze detector stayed IDLE all morning on stocks where the sim finds entries and makes money.

**This is not a data issue.** Both the live bot and the sim had the same stocks (MLEC, FCUV). Both had IBKR tick data. The difference is HOW the bars are fed to the squeeze detector.

---

## What the Backtest Found (April 6, 2026)

| Stock | Trades | P&L | Details |
|-------|--------|-----|---------|
| PRFX | 0 | — | Never armed |
| MLEC | 1 | -$416 | Entry 07:43 @ $11.52, bearish engulfing exit |
| FCUV | 2 | +$1,224 | Loss -$357 (para trail 08:11), then +$1,581 (2R target 09:48) |
| IOTR | 0 | — | Never armed |
| PFSA | 0 | — | Armed but never triggered |
| **Total** | **3** | **+$808** | |

## What the Live Bot Did

| Stock | Result | Notes |
|-------|--------|-------|
| MLEC | sq=IDLE all morning | Seeded 43 bars, never armed |
| FCUV | sq=IDLE all morning | Seeded 29 bars, never armed |
| All others | sq=IDLE | Same — no arming, no triggers |
| **Total** | **0 trades, $0** | |

---

## Root Cause: How Bars Are Fed Differently

### Backtester (simulate.py)
1. Loads raw tick data from `tick_cache/2026-04-06/FCUV.json.gz`
2. Replays ticks one by one through `TradeBarBuilder`
3. Bars close naturally at 1-minute boundaries
4. Squeeze detector sees each bar in real time — volume spikes register as they happen
5. `vol_ratio` is computed against a running average that builds organically

### Live Bot (bot_v3_hybrid.py)
1. At catchup scan (~6:48 ET), discovers FCUV
2. Calls `ib.reqHistoricalData()` for 1-minute bars (gets 29 pre-built bars)
3. **Dumps all 29 bars into the squeeze detector at once** via the seed loop
4. Squeeze detector processes 29 bars in rapid succession — all in the same second
5. `avg_vol` baseline is computed from these 29 bars (includes pre-market low-volume bars)
6. When real ticks start arriving, the volume baseline is skewed
7. Bars that SHOULD trigger arming (vol_ratio > 3x threshold) show as 0.4x because the average is wrong

### The Critical Difference

```
SIM:  bar 1 → detect → bar 2 → detect → bar 3 → detect (organic, like real trading)
LIVE: bar 1, bar 2, bar 3, ..., bar 29 → all dumped → then live ticks start

The detector's internal state (volume averages, prime bar counting, etc.)
behaves differently when 29 bars arrive in 0.01 seconds vs 29 minutes.
```

---

## Evidence from Logs

FCUV live bot chart logs show `vol_ratio` never exceeding 2.4x during the entire session:

```
[08:15 ET] FCUV CHART | vol_ratio=0.6x avg_vol=104,470  ← should have armed here
[09:35 ET] FCUV CHART | vol_ratio=2.4x avg_vol=43,714   ← highest all day, still didn't arm
```

The sim's squeeze detector armed at 08:11 because it saw the volume spike in the context of organically-built volume history. The live bot's detector saw the same spike but against a different baseline.

---

## Impact Assessment

**This is not a "the backtests are useless" problem.** The backtests correctly identify which stocks have squeeze setups and what the P&L should be. The strategy logic is sound.

**This IS a "the live bot can't execute what the backtest finds" problem.** The plumbing that feeds historical bars to the detector doesn't match how the sim feeds them. The detector's state machine ends up in a different state after seeding vs after organic replay.

**How big is the gap?** Unknown without more live days to compare. April 6 was a quiet day (+$808 theoretical). On a big day with cascading entries (like AHMA +$109K in backtests), the miss could be enormous.

---

## Proposed Fix

**Goal:** Make the seed bar processing match the sim's replay exactly.

### Option A: Replay Seed Bars Through the Full Sim Path
Instead of dumping historical bars directly into the detector, replay them through `TradeBarBuilder.on_trade()` as synthetic ticks:

```python
# Current (broken):
for bar in historical_bars:
    detector.on_bar_close_1m(bar, vwap=vwap)  # 29 bars in 0.01 seconds

# Fixed:
for bar in historical_bars:
    # Synthesize a tick at bar close to drive TradeBarBuilder naturally
    bar_builder.on_trade(symbol, bar.close, bar.volume, bar.start_utc)
    # TradeBarBuilder will call on_bar_close_1m when the bar boundary crosses
```

This ensures the detector sees bars arrive at proper 1-minute boundaries with correct volume accumulation.

### Option B: Reset Detector Volume State After Seeding
After seeding, reset the squeeze detector's running volume average so that the first live bar is evaluated without seed bias. Simpler but less thorough — doesn't fix other state machine quirks from rapid bar injection.

### Option C: Use Tick-Level Historical Data for Seeding
Instead of `reqHistoricalData` (1m bars), pull tick data from IBKR for the seed period and replay it through `TradeBarBuilder.on_trade()` exactly like the sim does. Most accurate but slower (more IBKR API calls).

**Recommended: Option A** — it's the least invasive change and should achieve near-parity with the sim. Option C is the gold standard but may be too slow for live use.

---

## Where to Look

| File | Function | What Happens |
|------|----------|-------------|
| `bot_v3_hybrid.py` | `subscribe_symbol()` or `seed_bars()` | Where historical bars are fetched and fed to detectors |
| `bars.py` | `TradeBarBuilder.on_trade()` | How ticks become bars |
| `squeeze_detector.py` | `on_bar_close_1m()` | Where vol_ratio and arming decisions happen |
| `simulate.py` | Main loop | How the sim replays ticks — this is the "correct" behavior |

The fix should ensure that after seeding, `squeeze_detector.vol_ratio` on the next live bar produces the same value it would if those bars had arrived organically one per minute.

---

## Urgency

This should be fixed before the next trading day. Every day the live bot runs with this bug, it's potentially missing the exact trades the backtest says are profitable. The backtests aren't wrong — the live plumbing is.

---

*Report by CC (Claude Code). For Cowork + Manny review.*
