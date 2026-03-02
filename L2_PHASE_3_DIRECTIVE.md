# L2 PHASE 3 DIRECTIVE — Conditional Stop Tighten + Full 93-Stock Study
**Date**: March 2, 2026  
**From**: Research Team (Perplexity)  
**To**: Claude Code  
**Priority**: HIGH — One small refinement, then scale to the full stock set  

---

## CONTEXT

Phase 2.5 moved L2 from -$43 to +$85 vs baseline on 10 stocks. The warmup fix and stop-tighten disable both worked directionally. One refinement remains before we scale up:

**Bid-stack stop tightening should be conditional on imbalance confirmation, not fully disabled.**

Evidence from v2:
- CRSR T2: Stop tightened with neutral imbalance → false floor → -$842 (correctly blocked by disabling)
- BDSX T3: Stop tightened with 0.80-0.93 imbalance → genuine support → +$315 (lost $125 by disabling)
- Pattern: When imbalance is strongly bullish AND bid stacking is detected, the floor is real. When imbalance is neutral/bearish and stacking is detected, the floor is fake.

---

## STEP 1: Conditional Stop Tightening

Replace `WB_L2_STOP_TIGHTEN_ENABLED` (binary on/off) with `WB_L2_STOP_TIGHTEN_MIN_IMBALANCE`:

**New env variable:**
```bash
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65   # Only allow L2 bid-stack stop tightening when imbalance >= this value (0=always tighten, 1.0=never tighten, 0.65=only when book is bullish)
```

**Implementation** (in both `_direct_entry_check()` and `_pullback_entry_check()`):

```python
# BEFORE (v2 — binary toggle):
l2_stop_tighten = int(os.getenv("WB_L2_STOP_TIGHTEN_ENABLED", "0"))
if l2_stop_tighten and l2_state is not None and l2_state.get("bid_stack_levels"):
    ...

# AFTER (v3 — conditional on imbalance):
l2_stop_tighten_min_imb = float(os.getenv("WB_L2_STOP_TIGHTEN_MIN_IMBALANCE", "0.65"))
if l2_state is not None and l2_state.get("bid_stack_levels"):
    current_imbalance = l2_state.get("imbalance", 0.0)
    stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
    if stack_prices:
        highest_stack = max(stack_prices)
        if current_imbalance >= l2_stop_tighten_min_imb:
            # Imbalance confirms bullish — allow stop tightening
            if highest_stack > raw_stop and highest_stack < entry:
                logger.info(f"L2 bid_stack tighten ACTIVE: stack={highest_stack:.4f} imbalance={current_imbalance:.2f} >= {l2_stop_tighten_min_imb} (stop {raw_stop:.4f} → {highest_stack:.4f})")
                raw_stop = highest_stack
        else:
            # Imbalance does NOT confirm — log but do not adjust
            logger.info(f"L2 bid_stack tighten BLOCKED: stack={highest_stack:.4f} imbalance={current_imbalance:.2f} < {l2_stop_tighten_min_imb} (stop stays {raw_stop:.4f})")
```

You can **remove** `WB_L2_STOP_TIGHTEN_ENABLED` — it's superseded by the min imbalance threshold. Update `.env.example` accordingly:

```bash
# WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65  # L2 bid-stack stop adjustment requires imbalance >= this (0.65=bullish confirmed only)
```

Also apply the same logic in `l2_entry.py._find_stop()` if it has a similar bid-stack stop pattern.

---

## STEP 2: Quick Validation (10-Stock Re-run)

Re-run the 10 pilot stocks with the updated config:
```bash
WB_L2_HARD_GATE_WARMUP_BARS=30
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65
```

**Expected results vs v2:**
- BDSX: Should recover ~$125 (T3 imbalance was 0.80-0.93, passes 0.65 threshold)
- CRSR: Should remain fixed (T2 imbalance was neutral, still blocked)
- Everything else: Unchanged

No need for a full report — just a quick summary table confirming the above. Append to `L2_PILOT_RESULTS_V2.md` as a "V3 Quick Check" section, or create a short note.

Also re-run the 3 regressions without L2 to confirm no breakage:
```bash
python simulate.py VERO 2026-01-16 --ticks     # Expected: +$6,890
python simulate.py GWAV 2026-01-16 --ticks     # Expected: +$6,735
python simulate.py ANPA 2026-01-09 --ticks     # Expected: +$2,088
```

---

## STEP 3: Full 93-Stock Study With L2

This is the main event. Run ALL remaining stocks from the Scanner Study data with L2 enabled.

### Stock List

Use the full scanner study stock list. The 30 stocks from Scanner Study 30 have already been run — we need the remaining stocks from `scanner_data_parsed.csv` that were NOT in the 30-stock sample.

**How to identify the full list:**
1. `scanner_data_parsed.csv` contains all 123 scanner entries
2. `scanner_study_30_stocks.csv` contains the 30 already tested
3. The remaining ~93 entries need to be run

For each stock:
- Use the scanner appearance time as `--sim-start`
- Run WITHOUT L2 first (baseline)
- Run WITH L2 (`--l2` flag, using the v3 config above)

### Execution

```bash
# For each stock in the remaining list:
python simulate.py {SYMBOL} {DATE} --ticks --sim-start {SCANNER_TIME}                    # No-L2 baseline
python simulate.py {SYMBOL} {DATE} --ticks --l2 --sim-start {SCANNER_TIME}               # With L2 v3
```

**Cost estimate**: ~$0.023/stock × 93 stocks = ~$2.14 Databento cost. Negligible.

**Monitor the first 5 stocks** — if Databento costs are higher than expected (>$0.10/stock), pause and report.

### Output Format

Create `L2_FULL_STUDY_RESULTS.md` with:

```markdown
# L2 Full Study Results (93 Stocks)

## Summary
| Metric | No-L2 | With L2 | Delta |
|--------|-------|---------|-------|
| Total P&L | ??? | ??? | ??? |
| Win Rate | ??? | ??? | ??? |
| Avg P&L/Trade | ??? | ??? | ??? |
| Total Trades | ??? | ??? | ??? |

## Per-Stock Results
| Symbol | Date | Scanner Time | No-L2 P&L | With-L2 P&L | Delta | Trades (no-L2) | Trades (L2) | Key L2 Impact |
|--------|------|-------------|-----------|-------------|-------|----------------|-------------|---------------|
(one row per stock)

## L2 Impact Analysis

### Stocks Where L2 Helped (Delta > $100)
(list with explanation of which L2 mechanism helped)

### Stocks Where L2 Hurt (Delta < -$100)  
(list with explanation of which L2 mechanism hurt)

### Stocks Where L2 Had No Impact (|Delta| < $100)
(count and summary)

### L2 Impact by Stock Characteristics
| Characteristic | L2 Avg Delta | Count | Notes |
|---------------|-------------|-------|-------|
| Low float (<10M) | ??? | ??? | |
| Medium float (10-50M) | ??? | ??? | |
| High float (>50M) | ??? | ??? | |
| Small gap (<10%) | ??? | ??? | |
| Medium gap (10-30%) | ??? | ??? | |
| Large gap (>30%) | ??? | ??? | |
| Scanner pre-8am | ??? | ??? | |
| Scanner 8-9am | ??? | ??? | |
| Scanner 9am+ | ??? | ??? | |

### L2 Mechanism Breakdown (aggregate across all stocks)
| Mechanism | Times Fired | Net P&L Impact | Avg Impact |
|-----------|------------|----------------|------------|
| l2_bearish_exit | ??? | ??? | ??? |
| NO_ARM L2_bearish (hard gate, post-warmup) | ??? | ??? | ??? |
| L2_warmup (gate would have fired but warmup active) | ??? | ??? | ??? |
| L2 bid-stack stop tighten (confirmed, imbalance ≥ 0.65) | ??? | ??? | ??? |
| L2 bid-stack stop blocked (imbalance < 0.65) | ??? | ??? | ??? |
| L2 score boost (imbalance/stack/thinning) | ??? | ??? | ??? |
| L2 score penalty (bearish/spread/ask wall) | ??? | ??? | ??? |

## The Filtration Question
Based on ALL stock data (30 pilot + 93 new), which combination of pre-trade filters
produces the best results? Consider:
1. Float range
2. Gap % range  
3. Scanner appearance time
4. Strategy type (micro_pullback vs micro_pullback_l2)
5. L2 book quality at first entry (if available)

What is the CONSISTENT winning profile? What should the filtration gate accept/reject?
```

Also export the raw data as `l2_full_study_data.csv` with one row per stock and all key metrics.

---

## IMPORTANT NOTES

- **Signal mode cascading exits must NOT be suppressed** — the bot's core edge
- **Do NOT modify `l2_signals.py` or `check_l2_exit()`** — exit signals are the best L2 feature
- **GWAV with `--l2` will still show -$907** — accepted as structural L2 limitation on extreme gap stocks at open. This does NOT mean L2 is broken; it means GWAV-type stocks (30%+ gap, session open) need the filtration gate, not L2 adjustments
- **Cache all Databento data** in `l2_cache/` — do not re-fetch what was already downloaded in Phase 2
- **If any stock fails to fetch L2 data** (Databento error, exchange mismatch), log it and continue with the no-L2 baseline for that stock
- The goal of this study is NOT just "does L2 help?" — it's "what is the consistent winning stock profile, and does L2 change that profile?"

---

*Directive authored by Research Team — March 2, 2026*  
*Reference: L2_PILOT_RESULTS_V2.md, L2_PHASE_2_5_DIRECTIVE.md, scanner_data_parsed.csv*
