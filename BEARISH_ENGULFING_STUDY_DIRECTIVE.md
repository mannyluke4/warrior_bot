# Bearish Engulfing First-Exit Study — Directive for Claude Code
## Priority: HIGH | Profile: A only | Date: March 5, 2026

---

## Motivation

JZXN on 2026-03-04 exposed a systematic issue: the bot's bearish engulfing (BE) exit fires too aggressively in the first minutes of a micro-float runner, cutting winners short.

**JZXN recap:**
- Scanner 07:16 ET, float 1.32M, gap 57-91% — textbook Profile A
- Bot entered $1.36 at 07:17, exited $1.45 at 07:19 via bearish engulfing → **+$333 (+0.3R)**
- Stock continued running significantly after exit
- High-score re-entry (12.5, ABCD+Volume Surge) at 07:54 was blocked by VWAP loss
- Ross Cameron reportedly made $50k+ on this stock

The core question: **is the first bearish engulfing exit systematically premature on Profile A stocks?**

---

## Study Design

### Phase 1: Collect Per-Trade Data (verbose backtests)

Run `--verbose` backtests on **all 27 Profile A stocks that had trades** in the 137-stock study. We need per-trade granularity — the CSV only has session totals.

**Profile A stock list** (27 sessions across 19 unique tickers):

| # | Symbol | Date | Float (M) | Gap% | Session P&L | Trades |
|---|--------|------|-----------|------|-------------|--------|
| 1 | ROLR | 2026-01-06 | 3.6 | -6.2 | -$1,422 | 2 |
| 2 | ACON | 2026-01-08 | 0.7 | 6.9 | -$2,122 | 3 |
| 3 | APVO | 2026-01-09 | 0.9 | -3.4 | +$7,622 | 1 |
| 4 | BDSX | 2026-01-12 | 3.7 | 2.7 | -$45 | 6 |
| 5 | PMAX | 2026-01-13 | 1.2 | -7.4 | -$1,098 | 1 |
| 6 | ROLR | 2026-01-14 | 3.6 | -6.2 | +$1,644 | 5 |
| 7 | BNAI | 2026-01-16 | 3.3 | -1.8 | -$674 | 2 |
| 8 | GWAV | 2026-01-16 | 0.8 | -1.4 | +$6,735 | 2 |
| 9 | LCFY | 2026-01-16 | 1.4 | -0.6 | -$627 | 2 |
| 10 | ROLR | 2026-01-16 | 3.6 | -6.2 | -$1,228 | 3 |
| 11 | SHPH | 2026-01-16 | 1.6 | -4.0 | -$1,111 | 1 |
| 12 | TNMG | 2026-01-16 | 1.2 | -0.7 | -$481 | 1 |
| 13 | VERO | 2026-01-16 | 1.6 | -9.1 | +$6,890 | 4 |
| 14 | PAVM | 2026-01-21 | 0.7 | -0.2 | +$1,586 | 3 |
| 15 | MOVE | 2026-01-23 | 0.6 | 13.6 | -$156 | 1 |
| 16 | SLE | 2026-01-23 | 0.7 | 1.5 | -$390 | 1 |
| 17 | BCTX | 2026-01-27 | 1.7 | 6.7 | $0 | 1 |
| 18 | HIND | 2026-01-27 | 1.5 | -0.6 | +$260 | 2 |
| 19 | MOVE | 2026-01-27 | 0.6 | 13.6 | +$5,502 | 3 |
| 20 | SXTP | 2026-01-27 | 0.9 | -4.8 | -$2,078 | 2 |
| 21 | BNAI | 2026-01-28 | 3.3 | -1.8 | +$5,610 | 4 |
| 22 | BNAI | 2026-02-05 | 3.3 | 0.1 | +$160 | 2 |
| 23 | MNTS | 2026-02-06 | 1.3 | -7.3 | +$862 | 1 |
| 24 | ACON | 2026-02-13 | 0.7 | 6.9 | -$214 | 1 |
| 25 | MLEC | 2026-02-13 | 0.7 | -21.7 | +$173 | 4 |
| 26 | SNSE | 2026-02-18 | 0.7 | -2.3 | -$125 | 2 |
| 27 | ENVB | 2026-02-19 | 0.5 | -6.8 | +$474 | 1 |

**Baseline totals**: 12 winners, 14 losers, 46% WR, +$25,747 total P&L.

**For each stock, run:**
```bash
python simulate.py --symbol SYMBOL --date YYYY-MM-DD --profile A --ticks --verbose
```

**Capture for EACH trade in the session:**
1. Trade number (1, 2, 3...)
2. Entry price and time
3. Exit price, time, and **exit reason** (bearish_engulfing, stop_loss, tp_hit, classifier_suppress, etc.)
4. P&L (dollars and R-multiple)
5. Time held (minutes from entry to exit)

Save all results to: `studies/bearish_engulfing/phase1_verbose_trades.md`

### Phase 2: Analyze Trade 1 Exits

From the Phase 1 data, answer these questions:

**Q1: How many Trade 1 exits were bearish engulfing?**
Count how many of the 27 sessions had their first trade exit via bearish engulfing vs. other reasons (stop loss, tp_hit, etc.).

**Q2: What was Trade 1 P&L across all 27 sessions?**
Separate analysis:
- Trade 1 P&L on stocks where Trade 1 exited via BE
- Trade 1 P&L on stocks where Trade 1 exited via other reason
- Are BE Trade 1 exits systematically worse than other Trade 1 exits?

**Q3: How fast did Trade 1 BE exits happen?**
For all Trade 1 BE exits: how many minutes from entry to exit?
- < 2 minutes?
- 2-5 minutes?
- 5-10 minutes?
- > 10 minutes?

This tells us if the "too early" problem is concentrated in the first few minutes (like JZXN's 2-minute exit) or spread out.

**Q4: On stocks where Trade 1 exited via BE in < 5 minutes, what happened next?**
For each such stock:
- Did the stock continue higher after the BE exit? (Check if price exceeded exit price within the next 10, 20, 30 minutes)
- Did the bot re-enter? If so, was the total session P&L positive?
- Would holding through the first BE have been better or worse?

Save analysis to: `studies/bearish_engulfing/phase2_analysis.md`

### Phase 3: Simulate BE Suppression (What-If)

**This is the key experiment.** For each stock where Trade 1 exited via bearish engulfing within 5 minutes of entry, simulate what would have happened if the BE exit was suppressed for a configurable window:

**Test three suppression windows:**
- `WB_BE_SUPPRESS_MINUTES=3` — suppress BE exits for 3 minutes after entry
- `WB_BE_SUPPRESS_MINUTES=5` — suppress for 5 minutes
- `WB_BE_SUPPRESS_MINUTES=10` — suppress for 10 minutes

For each window, the sim should:
1. Ignore bearish engulfing exit signals that fire within N minutes of entry
2. Still honor stop losses (safety must remain)
3. Still honor all other exit signals (tp_hit, classifier suppress, etc.)
4. After the suppression window expires, bearish engulfing exits fire normally

**Calculate for each window:**
- Trade 1 P&L (did holding longer help or hurt?)
- Full session P&L (did the later trades still fire? were they affected?)
- Net impact across all 27 sessions: `(new total P&L) - $25,747`

**CRITICAL: Also run all 6 regression benchmarks with each setting.**
The suppression MUST NOT break the regression stocks:
- VERO 2026-01-16: baseline +$6,890
- GWAV 2026-01-16: baseline +$6,735
- APVO 2026-01-09: baseline +$7,622
- BNAI 2026-01-28: baseline +$5,610
- MOVE 2026-01-27: baseline +$5,502
- ANPA 2026-01-09: baseline +$2,088

Save results to: `studies/bearish_engulfing/phase3_whatif.md`

---

## Implementation Proposal (pending Phase 3 results)

If the data supports BE suppression, implement as:

```python
# New env var
WB_BE_SUPPRESS_MINUTES = int(os.getenv("WB_BE_SUPPRESS_MINUTES", "0"))  # 0 = disabled (current behavior)

# In the bearish engulfing exit logic:
if exit_reason == "bearish_engulfing":
    minutes_since_entry = (current_time - entry_time).total_seconds() / 60
    if minutes_since_entry < WB_BE_SUPPRESS_MINUTES:
        log(f"BE exit suppressed — only {minutes_since_entry:.1f}m since entry (suppress window: {WB_BE_SUPPRESS_MINUTES}m)")
        continue  # skip this exit signal
```

**Scope rules:**
- Profile A only (this is a micro-float phenomenon)
- Only suppresses bearish engulfing — stop losses ALWAYS fire
- Only applies to signal mode (the bot's core edge in cascading exits)
- Env-gated and OFF by default (`WB_BE_SUPPRESS_MINUTES=0`)

---

## What This Study Does NOT Cover

1. **VWAP gate override for high-score re-entries** (JZXN Q2) — separate study, lower priority. Fix the first exit before worrying about re-entry.
2. **Classifier lag** (JZXN Q3) — low priority, unlikely to move the needle.
3. **Trailing stop interaction** — trailing stop activates at 3R+. If Trade 1 exits at 0.3R via BE, the trailing stop never engaged. These are independent systems.

---

## Expected Output

When complete, deliver:
1. `studies/bearish_engulfing/phase1_verbose_trades.md` — raw per-trade data for all 27 sessions
2. `studies/bearish_engulfing/phase2_analysis.md` — Trade 1 exit analysis with answers to Q1-Q4
3. `studies/bearish_engulfing/phase3_whatif.md` — BE suppression simulation results with regression checks
4. A **recommendation** (with data backing) on whether to enable BE suppression, and if so, what value for `WB_BE_SUPPRESS_MINUTES`

---

## Decision Framework

| Outcome | Action |
|---------|--------|
| BE suppression improves P&L AND passes all regressions | Ship it — add `WB_BE_SUPPRESS_MINUTES` env var, default OFF, enable on Profile A |
| BE suppression improves P&L but breaks regressions | Needs tuning — try Profile A-only or time-of-day filter |
| BE suppression has no significant impact | Close study — the early BE exit is noise, not a systematic problem |
| BE suppression makes things worse | Close study — current behavior is correct, JZXN was an outlier |

---

*Directive by Perplexity Computer — March 5, 2026*
*Motivated by: JZXN Trade Study (Duffy, 2026-03-05)*
*Data source: 137-stock L2 study CSV, 27 Profile A sessions with trades*
