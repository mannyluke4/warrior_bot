# Scanner Time Window Widening Directive

## Summary
The current profile classification system requires scanner appearance at exactly 07:00 ET. Analysis of the 137-stock study reveals that stocks appearing at 07:01-07:14 are often identical in character to 07:00 stocks — the delay is scanner lag, not a fundamentally different setup. Widening the window from `== 07:00` to `07:00-07:14` captures proven winners that are currently misclassified as Profile X.

---

## Evidence

### SPRC — 2026-01-16
- **Scanner time**: 07:02 ET (2 minutes after open)
- **Float**: 0.4M — textbook micro-float, perfect Profile A candidate
- **Databento P&L**: +$3,454
- **Current classification**: Profile X (because scanner time != 07:00)
- **Correct classification**: Profile A (micro-float <5M, scanner within first 15 min)

### STSS — 2026-01-24
- **Scanner time**: 07:01 ET (1 minute after open)
- **Float**: 20.3M — mid-float, Profile B candidate
- **Current classification**: Profile X
- **Correct classification**: Profile B (mid-float 5-50M, L2 on)

### Key Finding from Full Backtest
The 07:00-07:14 window stocks behave like their profile counterparts. The 07:30+ stocks are genuinely different and perform worse — those should remain Profile X or be skipped entirely.

---

## Proposed Change

### Current Rule
```python
if scanner_time == "07:00":
    if float_shares < 5_000_000:
        profile = "A"
    elif float_shares <= 50_000_000:
        profile = "B"
else:
    profile = "X"
```

### New Rule
```python
SCANNER_EARLY_WINDOW_MINUTES = int(os.environ.get("WB_SCANNER_WINDOW_MINUTES", "14"))
scanner_minutes_after_open = (scanner_time - market_open).total_minutes()

if 0 <= scanner_minutes_after_open <= SCANNER_EARLY_WINDOW_MINUTES:
    if float_shares < 5_000_000:
        profile = "A"
    elif float_shares <= 50_000_000:
        profile = "B"
    else:
        profile = "X"
else:
    profile = "X"
```

### Environment Variable
```
WB_SCANNER_WINDOW_MINUTES=14
```

---

## Why 14 Minutes (Not 30)

- **07:00-07:14**: Behave like their profile type. Scanner lag accounts for delay.
- **07:30+**: Genuinely different character. Mid-morning movers, different pattern.
- **07:15-07:29**: Gray zone. Keep as X, revisit with more data.

---

## Backtest Plan

1. Reclassify 137-stock study with new window
2. Run reclassified stocks through correct profiles (SPRC as A, STSS as B)
3. Compare to X results
4. Recalculate weekly summaries

## Regression Safety

Classification-only change. All existing A/B benchmarks appeared at 07:00 and are unaffected.

## Priority
**MEDIUM** — After reconcile fix (CRITICAL) and trailing stop (HIGH).

---

*Directive created by Perplexity Computer — March 3, 2026*
