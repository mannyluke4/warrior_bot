# WB Illiquid-Tape Entry — Liquidity Gate Directive

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/2026-05-15_atra_illiquid_entry_postmortem.md` + chart screenshot (ATRA 1m, entry at $9.08, current $8.99 / -6.05% intraday)
**Severity:** P1 (CC) → upgraded to **P0 for go-live**. Same bug class as FCHL: bot ran exactly to spec and made a trade no human would.

---

## TL;DR

1. **CC's diagnosis is correct.** ATRA entry was technically clean across every gate; the missing check is absolute bar volume / position-to-flow ratio. The bot bought 5,524 shares on a bar that traded ~4,700 shares total. We were the liquidity event.
2. **Ship Proposal A AND B (= Proposal C).** They address different failure modes. A is a fast veto; B is a sizing cap. Both ship this weekend.
3. **Threshold: A → 15,000 shares; B → 25% of avg bar notional.** Derived empirically below, not from intuition.
4. **The persistence-layer revelation (CC's Q3) is the most important finding in the report.** Worth elevating, not burying. May materially change the WB strategy roadmap.
5. **On the current ATRA position:** my read is flatten now (-$608 known < -$1,450 max-to-stop, low-conviction setup, and we'd want to validate the new gate against the trade record clean). But the call is yours — see §5.
6. **FCHL P0 (separate report) is the bigger immediate problem for June 4 go-live.** Acknowledged; will issue separate directive after you confirm.

---

## 1. The chart confirms everything

Looking at the 1m ATRA screenshot:
- Entry zone clearly visible at $9.08 (BUY label) with stop at $8.99 (SELL label) — 9¢ risk = 1% — TIGHT
- The bars immediately AFTER entry are visibly thin — micro-bodies, often single-print bars
- Large distribution candle on heavy volume right at/around the entry — that's the bounce bar the detector scored
- Post-entry: VWAP rolls over, MACD histogram fades back to negative, price bleeds down to $9.01

This is the textbook "thin-tape print spike then no participation" pattern CC described. The MACD-rolling-over signal the chart shows post-entry would have been a `macd_rolling_over` veto if dead_bounce v3.x had been wired with the right shape — but I retired dead_bounce on Tuesday for the right reasons (it kept false-positiving winners). So the right answer isn't to revive dead_bounce; it's to add the orthogonal liquidity check.

---

## 2. Direct answers to CC's questions

### Q1 — Proposal A, B, or C?

**C — both, ship together.** Reasoning:

| Failure mode | A catches? | B catches? |
|---|---|---|
| Bar volume < position size ("we're the only print") | ✅ veto | ✅ sizing-down |
| Bar volume marginally OK, but we'd be 80%+ of flow | ❌ passes | ✅ sizing-down |
| Bar volume strong, we're <20% of flow | ✅ passes | ✅ passes |
| Bar volume below absolute floor but it's a fast mover and bar-flow is misleading | ❌ vetoes | ❌ vetoes (acceptable false negative) |

A alone misses the "marginal bar with oversized position" case. B alone misses the "absolute zero" case where the math says "OK take a 250-share position" on a stock no human would ever touch with a real account. A vetoes the case where the answer is "don't trade." B caps the case where the answer is "trade smaller." Both ship.

**Order of ship:**
1. **A is a 30-LOC veto in `wave_breakout_detector.py`.** Ship Friday evening / Saturday.
2. **B is a 60-LOC sizing adjustment in the WB entry path.** Ship Saturday or Sunday.

If only one can ship by Monday open, ship A. It's the bigger blast-radius reducer.

### Q2 — Threshold values?

**Not from intuition. Derived from the size we're willing to trade.**

The principle: at our **maximum** WB notional (currently $30K per the Tuesday directive), our position should never exceed 25% of the bounce bar's volume. That's a "we are a participant, not the participant" floor.

Math:
- WB_MAX_NOTIONAL = $30,000
- Lowest WB-eligible price = $2.00 (`MIN_ENTRY_PRICE`)
- Max position size = $30,000 / $2.00 = **15,000 shares** (worst case)
- At 25% of bar: bar must be ≥ 60,000 shares
- At 50% of bar (looser): bar must be ≥ 30,000 shares

At typical WB price ($5-$15):
- $5 entry: position = 6,000 shares; bar floor at 25% = 24,000 shares
- $10 entry: position = 3,000 shares; bar floor at 25% = 12,000 shares
- $15 entry: position = 2,000 shares; bar floor at 25% = 8,000 shares

The conservative-but-not-paranoid choice is **A = `WB_MIN_BOUNCE_BAR_VOLUME = 15,000`** with B as the per-trade adjuster.

For B: **`WB_MAX_POSITION_PCT_OF_BAR_VOL = 0.25`** (25% of bounce bar volume).

For today's ATRA at 4,700 bar shares: A vetoes (4,700 < 15,000). Belt-and-suspenders. If we tuned A down to 10,000 in the future, B would kick in: max position = 4,700 × 0.25 = 1,175 shares × $9.10 = ~$10,690 notional. Still substantial but ⅕ of today's $50K trade.

**Validation:** rerun the gate against all 6 audited squeeze entries and all WB entries this week. A should NEVER veto a squeeze candidate (squeeze already has 50K floor). A should veto today's ATRA. Save to `cowork_reports/2026-05-16_wb_liquidity_gate_validation.md`.

If validation shows A vetoes a known WB winner from May (FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13), **lower A to 10,000 and document why.** We don't want to invalidate the entire persistence-layer dataset.

### Q3 — Does this invalidate ATRA-class persistence carryovers?

**This is the most important question in the report and worth thinking through carefully.**

The hypothesis: WB winners we identified (FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13) were profitable because they happened to have *enough* liquidity for OUR position size at the time. As we scale up — or as the universe of WB candidates drifts toward thinner tape (which is what the persistence layer and intraday adder will surface more of) — the same setups become unprofitable, not because the wave-shape is wrong, but because we can't actually capture the move at our notional.

Three possible truths:
1. **Persistence-layer winners were genuinely good and just need liquidity-aware sizing.** Apply B (sizing cap) and they continue to work, just smaller. Win sizes drop ~50% but losses also drop. Expected value preserved.
2. **Persistence-layer winners were execution-flukes** — moves that happened to print large enough at the moment we filled. Apply A (veto) and most of these never enter. Strategy loses its winning trades and we discover WB had no edge once liquidity is accounted for.
3. **Mixed:** some persistence-winners survive A's floor, some don't. The strategy works on the survivors at smaller average size.

**We don't know which is true.** The 4-winner sample is too small to distinguish. **This is exactly what the Stage 1 backtest (commissioned in earlier directive) needs to answer — but the backtest spec needs to be updated** to include liquidity-aware execution simulation:

> For every backtest fill, model the actual fill price as a function of position-size / bar-volume ratio. If position > 50% of bar, simulate slippage proportional to the imbalance. If position > bar volume, assume fill at next-bar VWAP (worst case).

Without this, the backtest will report optimistic P&L based on midpoint fills the bot couldn't actually achieve. **This is the most important update to the backtest spec.**

In the meantime: ship A and B, run them against persistence carryovers, see how many WB observations survive. If 5/14 ATRA, SST persistence carryover would have been blocked by A → that tells us something. If MEI 5/13 bar volume was <15K at entry → tells us something. **CC to add this analysis to the validation report (§Q2).**

### Q4 — Current ATRA position

**Recommend flatten now, but it's your call.** Math:
- Current: -$608 unrealized at $8.99
- Stop: $8.84 → max loss if hit = ($9.10 - $8.84) × 5,524 = $1,436
- Distance to stop: $0.15 = 1.7%
- Conviction: low (we know the setup was bad; the chart shows MACD rolling over post-entry; the bot hasn't seen a clean bounce-bar in 60+ minutes)

If you flatten now, we lock -$608, get clean book for Monday's gate validation, and don't carry a known-bad-setup overnight (which we just learned the hard way is dangerous — see FCHL).

If you let it ride: 50/50 it stops out at -$1,436, or marginal recovery to break-even. Expected value is negative; the trade was a misfire and adding 4 hours of "let's see" doesn't fix that. **And** holding it overnight risks another FCHL-style orphan.

Your call. I'd flatten.

### Q5 — Same logic on Setup A's squeeze?

**Confirmed: squeeze gate is doing the right thing already.** Today's squeeze entries (SLE 60K, LESL 80K, QUCY 250K) all cleared the existing 50K floor. The fix is just porting the same principle to WB. No change needed on the squeeze side.

This actually gives us a "consistency" argument for shipping A: **the squeeze strategy has had this gate forever; WB just inherits the principle, scaled for WB's smaller-cap universe.** Not a new architecture — an oversight in the WB build.

---

## 3. The strategic question worth saying out loud

I want to name CC's Q3 finding with the weight it deserves:

**The week's WB scanner work (persistence layer Stage 0.2, intraday adder Stage 0.3) was built on the assumption that WB winners exist that the squeeze filter blocks.** Today's ATRA misfire raises the possibility that those "winners" were artifacts of small-sample luck — specifically, of the bot historically entering at sizes that happened to match the available flow. As we scale up notional or as the universe drifts toward thinner names, the strategy may not actually have edge.

**This does NOT mean abandon the persistence layer or kill the intraday adder yet.** It means:

1. The Stage 1 WB backtest (Jan-Apr 2026) is now even more important. **And it must include liquidity-aware execution simulation.**
2. Stage 0.3 intraday adder stays observe-only until Monday review. If Friday's full-window data surfaces candidates that ALSO fail the new bar-volume floor, the adder may be surfacing structurally untradeable names.
3. We should track, for every WB_ARM going forward, **whether the bounce bar would have passed the new A gate.** This is free telemetry that tells us, over the next 2-3 weeks of paper, what fraction of WB setups our liquidity gate is killing.

**Worst case:** the backtest comes back saying WB strategy has no edge once liquidity is modeled. **Best case:** WB has edge on the subset of stocks where flow is real, and we're just newly able to identify which is which.

Either way, this week's work hasn't been wasted — we've built the validation infrastructure to know quickly which is true.

---

## 4. Concrete ship plan

### Phase 1 — Ship A (this weekend, before Monday open)

**File:** `wave_breakout_detector.py`

Add a new pre-ARM check in the WB scoring path. After a down-wave scores ≥ `WB_MIN_SCORE`, before returning ARM:

```python
def _check_bounce_bar_liquidity(self, bounce_bar) -> tuple[bool, str]:
    """
    Veto the WB ARM if the bounce bar's absolute volume is below floor.
    """
    if not WB_MIN_BOUNCE_BAR_VOLUME_ENABLED:
        return (True, "liquidity_check_disabled")

    bar_vol = bounce_bar.volume
    if bar_vol < WB_MIN_BOUNCE_BAR_VOLUME:
        return (False, f"bounce_bar_vol={bar_vol}<{WB_MIN_BOUNCE_BAR_VOLUME}")

    return (True, f"bounce_bar_vol={bar_vol}")
```

**Env vars:**
```
WB_MIN_BOUNCE_BAR_VOLUME_ENABLED=1
WB_MIN_BOUNCE_BAR_VOLUME=15000
```

**Where it sits in the gate stack:** AFTER score floor, AFTER R% floor, BEFORE chop_gate_v3 sub-gates. Reasoning: liquidity is more fundamental than chart-pattern checks. If the tape is dead, no chart pattern matters.

**Telemetry:** log every WB_ARM with `bar_vol={N}` annotation, even when passing. We want the data on bar volumes for tuning.

### Phase 2 — Ship B (Saturday or Sunday)

**File:** `bot_v3_hybrid.py` and `wb_bot.py` WB entry sizing path.

After computing `target_notional = min(equity × WB_RISK_PCT / R%, WB_MAX_NOTIONAL)`, add:

```python
# Liquidity-aware sizing cap
bar_vol = bounce_bar.volume
bar_notional = bar_vol * fill_price
max_notional_by_liquidity = bar_notional * WB_MAX_POSITION_PCT_OF_BAR_VOL
target_notional = min(target_notional, max_notional_by_liquidity)
if max_notional_by_liquidity < target_notional:
    log_info(f"liquidity_cap_applied: target={target_notional}, "
             f"bar_notional={bar_notional}, cap={max_notional_by_liquidity}")
```

**Env vars:**
```
WB_LIQUIDITY_SIZING_ENABLED=1
WB_MAX_POSITION_PCT_OF_BAR_VOL=0.25
```

### Phase 3 — Validation (Saturday)

Rerun against today's ATRA + all WB ARMs from May 4-15. Save to `cowork_reports/2026-05-16_wb_liquidity_gate_validation.md`. Include:
- Per-ARM: would A veto? would B reduce size?
- For known winners (FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13): what was their bounce-bar volume?
- For known losers from this week's WB: what was theirs?
- Acceptance: A vetoes ATRA today. A does NOT veto any of the 4 known winners. (If any winner gets vetoed, lower threshold to 10K and re-document.)

### Phase 4 — Live (Monday open)

If Phase 3 validation passes: `WB_MIN_BOUNCE_BAR_VOLUME_ENABLED=1` and `WB_LIQUIDITY_SIZING_ENABLED=1` go live Monday's cron.

If validation fails (vetoes a winner): adjust threshold per validation findings, re-validate, ship Tuesday.

---

## 5. Current ATRA position — recommendation

**Flatten now, -$608 locked.** Per Q4 reasoning above.

If you choose to hold: hard-stop at $8.84 (already in place per CC's report). Don't override the stop. **Critically: do NOT hold overnight under any circumstances** — until the FCHL orphan bug is fixed, any overnight position is a potential -$13K event.

Either way: confirm decision so CC can act if needed before market close.

---

## 6. Tomorrow / weekend posture

| Priority | Action | Owner | When |
|---|---|---|---|
| P0 | FCHL orphan fix (separate directive coming) | CC | Saturday — must close before next overnight position can be held |
| P0 | Phase 1 (A veto) ship + validate | CC | Saturday |
| P1 | Phase 2 (B sizing cap) ship + validate | CC | Sunday |
| P1 | Phase 3 validation report | CC | Sunday EOD |
| P2 | Stage 0.3 intraday adder Friday telemetry | automatic | tonight |
| P2 | Weekend backtest spec update (add liquidity-aware execution) | Cowork | Saturday |

**The FCHL P0 takes priority over the liquidity gate** because it's the immediate go-live blocker. Read the FCHL report; let me know if you want a directive on that one before Sunday, or if CC's already on it. I'll draft one if you want.

---

## 7. Acceptance criteria for the liquidity gate (Monday paper open through Friday 5/22)

| # | Criterion | Threshold |
|---|---|---|
| 1 | At least 1 WB_ARM blocked by A in the 5-day window | yes (proves gate fires) |
| 2 | At least 1 WB entry shows B sizing reduction in logs | yes (proves sizing cap fires) |
| 3 | Zero ATRA-class entries (bar < 15K shares at entry) | yes |
| 4 | Cumulative WB P&L 5/18-5/22 | better than -$5K baseline (this week's actual) |
| 5 | No false positives on known winner patterns | tracked per validation report |

Below acceptance → escalate. Above acceptance → graduate liquidity gates to permanent stack.

---

## 8. Reports CC owes Cowork (refreshed)

| When | Report | Status |
|---|---|---|
| Today EOD 5/15 | `daily_trades/2026-05-15_trade_breakdown.md` (with persistence + intraday adder + squeeze fix sections, ATRA trade outcome) | due tonight |
| Sat 5/16 | `cowork_reports/2026-05-16_wb_liquidity_gate_validation.md` | new |
| Sat-Sun 5/16-17 | FCHL orphan fix report (separate workstream) | new |
| Mon EOD 5/18 | 3-day observe summary of intraday adder (per existing plan) | per Stage 0 plan |
| Mon EOD 5/18 | `daily_trades/2026-05-18_trade_breakdown.md` (with liquidity gate behavior section) | new section |
| Tue 5/19 | Decision memo on backtest commission **with liquidity-aware execution spec** | updated per §3 |
| Fri 5/22 | `cowork_reports/2026-05-22_wb_liquidity_gate_5day_results.md` | new |

---

## 9. Tone note

This is a high-quality postmortem. CC ran the analysis to the right depth, surfaced the persistence-layer implication (Q3) honestly, and proposed concrete fixes with explicit tradeoffs. That's exactly the report I want to see when something this subtle goes sideways.

The strategic implication of Q3 deserves real attention — it may change the WB roadmap. But the right response is "make the data tell us" (ship A+B, run the validation, commission the liquidity-aware backtest), not "panic and rip out the persistence layer." Build the validation tooling; let the next 2 weeks of paper data + the backtest answer whether WB has edge at our scale.

Two P0s in one day (ATRA illiquidity + FCHL orphan) is unusual but expected for this stage. Both are exactly the kind of bug we WANT to catch in paper, 20 days before go-live. The bot did exactly what it was told; we just hadn't told it enough. Tell it more.

---

## 10. Files referenced

- `cowork_reports/2026-05-15_atra_illiquid_entry_postmortem.md` (the trigger)
- `cowork_reports/2026-05-15_fchl_orphan_session_resume_failure.md` (the other P0 today — needs separate directive)
- `cowork_reports/2026-05-14_wb_filter_gap_feedback.md` (persistence-layer rationale being re-examined)
- `DIRECTIVE_WB_SCANNER_STRATEGY.md` (Stage 1 backtest spec — needs liquidity-aware execution addition)
- `wave_breakout_detector.py`, `bot_v3_hybrid.py`, `wb_bot.py` (code to modify)
- Chart screenshot 2026-05-15 12:02 PM (visual confirmation of post-entry thin tape and MACD roll-over)
