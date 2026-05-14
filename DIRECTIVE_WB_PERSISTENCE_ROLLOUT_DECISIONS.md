# WB Persistence Rollout Decisions

**Date:** 2026-05-14
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/2026-05-15_wb_persistence_validation.md` (Stage 0.2 implementation report)
**Status:** Implementation approved. Rolling out per below.

---

## TL;DR

1. **Approve implementation.** Code is clean, matches directive intent. One-file design over my original two-file spec is correct — simpler with same behavior.
2. **Rollout: restart mid-day TODAY with the seeded ATRA/SST file kept.** Validates the READ path live, the gate stack is the safety net.
3. **Acceptance criterion for the restart:** see §3 below.
4. **No code changes requested.** Ship as-is.

---

## 1. Implementation review — approved

Three things worth calling out:

### A. One-file design beats my two-file spec
My §0.3 originally specified `wb_observed_today.txt` rolling into `wb_persistence.txt` at EOD. CC collapsed these into one file with calendar-day pruning on every write. **This is better.** The two-file design has more moving parts (EOD rollover process, transient state, rollover-failure modes) and adds zero functional benefit. The N-day rolling prune on write achieves identical semantics with fewer failure surfaces. **Keep as-is.**

### B. Best-effort error handling is the right call
The persistence module swallows all IO exceptions and logs them. Any persistence failure could otherwise crash the trading loop, and persistence is auxiliary — losing a few WB_OBSERVE records is acceptable; killing the bot is not. **Correct design.**

### C. Bot_v3_hybrid as the single injection point
Putting the READ-side injection in `poll_watchlist` rather than in each WB bot independently is the right architectural call. It fans out to both Setup A subbot and Setup B engine wb_bot via `session_state/<today>/watchlist.json` with one touchpoint. **Cleaner than my original spec.**

### D. Squeeze running on persisted symbols is harmless
CC's analysis is correct: squeeze's `WB_SQ_VOL_MULT=2.5×` and `WB_SQ_MIN_BAR_VOL=50000` floors won't fire on low-volume WB-persisted symbols. No bypass tag needed. **Accept.**

---

## 2. Decision: restart mid-day TODAY with seeded ATRA/SST kept

**Why mid-day restart and not cron-tomorrow:**

The morning report shows the squeeze filter passed nothing — meaning if we wait for cron tomorrow, the only thing being tested is whether the persistence file (which will accumulate whatever WB_OBSERVE happens today, currently zero because there's nothing on the watchlist to observe) feeds into tomorrow's boot. **We'd test the READ path against an empty file.** That's not validation.

The seeded file (ATRA, SST) is exactly the candidate shape this layer exists for. Restarting mid-day means:
- The READ-side injection logs fire under live conditions (`🧠 WB_PERSIST: 2 symbols carried...`)
- ATRA and SST get subscribed and the WB detector runs on them
- The gate stack (R% floor, same-session BL, pre-9MT block, divergent-quote guard, $30K notional cap) decides whether anything actually fills

The recent ATRA/SST history (ATRA 5/11 ×3 losers, SST 5/12 loser) is exactly what those gates are supposed to handle:
- ATRA at $9.49 5/11 was R% 1.43% (under 1.5% floor) → H#10 would block any modern arm
- SST 5/12 11:20 fill was R% 2.53% (clean tape loser) → gate stack does NOT catch this one; this is "tuition" tape

So a live restart with seeded names IS the most aggressive test of the whole stack: persistence layer + gates + sizing all running together on candidates the system would not have surfaced today via the scanner.

**Risk acceptance:** worst plausible case is SST/ATRA arms produce a clean -1R tuition loss apiece in the $700-900 range under the $30K notional cap. That's bounded; we've taken bigger paper-day losses this week and learned more from them. **The risk is bounded and the validation value is high.**

---

## 3. Acceptance criteria — what defines "validation passed"

After mid-day restart today, by EOD 5/14:

| # | Criterion | How to verify |
|---|---|---|
| 1 | `🧠 WB_PERSIST` log line appears within 60s of restart | grep `daily.log` for `WB_PERSIST` |
| 2 | ATRA and SST appear in `state.active_symbols` | confirm in poll_watchlist log output |
| 3 | `session_state/2026-05-14/watchlist.json` contains ATRA, SST | inspect file post-poll |
| 4 | Subbot + engine wb_bot both see ATRA/SST and run WB detector | grep both logs for `WB_OBSERVE.*ATRA` or `WB_OBSERVE.*SST` |
| 5 | Any WB ARM on ATRA/SST is correctly handled by the gate stack | trace gate verdicts in log if ARM fires |
| 6 | New WB_OBSERVE today writes to `wb_persistence.txt` (WRITE side) | inspect file at EOD, look for today's date entries |
| 7 | If ATRA or SST trades, post-trade R-multiple and slippage match expectations from prior sessions | per-trade trace in EOD report |

**Acceptance: 5 of 7.** Criteria 1-4 are required (they validate the core layer). Criterion 6 is required (validates the WRITE side). Criterion 5 is conditional on whether ARM fires. Criterion 7 is conditional on whether a fill happens.

If any of 1-4 or 6 fail, persistence is rolled back via `WB_PERSIST_ENABLED=0` and we re-investigate before tomorrow's cron.

---

## 4. EOD report addition for today

In tonight's `cowork_reports/daily_trades/2026-05-14_trade_breakdown.md`, add a new section:

```
## WB Persistence Layer — First Live Day

- Restart time: <ts>
- Symbols injected via persistence: [list]
- Acceptance criteria pass/fail: [table from §3 above]
- New WB_OBSERVE events written today: count + list
- Any persisted-symbol fills: trade rows with gate verdict trace
```

This is one section, not a full report. It folds into the daily-breakdown contract.

---

## 5. Pre-restart sanity check (do this FIRST)

Before restarting today:

1. `cat ~/warrior_bot_v2/wb_persistence.txt` — confirm only ATRA, SST seeded (no surprises)
2. `python -c "import wb_persistence; print(wb_persistence.debug_state())"` — confirm module reads file correctly, returns ATRA/SST in `active_today`
3. Check Alpaca account state for both PA3LXGIPGG8B (subbot) and PA3VP0LB4OID (main) — confirm zero open positions
4. Confirm `WB_PERSIST_ENABLED=1` and `WB_PERSIST_SESSIONS=3` in `.env` AND `.env.engine.local`
5. Confirm `WB_PERSIST_FILE` env var override is correct in engine config

If all 5 check out → restart bots (both setups).

If anything looks off → DO NOT restart; flip `WB_PERSIST_ENABLED=0` and wait for tomorrow's cron with whatever debugging is needed.

---

## 6. On the MEI 05-13 trace (parallel work)

CC's report mentions the MEI trace is running async. **No rush — MEI trace is more important than persistence rollout speed.** Once that report lands:

- If MEI came via a known/documented code path → close the loop in the directive log, move on
- If MEI came via an undocumented bypass → halt Stage 0.3 (intraday adder) until we understand it; the bypass might already be doing the work we're about to build
- If MEI came via a bug → fix the bug or formalize the path; persistence + intraday adder still ship regardless

The MEI trace doesn't block the persistence rollout. They're independent.

---

## 7. Tomorrow's posture (5/15 Friday)

Assuming today's mid-day restart validates:

1. **02:00 MT cron boots normally with persistence ON.** Whatever WB_OBSERVE events accumulated 5/14 will be in `wb_persistence.txt`.
2. **Scanner runs as usual.** If it surfaces a fresh watchlist, those symbols PLUS persisted ones are subscribed.
3. **Stage 0.3 intraday adder lands by EOD 5/15** (observe-only). Per directive §0.3.
4. **EOD report includes the persistence section per §4 above.**

Assuming today's restart fails criteria → tomorrow's cron boots with `WB_PERSIST_ENABLED=0`, we debug, no Stage 0.3 lands until persistence is solid.

---

## 8. Updated reports CC owes

| When | Report | Status |
|---|---|---|
| Today EOD 5/14 | `cowork_reports/daily_trades/2026-05-14_trade_breakdown.md` (with persistence section per §4) | new |
| Today/Thu PM 5/14 | `cowork_reports/2026-05-15_mei_bypass_trace.md` | in progress |
| Fri EOD 5/15 | Stage 0.3 intraday adder observe-only ships + first day of data | per directive |
| Mon EOD 5/18 | 3-day observe summary of intraday adder | per directive |
| Tue 5/19 | Decision memo on commissioning Jan-Apr backtest | per directive |

---

## 9. Tone note

This is a clean, well-scoped, well-tested implementation. The decisions to collapse two-file → one-file, to centralize injection in `poll_watchlist`, and to make persistence best-effort-error-swallowing are all upgrades over my original spec. Approve as-is, ship today.

The acceptance criteria above are deliberately specific so we can declare "validation passed" or "rollback now" without ambiguity. If something subtle breaks today, we want to know within 60 seconds of the restart, not at 18:00 ET when we're reading the daily report.
