# Round 7 Directive: Feb 27 Live Session Fix
**Date**: February 27, 2026
**Goal**: Turn today's -$5,617 session into a profitable day through targeted exit logic improvements
**Method**: Analyze each trade's exit decision, propose specific code changes, backtest against today's stocks

---

## How the Exit Logic Currently Works

Understanding the machinery before proposing changes:

### Signal Exit Mode (current config: `WB_EXIT_MODE=signal`)
1. **Hard stop** at entry - R (e.g., entry $4.06, R=$0.09, stop=$3.97)
2. Once price reaches **entry + 1.0R** (`WB_BE_TRIGGER_R=1.0`), trailing activates:
   - Stop moves to breakeven (entry + $0.01)
   - Trail = peak × (1 - 5%) (`WB_SIGNAL_TRAIL_PCT=0.05`)
3. **No fixed take-profit** — the bot relies entirely on signal exits (TW, BE) or the trail

### Topping Wicky Exit
- Fires on **10-second bars** via `patterns.py`
- Condition: bar near session high + upper wick >= 45% of bar range + body <= 35% of range
- **Grace period**: 3 minutes after entry (`WB_TOPPING_WICKY_GRACE_MIN=3`)
- When it fires: **full position exit** (if no TP hit yet) or runner exit (if TP hit)

### Bearish Engulfing Exit
- Fires on **10-second bars** via `candles.py`
- Condition: previous bar green, current bar red, current body engulfs previous body
- Time-based grace: `WB_BE_GRACE_MIN` (default 0 = no time grace)
- Parabolic grace suppresses in non-signal mode only
- **In signal mode: BE exits are NEVER suppressed** (cascading re-entry is the strategy)

### Key Insight
In signal mode, the bot exits aggressively on ANY bearish engulfing or topping wicky on 10-second bars, then re-arms for re-entry. This works brilliantly on VERO-type stocks where the re-entry captures another leg up. **But on normal stocks, the first 10-second red candle after entry triggers an exit, and the re-entry often fails.**

---

## Trade-by-Trade Exit Analysis

### ARLO: TW Exit Captured 7% of Move (+$35 instead of +$472)

**What happened mechanically:**
- Entry 09:36:36 at $15.47
- TW grace: 3 minutes (expires 09:39:36)
- TW exit at 09:39:43 at $15.49 — **fired 7 seconds after grace expired**
- Stock continued to $15.74 (7 more green candles)

**Why the exit was wrong:**
The 3-minute grace period expired, and the very first 10s bar that showed a wick near the high triggered TW. At $15.49, the stock was only +$0.02 above entry — barely positive. The TW pattern is designed to detect exhaustion at the TOP of a move, but here it fired at the very START of the move. The stock had only moved +$0.02 and the pattern said "topping."

**The problem:** TW has no concept of how far the trade has moved. A wick at +$0.02 gets the same treatment as a wick at +$2.00. On a $15 stock with R=$0.60, a topping wicky at +$0.02 is noise, not exhaustion.

**What would have helped:**
- **TW should require minimum profit before firing.** If the trade hasn't reached at least 1R of profit, TW should be suppressed. ARLO at +$0.02 on R=$0.60 was only +0.03R — nowhere near a "top."
- Alternatively, extend TW grace period from 3 minutes to 5 minutes. ARLO's exit was 7 seconds past grace. But time-based grace is crude — profit-based is smarter.

---

### CDIO T1: TW Exit Captured Pennies (+$84), Then Re-entry Gave It Back (-$78)

**What happened mechanically:**
- Entry 09:52:02 at $6.952 (score 12.5)
- TW grace expires 09:55:02
- TW exit at 09:56:27 at $6.97 — +$0.018/share, +$84 total
- Re-armed at $7.14, re-entered 09:57:51
- BE exit at 09:58:11 at $7.12 — -$78
- Net CDIO: +$6

**Why the exit was wrong:**
Same as ARLO. TW fired shortly after grace on a trade that had barely moved (+$0.018/share = +0.08R). The stock was building, not topping. The re-entry at $7.14 confirms the stock continued up, but by then the setup was weaker and the BE immediately killed it.

**What would have helped:**
- TW minimum profit gate: at +0.08R, TW should not fire
- If TW had been suppressed, the original position at $6.952 would have ridden the move to $7.14+ — capturing +$0.19/share × 4,545 = +$864 instead of +$6 net

---

### ANNA T1 & T2: Tight R Shakeout (-$2,633 combined)

**What happened mechanically:**
- T1: Entry $4.06, stop $3.97, R=$0.09. Stopped out at $3.94 in 27 seconds. -$1,333
- T2: Entry $4.14, stop $4.04, R=$0.10. Stopped out at $4.01 in 25 seconds. -$1,300
- Stock reached $5.04 at 08:49 (one bar after T2 stop)

**Why the exit was wrong:**
These weren't signal exits (TW or BE) — they were **hard stop hits**. The stops were correct relative to the pullback structure, but R=$0.09 on a stock with 39.5% gap is structurally insufficient. The stock's normal volatility exceeded the stop distance.

**The problem is entry sizing, not exit logic:**
The bot calculated R=$0.09, which produced 11,111 shares ($45K notional). A $0.12 price move (totally normal for a gapping $4 stock) = -$1,333. The vol floor proposal addresses this, but needs activation criteria.

**What would have helped:**
- **Vol Floor with targeted activation**: When gap% > 20% AND R/entry_price < 3%, widen the stop to max(original_stop, entry × (1 - 5%)) = $3.86 instead of $3.97. Position drops to ~5,000 shares. If the $3.94 price holds above the wider $3.86 stop, trade 1 survives and rides to $5.04.
- **Re-entry cooldown**: After being stopped out on ANNA T1, the bot re-entered 2 minutes later with the same tight R. A per-symbol cooldown after a stop-out (e.g., skip next ARM on same symbol) would have saved -$1,300.

---

### LBGJ T1 & T2: Low Conviction Double Loss (-$1,077)

**What happened mechanically:**
- T1: Score 5.5, zero tags. BE exit at -$6 (17 seconds). Bearish engulfing saved it.
- T2: Score 4.0 (!), zero tags. Stopped out at -$1,070 (8 seconds).

**Why T2 should never have happened:**
T1 was marginal (5.5, no tags). T2 was worse (4.0, no tags) — entered at a LOWER price on a stock that had just shown weakness. The bot has no minimum score gate and no concept of "this stock is failing."

**What would have helped:**
- **Minimum score gate**: Score < 5.0 should block entry. LBGJ T2 at 4.0 would be blocked.
- **Minimum tag requirement**: Zero pattern tags = zero structural conviction. Require at least 1 tag (FLAT_TOP, ASC_TRIANGLE, R2G, etc.) for entry. MRM (0 tags), LBGJ T1 (0 tags), LBGJ T2 (0 tags) all blocked.
- **Per-symbol failure memory**: After T1's bearish engulfing, the bot should cool off on LBGJ.

---

### AAOI T1 & T2: Extended Entry + Re-entry Loss (-$1,461)

**What happened mechanically:**
- T1: Entry $76.60, PM_HIGH was $66.00. That's 16% above PM_HIGH. BE exit at $75.03. -$447.
- T2: Re-entry at $77.43, 4 minutes later. Stopped out at $74.02. -$1,014.

**Why this happened:**
The bot found a valid setup structure at $76.60 (12.5 score, strong tags), but the entry was 16% above the premarket reference level. The pattern detection correctly identified a pullback-breakout structure in the intraday price action, but the stock was already massively extended from its PM_HIGH.

**What would have helped:**
- **PM_HIGH distance filter**: If entry price is > 10% above PM_HIGH, skip. This is not a "PM_HIGH break" play — the stock has already moved.
- **Re-entry cooldown**: Same as ANNA — skip next ARM after BE/stop on the same symbol.

---

### ONMD T1 & T2: Resistance + Tight R (-$757)

**What happened:**
- T1: 7 failed attempts at $1.00 resistance, then finally broke through. Score 12.5. BE exit at -$328.
- T2: Re-armed at $1.20 with R=$0.07 → 14,285 shares. BE exit at -$429.

**What would have helped:**
- **Whole-dollar failure gate**: After 7 failed $1.00 breaks, the resistance evidence is overwhelming. Should require clean break + hold above for N bars before arming.
- **Vol floor on T2**: R=$0.07 on $1.20 entry = 5.8%. But 14,285 shares on a sub-$2 stock is extreme.

---

### FIGS: The Orphan That Worked (+$1,300 accidental, +$4,740 peak)

**What happened:**
The bot gave up on entry after 7 ARM attempts, but the order filled anyway (orphan bug, now fixed). Stock ran to +$4,740 unrealized. User manually closed at +$1,300.

**What this tells us:**
FIGS was score 12.5 with ASC_TRIANGLE + FLAT_TOP + R2G + VOL_SURGE — the strongest setup of the day. The entry at $14.44 was excellent. If the bot had managed this trade properly with the current exit logic, the question is: would TW or BE have clipped it early like ARLO?

**Backtest question:** Run FIGS through simulate.py. If TW/BE clips the profit, that confirms the exit problem is real and needs fixing.

---

## Proposed Changes (Prioritized)

### Change 1: TW Minimum Profit Gate (HIGH PRIORITY)
**Problem**: TW fires at +0.03R, killing trades before they develop
**Fix**: Add `WB_TW_MIN_PROFIT_R` env var (default 1.0). TW exit is suppressed when unrealized profit < min_profit × R.

```
Location: bot.py ~line 416, simulate.py ~line 631
Logic: Before calling on_exit_signal("topping_wicky"), check:
  current_price - entry >= WB_TW_MIN_PROFIT_R * R
If not, skip the TW exit.
```

**Expected impact:**
- ARLO: TW at +0.03R blocked → holds through 7 green candles → captures more of $0.30 move → est. +$300-$500 instead of +$35
- CDIO: TW at +0.08R blocked → holds through to $7.14+ → est. +$400-$800 instead of +$6 net

### Change 2: BE Minimum Profit Gate (HIGH PRIORITY)
**Problem**: BE fires at breakeven or tiny profit on 10s bars, killing developing trades
**Fix**: Add `WB_BE_MIN_PROFIT_R` env var (default 0.5). BE exit suppressed when unrealized profit < min_profit × R.

```
Location: trade_manager.py ~line 1745 (in the bearish engulfing handler)
Logic: After bear = is_bearish_engulfing(...), before exiting, check:
  current_price - entry >= WB_BE_MIN_PROFIT_R * R
If not, the hard stop provides protection — no need for aggressive early exit.
```

**Expected impact:**
- ONMD T1: BE at -$0.044/share would still fire (it's a loss, below min profit). No change — this is correct.
- LBGJ T1: BE at -$0.0015 would still fire. Correct.
- AAOI T1: BE at -$1.57/share would still fire. Correct.
- The profit gate only suppresses BE when the trade IS profitable but not profitable enough — preventing premature exits on winning positions.

**IMPORTANT**: In signal mode for VERO-type stocks, cascading re-entry after BE is the core edge. This gate MUST only suppress BE at very low profit levels (< 0.5R). At 1R+ profit, BE should fire normally so the bot can re-enter at higher levels. **Test thoroughly against VERO, GWAV, ALMS baselines.**

### Change 3: Per-Symbol Re-Entry Cooldown (HIGH PRIORITY)
**Problem**: Bot re-enters same symbol after failure, doubling losses. -$3,384 from re-entries today.
**Fix**: Add `WB_REENTRY_COOLDOWN_BARS` env var (default 5). After a stop_hit or bearish_engulfing_exit on a symbol, suppress the next N 1-minute bars of ARM attempts on that same symbol.

```
Location: micro_pullback.py — in the ARM logic
Logic: Track last_exit_time per symbol. If last exit was < N bars ago AND exit was
  stop_hit or BE_exit_full, skip arming.
```

**Expected impact:**
- ANNA T2 (-$1,300): blocked. Bot would wait 5+ minutes before re-entering ANNA.
- LBGJ T2 (-$1,070): blocked.
- AAOI T2 (-$1,014): blocked.
- **Total saved: up to +$3,384** (assuming re-entries would have been losses, which they were)

**Risk:** On cascading re-entry stocks like VERO, the cooldown could delay entries. VERO's re-entries were at 07:03, 07:04, 07:14, 07:30 — gaps of 1, 10, and 16 minutes. A 5-bar (5-minute) cooldown would delay the 07:04 re-entry to 07:08, but the 07:14 and 07:30 entries would be unaffected. **Test against VERO baseline.**

**Refinement option:** Only apply cooldown after **stop_hit** exits (where the trade fully failed), not after BE/TW exits (where the bot took profit or broke even). VERO's exits were all BE/TW, so they'd be unaffected by this refinement.

### Change 4: Minimum Score + Tag Gate (MEDIUM PRIORITY)
**Problem**: Score 4.0–5.5 entries with zero tags are consistently losers. -$2,106 today.
**Fix**: Add `WB_MIN_SCORE` (default 5.5) and `WB_MIN_TAGS` (default 1). Block ARM when score < min AND tag count < min.

```
Location: micro_pullback.py — in the ARM decision logic
Logic: If score < WB_MIN_SCORE AND len(pattern_tags) < WB_MIN_TAGS, skip ARM.
  This means: low score is OK if you have tags (structural evidence),
  and zero tags is OK if score is high (strong signals).
  But low score + zero tags = no basis for entry.
```

**Expected impact:**
- MRM (5.5, 0 tags): BLOCKED (below 5.5 AND 0 tags). Saves +$1,029
- LBGJ T1 (5.5, 0 tags): BLOCKED. Saves +$6 (was breakeven)
- LBGJ T2 (4.0, 0 tags): BLOCKED. Saves +$1,070
- ANNA (12.5, 6 tags): NOT blocked (high score + tags). Correct.
- FIGS (12.5, 4 tags): NOT blocked. Correct.
- ARLO (9.5, 4 tags): NOT blocked. Correct.

**Note:** Set `WB_MIN_SCORE=6.0` to also catch 5.5/0-tag entries, or keep at 5.5 and rely on the tag gate.

### Change 5: Vol Floor with Targeted Activation (MEDIUM PRIORITY)
**Problem**: Tight R + massive position on gapping stocks = instant shakeout losses
**Fix**: Activate vol floor ONLY when: gap% > 20% AND R/entry_price < 3%

```
Already implemented (WB_VOL_FLOOR_ENABLED), needs activation criteria change.
Location: micro_pullback.py — _vol_floor_stop()
Logic: Add conditional check:
  if abs(gap_pct) > 20 and (R / entry_price) < 0.03:
      apply vol floor
  else:
      skip vol floor (original R stands)
```

**Expected impact on today's trades:**
- ANNA (39.5% gap, R/entry = 2.2%): Vol floor activates. Stop widens. Position smaller. Survives shakeout.
- ARLO (R/entry = 3.9%): Vol floor does NOT activate. Original sizing preserved. Good.
- VERO, GWAV: Would need testing, but with the 3% R/entry gate, VERO (R=$0.17, entry=$3.52, ratio=4.8%) would NOT trigger vol floor. GWAV (R=$0.14, entry=$5.49, ratio=2.5%) WOULD trigger — needs verification.

### Change 6: PM_HIGH Distance Filter (LOW PRIORITY — defer)
**Problem**: AAOI entered 16% above PM_HIGH
**Fix**: Add `WB_MAX_PM_HIGH_DISTANCE_PCT` (default 15). Skip ARM when entry is > X% above PM_HIGH.
**Defer reason**: Only affected one stock today. Need more data on whether this is recurring.

---

## Backtest Commands

### Phase 1: Validate changes don't regress winners
Run the core regression suite FIRST with each change individually:

```bash
# Baseline (current code, no changes)
python simulate.py VERO 2026-01-16 07:00 12:00
python simulate.py GWAV 2026-01-16 07:00 12:00
python simulate.py APVO 2026-01-09 07:00 12:00
python simulate.py ALMS 2026-01-06 07:00 12:00
python simulate.py ANPA 2026-01-09 07:00 12:00

# After each change, re-run all 5 and verify P&L matches or improves
```

### Phase 2: Test against today's stocks
Use the actual scanner/watchlist add times from the live session:

```bash
# Session 1 stocks (IEX data, but backtest will use SIP — that's fine, we want to see what SHOULD have happened)
python simulate.py MRM 2026-02-27 08:00 12:00
python simulate.py BATL 2026-02-27 08:00 12:00

# Session 2 stocks (SIP data)
python simulate.py ANNA 2026-02-27 08:30 12:00
python simulate.py LBGJ 2026-02-27 09:00 12:00
python simulate.py FIGS 2026-02-27 09:00 12:00
python simulate.py ONMD 2026-02-27 08:30 12:00
python simulate.py ARLO 2026-02-27 09:20 12:00
python simulate.py AAOI 2026-02-27 09:30 12:00
python simulate.py CDIO 2026-02-27 09:45 12:00
```

**Note:** Start times are approximate based on when stocks were added to the watchlist during the live session. Adjust if the actual add times are known.

### Phase 3: Full regression with all changes combined
Run the full 25-stock suite with all changes active to verify net P&L improves.

---

## Implementation Priority

| # | Change | Expected P&L Impact | Regression Risk | Implement |
|---|--------|-------------------|-----------------|-----------|
| 1 | TW min profit gate (1R) | +$400-$800 (ARLO, CDIO) | Low — only suppresses TW on tiny gains | FIRST |
| 2 | BE min profit gate (0.5R) | Moderate — prevents premature BE exits | Medium — must verify VERO cascading re-entry | SECOND |
| 3 | Re-entry cooldown (5 bars, stop_hit only) | +$3,384 (ANNA T2, LBGJ T2, AAOI T2) | Low if stop_hit only | THIRD |
| 4 | Min score + tag gate | +$2,106 (MRM, LBGJ) | Very low — only blocks the weakest entries | FOURTH |
| 5 | Vol floor activation criteria | +$500-$1,000 (ANNA) | Medium — needs GWAV verification | FIFTH |
| 6 | PM_HIGH distance filter | +$1,461 (AAOI) | Low | DEFER |

**Combined potential improvement: +$5,000 to +$8,000** on today's session, potentially flipping -$5,617 to breakeven or positive.

---

## Success Criteria

After implementing changes 1-5 and backtesting today's stocks:
1. **VERO baseline preserved**: +$6,890 ± $200
2. **GWAV baseline preserved**: +$6,735 ± $500
3. **ALMS baseline preserved**: +$3,407 ± $200
4. **Today's session P&L**: Improved from -$5,617 to at least -$2,000 (ideally positive)
5. **ARLO**: Captures at least +$200 of the $472 available move
6. **ANNA T2, LBGJ T2, AAOI T2**: All blocked by re-entry cooldown

---

*Directive by Perplexity Computer — February 27, 2026*
*Source: Session log (commit 4ad9ee4c), trade_manager.py, micro_pullback.py, patterns.py, candles.py, bot.py*
