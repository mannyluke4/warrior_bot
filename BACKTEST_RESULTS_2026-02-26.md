# Backtest Results: Algorithmic Feature Validation
**Date**: February 26, 2026
**Tester**: Claude Opus 4.6 (VS Code)
**Methodology**: Tick-mode simulation, 07:00-12:00 ET window, all 10 study stocks

---

## Features Implemented

Three new algorithmic features were built and integrated across the codebase:

### Feature 1: LevelMap (Resistance Tracking + Entry Gate)
- **File**: `levels.py` (new), integrated into `micro_pullback.py`, `simulate.py`, `bot.py`
- **Purpose**: Track whole/half dollar levels, PM high, VWAP as resistance/support zones. Block entries near levels with 2+ prior rejections.
- **Toggle**: `WB_LEVEL_MAP_ENABLED=0` (default OFF)
- **How it works**: Each level tracks touch_count, fail_count, break_count. Entry gate fires when price is within zone of a level with fail_count >= min_fail_count.

### Feature 2: 3-Tranche Exit Scaling
- **File**: Updated `simulate.py` (SimTrade dataclass + SimTradeManager), `trade_manager.py` (OpenTrade + PaperTradeManager)
- **Purpose**: Replace binary 65/35 core/runner split with 3-part scaling: T1 (40%) at 1R, T2 (35%) at 2R, T3 (25%) trailing.
- **Toggle**: `WB_3TRANCHE_ENABLED=0` (default OFF)
- **Key constraint**: Forces classic exit mode when enabled (incompatible with signal mode)

### Feature 3: Parabolic Regime Detector
- **File**: `parabolic.py` (new), integrated into `simulate.py`, `trade_manager.py`, `bot.py`
- **Purpose**: Multi-signal detection of parabolic momentum. Suppresses BE/TW exits during genuine ramps. Uses Chandelier trailing stop (peak - 2.5*ATR) and exhaustion detection.
- **Toggle**: `WB_PARABOLIC_REGIME_ENABLED=0` (default OFF)
- **Signals**: Consecutive new highs (3+), volume expansion (1.5x), ATR expansion (1.3x). Parabolic = 2+ signals AND in-profit.

---

## Baseline Configuration
- `WB_EXIT_MODE=signal` (full position, no fixed TP, trailing stop on signal)
- `WB_BE_TRIGGER_R=3.0`, `WB_SIGNAL_TRAIL_PCT=0.99`
- `WB_RISK_DOLLARS=1000`, `WB_MAX_NOTIONAL=60000`
- `WB_BE_PARABOLIC_GRACE=1` (legacy grace ON)
- `WB_STALE_STOCK_FILTER=1`
- All 3 new features OFF

---

## Results: Per-Stock Comparison

### Full 10-Stock Suite

| Stock | Date | Baseline | LevelMap | Parabolic | LM Delta | Para Delta |
|-------|------|----------|----------|-----------|----------|------------|
| ROLR | 2026-01-14 | -$889 | -$889 | -$889 | $0 | $0 |
| MLEC | 2026-02-13 | +$173 | +$173 | +$235 | $0 | +$62 |
| VERO | 2026-01-16 | +$6,890 | +$6,890 | -$1,717 | $0 | **-$8,607** |
| TNMG | 2026-01-16 | -$481 | -$481 | -$481 | $0 | $0 |
| GWAV | 2026-01-16 | +$6,735 | +$6,735 | +$3,949 | $0 | **-$2,786** |
| LCFY | 2026-01-16 | -$627 | -$627 | -$496 | $0 | +$131 |
| PAVM | 2026-01-21 | -$2,800 | -$2,800 | -$770 | $0 | **+$2,030** |
| ACON | 2026-01-08 | -$2,122 | -$2,122 | -$2,122 | $0 | $0 |
| FLYX | 2026-01-08 | -$1,727 | -$1,727 | -$1,727 | $0 | $0 |
| ANPA | 2026-01-09 | -$3,551 | -$3,551 | -$2,985 | $0 | +$566 |
| **TOTAL** | | **+$1,601** | **+$1,601** | **-$7,003** | **$0** | **-$8,604** |

### GWAV Deep Dive (Critical Regression Test)

GWAV is the flash spike profile (Profile D) — the bot's biggest single win. All features were tested independently:

| Config | GWAV P&L | Trade 1 Exit | Trade 1 Reason | Delta vs Baseline |
|--------|----------|-------------|----------------|-------------------|
| Baseline | +$6,735 | $6.57 | bearish_engulfing_exit_full | — |
| LevelMap only | +$6,735 | $6.57 | bearish_engulfing_exit_full | $0 |
| Parabolic only | +$3,949 | $6.18 | chandelier_stop_exit_full | -$2,786 |
| 3-Tranche only | -$922 | $5.63 / $5.41 | t1_tp / post_t1_stop | -$7,657 |
| LevelMap + Parabolic | +$3,949 | $6.18 | chandelier_stop_exit_full | -$2,786 |
| All 3 features | -$922 | $5.63 / $5.41 | t1_tp / post_t1_stop | -$7,657 |

---

## Analysis: Feature 1 (LevelMap)

### Result: Zero impact across all 10 stocks

**Why it had no effect:**
1. **New HOD entries**: Most entries in the test suite occur at new session highs where there is no prior rejection history at that level.
2. **Insufficient accumulation time**: The LevelMap needs repeated rejections at the SAME level within a session. Our test stocks don't re-test failed levels quickly enough — by the time a 3rd attempt happens, the stock is either in cooldown or the level has been broken.
3. **Primary target stocks**: LCFY (3 entries at $6.00-$6.50) and ACON (4 entries at $8.50) were the motivation. But each entry is at a slightly different price, and the zone width (0.5% = 2.5c on $5 stock) may be too narrow to cluster them as the same level.

**Recommendation**:
- Wider zone widths may help (try 1-2% instead of 0.5%)
- Consider pre-seeding levels from the first 30 min of trading before allowing entries
- May need multi-session memory (persist levels across days) to catch repeat offenders
- Feature is architecturally sound but needs parameter tuning and possibly richer seed data

---

## Analysis: Feature 3 (Parabolic Regime Detector)

### Result: Net -$8,604 regression (devastating)

**Winners (parabolic helped):**
- PAVM: -$2,800 -> -$770 (+$2,030) — Held longer through multi-leg runner
- ANPA: -$3,551 -> -$2,985 (+$566) — Suppressed premature exit
- MLEC: +$173 -> +$235 (+$62) — Minor improvement
- LCFY: -$627 -> -$496 (+$131) — Minor improvement
- **Total improvement on helped stocks: +$2,789**

**Losers (parabolic hurt):**
- VERO: +$6,890 -> -$1,717 (-$8,607) — **Catastrophic.** Our best stock destroyed.
- GWAV: +$6,735 -> +$3,949 (-$2,786) — Flash spike misidentified as parabolic.
- **Total regression on hurt stocks: -$11,393**

**Root cause — Chandelier stop conflict with signal mode:**
The Chandelier stop (peak - 2.5*ATR) is fundamentally **wider** than signal mode's trailing stop. When the detector suppresses a BE exit during what it thinks is a parabolic move:
1. The normal signal trail would have exited at a better price
2. Instead, the wider Chandelier catches it much lower
3. Net effect: worse exits on stocks where the original BE/trail was correct

**VERO deep dive:**
- Baseline: BE exits allowed the bot to exit and re-enter multiple times during VERO's volatile parabolic run, capturing +$6,890
- Parabolic: Detector suppressed BE exits, held through drawdowns, eventually exited via Chandelier at much worse prices, netting -$1,717
- The irony: VERO IS genuinely parabolic, but the bot's signal-mode cascading re-entry strategy actually works BETTER than holding through

**GWAV deep dive:**
- Baseline: BE exit at $6.57 captured the flash spike perfectly
- Parabolic: Detector saw consecutive new highs + ATR expansion, classified as parabolic, suppressed BE. Chandelier eventually fired at $6.18 — $0.39 lower per share on 7,142 shares = -$2,786

**Recommendations:**
1. Chandelier stop should NOT override signal mode's trail — only use in classic mode
2. The min hold period (12 bars = 120s) is too aggressive for flash spikes
3. Consider a "flash spike" classifier: if all new highs occur within 60s, don't treat as parabolic
4. The feature helps on PAVM-style multi-leg runners — need to find a way to distinguish these from flash spikes and cascading re-entry stocks

---

## Analysis: Feature 2 (3-Tranche Exit Scaling)

### Result: Tested on GWAV only — massive regression

**The fundamental problem:**
3-Tranche forces classic exit mode, which is incompatible with the current signal-mode strategy. In signal mode:
- Full position rides the entire move
- Trailing stop captures the peak
- BE/TW pattern exits provide risk management

In classic/3-tranche mode:
- T1 (40%) exits at just 1R ($0.14 on GWAV) — locking in tiny profit
- T2 (35%) and T3 (25%) get stopped out on pullback at breakeven
- The massive $1.08/share move that signal mode captured is split into a $0.14 T1 win and a BE loss on T2/T3

**GWAV specific:**
- Signal mode: Rode 100% of position from $5.49 to $6.57 = +$7,713
- 3-Tranche: T1 exited at $5.63 (+$400), T2/T3 stopped at $5.41 (-$343) = +$57 net on Trade 1

**Recommendation:**
- 3-Tranche should NOT be used with the current signal-mode .env configuration
- It's designed for classic exit mode where the bot already splits core/runner
- Testing should be done with `WB_EXIT_MODE=classic` as the baseline
- The feature code is correct — it's the mode conflict that causes the regression

---

## Summary Table

| Feature | Total Delta | Verdict | Ready for Production? |
|---------|-------------|---------|----------------------|
| LevelMap | $0 | No impact | Code correct, needs parameter tuning |
| Parabolic | -$8,604 | Regression | Needs architectural fix (Chandelier vs signal mode) |
| 3-Tranche | N/A (GWAV only: -$7,657) | Regression | Needs classic-mode baseline testing |

---

## Recommended Next Steps

### Immediate (before enabling any feature):
1. **Parabolic fix**: Disable Chandelier stop in signal mode — only suppress BE/TW exits, let the existing signal trail handle the actual stop. This preserves the "hold longer" benefit without the "exit worse" problem.
2. **3-Tranche**: Run full 10-stock suite with `WB_EXIT_MODE=classic` as baseline, then compare 3-tranche ON vs OFF within classic mode.
3. **LevelMap**: Try wider zone width (1-2%), or add a "warmup period" where levels accumulate touches for 30 min before the gate activates.

### Research needed (for web Claude):
1. Study VERO more closely — why does cascading re-entry outperform holding through parabolic?
2. Develop a flash spike classifier (time-to-peak metric?)
3. Investigate if LevelMap needs pre-session level data (yesterday's key levels?)
4. Consider whether 3-tranche scaling makes sense at all given signal mode's edge

---

## .env Additions (all default OFF)

```bash
# Feature 1: LevelMap
WB_LEVEL_MAP_ENABLED=0
WB_LEVEL_MIN_FAILS=2
WB_LEVEL_ZONE_WIDTH_PCT=0.5
WB_LEVEL_BREAK_CONFIRM_BARS=2

# Feature 2: 3-Tranche Exit Scaling
WB_3TRANCHE_ENABLED=0
WB_SCALE_T1=0.40
WB_SCALE_T2=0.35
WB_T1_TP_R=1.0
WB_T2_TP_R=2.0
WB_T2_STOP_LOCK_R=0.5

# Feature 3: Parabolic Regime
WB_PARABOLIC_REGIME_ENABLED=0
WB_PARABOLIC_MIN_NEW_HIGHS=3
WB_PARABOLIC_CHANDELIER_MULT=2.5
WB_PARABOLIC_MIN_HOLD_BARS=12
WB_PARABOLIC_MIN_HOLD_BARS_NORMAL=3
```

---

## Files Changed in This Session

### New files:
- `levels.py` — LevelMap + PriceLevel (resistance tracking)
- `parabolic.py` — ParabolicRegimeDetector + ParabolicState

### Modified files:
- `micro_pullback.py` — LevelMap entry gate at both ARM paths
- `simulate.py` — All 3 features: LevelMap seeding, parabolic detector, 3-tranche dataclass + exits + report
- `trade_manager.py` — All 3 features: parabolic BE/TW suppression + Chandelier + exhaustion, 3-tranche split/exits/accounting
- `bot.py` — LevelMap in ensure_detector(), volume passed to trade_manager.on_bar_close()
- `.env` — 15 new configuration knobs
- `.env.example` — Sanitized copy for GitHub (no API keys)

### New files (repo setup):
- `.gitignore` — Excludes .env, venv, logs, l2_cache, __pycache__
- `WARRIOR_BOT_RESEARCH_REPORT.md` — Copied from Downloads into repo
- `BACKTEST_RESULTS_2026-02-26.md` — This report
