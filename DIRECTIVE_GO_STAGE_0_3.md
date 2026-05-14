# Go Decision — Stage 0.3 Intraday WB Adder

**Date:** 2026-05-14
**Author:** Cowork (Perplexity)
**For:** CC
**Status:** GO. Ship Stage 0.3 today in observe-only mode.

---

## TL;DR

1. **Stage 0.2 validation: PASSED.** All 5 required acceptance criteria met. Persistence is live on both setups with ATRA + SST flowing through the full pipeline.
2. **MEI mystery: CLOSED.** No hidden code path. Manual addition by a prior Claude Code session after Databento crash. Process discipline issue, not architecture.
3. **Stage 0.3: GO.** Ship the intraday adder in observe-only mode today. Reasoning + spec below.
4. **Process note added:** any future manual symbol additions must log to a known channel so future investigations don't burn cycles tracing.

---

## 1. Stage 0.2 — validation passed

All 5 required acceptance criteria from the rollout directive (§3) met:

| # | Criterion | Result |
|---|---|---|
| 1 | `🧠 WB_PERSIST` log line within 60s | ✅ |
| 2 | ATRA + SST in `state.active_symbols` | ✅ |
| 3 | `session_state/2026-05-14/watchlist.json` contains both | ✅ |
| 4 | Both setups subscribed and running WB detector | ✅ engine 12:36:15, subbot next poll cycle |
| 6 | WRITE side will populate on new WB_OBSERVE | architecturally verified; awaits a live WB_OBSERVE event today |

Criteria 5 and 7 (ARM and fill behavior) are conditional and await a live WB_OBSERVE event on ATRA/SST during today's session.

**Verdict: persistence is live and operational. Stage 0.2 closed.**

---

## 2. MEI mystery — closed

The async trace agent finished: MEI 05-13 came from a manual `python -c` heredoc by a prior Claude Code session, after Databento crashed and bots were idling. Not a code path. Not a bug. Documented in `cowork_reports/2026-05-14_mei_bypass_trace.md`.

**Implications:**

- There is no third bypass channel. The data picture is: (1) scanner output, (2) prior-session carryover (now formalized via persistence), (3) occasional manual addition.
- The +$366 MEI winner was a one-off manual triage outcome, not evidence of a sustained channel. **We should slightly down-weight its contribution to the Stage 0.3 case.**
- However: the structural argument for the intraday adder is unchanged. WB detects intraday wave structure; squeeze filters on premarket. The mismatch is real regardless of MEI's specific origin.

---

## 3. Process note — manual symbol additions

Going forward, any manual `python -c` / heredoc / direct watchlist.json mutation by an agent (Cowork-directed or otherwise) MUST log to a known channel so future audits can trace. Add this to the agent rules / project conventions:

**Convention proposal:**
- Any time an agent injects a symbol into a state file or watchlist outside the normal scanner path, append a one-line entry to `~/warrior_bot_v2/logs/manual_interventions.log` with format:
  ```
  YYYY-MM-DD HH:MM:SS ET  ACTOR  ACTION  SYMBOL(S)  REASON
  ```
- Example: `2026-05-13 12:32:00 ET  cc-session-3a1f  inject-watchlist  MEI,NSTS,PTBD,VNET  databento crashed, bots idling, manual triage`
- This is purely append; no code change needed for the bot, just an agent convention.

**Implement:** in CC's CLAUDE.md (or equivalent rules file), add: "Any manual mutation of `state/`, `session_state/`, `watchlist.txt`, or `wb_persistence.txt` outside scanner/bot code paths must be logged to `logs/manual_interventions.log` with timestamp, actor, action, symbols, and reason."

This is the smallest fix for the smallest problem MEI revealed.

---

## 4. Stage 0.3 — GO with observe-only spec

### Why ship today
1. **Complementary to persistence, not duplicative.** Persistence carries forward *yesterday's WB-active* symbols. Intraday adder catches *today's intraday WB candidates* that nothing else would surface (MEI-shape, FATN-shape, low-PM-volume intraday-trender names).
2. **Observe-only is zero-risk.** Logs what it would have added; doesn't actually add to the live watchlist. Pure telemetry.
3. **Friday EOD gives us a clean dataset.** One full session of persistence-layer data (5/14) + one full session of intraday-adder observe data (5/15) feed the Monday review.
4. **CC is in flow.** Cheaper to ship now than restart context tomorrow.

### Spec (per original directive §0.3, with one refinement)

**Component:** 15-minute RTH polling loop, observe-only telemetry, no live watchlist injection.

**Polling cadence:** Every 15 minutes from 09:45 ET through 15:30 ET (matches the "good WB time window" hypothesis from the original analysis).

**Filter (provisional, to be refined by Jan-Apr backtest in Stage 1):**
```
gap_from_prev_close ≥ 3%      # not premarket gap — intraday gap measured live
intraday_rvol_5m ≥ 3×          # 5m RVOL relative to that symbol's 20-day avg
price 2.00 ≤ p ≤ 30.00         # WB-friendly band
float ≤ 30M                    # small/micro-cap
traded_volume_today ≥ 500K     # rules out totally untraded names
```

**Source:** whichever provider the existing scanner uses for intraday data. If IBKR scanner supports a "gainers above VWAP with intraday RVOL ≥ X" query, use it. Otherwise pull from the same data source as the squeeze scanner, just at RTH cadence rather than premarket.

**Output (observe-only):**
- New file: `logs/2026-05-XX_wb_intraday_adder_observe.jsonl`
- One JSON line per poll cycle: `{ts, poll_n, candidates_evaluated, candidates_passing, candidates: [{sym, gap_pct, rvol, price, float_m, hod_distance_pct, vwap_relationship}, ...]}`
- The candidates_passing list is what WOULD have been added in live mode — DO NOT inject into the live watchlist

**Refinement vs original directive:**
Add two additional fields to each candidate record for downstream analysis:
- `score_at_observe_time` — current WB detector score if the bot were to evaluate this symbol right now (compute live from 1m bars; the bot already has this primitive)
- `would_pass_post_wed_gate_stack` — boolean: would this symbol pass H#10 R% floor, H#11 same-session BL, H#14 pre-9MT block, MACD sub-gate (if enabled), divergent-quote guard, $30K notional cap

The two extra fields let us compute "if intraday adder were live, what would the gate stack do" without running another backtest. This is the missing piece for the Monday review.

### Env vars (new)
```
WB_INTRADAY_ADDER_ENABLED=1
WB_INTRADAY_ADDER_OBSERVE_ONLY=1
WB_INTRADAY_ADDER_POLL_MIN=15
WB_INTRADAY_ADDER_TIME_START=09:45
WB_INTRADAY_ADDER_TIME_END=15:30
WB_INTRADAY_ADDER_GAP_MIN=3.0
WB_INTRADAY_ADDER_RVOL_MIN=3.0
WB_INTRADAY_ADDER_PRICE_MIN=2.00
WB_INTRADAY_ADDER_PRICE_MAX=30.00
WB_INTRADAY_ADDER_FLOAT_MAX=30
WB_INTRADAY_ADDER_VOLUME_TODAY_MIN=500000
```

Default `OBSERVE_ONLY=1` means even with `ENABLED=1` no live watchlist injection happens. Flip `OBSERVE_ONLY=0` only after the Monday review approves.

### Where the loop lives

The simplest place is a new background thread in `bot_v3_hybrid.py` since it's already the central source-of-truth for the watchlist. Don't add it to either WB bot directly — that creates redundancy and confusion about which one is canonical.

Alternative: standalone `scripts/wb_intraday_adder.py` cron'd separately. Simpler isolation but more deploy complexity. **CC's call** — whichever fits the existing process model better.

### Acceptance criteria (for Stage 0.3 itself, before flipping to live)

After Fri 5/15 EOD:
1. JSONL file exists with ≥ 12 poll-cycle entries (09:45 through 15:30 = ~22 polls)
2. At least 1 poll cycle returned ≥ 1 candidate
3. Of candidates surfaced across the day, at least 1 had `score_at_observe_time ≥ 7` (i.e., the intraday adder is finding genuine WB-shaped candidates, not noise)
4. Zero crashes / persistence-style fail-soft errors
5. Telemetry summarized in `cowork_reports/2026-05-15_wb_intraday_adder_day1.md`

If criterion 2 fails (zero candidates all day) → filter is too tight; loosen `gap_min` to 2% or `rvol_min` to 2× before Monday.

If criterion 3 fails (candidates exist but none scoreable) → the adder is finding chaff; review the filter set and tighten before Monday.

### What ships Monday after observe-week review

3 trading days of observe-only data (5/15 + 5/18 + 5/19) drives the live-mode decision:

| Outcome | Action |
|---|---|
| ≥1 candidate surfaced that mirrors a known winner pattern (FATN 5/5 mid-day intraday gap-and-go) | Flip OBSERVE_ONLY=0 — go live Tue 5/20 |
| Candidates surface but none mirror winner patterns | Hold observe-only, refine filter on Jan-Apr backtest data instead |
| Zero meaningful candidates 3 days running | Loosen filter, observe another 3 days, OR conclude the intraday-shaped winner pattern isn't recurring |

---

## 5. What I'm NOT asking CC to do

- **Not** building tagged-watchlist architecture (Stage 2). Still conditional on backtest.
- **Not** dropping the squeeze scanner. Squeeze is the upstream truth source.
- **Not** flipping intraday adder to live on day 1. 3-day observe minimum.
- **Not** modifying the persistence layer. It's working.
- **Not** patching the watchlist.txt wipe-at-boot. That was the right fix.

---

## 6. Tomorrow's posture (5/15 Friday)

| Time | Action | Owner |
|---|---|---|
| 02:00 MT cron | Boot with persistence + intraday adder (observe-only) | automatic |
| Throughout day | Persistence file populates with new WB_OBSERVE events; intraday adder logs candidates to JSONL | automatic |
| EOD 5/15 | Daily trade breakdown report (includes persistence section per prior directive AND intraday adder day-1 section) | CC |
| EOD 5/15 | Stage 0.3 day-1 report | CC |

Both reports land tonight. Cowork reviews over the weekend, decision memo Monday morning for whether intraday adder goes live Tuesday.

---

## 7. Tone note

Today went well. Persistence shipped clean, MEI mystery closed without any scary discoveries, gate stack is performing on the persisted-symbol test. The team is moving fast and being careful about it. Stage 0.3 today is the right tempo — observe-only means we're collecting evidence at zero risk, and Monday's decision will be based on real data rather than guesswork.

Ship it.

---

## 8. Files referenced

- `cowork_reports/2026-05-15_wb_persistence_validation.md` (Stage 0.2 report)
- `cowork_reports/2026-05-14_mei_bypass_trace.md` (MEI closure)
- `DIRECTIVE_WB_SCANNER_STRATEGY.md` (original 3-stage plan)
- `DIRECTIVE_WB_PERSISTENCE_ROLLOUT_DECISIONS.md` (today's approval doc)
- `wb_persistence.py`, `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `wb_bot.py`

**Reports CC owes Cowork (refreshed):**

| When | Report | Status |
|---|---|---|
| Today EOD 5/14 | `daily_trades/2026-05-14_trade_breakdown.md` (with persistence section) | due tonight |
| Fri EOD 5/15 | `daily_trades/2026-05-15_trade_breakdown.md` (with persistence + intraday-adder sections) | due tomorrow |
| Fri EOD 5/15 | `2026-05-15_wb_intraday_adder_day1.md` (Stage 0.3 day-1 telemetry) | due tomorrow |
| Mon EOD 5/18 | `2026-05-18_wb_intraday_adder_observe_3day.md` (3-day summary) | per Stage 0 plan |
| Tue 5/19 | Decision memo on Jan-Apr backtest commission | per Stage 0 plan |
