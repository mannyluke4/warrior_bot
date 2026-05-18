# SLE Evening Fill Clarification — 2026-05-15

**Author:** Cowork reconciliation per DIRECTIVE_2026-05-18_ENGINE_FRAMEWORK_DEPLOY.md Track 1
**Scope:** Verify whether any **engine** (Setup B) SLE fill occurred in extended hours on Friday 2026-05-15 (after 16:00 ET / 14:00 MDT).
**Mode:** READ-ONLY reconciliation. Not Monday-blocking.

---

## Verdict — definitive: NO

**No engine SLE fill occurred in extended hours on 2026-05-15.** The engine's only SLE fill all day was at **08:32 ET (regular morning)**, closed within ~3 seconds for $-445.58, and that single trade accounts for the entire engine `daily_pnl=$-445.58, open_positions=0` shutdown line. The 19:55 ET `SESSION_END_FORCE_EXIT` fired against an already-flat book and closed nothing.

---

## Evidence

### Engine (Setup B) — `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-15_squeeze_bot.log`

The engine produced **exactly one** SLE order pair the entire session:

| Time (ET) | Event | Detail |
|-----------|-------|--------|
| 08:32:00.071 | `SLE ENTRY` | qty=7949, ibkr_signal=$6.29, stop=$5.90, R=$0.12, score=6.6, notional=$49,999 |
| 08:32:00.469 | `BROKER ORDER` (BUY) | 6391ec68... BUY 7949 SLE @ $6.35 (fallback no_quote) |
| 08:32:01.168 | `SLE FILL` | filled @ $6.3100 qty=7949 [PARABOLIC] |
| 08:32:02.639 | `SLE EXIT submitting` | reason=`sq_para_trail_exit` qty=7949 ref=$6.27 |
| 08:32:02.713 | `BROKER ORDER` (SELL) | 8bd0b0f8... SELL 7949 SLE @ $6.21 |
| 08:32:03.369 | `SLE CLOSED` | @ $6.2539 → **pnl=$-445.58, daily_pnl=$-445.58** |

After 08:32:03 the engine has **zero further SLE entries, fills, exits, or order submissions** of any kind on SLE — the next non-status engine events on SLE are routine "seed→live transition" book-keeping at 19:54 ET.

### Engine extended hours: fail-CLOSED state, no entries possible

From 16:15 ET onward the engine cycled through repeated `engine socket closed — fail-CLOSED, no new entries. Open positions: 0` / reconnect events (16:15, 16:23, 17:14, 17:23, 17:44 ET — five disconnect/reconnect cycles before 17:48). While in fail-CLOSED state the engine emits zero entries by design; "Open positions: 0" is logged on each disconnect.

The 19:55 force-exit fired:
> `2026-05-15T19:55:09.088432-04:00 🟧 SESSION_END_FORCE_EXIT triggered`

…but no SELL order, no CLOSED line, and no pnl delta follow. With `open_positions=0` already logged seconds earlier on the disconnect/reconnect cycles, the force-exit had nothing to flatten. The next P&L-impacting line is the 20:05 shutdown — still `daily_pnl=$-445.58` (unchanged from 08:32:03).

### Cross-check: engine has no other fills all day

Engine grep for `FILL` on 5/15 returns:
- 08:32:01 SLE FILL @ $6.31 (single hit, already itemized above)

No fills on ONDG (entries at 09:31, 09:34, 09:38 all timed out or BP_BLOCKed). No fills on any other symbol. The "single SLE fill" line in the audit is literally the only fill of the engine's whole 5/15 session.

### Setup A (main IBKR bot) for context — `logs/2026-05-15_daily.log`

The audit's mention of "6+ Setup A SLE chase-cap attempts in extended hours" is what I think the original brief mistook for an engine fill. Setup A's SLE timeline on 5/15:

| # | Time (ET) | Outcome | Detail |
|---|-----------|---------|--------|
| 1 | 08:32:00 | **FILL @ $6.1229** | qty=2491, score=10.0, two-piece exit (250sh bearish_engulf @ $6.12 −$1; 2241sh sq_target @ $6.33 +$469). **net +$468** |
| 2 | 09:19:06 | **FILL @ $7.0615** | qty=2132, score=5.3, sq_para_trail @ $6.94. **net −$247** |
| 3 | 10:46:00 | ENTRY signal → CHASE_TIMEOUT | mkt $6.39 > cap $6.21 (2.0% gate, score=7.0). No fill. |
| 4 | 16:17:15 | ENTRY signal → CHASE_TIMEOUT | mkt $5.90 > cap $5.27 (3.5% gate, score=11.0). No fill. |
| 5 | 16:25:36 | ENTRY signal → CHASE_TIMEOUT | mkt $5.97 > cap $5.27. No fill. |
| 6 | 17:16:38 | ENTRY signal → CHASE_TIMEOUT | mkt $6.09 > cap $5.27. No fill. |
| 7 | 17:25:46 | ENTRY signal → CHASE_TIMEOUT | mkt $5.82 > cap $5.27. No fill. |
| 8 | 17:46:16 | ENTRY signal → CHASE_TIMEOUT | mkt $5.88 > cap $5.27. No fill. |
| 9 | 17:50:14 | ENTRY signal → CHASE_TIMEOUT | mkt $5.93 > cap $5.27. No fill. |

Every entry #3 through #9 ended in `ORDER TIMEOUT: SLE market $X exceeds max chase $5.27 (3.5% above original $5.09, score=11.0) — giving up`. Zero `FILL: SLE` lines in the daily log after 09:19:10. Setup A `session_state/2026-05-15/risk.json` lists exactly 4 `closed_trades` (SLE 250sh −$1, SLE 2241sh +$469, LESL 2666sh −$533, SLE 2132sh −$247) with final `daily_pnl=-311.92` and `open_trades=[]`. No phantom evening trade.

Setup B-shaped subbot (`session_state_alpaca/`) is irrelevant: `WB_SQUEEZE_ENABLED=OFF` per its boot banner, `daily_pnl=$0.00`, zero entries the whole day.

---

## What the audit interpreted as an evening fill

The 5/16 audit's brief reportedly contained the line *"evening SLE FILLED on engine $5.61 held into 19:55 force-exit at $5.53."* That description is **not in any engine log**. The likely source of the confusion:

1. **Setup A SLE #4–#9 chase-cap attempts at 16:17–17:50 ET** produced six `🟩 ENTRY: SLE qty=2956 limit=$5.09 ... type=squeeze` lines in the main bot log. Skimming, those entry lines look like fills; in fact each is followed (sometimes minutes later in the log) by `ORDER TIMEOUT: SLE ... — giving up`. None became fills.
2. **The 19:55 ET `SESSION_END_FORCE_EXIT` line in the engine log** fires unconditionally at end-of-extended-hours, regardless of whether there's anything to flatten. With engine `open_positions=0` already established earlier in the evening's disconnect cycles, it closed nothing — but reading the log out of context, "force-exit triggered" can be misread as "force-exit closed a position."
3. The "$5.61 → $5.53" price pair doesn't match any actual engine or Setup A fill. SLE's 19:54 ET engine `seed→live transition` shows `seed_last_price=$5.5400`, which is approximately the $5.53 number; the $5.61 is presumably from a tick around that window. These are tick-cache prices, not order prices.

The audit's own §F.8 / §"Limitations" line correctly flagged the discrepancy and asked for confirmation. This report is that confirmation.

---

## Reconciliation of `daily_pnl=$-445.58`

The audit cited Setup B's 5/15 shutdown as `daily_pnl=$-445.58, open_positions=0`. That figure is **fully accounted for by the single 08:32 SLE round-trip** (`pnl=$-445.58` on the close at $6.2539 vs entry $6.31). The engine `daily_pnl` field did not move again all day. No evening fill happened; no evening P&L was suppressed or unrecorded.

---

## Recommendation — audit correction

1. **Strike** the "evening SLE FILLED on engine $5.61 → 19:55 force-exit at $5.53" detail from any working brief / handoff doc that still carries it. It never happened on either setup.
2. **Replace** with: *"Engine's only SLE fill 5/15 was the 08:32:01 morning round-trip (entry $6.31, sq_para_trail exit $6.2539, −$445.58). The 19:55 force-exit fired against an already-flat book."*
3. The audit's §F.8 hedge (*"Worth confirming"*) is now resolved — the audit body P&L tally stands as written; only that one prose line in §F.8 needs the note updated.
4. **Optional, low-priority:** add a per-symbol max-attempts-per-day soft cap (the audit's own action item §H.9, suggesting 3 attempts/ticker/day) to prevent the SLE 16:17–17:50 stack of 6 timeouts that contributed to the log-noise that triggered this whole reconciliation question.

---

## Files referenced

- `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-15_squeeze_bot.log` (engine, Setup B)
- `/Users/duffy/warrior_bot_v2/logs/2026-05-15_daily.log` (main IBKR, Setup A)
- `/Users/duffy/warrior_bot_v2/logs/2026-05-15_subbot_alpaca.log` (Alpaca subbot, squeeze OFF — irrelevant)
- `/Users/duffy/warrior_bot_v2/session_state/2026-05-15/risk.json` (Setup A: 4 closed trades, daily_pnl=$-311.92)
- `/Users/duffy/warrior_bot_v2/session_state/2026-05-15/open_trades.json` (Setup A: `[]`)
- `/Users/duffy/warrior_bot_v2/session_state_alpaca/2026-05-15/risk.json` (subbot: daily_pnl=$0)
- `/Users/duffy/warrior_bot_v2/cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md` §F.8 (original "worth confirming" hedge)

**Conclusion:** The audit's totals are correct; only the §F.8 prose line about an unconfirmed evening fill needs replacing with the morning-only finding. Not Monday-blocking.
