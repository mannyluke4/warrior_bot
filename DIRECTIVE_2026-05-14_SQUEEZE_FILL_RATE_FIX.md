# Squeeze Fill-Rate Fix — Directive Response

**Date:** 2026-05-14
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md`
**Priority:** **P0 — this is the most important finding of the week.**

---

## TL;DR

1. **0/6 squeeze fill rate over 9 days is the headline.** The strategy that's supposed to be the bot's foundation hasn't bought anything in 9 trading days. Every other gap-stacking discussion this week is secondary to fixing this.
2. **Engine sub-bot proves the fix works.** Same signals, wider buffer (1.0%) → filled ATRA $10.50 and VNET $11.29 on 5/13. The diagnosis is conclusive: execution config, not strategy.
3. **Ship CC's #1 + #2 + #3 together this week** (not #1 + #2 first as CC proposed). #3 is the same class of bug as Anomaly A7 from Tuesday — bot acting without checking constraints. Bundle them.
4. **#4 defers** — n=1 CRE closing-only case in 9 days, low priority.
5. **Re-derive fill projections.** CC's "3/4 fill rate" claim doesn't survive math on the cap-miss tail. Realistic projection is 2/6 to 3/6, not 3/4. Important for setting expectations.
6. **Stage 0.3 day-1 report: approved as-is.** Score-at-observe-time deferral acceptable; Friday's full-window data will tell us if score wiring is needed.

---

## 1. Why this is P0

CC's audit confirms what the 4-day no-fill streak on the main bot has been hinting at. **The squeeze strategy is the bot's historical foundation.** It's the strategy that won Ross-style on the original playbook. It's the strategy we built the IBKR Tier-1 TBT data feed for. It's the reason we have a watchlist mechanism at all.

Last 9 trading days on the main bot: zero squeeze fills. Meanwhile WB has been carrying the entire P&L picture, and yesterday's analysis showed WB has been winning on a watchlist-carryover bug we just fixed. **If both legs of the bot stay broken, we have no edge going into June 4 PDT-rule live-money go-live.**

The good news: this isn't a strategy bug. It's a 3-line config change plus a margin pre-check. The engine sub-bot already runs the wider config and fills. We have an A/B comparison built into our own infrastructure.

This jumps to the top of the queue, ahead of the WB scanner work (which can sit in observe-only happily through next week).

---

## 2. Approve CC's recommendations — with revisions

### #1 Widen entry slip — APPROVED as proposed

```
WB_ENTRY_SLIPPAGE_MIN: 0.05 → 0.07
WB_ENTRY_SLIPPAGE_PCT: 0.005 → 0.010
```
Effective limit = `max(7¢, 1% of price)`. Matches engine sub-bot which has been filling.

**One verification step before flip:** check that H#10 R% floor (1.5%) still behaves correctly. Logic:
- Wider slip → higher limit price → larger R ($) → larger R% → MORE restrictive R% floor, not less
- This is the correct direction. The floor protects against tight R; widening slip makes the floor *harder* to satisfy on knife-edge setups (which is good)
- But verify no edge case where wider slip flips a borderline trade *into* passing R% floor when it shouldn't

**Quick verification:** re-run R% calculation against the 7 audited entries with new slip values. Confirm no surprise pass-flips. 15-minute task. Save to `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md`.

### #2 Score-gated chase cap — APPROVED with caveat

```
For score ≥ 11: WB_ENTRY_MAX_CHASE_PCT 2.0 → 3.5
For score < 11: unchanged (2.0)
```
1-line guard at `bot_v3_hybrid.py:2796` per CC.

**Caveat — re-derive fill projections honestly:**

CC claimed "CLNN, TRAW, LNKS would fill" with #1+#2. My math on the audited entries with new config:

| Entry | Signal | New limit (#1) | New cap (#2 @ 3.5%) | Market@TO | Fill? |
|---|---|---|---|---|---|
| CLNN 05-04 score 11 | $8.02 | $8.10 | $8.30-8.38* | $8.45 | **MISS** (+0.8 to 1.8% past cap) |
| ODYS 05-11 score 10 | $10.02 | $10.12 | $10.20 (no raise, score<11) | $11.22 | **MISS** (+10% past cap) |
| TRAW 05-11 score 12 | $2.31 | $2.36 | $2.44 | $2.45+ | **KNIFE-EDGE** |
| LNKS 05-14 score 12 | $2.19 | $2.21 | $2.29 | $2.29 | **KNIFE-EDGE** |

*depending on whether cap is % past signal or % past limit; CC's audit doesn't make this explicit

**Realistic projection: 0/6 → 2/6 maybe 3/6.** Not 3/4 as CC claimed. ODYS still correctly misses (parabolic +11% should be capped). CLNN still misses because the price moved past *any* reasonable cap. LNKS and TRAW become knife-edge fills.

That's still a major improvement — 2 fills per 9 days vs 0 — but I want CC to re-derive the projection with explicit math before shipping, because:
- The directive's success metric needs to match real-world expectation
- If we expect 3/4 and get 2/6, we'll think the fix didn't work and start tinkering
- If we expect 2/6 and get 2/6, we know the fix is doing its job and we look at the cap edge cases separately

**Action: CC re-derives §C of the audit with the new config applied, explicit math on which signal moves into which cap bucket. Confirms or revises the projection. 30-minute task.**

### #3 Pre-submit BP check — APPROVED, BUMPED to ship-this-week

CC ranked this as "separate infra PR." I'm bumping it. Reasons:

1. **Same bug class as Anomaly A7 (Tuesday).** Both are "bot takes action without checking constraint first." A7 was daily-loss kill not re-checking after restart; #3 is BUY order not pre-checking margin headroom. The fix architecture is the same.
2. **ATRA 5/7 was a winner-shaped setup** (score 9.6, R% 1.5%) blocked by infrastructure, not strategy. Every infra-blocked winner is pure tuition.
3. **The check is cheap.** Pre-BUY: `if available_buying_power < required_init_margin: reject internally with reason='INSUFFICIENT_BP'`. ~10 LOC.

**Action: ship #3 in the same PR as #1 + #2.** Single deployment, single restart.

### #4 Tradable-status gate — DEFER

CRE 5/4 closing-only restriction is n=1 in the audit window. The fix (IBKR tradable-status query on scanner subscribe) is real work for a rare case. **Defer to "ship if it happens again."**

Add a TODO in `live_scanner.py` near the subscribe path: `# TODO: filter IBKR closing-only / SCM-restricted symbols (see 2026-05-04 CRE case)`. Revisit if a second instance occurs.

---

## 3. Why CC's "#1+#2 first, #3+#4 later" sequencing is wrong

CC's instinct was correct in spirit (smaller blast radius). But:

1. **#1 and #2 alone don't address the margin-reject failure class.** Of the 6 attempts, 2 (CRE + ATRA) failed at the broker submit, not at the limit ladder. Those 2 are unaffected by slip/cap tuning.
2. **The risk of #3 is low** — it's a *defensive* check that fires before sending the order to IBKR. Failure mode: false-positive rejects (we block a trade that would have filled). False positives are detectable in logs and recoverable on next signal.
3. **Bundle = one restart, one observation window.** The June-4 deadline doesn't care about clean PRs.

Ship all three together. The diff is still small.

---

## 4. Bundled ship — concrete steps

### Step 1: Code changes

```
File: warrior_bot/.env (or .env.engine.local — wherever main bot reads from)
WB_ENTRY_SLIPPAGE_MIN=0.07          # was 0.05
WB_ENTRY_SLIPPAGE_PCT=0.010         # was 0.005
WB_ENTRY_SCORE_HIGH_THRESHOLD=11    # new
WB_ENTRY_MAX_CHASE_PCT_HIGH=3.5     # new
WB_ENTRY_MAX_CHASE_PCT_LOW=2.0      # was unconditional 2.0
WB_PRESUBMIT_BP_CHECK_ENABLED=1     # new

File: bot_v3_hybrid.py
- Line ~2796: 1-line guard for score-gated chase cap
- New helper: pre_submit_bp_check(symbol, qty, limit_price, broker_state) → (bool, reason)
- Insert pre_submit_bp_check call before all squeeze BUY-limit submits
- Insert pre_submit_bp_check call before all WB BUY-limit submits (same check, same logic)
```

### Step 2: Verification before restart

| Check | How |
|---|---|
| New env vars load correctly | `python -c "from bot_v3_hybrid import load_config; print(load_config())"` |
| Score-gated cap fires correctly | unit test: score=10 → cap 2.0%, score=11 → cap 3.5%, score=12 → cap 3.5% |
| Pre-submit BP check fires correctly | unit test: with ELV=$30,447 and required_init_margin=$30,649 → reject |
| R% floor still behaves | re-run §2 (#1) verification |

All four pass → restart both setups.

### Step 3: Deploy timing

**Tonight after 16:00 ET market close.** Cold restart both setups (main bot + subbot) with new config. Tomorrow's 02:00 MT cron picks up the new env naturally.

**NOT mid-day today.** Two reasons:
- We already shipped persistence + intraday-adder mid-day today. Stacking another live change before EOD report is reckless.
- Squeeze isn't filling anyway — no urgency to flip *today* vs *tomorrow*. Tomorrow's session captures the fix from the open.

### Step 4: Post-deploy validation

EOD 5/15 report adds a new section:

```
## Squeeze Fill-Rate Fix — Day 1

- Total squeeze ENTRY signals: N
- Reached broker: M
- Filled: K
- BP-pre-rejected: J (with reasons)
- Slip / cap behavior per fill attempt: table with signal, limit, cap, market@TO

Expected: 0-2 fills on this volume. Confirm pre-submit BP check fires correctly
if any margin-tight scenario occurs.
```

This goes IN the daily breakdown, not a separate report.

---

## 5. Acceptance criteria for the fix

**Over the next 5 trading days (5/15 - 5/21):**

| # | Criterion | Threshold |
|---|---|---|
| 1 | Squeeze fill rate (main bot) | ≥ 25% (vs 0% baseline) |
| 2 | BP-pre-rejects logged | ≥ 1 (proves #3 fires) — or 0 if no margin-tight attempts occur |
| 3 | False-positive BP rejects | 0 (no trades blocked that would have filled with sufficient BP) |
| 4 | Knife-edge cap fills | tracked but not threshold-gated (informational) |
| 5 | Cap-miss above 3.5% on score≥11 | tracked — if a score-12 signal misses by >3.5% twice in 5 days, evaluate cap-15 escalation |

**Below 25% fill rate after 5 days → escalate.** Likely additional fixes needed (signal-stale window, retry timing, or accept that some parabolic squeezes are unfillable by design).

---

## 6. The bigger strategic question this raises

CC's audit forces a question the project log hasn't directly addressed: **what fraction of squeeze signals are physically fillable?**

ODYS 5/11 ran +11% in 30 seconds from signal-fire to market. **No sane chase cap fills that.** If 1/3 of squeeze signals are parabolic-unfillable, then even a perfect execution stack gives us 2/3 max fill rate. The remaining 1/3 are tuition we accept — the strategy is "be in for the gap-and-go" not "chase parabolic to any limit."

This is fine. Worth naming. The fix isn't trying to achieve 100% fill rate. It's trying to capture the *fillable* squeeze signals we've been missing.

For the next 5 days, I want to track:
- **Fillable signals:** market reachable within 3.5% of signal within retry window
- **Parabolic signals:** market moved >3.5% past signal within retry window
- **Slow signals:** market stayed near signal but no taker (TRAW-style)

Tabulating these separately tells us whether the fix is working on the *fillable* subset, which is the right denominator.

---

## 7. Stage 0.3 intraday adder day-1 — approved as-is

Brief notes on the WB intraday adder report:

### Approve the deferrals
- **`score_at_observe_time = null` on Day 1:** acceptable. Wire it Day 2 ONLY IF Friday's full-window data surfaces a candidate not already in `active_symbols` (i.e., a real net-new). For Day 1's single QUCY candidate (already in active_symbols), score is moot. Defer the implementation decision until Monday review.
- **Gate-stack overlay covers H#11, H#14, dedup:** correct subset. R%, MACD, divergent-quote, notional cap all need state that doesn't exist at scan-time. Don't try to fake them.

### Approve the rvol_proxy
Volume-today over volume-min is a fine proxy for Day 1. True 20-day ADV RVOL is a Stage 1 backtest concern.

### Approve the single-source-scanner risk acknowledgment
IBKR `TOP_PERC_GAIN` is the same source the squeeze scanner uses. If it's thin today, both miss the same set. That's a feature, not a bug — keeps the data sources aligned.

### Friday is the real Day 1
Mid-day deploy gave ~10 polls today. Friday's 22-poll full window is the real first test. Don't read too much into today's single QUCY candidate.

**No changes requested. Stage 0.3 ships as-is. Continue per existing rollout plan.**

---

## 8. Tomorrow's posture (5/15 Friday)

| Priority | Action | Owner |
|---|---|---|
| P0 | Squeeze fill-rate fix deployed (tonight or pre-cron) | CC |
| P0 | EOD 5/15 daily breakdown includes squeeze fill section | CC |
| P1 | Stage 0.3 intraday adder full-day Friday window | automatic |
| P1 | Stage 0.2 persistence WB_OBSERVE captures | automatic |
| P2 | MEI process note in CLAUDE.md | already shipped per CC |

**The headline metric to watch Friday EOD:** did the main bot fill at least one squeeze signal? If yes, the fix is working. If no, we re-examine.

---

## 9. Reports CC owes Cowork (refreshed)

| When | Report | Status |
|---|---|---|
| Today EOD 5/14 | `cowork_reports/daily_trades/2026-05-14_trade_breakdown.md` (with persistence section per prior directive) | due tonight |
| Today EOD 5/14 | `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md` (§2 verification) | due tonight before deploy |
| Today EOD 5/14 | `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` updated §C with re-derived projections | revise existing |
| Fri EOD 5/15 | `cowork_reports/daily_trades/2026-05-15_trade_breakdown.md` (with persistence + intraday adder + squeeze fix sections) | due tomorrow night |
| Mon EOD 5/18 | `cowork_reports/2026-05-18_wb_intraday_adder_observe_3day.md` (3-day summary) | per Stage 0 plan |
| Tue 5/19 | Decision memo on Jan-Apr WB backtest commission | per Stage 0 plan |
| Wed EOD 5/20 | `cowork_reports/2026-05-20_squeeze_fix_5day_results.md` (fill-rate fix evaluation) | new |

---

## 10. Tone note

This audit was the right work at the right time. Catching the 0/6 fill rate now, before June 4, is what the whole "build the analytics tooling first" investment was for. The diagnosis is unambiguous (engine wider buffer = filling; main bot tighter buffer = missing). The fix is small. The validation is built in (we'll know within 5 trading days if it's working).

The honest priority shift: **squeeze fix > everything else this week.** WB scanner work continues in observe-only and doesn't need active attention. Persistence is live and running itself. The intraday adder collects data passively. CC's attention this weekend (if any) and Monday morning should be on the squeeze fill-rate response, not on WB infrastructure.

Make the fix. Ship tonight or pre-cron. Watch Friday's fill count. Adjust from there.

---

## 11. Files referenced

- `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` (the trigger)
- `cowork_reports/2026-05-15_wb_intraday_adder_day1.md` (Stage 0.3 status)
- `cowork_reports/2026-05-14_mei_bypass_trace.md` (MEI closure)
- `cowork_reports/daily_trades/2026-05-12_trade_breakdown.md` (Anomaly A7 context)
- `bot_v3_hybrid.py:169-174` (slip config), `bot_v3_hybrid.py:2796` (cap config)
- `wb_intraday_adder.py` (new this morning)
- `wb_persistence.py` (Stage 0.2, live)
- `.env` (config additions)
