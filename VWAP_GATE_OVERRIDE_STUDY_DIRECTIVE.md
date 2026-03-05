# VWAP Gate Override for High-Score Re-Entries — Study Directive
## Priority: HIGH | Profile: A (primary), B (secondary) | Date: March 5, 2026

---

## Motivation

The bearish engulfing study (commit `a4b5ed2`) concluded that BE exits are working correctly — the bot's cascading re-entry edge depends on them. But it identified the **real** missed opportunity from JZXN: a 12.5-score re-entry was blocked by the VWAP gate.

**JZXN recap (the blocked re-entry):**
- Bot exited at 07:19 via BE → +$333 (correct behavior per BE study)
- At 07:54, bot armed a re-entry: score 12.5, tags [ABCD, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY]
- This was a near-perfect setup — among the highest possible signal scores
- At 07:55, VWAP loss triggered a 1M RESET → entry blocked, trade never taken
- Stock continued running; Ross Cameron reportedly made $50k+ on this name

The VWAP gate exists for good reason — it prevents entries on stocks that have lost momentum. But on extremely high-conviction signals, the gate may be too aggressive. A momentary VWAP dip on a fast-moving micro-float is often noise, not a genuine momentum shift.

**This study asks:** Can we safely override the VWAP gate when the signal score is exceptionally high?

---

## Study Design

### Phase 1: Identify All VWAP-Blocked High-Score Arms

This is the data we don't have yet. The BE study's Phase 1 verbose output only captured executed trades — not armed setups that were killed by VWAP resets.

**Run all 27 Profile A sessions (same list from BE study) with enhanced verbose logging that captures:**
1. Every ARM event (including score, tags, entry price, stop, R)
2. Every VWAP RESET event (1M RESET) — specifically when it kills an armed setup
3. The relationship: was a setup armed AND then killed by VWAP within the same or next bar?

For each VWAP-blocked arm, capture:
- Symbol, date, time of arm
- Score and tags at arm time
- Price at arm, stop, R
- Time of VWAP reset
- What price did afterward (did the stock continue higher or was VWAP correct to block?)

**If the simulator doesn't currently log VWAP resets on armed setups at this level of detail**, add temporary verbose logging:
```python
if armed and vwap_lost:
    log(f"VWAP_BLOCKED_ARM: {symbol} score={score} tags={tags} arm_price={arm_price} vwap_reset_price={price}")
```

Save results to: `studies/vwap_override/phase1_blocked_arms.md`

**Stock list (same 27 Profile A sessions from BE study):**

| # | Symbol | Date |
|---|--------|------|
| 1 | ROLR | 2026-01-06 |
| 2 | ACON | 2026-01-08 |
| 3 | APVO | 2026-01-09 |
| 4 | BDSX | 2026-01-12 |
| 5 | PMAX | 2026-01-13 |
| 6 | ROLR | 2026-01-14 |
| 7 | BNAI | 2026-01-16 |
| 8 | GWAV | 2026-01-16 |
| 9 | LCFY | 2026-01-16 |
| 10 | ROLR | 2026-01-16 |
| 11 | SHPH | 2026-01-16 |
| 12 | TNMG | 2026-01-16 |
| 13 | VERO | 2026-01-16 |
| 14 | PAVM | 2026-01-21 |
| 15 | MOVE | 2026-01-23 |
| 16 | SLE | 2026-01-23 |
| 17 | BCTX | 2026-01-27 |
| 18 | HIND | 2026-01-27 |
| 19 | MOVE | 2026-01-27 |
| 20 | SXTP | 2026-01-27 |
| 21 | BNAI | 2026-01-28 |
| 22 | BNAI | 2026-02-05 |
| 23 | MNTS | 2026-02-06 |
| 24 | ACON | 2026-02-13 |
| 25 | MLEC | 2026-02-13 |
| 26 | SNSE | 2026-02-18 |
| 27 | ENVB | 2026-02-19 |

**Also run JZXN 2026-03-04** (the motivating case) as a 28th session — this gives us one known VWAP-blocked high-score arm to validate the logging.

### Phase 2: Analyze Blocked Arms

From Phase 1 data, answer:

**Q1: How many arms were blocked by VWAP across all 28 sessions?**
- Total count
- Breakdown by score bucket: < 8, 8-10, 10-12, 12+

**Q2: For high-score blocked arms (score ≥ 10), what happened after the block?**
For each:
- Did the stock continue higher within 5, 10, 30 minutes? (i.e., was VWAP wrong to block?)
- Did the stock fall further? (i.e., was VWAP correct?)
- What would the trade P&L have been if it entered at the arm price with the proposed stop?

**Q3: Is there a score threshold where VWAP blocks are consistently wrong?**
- At score ≥ 10, what % of VWAP blocks were "premature" (stock went higher)?
- At score ≥ 11?
- At score ≥ 12?
- Is there a clear breakpoint?

**Q4: Do specific tag combinations correlate with VWAP blocks being wrong?**
- ABCD + VOLUME_SURGE?
- RED_TO_GREEN?
- WHOLE_DOLLAR_NEARBY?
- Which tags, if present, make a VWAP block more likely to be a false negative?

Save analysis to: `studies/vwap_override/phase2_analysis.md`

### Phase 3: Simulate VWAP Override (What-If)

**Implement a configurable VWAP gate override:**

```python
# New env var
WB_VWAP_OVERRIDE_MIN_SCORE = float(os.getenv("WB_VWAP_OVERRIDE_MIN_SCORE", "0"))  # 0 = disabled

# In the VWAP gate / 1M RESET logic:
if vwap_lost and armed:
    if score >= WB_VWAP_OVERRIDE_MIN_SCORE and WB_VWAP_OVERRIDE_MIN_SCORE > 0:
        log(f"VWAP gate overridden — score {score} >= threshold {WB_VWAP_OVERRIDE_MIN_SCORE}")
        # allow entry despite VWAP loss
    else:
        # normal behavior — reset/block
```

**Test three thresholds:**
- `WB_VWAP_OVERRIDE_MIN_SCORE=10.0` — override on scores ≥ 10
- `WB_VWAP_OVERRIDE_MIN_SCORE=11.0` — override on scores ≥ 11
- `WB_VWAP_OVERRIDE_MIN_SCORE=12.0` — override on scores ≥ 12 (most conservative)

**For each threshold, run all 28 sessions and calculate:**
- Per-session P&L vs baseline
- Total P&L impact across all sessions
- Number of additional trades taken (new entries that would have been blocked)
- Win rate on the new entries specifically

**CRITICAL: Run all 6 regression benchmarks + JZXN with each threshold.**
- VERO 2026-01-16: baseline +$6,890
- GWAV 2026-01-16: baseline +$6,735
- APVO 2026-01-09: baseline +$7,622
- BNAI 2026-01-28: baseline +$5,610
- MOVE 2026-01-27: baseline +$5,502
- ANPA 2026-01-09: baseline +$2,088

Save results to: `studies/vwap_override/phase3_whatif.md`

---

## Key Constraints

1. **Signal mode cascading exits must NOT be touched.** This study only changes entry gating, not exit behavior.
2. **Stop losses are unaffected.** If the override lets an entry through and the stock keeps falling, the stop fires normally.
3. **This is Profile A only** for now (micro-float, Alpaca ticks). If it works, we can evaluate for Profile B later.
4. **The override only applies to the VWAP distance/loss gate**, not to other entry filters (stale stock, classifier suppress, etc.).
5. **Grace period consideration:** If the override lets an entry through on a momentary VWAP dip, but VWAP is regained within 1-2 bars, that's the signal working correctly. If VWAP stays lost for 5+ bars after override, that entry is likely bad.

---

## Implementation Proposal (pending Phase 3 results)

If the data supports a VWAP override:

```python
WB_VWAP_OVERRIDE_MIN_SCORE = float(os.getenv("WB_VWAP_OVERRIDE_MIN_SCORE", "0"))
```

- Default `0` = disabled (current behavior, no change)
- Profile A only via `profiles/A.json`
- Only applies when a setup is armed AND the VWAP gate would block it
- Score must meet the threshold at arm time

---

## What This Study Does NOT Cover

1. **Bearish engulfing suppression** — closed, do not revisit (commit `a4b5ed2`)
2. **Classifier lag / early detection** — low priority per JZXN analysis
3. **Trailing stop tuning** — independent system, already implemented (commit `80fa4c1`)
4. **VWAP calculation changes** — we're not changing how VWAP is computed, only when the gate can be overridden

---

## Expected Output

1. `studies/vwap_override/phase1_blocked_arms.md` — all VWAP-blocked arms with scores, tags, and post-block price action
2. `studies/vwap_override/phase2_analysis.md` — analysis of blocked arms by score bucket and tag combination
3. `studies/vwap_override/phase3_whatif.md` — override simulation results with regression checks
4. A **recommendation** on whether to ship the override, and if so, what score threshold

---

## Decision Framework

| Outcome | Action |
|---------|--------|
| Override improves P&L AND passes all regressions | Ship it — add `WB_VWAP_OVERRIDE_MIN_SCORE` to Profile A config |
| Override improves P&L but breaks regressions | Try higher threshold or add tag-based filter |
| Few VWAP-blocked high-score arms exist | Close study — the opportunity is too rare to optimize for |
| Override makes things worse or neutral | Close study — VWAP gate is correct even on high scores |

---

## Important Note on Scope

This may be a smaller study than the BE study. It's possible that across 28 sessions, there are only a handful of VWAP-blocked high-score arms. If Phase 1 finds fewer than 5 blocked arms with score ≥ 10, the sample size is too small for a reliable conclusion. In that case, report the findings but note that we need more data (future live sessions) before making a change.

---

*Directive by Perplexity Computer — March 5, 2026*
*Motivated by: Bearish Engulfing Study recommendation (commit a4b5ed2)*
*Root cause: JZXN 2026-03-04 — 12.5-score re-entry blocked by VWAP gate*
