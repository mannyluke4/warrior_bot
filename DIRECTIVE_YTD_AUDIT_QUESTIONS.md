# DIRECTIVE: YTD Backtest Audit — Questions for CC

**Date:** 2026-03-31  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P1 — Answer before any further strategy work  
**Context:** Independent price verification on TradingView Premium (1-min pre-market candles) confirmed IBKR tick data is accurate for ROLR (Jan 14) and NPT (Feb 3). Prices match within ~1 minute offset (bar-boundary artifact). The data is real. But several accounting discrepancies in the "honest YTD" trade log need to be explained.

---

## Question 1: Report Total vs JSON Total

The report header (`2026-03-31_honest_ytd_verification.md`) says:

> $30,000 → $141,070 (+370%)

But summing all 25 trades in `2026-03-31_honest_ytd_trades.json` gives **+$74,298** ($104,298 final equity).

**Discrepancy: $36,772**

Please explain the difference. Is the $141K number from a different run? Did the JSON miss trades? Is the report header wrong?

**Evidence required:** Show the exact equity progression trade-by-trade from $30K to whatever the actual final number is.

---

## Question 2: Three Duplicate Trades

These three trades appear twice in the JSON — once with a morning window and once with an evening window, but with identical entry times, prices, and P&L:

| Symbol | Date | Entry Time | Entry Price | P&L | Window 1 | Window 2 |
|--------|------|-----------|-------------|-----|----------|----------|
| AHMA | 2026-01-13 | 08:23 | $12.04 | +$5,472 | 04:00-11:00 | 16:00-20:00 |
| BGL | 2026-01-23 | 07:50 | $6.04 | +$1,223 | 04:00-11:00 | 16:00-20:00 |
| SVRE | 2026-01-16 | 06:49 | $3.04 | +$357 | 04:00-11:00 | 16:00-20:00 |

An 08:23 entry cannot be in the 16:00-20:00 window. These duplicates inflate the total by **+$7,052**.

**Please explain:** Are these real separate trades (different entries in the evening session)? Or are they duplicates from a bug in the trade logging? If duplicates, what is the corrected total?

**Evidence required:** Show the raw simulator output for AHMA Jan 13 — was there actually an evening session trade, or just the morning one?

---

## Question 3: Position Sizing Math

I recalculated every trade using 2.5% equity risk with compounding. Not a single trade's P&L matches. Examples:

| Trade | Equity at Entry | 2.5% Risk | R | Calculated Qty | Calc P&L | Logged P&L | Difference |
|-------|----------------|-----------|---|---------------|----------|------------|------------|
| ROLR #1 (08:20, $6.04) | ~$42,588 | $1,065 | $0.14 | 7,605 | +$12,320 | +$5,517 | -$6,803 |
| NPT (08:06, $9.04) | ~$59,799 | $1,495 | $0.14 | 10,678 | +$128,812 | +$42,468 | -$86,344 |
| ACCL #1 (04:08, $9.04) | ~$54,729 | $1,368 | $0.14 | 9,773 | +$6,548 | +$2,125 | -$4,423 |

The logged P&L is consistently ~30-40% of what a pure 2.5% risk calc produces. This suggests a notional cap, a core/runner split, or some other sizing constraint is binding.

**Please explain:** What is the exact position sizing formula used in this backtest? What caps are active (MAX_NOTIONAL, MAX_SHARES, core/runner split %)?

**Evidence required:** For the NPT trade specifically, show:
1. Account equity at time of entry
2. Risk dollars (equity × risk%)
3. Quantity calculation (risk$ / R)
4. Any caps that reduced the quantity
5. The final quantity that was used
6. P&L math: (exit - entry) × qty = P&L

---

## Question 4: Same-Minute Entry and Exit

18 of 25 trades show entry and exit in the same 1-minute bucket. We confirmed on TradingView that NPT's 08:06 candle had an $8.82-$29.95 range (halt-through), so same-minute fills are plausible on halting stocks.

**But for non-halting stocks**, same-minute entry AND exit means the 2R target was hit within seconds of entry. At R=$0.14, that's a $0.28 move needed for sq_target_hit.

**Please confirm:** For the same-minute trades that are NOT halt-throughs (e.g., ELAB 07:14, OM 09:06, BGL 07:50), did the stock actually move $0.28+ within that minute? Or is the exit timestamp just truncated to the minute (the actual exit was several minutes later but the log only records HH:MM)?

**Evidence required:** For ELAB Jan 24 trade 1 (entry 07:14 $5.04, exit 07:14 $5.32, +$1,027), show the actual tick-level entry and exit timestamps with seconds.

---

## Question 5: Gap Calculation Discrepancy

The verbose log for ROLR Jan 14 shows:

> Fundamentals: float=4.6M **gap=-3.0%**

But ROLR gapped from $3.52 to $15.50 that day (+340%). The scanner results file shows `gap_pct: 420.33` and `prev_close: 3.00`.

**Why does the verbose log say gap=-3.0%?** Is the fundamentals gap calculated differently than the scanner gap? Is it using a different prev_close? Is this a bug?

**Evidence required:** Show exactly what `prev_close` value the simulator used for ROLR on Jan 14, and how the gap% was computed.

---

## Question 6: Discovery Time vs Entry Time Inconsistency

Several trades show entry BEFORE discovery:

| Symbol | Discovery Time | Entry Time | Problem |
|--------|---------------|------------|---------|
| ROLR | 08:23 | 08:20 | Entry 3 min before discovery |
| NPT | 09:42 | 08:06 | Entry 96 min before discovery |
| GXAI (Feb 3) | 08:34 | 08:15 | Entry 19 min before discovery |
| GXAI (Mar 5) | 08:30 | 08:14 | Entry 16 min before discovery |
| BDSX | 08:02 | 07:00 | Entry 62 min before discovery |

The trade log says discovery times were computed by walking 1-min bars with RVOL ≥ 1.5x. But the simulator appears to have started watching these stocks much earlier than the recorded discovery time.

**Please explain:** What discovery time does the simulator actually use for entry gating? Is there a separate "sim_start" that's earlier than the RVOL-based discovery time? If the bot starts watching at 04:00 AM but the stock doesn't hit 1.5x RVOL until 08:23, can the squeeze still fire at 08:20?

**Evidence required:** For NPT specifically — how did the bot enter at 08:06 when the stock wasn't "discovered" until 09:42? What scanner source and what time did it actually start simulating NPT?

---

## Question 7: The 1-Minute Offset

We confirmed on TradingView that both ROLR and NPT entries are ~1 minute late compared to when the price actually hit the entry level on the chart. This is consistent and appears to be a bar-boundary artifact.

**Please confirm:** Is this because the squeeze detector ARMs on a bar close, and the trigger fires on the first tick of the NEXT bar that exceeds the trigger price? If so, this means live trading would also have the same ~1 minute delay, which is acceptable but worth documenting.

**Evidence required:** Walk through the exact ARM → trigger sequence for ROLR's $9.33 entry. What bar closed to cause the ARM? What was the first tick that triggered entry? What were the timestamps?

---

## Deliverable

Please answer each question with:
1. A clear explanation
2. Supporting evidence from the actual data/code
3. If a bug is found, note it and flag whether it affects the P&L total

Save to: `cowork_reports/2026-03-31_audit_answers.md`
