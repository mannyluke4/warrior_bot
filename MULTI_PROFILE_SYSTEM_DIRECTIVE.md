# Multi-Profile Trading System — Architecture & Implementation Directive

**Date**: March 3, 2026
**Author**: Perplexity Computer
**For**: Claude Code execution + Duffy training + Manual reference
**Priority**: HIGH — this is the next major architectural change

---

## Executive Summary

The bot's performance is NOT uniform across stock types. A 137-stock study proved this conclusively:

- **Micro-float pre-market stocks**: 44% win rate, +$24,737 P&L — the bot's core edge
- **Everything else**: 24% win rate, -$24,933 P&L — net destruction

The problem: every time we tune the bot to improve one stock type (e.g., L2 for large-float), it hurts another (micro-float runners). This tug-of-war has been the defining pattern across ALL testing phases.

**The solution**: A profile-based system where each stock on the watchlist is tagged with a profile code. Each profile has its own configuration — entry rules, exit behavior, L2 usage, position sizing, and stop management. The bot reads the tag and loads the right config. No more one-size-fits-all.

---

## Architecture: Profile Tagging

### How It Works

1. **You (or Duffy) add a stock to the watchlist with a profile tag**
   - Format: `SYMBOL:PROFILE_CODE` (e.g., `APVO:A`, `ANPA:B`, `CRSR:C`)
   - If no tag is provided, the bot defaults to Profile A (the proven winner)

2. **The bot reads the tag at watchlist-add time**
   - Parses the profile code from the symbol string
   - Loads the corresponding profile configuration
   - All subsequent trading decisions for that symbol use the profile config

3. **Each profile is a complete configuration override**
   - Stored as a JSON/YAML file or env-var block per profile
   - Overrides relevant subset of the bot's .env settings
   - Does NOT replace global settings (buying power, max position, etc.)

### Implementation in Code

```python
# In watchlist handler (wherever symbols are added):
def parse_profile(symbol_str):
    """Parse 'APVO:A' into ('APVO', 'A'). Default to 'A' if no tag."""
    if ':' in symbol_str:
        symbol, profile = symbol_str.split(':', 1)
        return symbol.strip(), profile.strip().upper()
    return symbol_str.strip(), 'A'  # Default: Profile A

# Profile configs loaded from profiles/ directory or PROFILE_CONFIGS dict
PROFILE_CONFIGS = {
    'A': { ... },  # Micro-float runner
    'B': { ... },  # Mid-float L2-assisted
    'C': { ... },  # Future: large-cap momentum
}
```

### Affected Systems

The profile tag must propagate to:
- **Entry logic**: Score thresholds, entry timing, fast mode toggle
- **Exit logic**: BE suppression, TW suppression, trail ATR mult, cascading exit behavior
- **L2 subsystem**: Enable/disable L2, L2 config overrides
- **Position sizing**: Risk per trade, max consecutive losses
- **Classifier**: Profile-specific AVOID gate thresholds
- **Simulate.py**: `--profile` flag for backtesting specific profiles

---

## Profile A: "Micro-Float Pre-Market Runner" (LOCKED)

**Tag**: `:A` or no tag (default)
**Status**: PROVEN — ready for live deployment

### Identification Criteria

| Attribute | Value | Confidence |
|-----------|-------|-----------|
| Float | < 5M shares | HIGH — 137-stock data |
| Scanner time | Pre-market / 7:00 AM ET | HIGH — 137-stock data |
| Gap % | Any (neg gap winners are common) | MEDIUM |
| Price | $1-$20 typical | LOW — weak predictor |
| Volume | Not a filter (micro-float = volatile) | N/A |

**What to look for on the scanner:**
- Stock appears in pre-market or at 7:00 AM ET scan
- Float under 5 million shares
- Typically a news catalyst (biotech, earnings, FDA, merger)
- May have negative gap % — that's fine, the bot handles gap-down runners well
- These are the "textbook gap-and-go" plays from Warrior Trading

### Performance Data (137-stock study)

- **28 stocks tested**, 12W / 15L
- **44% win rate** (vs 32% overall)
- **+$24,737 total P&L** (vs -$196 overall)
- **Average winner: +$3,118** | **Average loser: -$968**
- **Best: APVO +$7,622** | **Worst: ACON -$2,122**

### Configuration

```env
# Profile A — Micro-Float Pre-Market Runner
WB_PROFILE_A_L2_ENABLED=0              # L2 OFF — hurts micro-float by -$12,569
WB_PROFILE_A_EXIT_MODE=signal          # Signal mode cascading — DO NOT CHANGE
WB_PROFILE_A_CLASSIFIER_ENABLED=1      # AVOID gate ON
WB_PROFILE_A_SUPPRESS_ENABLED=0        # No BE suppression
WB_PROFILE_A_FAST_MODE=0               # Standard entry timing
WB_PROFILE_A_MAX_REENTRIES=5           # Allow cascading re-entries
WB_PROFILE_A_TRAIL_ATR_MULT=default    # Default trailing stop
```

**Key principle**: DO NOT add L2 to Profile A stocks. The 137-stock study showed L2 costs -$12,569 on micro-float. The `l2_bearish_exit` fires prematurely on thin order books, killing runners.

### Regression Benchmarks

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| VERO | 2026-01-16 | +$6,890 | Cascading runner, 4 trades |
| GWAV | 2026-01-16 | +$6,735 | Early bird, 2 trades |
| APVO | 2026-01-09 | +$7,622 | Single massive winner |
| BNAI | 2026-01-28 | +$5,610 | 4-trade cascading |
| MOVE | 2026-01-27 | +$5,502 | 3-trade runner |

---

## Profile B: "Mid-Float L2-Assisted" (CANDIDATE — needs validation)

**Tag**: `:B`
**Status**: EVIDENCE-BASED CANDIDATE — needs dedicated backtest

### Hypothesis

Stocks with float 5-50M lose money without L2 (-$14,893) but L2 cuts losses by $1,894. With float > 50M, L2 saves $3,100. The L2 `bearish_exit` mechanism works correctly on stocks with deeper order books (more float = more liquidity = more reliable book signals).

Additionally, ANPA showed +$3,003 L2 delta (from +$2,088 to +$5,091), demonstrating L2 can turn good trades into great ones on mid-float stocks.

### Identification Criteria (PROVISIONAL)

| Attribute | Value | Confidence |
|-----------|-------|-----------|
| Float | 5M - 50M shares | MEDIUM — L2 delta positive |
| Scanner time | 7:00 AM ET (pre-market) | MEDIUM — post-7am still loses |
| L2 | ENABLED | HIGH — clear positive delta |
| Gap % | < 15% (high gap = worse) | LOW — small sample |

**What to look for:**
- Stock on scanner at 7:00 AM with float between 5M and 50M
- Has news catalyst but isn't a parabolic gap-up
- These are "former momo" or "squeeze alert" type scanner hits
- The bot struggles here without L2 — the order book data helps it avoid bad entries and tighten exits

### Performance Data (137-stock study, float 5-50M)

- **27 stocks**, 8W / 19L (30% WR without L2)
- **No-L2: -$14,893** | **L2 v3: -$12,999** | **L2 delta: +$1,894**
- Still net negative — this profile needs MORE than just L2 to work
- Key winners: ANPA +$2,088 (L2 -> +$5,091), BATL +$1,972, VOR +$501

### Configuration (PROVISIONAL)

```env
# Profile B — Mid-Float L2-Assisted
WB_PROFILE_B_L2_ENABLED=1
WB_PROFILE_B_L2_HARD_GATE_WARMUP_BARS=30
WB_PROFILE_B_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65
WB_PROFILE_B_EXIT_MODE=signal
WB_PROFILE_B_CLASSIFIER_ENABLED=1
WB_PROFILE_B_SUPPRESS_ENABLED=0
WB_PROFILE_B_MAX_REENTRIES=3           # Fewer re-entries (less confident)
```

### What's Needed to Validate

1. Dedicated backtest: run the 27 mid-float stocks with L2 ON + tighter exit config
2. Test whether classifier thresholds need adjustment for this float range
3. Test whether fewer re-entries (3 vs 5) reduces the loser damage
4. Determine if additional filters (VWAP distance, gap %) can improve the 30% WR

---

## Profile C: "Fast Mover" (EARLY CANDIDATE — from Round 5/6 data)

**Tag**: `:C`
**Status**: EARLY — based on Fast Mode testing, not yet in 137-stock study

### Background

Stocks like HIND, GRI, and ELAB were identified in Rounds 5-6 as needing a fundamentally different entry approach. The bot's standard entry waits too long on these — they move too fast. "Fast Mode" (anticipation entry) was built for this, and HIND improved from -$3 to +$663 with Fast Mode + Databento tick data.

### Identification Criteria (PROVISIONAL)

| Attribute | Value | Confidence |
|-----------|-------|-----------|
| Float | < 5M (overlaps Profile A float range) | MEDIUM |
| Behavior | Fast, clean impulses — not choppy | HIGH |
| Entry | Needs Fast Mode anticipation entry | HIGH |
| Scanner time | 7:00 AM ET | MEDIUM |

**What to look for:**
- Micro-float stock that runs in clean, fast impulses
- Gaps don't create the setup — the stock just moves fast on any catalyst
- Standard entry timing misses because the impulse completes before the bot can react
- "If you blink, you miss it" — that's a Profile C stock

### Configuration (PROVISIONAL)

```env
# Profile C — Fast Mover
WB_PROFILE_C_FAST_MODE=1
WB_PROFILE_C_FAST_MODE_MIN_BARS=10     # From Round 6.5 tuning
WB_PROFILE_C_L2_ENABLED=0              # Micro-float, same L2 risk as Profile A
WB_PROFILE_C_EXIT_MODE=signal
WB_PROFILE_C_MAX_REENTRIES=3
```

### What's Needed to Validate

1. Re-run HIND, GRI, ELAB (and similar stocks) with Fast Mode ON vs OFF
2. Identify more Profile C candidates from the study data
3. Determine if there's a reliable way to distinguish C from A at scanner time (before the fast move happens)

---

## Profile X: "Unknown / Experimental" (CATCH-ALL)

**Tag**: `:X`
**Status**: Reserved for new stocks being studied

When you encounter a stock that doesn't clearly fit A, B, or C, tag it `:X`. The bot trades it with conservative defaults (Profile A settings + reduced position size). This generates data for future profile identification without risking full capital.

```env
# Profile X — Unknown / Conservative
WB_PROFILE_X_POSITION_SIZE_MULT=0.5    # Half size
WB_PROFILE_X_MAX_REENTRIES=2           # Conservative re-entries
WB_PROFILE_X_L2_ENABLED=0              # L2 off until proven
```

---

## Implementation Plan for Claude Code

### Phase 1: Profile Infrastructure (DO FIRST)

1. **Create `profiles/` directory** in repo root
2. **Create profile config files**: `profiles/A.json`, `profiles/B.json`, `profiles/C.json`, `profiles/X.json`
3. **Add profile parsing to watchlist handler**:
   - Parse `SYMBOL:PROFILE_CODE` format
   - Default to `A` if no code provided
   - Store profile code alongside symbol in watchlist state
4. **Add profile config loader**:
   - Read profile JSON at symbol-add time
   - Override relevant bot settings for that symbol's lifecycle
   - Log which profile is active for each symbol
5. **Add `--profile` flag to simulate.py**:
   - `python simulate.py APVO --profile A` loads Profile A config for backtest
   - Enables per-profile regression testing

### Phase 2: Profile A Lock-in

1. Extract current working config into `profiles/A.json`
2. Ensure Profile A regression benchmarks all pass (VERO, GWAV, APVO, BNAI, MOVE)
3. Add `WB_L2_ENABLED=0` explicitly to Profile A (it should already be off, but make it explicit)
4. NO changes to trading logic — just formalize what already works

### Phase 3: Profile B Validation (AFTER Phase 2)

1. Create `profiles/B.json` with L2 enabled + mid-float config
2. Run the 27 mid-float stocks from the 137-stock study with Profile B
3. Compare Profile B results to no-L2 baseline AND global L2 results
4. Iterate on B config until it's at least breakeven on this cohort
5. Add Profile B regression benchmarks once validated

### Phase 4: Profile C Validation (AFTER Phase 3)

1. Create `profiles/C.json` with Fast Mode config
2. Re-run HIND, GRI, ELAB + identify new candidates
3. Validate Fast Mode + Databento tick data improves outcomes
4. The key challenge: can we identify Profile C stocks BEFORE they start moving?

---

## Regression Testing

Each profile must maintain independent regression benchmarks:

```bash
# Profile A regression
python simulate.py VERO 2026-01-16 --profile A  # Expected: +$6,890
python simulate.py GWAV 2026-01-16 --profile A  # Expected: +$6,735
python simulate.py APVO 2026-01-09 --profile A  # Expected: +$7,622

# Profile B regression (TBD after validation)
python simulate.py ANPA 2026-01-09 --profile B  # Expected: +$5,091 (with L2)

# Cross-profile safety: Profile B must NOT change Profile A results
python simulate.py VERO 2026-01-16 --profile A  # Still +$6,890 after B changes
```

---

## Duffy Training Notes

When Duffy manages the watchlist, he needs to:

1. **Identify the stock's profile** based on scanner attributes (float, time, gap, catalyst)
2. **Tag the symbol** with the correct profile code
3. **Default to `:A`** when uncertain — it's the proven winner
4. **Flag `:X`** for anything genuinely novel — conservative sizing protects capital

Duffy's decision tree:
```
Stock appears on scanner
  -> Float < 5M AND scanner time = 7:00 AM ET?
    -> YES -> Tag :A (Micro-Float Pre-Market Runner)
    -> NO -> Float 5-50M AND scanner time = 7:00 AM ET?
      -> YES -> Tag :B (Mid-Float L2-Assisted) [once validated]
      -> NO -> Scanner time after 8:00 AM?
        -> YES -> SKIP (24% WR, -$20,648 P&L on post-7am stocks)
        -> NO -> Tag :X (Unknown -- half size)
```

---

## Manual Watchlist Quick Reference

**For when you're adding stocks yourself before Duffy is live:**

### Instant Adds (Profile A) -- Tag `:A` or just add the symbol

- Float under 5 million
- On scanner at or before 7:00 AM ET
- Any gap % is fine (negative gap winners are common)
- News catalyst present (biotech, FDA, earnings, merger, etc.)
- **These are your money makers -- 44% win rate, avg +$3,118 per winner**

### Cautious Adds (Profile B) -- Tag `:B` [once validated]

- Float 5M to 50M
- On scanner at 7:00 AM ET
- Gap under 15%
- L2 will activate automatically for these
- **Currently breakeven at best -- only add if you have excess buying power**

### Skip These

- Float > 50M (14% win rate, bot can't read them)
- Scanner appearance after 8:00 AM (24% WR, -$917 avg)
- "Squeeze Alert - Up 10% in 10min" scanner type (0% WR)
- Stocks appearing for 2nd+ consecutive day with no new catalyst

### When In Doubt

- Tag `:X` -- bot trades at half size with conservative settings
- Or just don't add it -- protecting capital beats chasing setups

---

*Document generated by Perplexity Computer -- March 3, 2026*
*Data sources: 137-stock L2 study, 108-stock behavior study, 30-stock scanner study, Round 5/6 Fast Mode results*