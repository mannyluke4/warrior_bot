# Tuning Brainstorm: What Can We Optimize?

**Date:** April 8, 2026
**Author:** CC (Claude Code)
**For:** Cowork + Manny
**Purpose:** Identify tuning levers worth A/B testing against the current YTD baseline

---

## Current Baseline (April 8, 2026)

```
$30K start, scaling notional (2x equity), MIN_R=0.06
Trades: 39, WR: 60% (23W/15L)
P&L: +$327,511 (+1,092%)
Equity: $357,511
```

This is our benchmark. Any tuning variation must beat this on P&L without destroying win rate or increasing max drawdown.

---

## Already Tested

| Variation | Result | Verdict |
|-----------|--------|---------|
| MIN_R=0.03 (looser) | +$316,747, 45 trades, 59% WR | **Worse** — extra trades are low quality |
| MIN_R=0.06 (current) | +$327,511, 39 trades, 60% WR | **Keep** |

---

## Tuning Levers to Test

### Category 1: Entry Sensitivity

**1a. VOL_MULT (volume spike threshold for priming)**
- Current: `WB_SQ_VOL_MULT=3.0` — bar volume must be 3x average to prime
- Test lower: 2.5x, 2.0x — catches more setups, but may add noise
- Test higher: 3.5x, 4.0x — fewer but higher-conviction entries
- **Why it matters:** This is the primary gate. Lowering it could catch setups like BBGI where the vol spike was borderline. Raising it filters to only the most explosive moves.

**1b. MIN_BAR_VOL (absolute volume floor)**
- Current: `WB_SQ_MIN_BAR_VOL=50000`
- Test lower: 25000, 10000 — allows lower-float stocks
- Test higher: 75000, 100000 — only high-liquidity setups
- **Why it matters:** Some of our best runners (VERO) had massive volume. But we might be filtering out mid-cap opportunities.

**1c. PRIME_BARS (how many bars after vol spike before arming)**
- Current: `WB_SQ_PRIME_BARS=3` — 3 bars to find a level break
- Test: 2, 4, 5
- **Why it matters:** Shorter window = faster entry but less confirmation. Longer = more confirmation but may miss fast breakouts.

**1d. MIN_BODY_PCT (minimum candle body size for priming)**
- Current: `WB_SQ_MIN_BODY_PCT=1.5` — candle body must be 1.5% of price
- Test: 1.0, 2.0, 2.5
- **Why it matters:** Larger body = stronger conviction bar. Smaller = catches more setups.

### Category 2: Exit Optimization

**2a. TARGET_R (profit target in R-multiples)**
- Current: `WB_SQ_TARGET_R=2.0` — take partial at 2R
- Test: 1.5R, 2.5R, 3.0R
- **Why it matters:** Lower target = more frequent wins but smaller. Higher = bigger wins but more time stops. The target hit is our biggest P&L contributor — sq_target_hit accounts for the majority of profits.

**2b. TRAIL_R (pre-target trailing stop)**
- Current: `WB_SQ_TRAIL_R=1.5` — trail at 1.5R from peak before target
- Test: 1.0, 2.0
- **Why it matters:** Tighter trail = exits earlier (preserves gains, but misses bigger moves). Looser = lets winners run but gives back more on reversals.

**2c. RUNNER_TRAIL_R (post-target runner trailing stop)**
- Current: `WB_SQ_RUNNER_TRAIL_R=2.5`
- Test: 2.0, 3.0, 3.5
- **Why it matters:** After the 2R target partial, the runner rides with this trail. Tighter = locks in more runner profit. Looser = catches the full cascade on stocks like VERO.

**2d. CORE_PCT (how much to sell at target)**
- Current: `WB_SQ_CORE_PCT=75` — sell 75% at 2R, keep 25% runner
- Test: 50/50, 60/40, 90/10
- **Why it matters:** More core = locks in more profit at target. More runner = bigger upside on cascading stocks but more giveback on reversals.

**2e. BAIL_TIMER_MINUTES (exit unprofitable trades after N min)**
- Current: `WB_BAIL_TIMER_MINUTES=5`
- Test: 3, 7, 10, OFF
- **Why it matters:** Shorter = cuts losers faster. Longer = gives more room for the setup to work. OFF = rely purely on stops.

### Category 3: Scanner / Discovery

**3a. MAX_GAP_PCT (upper gap limit)**
- Current: `WB_MAX_GAP_PCT=500`
- Test: 200, 300, 100
- **Why it matters:** Stocks with 300%+ gaps might be too extended. But some of our best winners had huge gaps.

**3b. MAX_PRICE**
- Current: `WB_MAX_PRICE=20.00`
- Test: 15.00, 25.00, 30.00
- **Why it matters:** Higher-priced stocks have bigger R values but need more capital. Lower cap focuses on the small-cap squeeze sweet spot.

**3c. MAX_FLOAT**
- Current: `WB_MAX_FLOAT=15` (million)
- Test: 10, 20, 25
- **Why it matters:** Lower float = more squeeze potential but less liquidity. Higher = more liquid but weaker squeezes.

**3d. Scanner cutoff time**
- Current: 9:30 AM ET hard cutoff (no new symbols after)
- Test: 10:00 AM, 8:30 AM
- **Why it matters:** Later cutoff catches late-morning runners. Earlier cutoff focuses on the golden hour.

### Category 4: Risk Management

**4a. RISK_PCT (% of equity per trade)**
- Current: `WB_RISK_PCT=0.025` (2.5%)
- Test: 2.0%, 3.0%, 3.5%
- **Why it matters:** Higher risk = bigger positions = more P&L on winners AND losers. The scaling notional already handles position growth, but risk % determines how aggressively we size within that.

**4b. MAX_DAILY_LOSS**
- Current: `WB_MAX_DAILY_LOSS=3000`
- Test: 2000, 5000, scale with equity (2% of equity)
- **Why it matters:** Fixed $3K cap made sense at $30K equity (10%). At $300K equity it's only 1% — very conservative. Scaling it could let us stay in the game on big days.

**4c. MAX_CONSECUTIVE_LOSSES**
- Current: 3
- Test: 2, 4, 5
- **Why it matters:** Tighter = stops trading sooner after a bad streak. Looser = more chances to catch the next setup.

**4d. MAX_ATTEMPTS (entries per stock per session)**
- Current: `WB_SQ_MAX_ATTEMPTS=3`
- Test: 2, 4, 5
- **Why it matters:** Cascading stocks (VERO, AHMA) need multiple entries. But on failed stocks, more attempts = more losses.

### Category 5: Structural Changes

**5a. Parabolic mode tuning**
- Current: Enabled with tight stop offset ($0.10)
- Test: Wider stop (0.15, 0.20), or disable entirely
- **Why it matters:** BBGI today armed in parabolic mode with $0.03 R — too tight. Wider parabolic stops might catch these while still protecting against flush-outs.

**5b. HOD gate (rolling vs fixed)**
- Current: `WB_SQ_NEW_HOD_REQUIRED=1` (must break HOD to arm)
- Test: OFF, or use PM_HOD_GATE (only requires breaking PM high, not session HOD)
- **Why it matters:** The HOD gate prevents re-arming after a stock pulls back from HOD. Loosening it could allow ABCD-style re-entries after pullbacks.

**5c. VWAP distance scoring**
- Current: Bonus points for being far above VWAP
- Test: Cap the VWAP bonus, or penalize extreme distance (>20%)
- **Why it matters:** Stocks 20%+ above VWAP are often extended and due for a pullback.

---

## Suggested Testing Priority

**High impact, easy to test (just change env vars):**
1. VOL_MULT (2.5 vs 3.0 vs 3.5)
2. TARGET_R (1.5 vs 2.0 vs 2.5)
3. RISK_PCT (2.5% vs 3.0%)
4. MAX_DAILY_LOSS (fixed vs scaling with equity)
5. CORE_PCT (75/25 vs 50/50 vs 60/40)

**Medium impact, worth exploring:**
6. TRAIL_R / RUNNER_TRAIL_R combinations
7. BAIL_TIMER (3 vs 5 vs 7 min)
8. MAX_ATTEMPTS (3 vs 4 vs 5)
9. Parabolic stop offset (0.10 vs 0.15 vs 0.20)

**Lower priority / bigger changes:**
10. HOD gate variations
11. Scanner cutoff time
12. Float/price range adjustments

---

## How to Test

Each variation is a single `run_backtest_v2.py` run with env var overrides:

```bash
WB_SQ_VOL_MULT=2.5 python run_backtest_v2.py --start 2026-01-02 --end 2026-04-02 --equity 30000 --scale-notional --label "VOL_MULT_2.5" --status-file vol_mult_25.md
```

We can run multiple in parallel since they're independent. Each takes ~5 minutes with cached ticks. Compare against the baseline ($327,511 / 39 trades / 60% WR).

---

*Report by CC (Claude Code). For Cowork + Manny to prioritize which variations to test.*
