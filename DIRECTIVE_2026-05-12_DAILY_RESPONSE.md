# Daily Response Directive — 2026-05-12 Trade Breakdown

**Date:** 2026-05-12
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/daily_trades/2026-05-12_trade_breakdown.md`
**Day P&L:** Combined −$8,894 (Setup A −$2,693 / Setup B −$6,201)
**Projected day with stack active on same tape:** −$1,489 (Δ +$7,405 saved)
**Bot infrastructure milestones validated today:** partial-fill terminal-status, broker-reject (ConnectionError) terminal handling, trail-retry-rescue mechanics, first dual-setup live paper day, +$41 first Setup B winner

---

## TL;DR

Three categories of work going into tomorrow:

**SHIP TONIGHT (blockers — must land before 5/13 cron at 02:00 MT):**
1. Fix `WB_MAX_DAILY_LOSS` post-restart re-engagement (Anomaly A7)
2. Add `WB_MAX_NOTIONAL=30000` to Setup B `.env`
3. Run MACD observe-only replay on 5/12 tick cache; gate the live-paper Wed open on the result

**SHIP THIS WEEK:**
4. Hypothesis #15 — post-exit cooldown extension to winning exits (spec'd below)
5. ODYS retry-escalation fix (Anomaly A6)
6. Squeeze detector 0-fill spot-check (Setup A main + Setup B squeeze)

**DEFER / NO-OP:**
7. dead_bounce stays retired (no v3.2)
8. Watchdog false-positive (A8) is cosmetic — log a TODO, no action this week

---

## 1. SHIP TONIGHT — `WB_MAX_DAILY_LOSS` post-restart bug (Anomaly A7)

**Severity:** Blocker. This is the only item that can plausibly trash tomorrow's session if untouched.

### What we observed
- Setup B WB cold-booted at 11:10 ET with intended `WB_MAX_DAILY_LOSS=9999999`
- Bot accepted 4 fills post-restart (FATN#1, ATRA partial, FATN#2, ATRA#2) up to a cumulative −$3,624
- Then REFUSE-entry re-engaged from 13:58 ET onward
- The threshold $3,624 closely matches `$92,421 × 3.92%` — suggesting a *second* gate that's equity-pct-driven, separate from `WB_MAX_DAILY_LOSS`

### Hypothesis ranking
1. **Most likely:** A second risk gate exists (e.g., `WB_DAILY_LOSS_SCALE`, `WB_RISK_BUDGET_PCT`, or hardcoded). The `WB_MAX_DAILY_LOSS=9999999` only disabled gate #1.
2. **Less likely:** The cap raise didn't actually propagate to the cold-booted process (env var loading order issue, or the bot reads it once at boot from a stale path).
3. **Long shot:** The `daily_pnl` counter was reset on cold boot but cumulative session P&L (from a state file) was loaded separately and triggers a different threshold.

### Action
1. **Grep the codebase for every daily-loss / risk-cap reference** in `wb_bot.py`, `bot_alpaca_subbot.py`, `data_engine.py`, and any included risk modules:
   ```
   grep -rn "daily_loss\|daily_pnl\|MAX_DAILY\|RISK_BUDGET\|LOSS_SCALE\|risk_kill\|REFUSE entry" warrior_bot/
   ```
2. **Identify the SECOND gate.** Trace the code path that produced "REFUSE entry: daily risk kill" between 13:58 and 20:05 ET. The first kill (06:35 ET) was the configured `WB_MAX_DAILY_LOSS` against the at-the-time $94,998 equity. The post-restart kill at −$3,624 must come from a different code path.
3. **Patch:** unify all daily-loss / risk-cap logic behind a single env-var stack. Recommend:
   - `WB_MAX_DAILY_LOSS_ABS` (absolute $ cap, current `WB_MAX_DAILY_LOSS`)
   - `WB_MAX_DAILY_LOSS_PCT` (equity-fraction cap; set to e.g. 0.05 = 5%)
   - Whichever fires first wins. ANY raise to one must also raise/disable the other.
4. **Restart behavior:** on cold boot, the daily counter resets to $0 (current behavior). The *cumulative* session $ counter should NOT reset — load from `state.json` (already written per A9). Then:
   - Daily-loss kill compares `(equity_now - session_start_equity)` against `−WB_MAX_DAILY_LOSS_ABS` AND `−WB_MAX_DAILY_LOSS_PCT × session_start_equity`
   - This survives a restart cleanly (the "fresh budget" exploit is closed)
5. **Validation before tomorrow's cron:** dry-run a synthetic post-restart scenario where session_start_equity is loaded from disk and the bot computes the kill threshold from that. Confirm threshold matches expectation.

### Acceptance criterion (must be met before 5/13 cron)
- A test that simulates `cold boot with state.json showing session_pnl=$-2,577` produces a kill threshold equal to BOTH the absolute cap AND the equity-pct cap of the SESSION START equity (not the post-restart equity), whichever is smaller.

If this can't be solved tonight, the fallback is: **disable WB on Setup B for the Wed open**, run only Setup A subbot WB + both squeezes. We'd rather skip a day than have a half-broken daily-kill let the bot bleed past intent.

---

## 2. SHIP TONIGHT — `WB_MAX_NOTIONAL=30000` on Setup B

**Severity:** High. This is the single biggest lever on Setup B's per-trade exposure.

### Justification
Today's data:
- Setup A BP cap of $32K rejected 5 trades (TRAW 05:31, XOS ×3, the 5th was ENSC pre-9MT eventually filled because the position size was below the cap)
- Each of those Setup A "accidental saves" had a Setup B counterpart that FILLED at ~$50K notional
- The 5 same-trade comparisons cost Setup B **$2,577 / day** in pure notional-multiplier loss
- H#10 catches most of these anyway, but as a belt-AND-suspenders: if H#10 ever has a bug or false-negative, the smaller notional dramatically caps the bleeding

### Action
Add to Setup B `.env`:
```
WB_MAX_NOTIONAL=30000
```
Add to Setup A `.env` (already accidentally enforced via BP, but make it explicit):
```
WB_MAX_NOTIONAL=30000
```

Code: in the entry-pricing path of both `wb_bot.py` and `bot_alpaca_subbot.py`, after computing `qty = floor(target_notional / fill_price)`, cap `qty = min(qty, floor(WB_MAX_NOTIONAL / fill_price))`. Log if cap fires.

### What this changes
- Per-position loss capped at `WB_MAX_NOTIONAL × R% × R_multiple` ≈ `$30K × 0.02 × 1.5` ≈ **$900/trade max** at the −1.5R level for clean losers
- Today's bleed-trades would have been ~40% smaller (e.g., FATN#1 −$1,381 → ~−$828)
- Winners are *also* smaller, but we don't have winners at this size today to compare against

### Tradeoff acceptance
Capping notional means giving up upside on the rare full-size winners. **Accepted** — the asymmetry of paper-day P&L right now (winners $41, losers $700-$1,400) says we're in the "minimize bleed" regime, not the "maximize hit size" regime. Revisit after 2 weeks of paper data with the new gate stack on.

---

## 3. SHIP TONIGHT — MACD observe-only replay on 5/12 tick cache

**Severity:** Medium-high. We are about to flip MACD live Wed open. We do NOT want to ship blind on 11 fills' worth of data we already have on disk.

### Action
1. Run `scripts/validate_chop_gate_v3.py` against today's tick cache, MACD sub-gate enabled, all other sub-gates observe-only:
   - Closed dataset: 22 trades through 5/8 + 5/11 + 11 fills from 5/12 = 33 trades
   - Tabulate MACD verdict per fill on 5/12
2. Save as `cowork_reports/2026-05-13_chop_gate_v3_macd_replay_on_512.md`
3. Acceptance criteria for keeping MACD live ON Wed open:
   - All 5/12 winners preserved (only +$41 ATRA partial) → must PASS
   - At least 1 of the 2 "clean tuition" losers (Setup A SST 11:20 OR Setup A TRAW 15:17) is blocked by MACD → confirms MACD adds value
   - Zero new false positives across the cumulative 33-trade set
4. If criteria pass → MACD ships Wed open as planned
5. If criteria fail → MACD goes observe-only Wed open; investigate; re-evaluate Thu

This is a 30-minute task; do it tonight so we don't ship blind tomorrow.

---

## 4. SHIP THIS WEEK — Hypothesis #15: post-exit cooldown (incl. winning exits)

**Severity:** Medium. Today's ATRA pair (+$41 → −$1,157, 25 min apart) is exactly the trade class that motivated this.

### Spec
After ANY closed position on symbol X (win OR loss):
- If close was a LOSS: blacklist X for the rest of session (current H#11)
- If close was a WIN: cooldown X for `WB_POST_WIN_COOLDOWN_MIN=45` minutes before allowing a re-arm

### Justification
Today's ATRA pair: ATRA partial closed +$41 at 13:26 ET, ATRA#2 entered 13:51 (25 min later). The detector saw what it thought was a fresh setup; the bot had no memory of "we just took profits 25 min ago on this same name." Result: −$1,157 with R% 0.35%.

Yesterday's ATRA pair (5/11) was similar — multiple ATRA arms close together, all losers.

The cooldown protects against the "victory-lap re-entry" pattern: bot wins, immediately re-arms hoping for another win, takes a worse setup.

### Action
1. Add to both `wb_bot.py` and `bot_alpaca_subbot.py`:
   - Track last-close time per symbol per session (extend the same-session memory already powering H#11)
   - On WB ARM: if last close on this symbol was a WIN within `WB_POST_WIN_COOLDOWN_MIN`, REFUSE entry with reason `post_win_cooldown`
2. Env defaults:
   - `WB_POST_WIN_COOLDOWN_ENABLED=1`
   - `WB_POST_WIN_COOLDOWN_MIN=45`
3. Telemetry: log when the cooldown fires; daily report tabulates count
4. Acceptance: replay against today's ATRA pair → ATRA#2 13:51 entry MUST be blocked (last close 13:26, 25 min < 45 min cooldown)
5. Replay against 5/8 + 5/11 to confirm zero winner false-positives (i.e., no winner this season came within 45 min of a prior winning close on same symbol)

### Open question — should the cooldown apply to losses too?
Current H#11 blocks the rest of session on a loss. If we tighten that to "loss = cooldown 90 min" instead of "session blacklist," we permit legitimate re-entries on stocks that genuinely come back. Recommend deferring this question until we have post-cooldown data — H#11's permanent blacklist is safer for now.

### Ship target
Wed-Thu (after the WB_MAX_DAILY_LOSS fix lands and validates). Should not go live the same day as the daily-loss fix — too many simultaneous changes.

---

## 5. SHIP THIS WEEK — ODYS retry-escalation fix (Anomaly A6)

**Severity:** Medium.

### What we observed
ODYS 12:34 and 12:55 each had 3 retry attempts at the SAME limit price ($4.32 / $4.47 respectively), all timed out. 6 attempts total at 2 stale prices.

### Action
1. Verify whether engine WB path inherits `WB_ENTRY_SLIPPAGE_PCT` per-retry escalation logic from the subbot path
2. If not, port it. Each retry should re-compute the limit using:
   ```
   limit_n = signal_n + (n * WB_ENTRY_SLIPPAGE_PCT * signal_n)
   ```
   where `signal_n` is the *fresh* signal at retry time (not the original signal frozen at first attempt).
3. Cap escalation at `WB_ENTRY_MAX_SLIPPAGE_PCT=2.0%` total — better to abandon than chase forever.

### Acceptance criteria
- Synthetic test: 3 retries with 2% rising tape produces 3 monotonically increasing limit prices
- Replay ODYS 12:34: had the limit escalated 0.5% per retry, retry-2 at $4.34 might have caught the buyer

### Ship target
Mid-week. Not a blocker — entry-timeouts are no-fill no-position events; they cost opportunity, not capital.

---

## 6. SHIP THIS WEEK — Squeeze detector 0-fill spot-check

**Severity:** Medium. The main bot has gone 4 days without an ENTRY SIGNAL. We need to know if this is the detector or the tape.

### Action
1. Pick 3 small-caps that ran ≥10% intraday on 5/12 (not on watchlist):
   - You have IBKR data; use top-gainers list or filter the scanner log for high-volume HOD-breaks
2. Run the squeeze detector against their tick cache offline
3. Tabulate per-stock per-bar: detector state, why no ARM
4. If detector evaluates ≥1 of the 3 to "should have armed" → tighten the watchlist or loosen detector
5. If detector correctly rejects all 3 → the watchlist is the problem; 4-day no-fill is the tape

### Specific stocks to check (your call which to use)
- Any stock that printed >25% gain Mon-Tue with 5M+ shares volume that wasn't on the watchlist
- Use scanner-log to surface candidates: `grep -i "gainer\|hod_break" warrior_bot/logs/2026-05-12_scanner.log`

### Acceptance criteria
A diagnostic report: `cowork_reports/2026-05-13_squeeze_detector_spotcheck.md`
- 3 stocks, bar-by-bar trace of detector state
- Verdict: detector vs watchlist vs tape

### Ship target
Wed EOD. This is diagnostic, not a code change.

---

## 7. DEFER / NO-OP — Items I'm explicitly NOT acting on

### dead_bounce v3.2 (CC's open question #2)
**Decision: stay retired.**
Reasons documented in `DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md`. Tonight's data doesn't change the calculus — H#11 + H#15 (cooldown) together cover the bounce-back pattern at the cost of two simpler, well-defined gates rather than one impossible-to-codify chart-shape gate.

### Watchdog false-positive on graceful 18:00 MT shutdown (Anomaly A8)
**Decision: log a TODO, no action this week.**
Cosmetic alert at session-end. No fills, no positions, no $$ impact. We have higher-priority items. Add a TODO comment in the cron script: `# TODO: watchdog death-detection false-positives on graceful 18:00 MT shutdown`. Revisit when something forces it.

### Pattern 4 (late-day chase) and Pattern 5 (HOD distance)
**Decision: hold queued.**
No data today to re-validate. Both stay in the hypothesis queue. Will surface again when a 16:00-ET+ trade fires.

### Setup B squeeze 0-fill
Folded into #6 — same diagnostic covers both.

---

## 8. Answers to CC's open questions

### Q1 (Hypothesis #15 cooldown spec)
**Yes, ship it.** §4 above gives the spec. 45-min cooldown after winning exits. Same-session blacklist after losses (unchanged).

### Q2 (v3.2 dead_bounce alternative)
**Stay retired.** Covered above.

### Q3 (WB_MAX_DAILY_LOSS restart bug)
**Highest priority, ship tonight.** §1 above gives the spec.

### Q4 (Setup B notional cap)
**Yes, $30K per position.** §2 above gives the spec.

### Q5 (MACD sub-gate replay)
**Run tonight on the 5/12 tick cache.** §3 above gives the spec.

### Q6 + Q7 (Setup A/B squeeze 0-fill)
**Spot-check 3 stocks.** §6 above gives the spec.

### Q8 (ODYS retry-no-reprice)
**Fix mid-week.** §5 above gives the spec.

---

## 9. Tomorrow's stack order (5/13 open)

The 6-patch stack going live, in evaluation order:

| # | Gate | Default | Catches today |
|---|---|---|---|
| 1 | Pre-9-AM-MT WB block (H#14) | ON | ENSC 08:16, TRAW 05:31, ODYS 05:48, XOS 06:29 |
| 2 | MACD sub-gate (v3 modular) | ON (pending §3 replay) | TBD — replay determines |
| 3 | R% post-fill floor 1.5% (H#10) | ON | 7 of today's 10 losers |
| 4 | Within-session same-symbol blacklist (H#11) | ON | FATN#2 |
| 5 | Divergent-quote guard scoped BUY-only | ON | Prevents SELL cross-feed false-floor windows |
| 6 | Notional cap $30K (NEW per §2) | ON | Reduces every fill's size |

Hypothesis #15 (post-win cooldown) ships later this week, not Wed open.
Hypothesis #11.5 (loss → cooldown vs permanent blacklist) is queued.

---

## 10. Daily report template — small revisions for tomorrow

Two additions to the daily report contract (`DIRECTIVE_CHOP_GATE_V3_SUBGATE_VERDICTS.md` §7):

1. **Gate-overlap table:** for each fill, show which gates COULD have caught it (today's report already does this for H#10/H#11/H#14/MACD — keep that format). This lets us see incremental value of each gate.
2. **"Saved P&L this session if gate had been ON" tally:** today's report does this beautifully. Keep it. It's the single most useful chart for prioritizing next week's gate work.

These are the right artifacts. No further changes.

---

## 11. Risk-budget posture for the week

Going into Wednesday:
- Setup A subbot: ~$32K BP cap holds; new gates layer on top
- Setup B WB: $30K notional cap (NEW); daily-loss kill fixed (NEW); new gate stack active
- Setup A main bot: 0-fill streak day 5 looming — squeeze still needs diagnostic

**Per-day max drawdown budget (informational, not enforced):**
- Setup A: 2.5% of $30K = $750/day worst-case after gate stack lands
- Setup B: 2.5% of $30K (post-notional cap, even though equity is $95K) = $750/day

Combined max-drawdown budget across both setups: **~$1,500/day** worst case. Today's actual was 6× that. Tomorrow's projected with the stack on: ~$1,500. The numbers are designed to converge.

---

## 12. Tone note

Today's −$8,894 looks awful in isolation. In context: it's the most informative session we've had. Two new architecture pieces (partial-fill terminal-status, retry-rescue, broker-reject handling) all validated under live stress. The data from today drove 6 patches in <8 hours, every one of which is justified by a specific observed loss. The +$7,400 projected delta from the new stack is the strongest empirical case yet for the gate work.

The remaining "tuition" is now **down to ~$1,500/day worst case** on tape that produced $8,900 of damage today. If tomorrow we run on the new stack and see −$1,500 to −$2,000 with the same arm rate, the stack is doing exactly what it's supposed to. If we see a winner emerge through the cleaner filter, we're at break-even or better.

We are getting closer to having a bot that doesn't bleed by default. Then we look at upside.

---

## 13. Files referenced

- `cowork_reports/daily_trades/2026-05-12_trade_breakdown.md` (the input)
- `DIRECTIVE_CHOP_GATE_V3_MODULAR_ROLLOUT.md`
- `DIRECTIVE_CHOP_GATE_V3_SUBGATE_VERDICTS.md`
- `DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md`
- Source code: `wb_bot.py`, `bot_alpaca_subbot.py`, `data_engine.py`, `chop_gate_v3.py`, `session_history.py`, `scripts/validate_chop_gate_v3.py`

**Reports CC owes Cowork by Wed EOD:**
1. `cowork_reports/2026-05-13_wb_max_daily_loss_fix.md` (anomaly A7 patch + test results)
2. `cowork_reports/2026-05-13_chop_gate_v3_macd_replay_on_512.md` (§3)
3. `cowork_reports/daily_trades/2026-05-13_trade_breakdown.md` (daily report per existing template)

**Reports CC owes Cowork by Fri EOD:**
4. `cowork_reports/2026-05-1X_squeeze_detector_spotcheck.md` (§6)
5. `cowork_reports/2026-05-1X_post_win_cooldown_validation.md` (§4)
6. `cowork_reports/2026-05-1X_odys_retry_escalation_fix.md` (§5)
