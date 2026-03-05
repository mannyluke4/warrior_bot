# Backtest Directive — JZXN 2026-03-04
**From:** Duffy  
**To:** Claude Code  
**Date:** 2026-03-04  
**Priority:** High — live session validation

---

## Task

Run a backtest on **JZXN** for today (2026-03-04) using Profile A configuration.

## Context

Today Ross Cameron reportedly made $50k+ on a single trade. Duffy pulled the full day's scanner data live from the Warrior Trading scanner via CDP connection and classified all morning stocks through the profile decision tree.

**JZXN is the only Profile A qualified stock from today's session:**
- Float: 1.32M shares (micro-float, well under 5M threshold)
- First scanner appearance: **7:16 AM ET**
- Gap at scanner time: 57-91% (extreme gap — flag in results)
- Strategy tags: "Former Momo Stock" + "Low Float - High Rel Vol"
- Still running at +85% at 9:54 AM ET

This is the exact Profile A setup the bot is designed to trade. We want to know: what would the bot have done with JZXN today, and what would the P&L have been?

## Files to Reference

- `profiles/A.json` — Profile A config
- `simulate.py` — backtesting engine
- `study_data/` — check if JZXN data exists; if not, may need to fetch from Alpaca/Databento for today's date

## What to Run

```bash
python simulate.py --ticker JZXN --date 2026-03-04 --profile A
```

Or whatever the correct simulate.py invocation is for a single ticker + date + profile.

## Success Criteria

- [ ] Simulation runs without errors
- [ ] Entry/exit times logged clearly
- [ ] P&L reported for the trade
- [ ] Regression baselines preserved — confirm VERO, GWAV, ANPA numbers unchanged after any code changes
- [ ] Note whether Alpaca or Databento ticks were used (Profile A should use Alpaca per prior decision)

## Expected Outcome

Given JZXN's profile (micro-float, 7am scanner, extreme gap, huge relative volume), we expect this to be a significant winner. If the bot missed it or had a bad entry, flag why.

## Report Back

Post results as a comment in this file or create `JZXN_BACKTEST_RESULTS.md` with:
- Entry price and time
- Exit price and time  
- P&L
- Number of shares
- Any issues encountered (missing data, etc.)

---

*Directive from Duffy — scanner data source: live CDP session 2026-03-04*
