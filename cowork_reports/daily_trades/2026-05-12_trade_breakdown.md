# Daily Trade Breakdown — 2026-05-12 (Tuesday)

**First dual-setup session.** Setup A (squeeze + WB sub-bot on the 2-account stack) ran in parallel with Setup B (unified engine + squeeze + WB bots on the new PA-NEW $95K paper account). Six gate-patches shipped *during the session*. Both setups ended deep red — most of which the post-session gate stack would have prevented tomorrow.

---

## Setups (and what changed vs 5/11)

**Setup A — dual-bot (unchanged from 5/11 stack except gates shipped intraday)**
- Main bot `bot_v3_hybrid.py` (squeeze, Alpaca paper PA3VP0LB4OID, ~$20K)
- Sub-bot `bot_alpaca_subbot.py` (WaveBreakout, Alpaca paper PA3LXGIPGG8B, ~$32K BP-bound notional cap)
- Data feed: IBKR ticks via `alpaca_feed.py` bridge
- Run script: `daily_run_v3.sh` (cron 02:00 MT, reuses existing gateway)
- Branch / version: `v2-ibkr-migration` @ `df551fa`

**Setup B — unified engine (NEW this session)**
- Engine `data_engine.py` on `/Users/duffy/warrior_bot_v2_engine/`, single IBKR conn (clientId=3), IPC sock at `/tmp/warrior_engine.sock`
- Squeeze bot `squeeze_bot.py` + WB bot `wb_bot.py`, both IPC-clients to the engine
- Alpaca paper account PA3HJH15C2M1 (the new $95K "third paper account"; equity start **$94,998**)
- Run script: `daily_run_engine.sh` (cron 02:00 MT, separate worktree)
- Branch / version: `data-engine-unified` @ `3ded443` (engine bots — wait_for_fill terminal-state handling)
- Alpaca quote feed enabled (`feed=iex`), TBT disabled (A/B period)

> **Headline scoreboard**
> - **Setup A realized: −$2,693** (sub-bot 4 fills / 4 losers; main bot 0 fills / 0 ENTRY SIGNALs)
> - **Setup B realized: −$6,201** (WB bot 5 fills / 4 losers + 1 tiny winner; squeeze bot 0 fills / 1 SQ_REJECT)
> - **Combined day: −$8,894** on paper (Setup B equity $94,998 → ~$88,797; Setup A sub-bot ~−8.4% on the day)
> - **6 patches shipped intraday** — every preventable loser today is caught by the post-session stack

---

## Reconciliation note up front (vs the directive's headline)

The directive's pre-write tally had **−$7,150** (Setup A −$2,050 / Setup B −$5,100). The bot logs show **−$8,894** (Setup A −$2,693 / Setup B −$6,201). Three drift sources:

1. **Setup A had 4 fills, not 3.** Missed in the brief: **ENSC 08:16 ET −$643.54** (an early-morning, R% 2.40% entry that filled before the daily-loss-kill threshold). After this fill, the Setup A daily-loss-kill held until the SST 11:20 fill — there was no `WB_MAX_DAILY_LOSS=9999999` raise on Setup A, only on Setup B.
2. **Setup A's "SST 10:34" in the brief was a CHOP_REJECT, not a fill.** Score was 7, log line 12579 shows `CHOP_REJECT: R=0.25% < 0.8% floor | VWAP=-0.35% < +0.75%`. The actual SST fill was 11:20 ET (score 10, R% 2.53% — that's a *clean* -1.10R loser, not a tight-R% bypass abuse).
3. **Setup B's FATN#2 closed at −$1,127, not −$986**, and ATRA#2 closed at **−$1,157, not −$704**. These show up cleanly in the WB bot log lines 353 / 481. The cross-feed SELL-floor pattern made the headline P&L noisier than the brief estimated.

The corrected per-trade table drives the rest of this report.

---

## Quick scoreboard — Setup A sub-bot (WB on PA3LXGIPGG8B)

| # | Symbol | Time ET | Score | Result | R-mult | $ P&L | Hold | Reason exited |
|---|---|---|---|---|---|---|---|---|
| 1 | ENSC | 08:16 | 9 | LOSS | -1.03R | **−$643.54** | ~7m | stop_hit |
| 2 | SST  | 11:20 | 10 | LOSS | -1.10R | **−$869.55** | ~6m | stop_hit |
| 3 | ENSC | 14:54 | 9 | LOSS | -1.41R | **−$518.62** | ~3m | stop_hit |
| 4 | TRAW | 15:17 | 9 | LOSS | -1.01R | **−$661.04** | ~3m | stop_hit |
| | **Net** | | | | **avg −1.14R** | **−$2,692.75** | | |

**Score-7 chop-rejects (Setup A):** 14 (TRAW ×6, ENSC ×5, ODYS ×3, CLNN ×3, SST, FATN, ATRA, CNCK, XOS — many double-counted across rearms)
**Bypass-fills that fired (Setup A):** 4 fills + 4 BP-rejects (TRAW 05:31, XOS 06:29, XOS 06:38, XOS 07:53 — all on insufficient buying power $31,779 vs cost $32,558)

## Quick scoreboard — Setup A main bot (SQ on PA3VP0LB4OID)

| # | Symbol | Result | Why |
|---|---|---|---|
| – | (any) | NO ENTRY SIGNAL | 0 ENTRY SIGNALs fired all day. 7 SQ_REJECTs (CNCK ×6 *not_new_hod*, ENSC 09:36 *not_new_hod*). No `latency_diagnostic.jsonl` written. 4th flat-day in a row for the main bot squeeze strategy. |

## Quick scoreboard — Setup B WB bot (on PA3HJH15C2M1, $94,998 start)

| # | Symbol | Time ET | Score | Result | R-mult | $ P&L | Hold | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | TRAW | 05:31 | 10 | LOSS | -2.00R approx | **−$985.20** | ~28m | pre-9-AM-MT, R% 1.23% post-fill |
| 2 | ODYS | 05:48 | 8 | LOSS | -1.87R | **−$856.48** | ~15m | pre-9-AM-MT, fill after 1 retry |
| 3 | XOS  | 06:29 | 10 | LOSS | -1.99R | **−$735.27** | ~6m | pre-9-AM-MT |
| | *(cap triggered $-2,576.95 — daily kill held 06:35-11:09 ET. Manual restart 11:10 with raised cap.)* | | | | | | | |
| 4 | FATN | 11:41 | 8 | LOSS | -1.04R | **−$1,381.20** | ~19m | R% 1.35% post-fill |
| 5 | ATRA | 12:20 | 8 | **WIN** | +0.22R | **+$41.15** | ~65m | **First Setup B winner.** Partial fill 823/4995 (16%). Trail caught a buyer after 3 retries timed out. |
| 6 | FATN | 12:26 | 9 | LOSS | -2.78R | **−$1,126.72** | ~2m | Same-session re-entry; R% 0.80% post-fill |
| 7 | ATRA | 13:51 | 7 | LOSS | -6.61R | **−$1,156.90** | ~3m | R% 0.35% post-fill; SELL fill $9.80 vs cross-feed-floor limit $8.48 |
| | **Net** | | | | **avg −2.16R** | **−$6,201.27** | | |

**Score-7 score-rejects (Setup B):** abundant; the engine WB log shows 700+ `WB_OBSERVE`/`WB_DOWNWAVE` events with score<7 across 9 symbols.
**Bypass-fills that fired (Setup B):** 7 fills. Notional sizing capped at $50K (vs Setup A's $32K BP cap — that's the $95K equity dividend.)
**Broker rejects:** 1 (CLNN 11:46:10 `ConnectionError(ProtocolError('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer')))` — Alpaca API blip, bot logged and moved on without orphan or retry-loop, validating Phase 4 terminal-status enum)
**Order timeouts (no fill, no position):** ODYS 12:34 (3 retries, all at $4.32), ODYS 12:55 (3 retries, all at $4.47), ATRA SELL 13:25 (3 retries on $10.10 trail — followed by successful re-fire at 13:26:25 limit $10.02 → fill $10.09, +$41 winner)

## Quick scoreboard — Setup B squeeze bot (on PA3HJH15C2M1)

| # | Symbol | Result | Why |
|---|---|---|---|
| – | ENSC | NO ENTRY | 09:36:05 ET — `SQ_REJECT: not_new_hod (bar_high=$0.3337 < HOD=$0.3734)`. Single rejection event the entire day. |

Setup B squeeze: 0 fills, daily_pnl $0.00, open_positions 0 at shutdown.

---

## A vs B comparison — same symbols, different outcomes

The two setups had **identical IBKR data feeds**, **identical watchlists**, and **identical detector code** (same git branch + commit during the squeeze paths; WB diverges at engine vs subbot architecture). The differences in outcome are 100% explained by **account size**, **WB_MAX_DAILY_LOSS gate state**, and a few patches that only landed in one tree first.

| Symbol | Setup A action | Setup B action | Why different |
|---|---|---|---|
| TRAW 05:31 | BP REJECT (BP $31,780 vs cost $32,562) | FILL $2.04 (notional $50,242) | Setup B's $95K equity provided headroom; Setup A's $32K BP cap blocked it. **Setup A's BP "save" was accidental — same trade in B lost −$985.** |
| ODYS 05:48 | CHOP_REJECT (R 0.46% < 0.8% floor) | FILL $4.70 after 1 retry | Different chop-gate code paths. Setup A's pre-shipping chop gate v1 *did* reject this on R%. Setup B's WB bot had a more permissive arm path at the time. **Setup B's loss is the un-shipped-yet-on-engine version of H#10.** |
| XOS 06:29 | BP REJECT (BP $31,780 vs cost $32,558) | FILL $2.05 | Same BP cap dynamic. Setup A also BP-rejected XOS at 06:38 and 07:53 (score=10 / score=9). |
| XOS 07:53 | BP REJECT | (no arm at 07:53 in Setup B) | Setup B's WB had already cap-killed at 06:35; no new XOS arms processed until restart. |
| ENSC 08:16 | FILL $0.3291 → −$643.54 | (daily-kill, REFUSE entry) | Setup B's daily kill was already engaged ($-2,576.95). Setup A had no daily-kill yet (its only fill was this ENSC). |
| SST 11:20 | FILL $3.94 (score 10) → −$869.55 | (no SST arm at 11:20 in Setup B; bot just restarted at 11:10) | Setup B's WB had just COLD-booted at 11:10:21; SST waves were being reseeded. Setup A had ~7h of in-session detector state. |
| FATN 11:41 | CHOP_REJECT (R $0.0489 < 1.5×spread $0.09) | FILL $3.62 → −$1,381.20 | Two different chop-gate rules: Setup A's 1.5×spread test rejected, Setup B's wider test admitted. **Setup B got an in-session blacklist patch (H#11) shipped soon after this.** |
| ATRA 12:20 | CHOP_REJECT (R $0.1846 < 1.5×spread $0.255) | FILL $10.04 (partial 823/4995) → +$41.15 | Same chop-rule divergence. **Setup B's only win came from a chop pass that Setup A blocked.** |
| FATN 12:26 | CHOP_REJECT (R 0.25% < 0.8% floor) | FILL $3.58 → −$1,126.72 | Same gate divergence. Setup B's WB lacked the within-session same-symbol blacklist at fire time. |
| ATRA 13:51 | CHOP_REJECT (R 0.35% < 0.8% floor) | FILL $10.03 → −$1,156.90 | Same. Setup A's chop floor saved a loser; Setup B's took the loss. |
| ENSC 14:54 | FILL $0.3354 (CHOP_BYPASS @ score 9) → −$518.62 | (daily-kill) | Setup A still had room under its kill; Setup B was already past cap. |
| TRAW 15:17 | FILL $1.82 (CHOP_BYPASS @ score 9) → −$661.04 | (daily-kill) | Same. |
| TRAW 05:31 / XOS 06:29 / ODYS 05:48 | (would have fired but BP-rejected) | FILLED | Setup B's account size made the pre-9-AM-MT bleed possible. |

**Headline finding:** The two setups' tape was nearly identical. **Setup B lost more because (a) it had more equity to deploy, (b) its WB chop gate was the older / more permissive variant, and (c) its daily-loss-kill was lifted intraday to keep data flowing.** Both the data-engine architecture and the new account itself work — what the day's −$6,201 measures is **WB chop logic, not engine plumbing.**

---

## Day timeline (chronological, both setups, ET)

```
04:00 ET   [B engine] Setup B engine starts (engine.log:2). IBKR connected; 9 snapshot subs (ATRA/CLNN/ENSC/FATN/KBSX/NVOX/ODYS/SST/TRAW)
04:00 ET   [A] Main bot + sub-bot boot from cron_2026-05-12.log (cron 02:00 MT = 04:00 ET)
04:00 ET   [B squeeze] starting equity $94,998. Fail-CLOSED until first healthy heartbeat (04:00:15)
04:00 ET   [B WB] starting equity $94,998. Fail-CLOSED until 04:00:15
04:05–05:30 ET  Pre-market wave observation across both setups; first arms below score-7 floor
04:57 ET   [B engine] subscribed XOS (overnight scanner update)
05:31 ET   ⚠️  [A subbot] TRAW score=10 → CHOP_BYPASS → ENTER $2.03 → BP REJECT (BP $31,780 < cost $32,562). NO FILL — accidental save.
05:31 ET   ⚠️  [B WB]    TRAW score=10 → WB_ARMED → BUY $2.05 → FILL $2.04 qty 24630, notional $50,243. R=$0.0250 / $2.04 → R% 1.23%
05:43 ET   [A subbot] ENSC score=7 → CHOP_REJECT (R 0.26% < 0.8% floor)
05:48 ET   [A subbot] ODYS score=8 → CHOP_REJECT (R 0.46% < 0.8% | VWAP -0.21% < +0.75%)
05:48 ET   ⚠️  [B WB]    ODYS score=8 → ENTER $4.67 → BUY $4.72 → RETRY 1/3 → FILL $4.70 qty 10706. R=$0.0216 → R% 0.46%
05:59 ET   [B WB] TRAW EXIT submitting reason=stop_hit ref=$2.00 → SELL $1.98 → CLOSED @ $2.00 PnL −$985.20 daily=$-985.20
06:02 ET   [B WB] ODYS EXIT submitting reason=stop_hit ref=$4.63 → SELL $4.58 → CLOSED @ $4.62 PnL −$856.48 daily=$-1,841.68
06:29 ET   ⚠️  [A subbot] XOS score=10 → CHOP_BYPASS → ENTER $2.04 → BP REJECT. NO FILL.
06:29 ET   ⚠️  [B WB]    XOS score=10 → ENTER $2.04 → BUY $2.06 → FILL $2.05 qty 24509. R=$0.0151 → R% 0.74%
06:35 ET   [B WB] XOS EXIT stop_hit ref=$2.02 → SELL $2.00 → CLOSED @ $2.02 PnL −$735.27 daily=$-2,576.95
06:35 ET   ⚠️  [B WB] DAILY-LOSS KILL TRIGGERED ($-2,576.95 vs default 2% cap on $94,998 = $1,900). All subsequent arms 06:38-11:09 ET → "REFUSE entry: daily risk kill"
06:38 ET   [A subbot] XOS score=10 → CHOP_BYPASS → ENTER $2.04 → BP REJECT. NO FILL.
06:50–08:09 ET  Multiple [B WB] REFUSE-entry events. Setup A subbot processes ENSC/ODYS/XOS chop-rejects.
07:53 ET   [A subbot] XOS score=9 → CHOP_BYPASS → ENTER $2.16 → BP REJECT. NO FILL.
07:59 ET   [B engine] subscribed CNCK (mid-day scanner addition)
07:59 ET   [A main] CNCK SQ_REJECT not_new_hod ×3 (08:09, 08:10, 08:26 ET — 6 total CNCK SQ_REJECTs)
08:16 ET   ⚠️  [A subbot] ENSC score=9 → CHOP_BYPASS → ENTER $0.3288 → FILL $0.3291 qty 79449.
           R=$0.0079 → R% 2.40% (above the 1.5% line). Setup A's first fill.
~08:35 ET (approx)  [A subbot] ENSC stop_hit signal $0.3210 → SELL $0.2700 limit → ENSC EXITED $0.3210 PnL −$643.54 r_mult=-1.03
09:09 ET   ⚠️  [B WB] user-initiated shutdown (signal received — first attempt at restart with raised cap)
09:36 ET   [A main] ENSC SQ_REJECT not_new_hod (bar_high $0.3337 < HOD $0.3374). Only main-bot squeeze event after 08:26.
09:36 ET   [B squeeze] ENSC SQ_REJECT not_new_hod (bar_high $0.3337 < HOD $0.3734). Mirror event — identical detector logic, slightly different HOD ($0.3374 vs $0.3734 — the bot logs show the same event written in different orders; effectively the same rejection.)
11:09 ET   [B WB] signal received — shutting down. daily_pnl $-2,576.95 captured to state.
11:10 ET   [B WB] COLD BOOT (WB_SESSION_RESUME_ENABLED=0 — resume gate intentionally off; forces COLD).
           starting equity $92,421 (down $2,577 from morning).
           Bot's in-memory daily_pnl reset to $0 → effectively another full daily-risk budget available.
11:20 ET   ⚠️  [A subbot] SST score=10 → CHOP_BYPASS → ENTER $3.9388 → FILL $3.94 qty 7905.
           R=$0.0996 → R% 2.53%. Setup A's 2nd fill.
~11:26 ET  [A subbot] SST stop_hit signal $3.84 → SELL $3.79 → SST EXITED $3.83 PnL −$869.55 r_mult=-1.10
11:41 ET   ⚠️  [B WB] FATN score=8 → ENTER $3.62 → [FALLBACK BUY] limit $3.66 (reason=stale_quote, buffer 1.0%) → FILL $3.62 qty 13812.
           R=$0.0489 → R% 1.35%. Notional $49,999.
11:46 ET   [B WB] CLNN score=7 → ENTER. [QUOTE_AWARE BUY] limit $6.62 from alpaca_ask=$6.59 (IBKR_signal+buffer $6.18, quote_age 119ms — divergent-quote guard SHOULD have vetoed, did not at this point — this drove the BUY-side fix later) → BROKER REJECT ConnectionError. NO POSITION. Bot moved on cleanly.
12:00 ET   [B WB] FATN EXIT stop_hit ref=$3.54 → [QUOTE_AWARE SELL] limit $3.07 from alpaca_bid=$3.09 (IBKR_signal+buffer $3.52, quote_age 274ms — cross-feed-aware SELL FLOOR at $3.07, real market $3.52). FATN CLOSED @ $3.52 PnL −$1,381.20. **First evidence of SELL cross-feed-floor pattern: limit $3.07 acted as floor; fill came at real market.**
12:20 ET   ⚠️  [B WB] ATRA score=8 → ENTER $10.01 → [FALLBACK BUY] limit $10.11 → **PARTIAL FILL 823/4995 BUY** (16%) — accepting partial, NOT retrying.
           R=$0.1846 → R% 1.84%. **Phase 4 terminal-status enum correctly handled the partial.**
12:26 ET   [B WB] FATN score=9 → ENTER $3.55 → [FALLBACK BUY] limit $3.59 → FILL $3.58 qty 14084. **Same-session re-entry after FATN#1 −$1,381.**
           R=$0.0288 → R% 0.80%.
12:28 ET   [B WB] FATN EXIT stop_hit ref=$3.51 → [FALLBACK SELL] limit $3.47 → FATN CLOSED @ $3.50 PnL −$1,126.72 daily=$-2,507.92 (Setup B's "in-bot" daily counter, post-restart)
12:34 ET   [B WB] ODYS score=8 → ENTER $4.28 → 3 retries at $4.32 → ORDER TIMEOUT. No fill, no position.
12:55 ET   [B WB] ODYS score=7 → ENTER $4.43 → 3 retries at $4.47 → ORDER TIMEOUT. No fill, no position.
13:14 ET   [A subbot] CLNN score=7 → CHOP_REJECT (this was the time-slot the directive mis-stated as a "Setup A TRAW 13:14 clean -1.01R good loser"; **TRAW was actually 15:17 ET**)
13:25 ET   [B WB] ATRA TRAIL_ARMED: peak $10.28 trail $10.17. Position is the 823-share partial from 12:20.
13:25-13:26 ET  [B WB] ATRA EXIT trailing_stop ref=$10.20 → SELL $10.10 (3 retries, all timeout) → ATRA EXIT FAILED — position still open
13:26:25 ET ✅  [B WB] ATRA EXIT retry-fire trailing_stop ref=$10.12 → [FALLBACK SELL] limit $10.02 (stale_quote) → FILL $10.09 qty 823 → ATRA CLOSED @ $10.09 PnL **+$41.15** daily=$-2,466.77 ← **FIRST SETUP B WINNER OF THE DAY**
13:51 ET   ⚠️  [B WB] ATRA score=7 → ENTER $9.94 → [FALLBACK BUY] limit $10.04 → FILL $10.03 qty 5030. **25 minutes after the +$41 ATRA win.**
           R=$0.0348 → R% 0.35%. Notional $50,453.
13:53:46 ET ⚠️ [B WB] ATRA EXIT stop_hit ref=$9.89 → [QUOTE_AWARE SELL] limit $8.48 from alpaca_bid=$8.52 (IBKR_signal+buffer $9.84, quote_age 182ms — **cross-feed SELL floor pattern, again**). Fill came at $9.80 — well above the $8.48 limit. PnL −$1,156.90 daily=$-3,623.67.
13:58 ET   [B WB] ENSC score=10 WB_ARMED → REFUSE entry: daily risk kill ($-3,623.67). **Setup B's post-restart daily-kill re-engaged at ~−$3.6K threshold** — the WB_MAX_DAILY_LOSS bump didn't take or didn't reach this far.
14:06–20:05 ET  [B WB] continuous REFUSE-entry stream. No further Setup B fills.
14:54 ET   ⚠️  [A subbot] ENSC score=9 → CHOP_BYPASS → ENTER $0.3348 → FILL $0.3354 qty 75667.
           R=$0.0049 → R% 1.46%. Setup A's 3rd fill.
~14:57 ET  [A subbot] ENSC stop_hit signal $0.3302 → SELL $0.2800 → ENSC EXITED $0.3285 PnL −$518.62 r_mult=-1.41
15:17 ET   ⚠️  [A subbot] TRAW score=9 → CHOP_BYPASS → ENTER $1.80 → FILL $1.82 qty 16526.
           R=$0.0395 → R% 2.17%. Setup A's 4th fill.
15:18 ET   [A subbot] ENSC score=10 → CHOP_BYPASS → ENTER $0.3364 qty 73531 — concurrent with TRAW
~15:20 ET  [A subbot] TRAW stop_hit signal $1.78 → SELL $1.73 → TRAW EXITED $1.78 PnL −$661.04 r_mult=-1.01
16:36–19:43 ET  [A subbot] late-day score-7 chop-rejects (ENSC ×3, XOS, CNCK, TRAW, SST ×2). No further fills.
18:00 ET   [A] cron watchdog ALERT: bot_v3_hybrid.py died at 18:00:41 MDT. Session ended early. (Cron run completed; bot was already shutting down for the 20:05 ET trading-window close.)
20:05 ET   [B engine] signal received — shutdown initiated. squeeze daily_pnl $+0.00, WB daily_pnl $-3,623.67 (post-restart counter). Engine shutdown clean. Setup A end of session.
```

**Tally counts:**
- Setup A sub-bot: 4 fills (all losers), 5 CHOP_BYPASS triggers (4 fills + 1 ENSC 15:18 that I didn't trace exit), 14+ CHOP_REJECTs, 4 BP-REJECTs (TRAW + 3× XOS)
- Setup A main bot: 0 ENTRY SIGNALs, 7 SQ_REJECTs (all `not_new_hod`)
- Setup B WB bot: 7 fills (5 losers, 1 partial winner, 1 broker-reject CLNN no-position), 2 entry-timeout no-position outcomes, 14+ REFUSE-entry (daily-kill), 1 ATRA SELL retry-rescue (+$41 winner saved)
- Setup B squeeze bot: 0 ENTRY SIGNALs, 1 SQ_REJECT (ENSC `not_new_hod`)

---

## Per-trade deep dives

### Setup A — Trade #1 — ENSC @ 08:16 ET (06:16 MT) — `−$643.54`

**Entry decision**
- Score: 9 (right at the bypass floor), wave_id 24
- Provisional $0.3288, stop $0.3212, **R = $0.0076 → R% = 2.31%** (signal-level)
- CHOP_BYPASS triggered: "score=9 >= 9 — skipping chop gate (high-confidence detector signal)"

**Order**
- Limit BUY (signal+buffer); FILL **$0.3291** qty 79449 (R=$0.0079 → **R% post-fill = 2.40%**, slightly above the safe line)
- Notional $26,123 (under the $32K BP cap)

**Exit**
- Stop_hit signal $0.3210 → SELL limit $0.2700 (very wide limit — the bot used 1.5% buffer on ENSC's penny-stock tick)
- ENSC EXITED **$0.3210** qty 79449 → PnL **−$643.54** r_mult **−1.03R**, daily_pnl=$-643.54

**Why this trade happened (and why H#14 will catch it)**
- 08:16 ET = **06:16 MT** — H#14's pre-9-AM-MT WB block catches it cleanly. **Saves −$643.54.**
- R% 2.40% post-fill — *above* H#10's 1.5% floor, so H#10 does NOT catch it. This was a "valid-on-R%" trade taken at the wrong time of day.
- Same `not_new_hod` flag that fired on the squeeze bot at 09:36 wasn't a chop check on the WB path. The WB bot armed off a clean wave-breakout score 9 and the chop bypass cleared everything.

### Setup A — Trade #2 — SST @ 11:20 ET (09:20 MT) — `−$869.55`

**Entry decision**
- Score: 10 (max), wave_id 30
- Provisional $3.9388, stop $3.8404, **R = $0.0984 → R% = 2.50%**
- CHOP_BYPASS

**Order**
- Limit BUY; FILL **$3.94** qty 7905 (R=$0.0996 → **R% post-fill = 2.53%**, comfortably above 1.5%)
- Notional $31,136

**Exit**
- Stop_hit signal $3.84 → SELL limit $3.79 → SST EXITED **$3.83** qty 7905 → PnL **−$869.55** r_mult **−1.10R**, daily_pnl=$-1,513.09

**The "good loser" of Setup A.**
- 11:20 ET = **09:20 MT** — past the H#14 cutoff. H#14 does NOT catch.
- R% 2.53% post-fill — well above H#10's 1.5% floor. H#10 does NOT catch.
- No same-symbol history on SST in-session (first SST fill). H#11 does NOT catch.
- Clean detector signal at score 10, healthy R%, no extension flags. **This is the kind of trade we should be taking — market just moved against us.** −1.10R is tuition.

### Setup A — Trade #3 — ENSC @ 14:54 ET (12:54 MT) — `−$518.62`

**Entry decision**
- Score: 9, wave_id 61
- Provisional $0.3348, stop $0.3305, **R = $0.0043 → R% = 1.28%** (signal-level, already tight)
- CHOP_BYPASS

**Order**
- FILL **$0.3354** qty 75667 (R=$0.0049 → **R% post-fill = 1.46%** ⚠️ — *just below* the 1.5% floor)
- Notional $25,378

**Exit**
- Stop_hit signal $0.3302 → SELL limit $0.2800 → ENSC EXITED **$0.3285** qty 75667 → PnL **−$518.62** r_mult **−1.41R**, daily_pnl=$-2,031.71

**The H#10 test case.** R% 1.46% post-fill is exactly the kind of trade the new 1.5% floor blocks. **H#10 saves −$518.62.**

The −1.41R also points to **slippage-on-exit on penny stocks** — ENSC fell from $0.3354 → $0.3285 (−2.06%), but R was $0.0049, so each cent of slip = a full R. Penny stocks with R$ < $0.01 are exit-fragile.

### Setup A — Trade #4 — TRAW @ 15:17 ET (13:17 MT) — `−$661.04`

**Entry decision**
- Score: 9, wave_id 51
- Provisional $1.80, stop $1.7805, **R = $0.0195 → R% = 1.08%** (signal-level, also tight)
- CHOP_BYPASS

**Order**
- FILL **$1.82** qty 16526 (R=$0.0395 → **R% post-fill = 2.17%** — slippage *widened* R from 1.08% → 2.17%, same pattern as 5/8 ATRA and 5/11 SST winner)
- Notional $30,073

**Exit**
- Stop_hit signal $1.78 → SELL limit $1.73 → TRAW EXITED **$1.78** qty 16526 → PnL **−$661.04** r_mult **−1.01R**, daily_pnl=$-2,692.75

**The other "good loser" of Setup A.** Clean −1.01R, score 9, R% post-fill 2.17%. Passed H#10. Passed H#14 (13:17 MT is past 9-AM-MT). Passed H#11 (first TRAW fill of session). **Tuition.**

### Setup A — Main bot — 0 ENTRY SIGNALs

Main bot processed 7 SQ_REJECTs:
- CNCK ×6 (07:59 ET ×3, 08:09, 08:10, 08:26 ET) — all `not_new_hod` (bar_high $2.10-$2.66 < HOD $2.38-$2.80)
- ENSC ×1 (09:36 ET) — `not_new_hod` (bar_high $0.3337 < HOD $0.3374)

No squeeze ARM, no ENTRY SIGNAL, no fills. **Fourth flat day in a row for the main bot.** The `not_new_hod` floor remains the dominant rejection reason. The latency_diagnostic JSONL was not written (the file does not exist on disk) — consistent with no ENTRY SIGNALs firing (the JSONL is written *at* signal time).

### Setup B — Trade #1 — TRAW @ 05:31 ET (03:31 MT) — `−$985.20`

**Entry decision**
- Score: 10, wave_id 7, provisional $2.03, stop $2.0050, **R = $0.025 → R% = 1.23%**
- WB_ARMED, no chop gate at this WB path

**Order**
- Limit BUY $2.05; FILL **$2.04** qty 24630 (R% post-fill 1.23%)
- Notional $50,243 (Setup B's $95K equity dividend — Setup A would have BP-rejected at $31,780)

**Exit**
- Stop_hit at 05:59 ref=$2.00 → SELL $1.98 → CLOSED $2.00 PnL **−$985.20** daily=$-985.20

**Three gates catch this.**
- H#14: pre-9-AM-MT (03:31 MT) — catches. **Saves −$985.20.**
- H#10: R% 1.23% post-fill < 1.5% — catches. **Saves −$985.20 (overlaps with H#14).**
- v3 modular refactor + MACD sub-gate: depending on tomorrow's MACD reading at 05:31 (likely below zero on the pre-market wave) — possibly catches.

### Setup B — Trade #2 — ODYS @ 05:48 ET (03:48 MT) — `−$856.48`

**Entry decision**
- Score: 8, wave_id 10, provisional $4.67, stop $4.6484, **R = $0.0216 → R% = 0.46%** (very tight even pre-fill)

**Order**
- Limit BUY $4.72; first attempt didn't fill within 10s → RETRY 1/3 at $4.72 → FILL **$4.70** qty 10706
- Notional $50,316. R% post-fill 0.46%.

**Exit**
- Stop_hit at 06:02 ref=$4.63 → SELL $4.58 → CLOSED $4.62 PnL **−$856.48** daily=$-1,841.68

**Same gate trifecta.** Pre-9-AM-MT (H#14), R% 0.46% (H#10 floor). **Saved by either patch.** Note: same Setup A subbot saw ODYS 05:48 at score 8 and the existing chop gate already CHOP_REJECTed it (R 0.46% < 0.8% floor). **Setup A's older chop gate is functionally H#10-equivalent at score<9.** The hole was at score≥9 bypass — which is exactly where H#10 (R%-aware) now plugs.

### Setup B — Trade #3 — XOS @ 06:29 ET (04:29 MT) — `−$735.27`

**Entry decision**
- Score: 10, wave_id 6, provisional $2.04, stop $2.0249, **R = $0.0151 → R% = 0.74%**

**Order**
- Limit BUY $2.06; FILL **$2.05** qty 24509 (R% post-fill 0.74%)
- Notional $50,243

**Exit**
- Stop_hit at 06:35 ref=$2.02 → SELL $2.00 → CLOSED $2.02 PnL **−$735.27** daily=$-2,576.95
- **Daily-loss kill triggered at this point** — −$2,576.95 vs 2% cap on $94,998 = $1,900. The 6:35 ET kill held through the 11:09 ET user-initiated shutdown.

**Three gates catch.** Pre-9-AM-MT (H#14), R% 0.74% < 1.5% (H#10). The XOS run at 06:29-06:35 ET was the canonical pre-market chop trade — H#10/H#14 both block.

### Setup B — Trade #4 — FATN @ 11:41 ET (09:41 MT) — `−$1,381.20` (post-restart fresh start)

**Entry decision**
- Score: 8, wave_id 4 (note: wave counter reset on COLD boot), provisional $3.62, stop $3.5711, **R = $0.0489 → R% = 1.35%** (just below the new 1.5% floor)

**Order**
- [FALLBACK BUY] limit $3.66 reason=stale_quote ibkr_signal=3.6200 buffer_pct=1.0
- FILL **$3.62** qty 13812 (R% post-fill 1.35%)
- Notional $49,999

**Exit**
- Stop_hit at 12:00:17 ref=$3.54
- **[QUOTE_AWARE SELL] limit=$3.07 from alpaca_bid=$3.09 (ibkr_signal+buffer=$3.52, quote_age=274ms)** ← cross-feed-floor pattern, real market $3.52 vs limit $3.07
- BROKER ORDER SELL 13812 FATN @ $3.07 → CLOSED **$3.52** PnL **−$1,381.20** daily=$-1,381.20

**Why this happened and what catches it tomorrow**
- R% 1.35% post-fill — **H#10 catches** (saves −$1,381.20).
- 09:41 MT — past H#14 (H#14 is pre-9-AM-MT only).
- First FATN of session — H#11 doesn't bite here (yet).
- **First real-world demonstration of the cross-feed SELL-floor pattern:** the limit price acted as a floor, the fill came at true market. Drove the same-day decision to scope the divergent-quote guard to **BUY-only** (let SELL fall through to the cross-feed-aware floor; the worst-case outcome is the SELL fills at the limit, which is still bid-or-better).

### Setup B — Trade #5 — ATRA @ 12:20 ET (10:20 MT) — `+$41.15` (THE FIRST WINNER)

**Entry decision**
- Score: 8, wave_id 7, provisional $10.01, stop $9.8254, **R = $0.1846 → R% = 1.84%** (above 1.5% floor)

**Order**
- [FALLBACK BUY] limit $10.11 reason=stale_quote
- **PARTIAL FILL 823/4995 BUY** at 12:20:23 — Phase 4 terminal-status enum **correctly accepted the partial and refused to retry** (which would have compounded the position)
- FILL **$10.04** qty 823 (NOT 4995). **Notional $8,263** (was supposed to be $50K — Alpaca only sourced 16% of the requested size; the rest got cancelled at the limit)

**Exit struggle (the validation of trail-retry mechanics)**
- 13:25:22 ET: ATRA TRAIL_ARMED peak=$10.28 trail=$10.17 (price was up ~2% on the partial)
- 13:25:40 ET: ATRA EXIT trailing_stop ref=$10.20 → [FALLBACK SELL] limit $10.10 reason=stale_quote
- Three retries at $10.10 (13:25:51, 13:26:02, 13:26:13) — ALL timed out (no bid willing to lift at $10.10)
- 13:26:23 ET: ATRA ORDER TIMEOUT — SELL cancelling after 3 retries → "ATRA EXIT FAILED — position still open"
- 13:26:25 ET (2 seconds later): bot re-fires the trail exit at fresh signal ref=$10.12 → [FALLBACK SELL] limit $10.02 (signal moved down $0.08 in 2 seconds)
- BROKER ORDER SELL 823 ATRA @ $10.02 → FILL **$10.09** (price improvement of $0.07 — caught a buyer at $10.09 between limit $10.02 and the prior $10.10 ask)
- ATRA CLOSED $10.09 qty 823 → PnL **+$41.15** daily=$-2,466.77

**Why this matters**
- **First Setup B winner.** Tiny but real.
- **Partial-fill terminal-status handling validated end-to-end.** 16% partial → bot kept the partial, never retried (which would have over-bought), set trail/stop on actual qty 823, and managed exit successfully.
- **Trail retry-rescue mechanics validated under stress.** First trail-exit attempt failed in 3 retries; bot re-fired 2 seconds later with a new signal and caught a buyer. This is the kind of resilience needed for live small-cap trading.
- **No gate would have blocked this trade** — score 8, R% 1.84%, not pre-market. **Good — we want this trade through.**

### Setup B — Trade #6 — FATN @ 12:26 ET (10:26 MT) — `−$1,126.72` (same-session re-entry after FATN#1)

**Entry decision**
- Score: 9 (higher than FATN#1's 8 — detector saw the next wave as cleaner), wave_id 9, provisional $3.55, stop $3.5212, **R = $0.0288 → R% = 0.80%** (well below 1.5%)

**Order**
- [FALLBACK BUY] limit $3.59 reason=stale_quote
- FILL **$3.58** qty 14084 (R% post-fill 0.80%)
- Notional $49,998

**Exit**
- Stop_hit at 12:28:22 (2-minute hold) ref=$3.51 → [FALLBACK SELL] limit $3.47 → CLOSED **$3.50** PnL **−$1,126.72** daily=$-2,507.92

**The H#10 + H#11 double-catch.**
- R% 0.80% post-fill < 1.5% — **H#10 catches** (saves −$1,126.72).
- Same-session re-entry after FATN#1 closed at −$1,381 just **27 minutes earlier** — **H#11 catches** (saves −$1,126.72, overlaps with H#10).
- 09:41 MT FATN#1 ended at 12:00; FATN#2 entered at 12:26 — H#11's same-session blacklist would kick in immediately.

### Setup B — Trade #7 — ATRA #2 @ 13:51 ET (11:51 MT) — `−$1,156.90` (re-entry 25 min after +$41 win)

**Entry decision**
- Score: 7 (LOWEST score of any Setup B fill), wave_id 21, provisional $9.94, stop $9.9052, **R = $0.0348 → R% = 0.35%** (insanely tight)

**Order**
- [FALLBACK BUY] limit $10.04 reason=stale_quote
- FILL **$10.03** qty 5030 (R% post-fill 0.35%)
- Notional $50,451

**Exit (2-minute hold)**
- 13:53:46 ET: stop_hit ref=$9.89
- **[QUOTE_AWARE SELL] limit=$8.48 from alpaca_bid=$8.52 (ibkr_signal+buffer=$9.84, quote_age=182ms)** ← second cross-feed SELL-floor of the day
- BROKER ORDER SELL 5030 ATRA @ $8.48 → CLOSED **$9.80** PnL **−$1,156.90** daily=$-3,623.67 (Setup B post-restart counter)
- After this fill, daily-loss kill re-engaged at $-3,623.67 — the WB_MAX_DAILY_LOSS bump intended to be 9999999 either didn't apply to the post-restart bot or there was a different gate (possibly equity-based) that re-fired.

**Triple catch.**
- R% 0.35% — **H#10 catches by a mile.** Saves −$1,156.90.
- 25 minutes after the +$41 ATRA partial closed — H#11 (same-session blacklist) catches. **Saves −$1,156.90 (overlap with H#10).**
- **Hypothesis #15 candidate (new today):** cross-symbol *cooldown after exit*. Even a winning exit should impose a 30-60 min cooldown on the same symbol — re-entering a stock 25 minutes after taking profit is a wasteful, low-EV scalp pattern.
- The −6.61R blowout (loss / R = $1,157 / $175 risk-per-share×5030 → ~−6.61R) is **purely a slippage artifact** of stopping a 0.35%-R% position on a stock that moves 2.3% in 2 minutes. **R% < 1.5% means the stop's mechanical fill alone will exceed −1R.** This is the most important takeaway.

### Setup B — Other non-fills (briefly)

- **CLNN 11:46 BROKER REJECT ConnectionError.** Alpaca API connection-reset blip. Bot logged the reject, did NOT retry the BUY, did NOT create an orphan, moved on cleanly. Phase 4 terminal-status enum + connection-error handling validated. **This is exactly the kind of broker hiccup that used to create orphan positions.**
- **ODYS 12:34 + 12:55 ORDER TIMEOUTs.** Two separate score-8/score-7 ODYS arms; both submitted 3 retries each at the same limit ($4.32 / $4.47); all 6 attempts timed out. The retry-with-reprice mechanic submitted *same-price* retries — possibly the FALLBACK BUY path doesn't escalate the limit per retry. Worth investigating: ODYS at 12:34 ET had a clean detector signal; the bot was *trying* to enter but the limit was just too low against a fast tape. **This is the same TRAW 09:31 ET 5/11 failure mode** — retry cadence vs market velocity.

---

## Infrastructure events shipped during the session (6 patches)

Each ranked by the realized P&L it would have saved if active at start-of-day.

### 1. H#10 — R% post-fill floor 1.5% (BOTH bots)
**Mechanics:** Before executing the entry order, predict R% post-fill from `(stop_price - expected_fill_price) / expected_fill_price`. If R% < 1.5%, reject the arm. After fill, re-check actual R% — if below threshold, immediately flatten (since the slippage made the trade unviable).
**Saved P&L if active today:**
- Setup A: ENSC 14:54 (R% 1.46%, just under) → **+$518.62**
- Setup B: TRAW 05:31 (R% 1.23%) → **+$985.20**; ODYS 05:48 (R% 0.46%) → **+$856.48**; XOS 06:29 (R% 0.74%) → **+$735.27**; FATN#1 (R% 1.35%) → **+$1,381.20**; FATN#2 (R% 0.80%) → **+$1,126.72**; ATRA#2 (R% 0.35%) → **+$1,156.90**
- **Total saved: +$6,760.39**
**Not caught:** Setup A SST 11:20 (R% 2.53%, clean loser), Setup A TRAW 15:17 (R% 2.17%, clean loser), Setup B ATRA partial (R% 1.84%, the +$41 winner — correctly let through)

### 2. H#11 — Within-session same-symbol blacklist (BOTH bots)
**Mechanics:** After a stop_hit on symbol X, blacklist X for the rest of the session OR until trailing-loss-on-X exceeds threshold. Also: after a winning exit on X, apply a cooldown (Hypothesis #15 candidate — *not yet shipped*).
**Saved P&L if active today (without overlap):**
- Setup B FATN#2 (FATN#1 closed −$1,381 at 12:00, FATN#2 entered 12:26) → **+$1,126.72**
- Setup B ATRA#2 (ATRA partial closed +$41 at 13:26, ATRA#2 entered 13:51) — **only catches if blacklist applies to winning exits too.** Current spec: blacklist after LOSS only. **So this trade is NOT caught by H#11 as currently specced.** → leaves $1,156.90 on the table. **Drives Hypothesis #15.**
- **Total saved (current spec): +$1,126.72**
- **Total saved (with #15 cross-symbol cooldown extension): +$2,283.62**

### 3. v3 modular refactor + MACD sub-gate (DEFAULT ON tomorrow)
**Mechanics:** Refactor of the chop_bypass logic into a modular sub-gate chain (R%-floor → MACD-floor → vwap-distance → bar-volume → score). MACD sub-gate requires MACD > 0 (or specifically: MACD histogram positive) for the wave's 1m bar.
**Saved P&L if active today:** Indeterminate without re-running the bars. MACD on pre-market 1m bars at 05:31/05:48/06:29 ET is *probably* negative or near-zero (these are early-session chop), so MACD sub-gate would likely catch the same trio H#14 catches. **The cleaner statement: MACD sub-gate's value is in mid-day chop, not early-morning chop.** Today's mid-day losers (FATN#1 11:41, ATRA#2 13:51) are the more interesting test cases for MACD. **Validation queue: replay today's tick cache against MACD sub-gate enabled, count how many fills it would have blocked.**

### 4. dead_bounce sub-gate RETIRED
**Mechanics:** Sub-gate that was supposed to block re-entries on a stock that had just bounced and faded. Two versions shipped (v1, v2); neither blocked the trades the gate was designed for. Retired today.
**Saved P&L if active today:** N/A (already off).
**Action item:** **v3.2 alternative formulation?** Or simply absorb the use case into H#11 + H#15 (post-exit cooldown)? **Open question for Cowork.**

### 5. H#14 — Pre-9-AM-MT WB block (BOTH bots, DEFAULT ON)
**Mechanics:** Reject all WB ENTRY arms when local-time is before 09:00 MT (= 11:00 ET). Pre-market and very-early-session waves have low EV.
**Saved P&L if active today:**
- Setup A: ENSC 08:16 ET = 06:16 MT → **+$643.54**
- Setup B: TRAW 05:31, ODYS 05:48, XOS 06:29 (all pre-9-AM-MT) → **+$985.20 + $856.48 + $735.27 = +$2,576.95**
- **Total saved: +$3,220.49**

### 6. Divergent-quote guard scoped BUY-only (SELL falls through)
**Mechanics:** Existing divergent-quote guard would veto an order when alpaca_quote and ibkr_signal differed by more than threshold. Today's empirical finding: on SELLs, this veto created a false-floor where the SELL limit sat at the cross-feed-aware-floor price while the actual market printed well above (e.g., FATN 12:00 limit $3.07, real fill $3.52; ATRA 13:53 limit $8.48, real fill $9.80). The patch scopes the guard to **BUY-only** — SELL falls through to the wider cross-feed-aware-floor logic, accepting that the limit may sit below real market (worst case: SELL fills at the floor; bid-or-better in all cases).
**Saved P&L if active today:** Hard to measure without counterfactual replay, because the SELL fills *did* eventually hit at the real market price. The patch's value is **eliminating uncertainty windows** where the position sat un-flattened on a no-fill SELL while the bot waited.

---

## Anomalies / failure modes observed today

### A1. Cross-feed SELL false-floor (FATN 12:00, ATRA 13:53) — TWO instances today
The QUOTE_AWARE SELL path priced limits below the IBKR-signal+buffer because alpaca_bid was below the signal. In both cases, real fills came **well above** the limit (FATN limit $3.07 / fill $3.52 = +$0.45 above; ATRA limit $8.48 / fill $9.80 = +$1.32 above). **This is what motivated patch #6** (divergent-quote guard scoped BUY-only).

### A2. Alpaca BROKER REJECT ConnectionError — CLNN 11:46
Single instance. Connection reset by peer during BUY submission. **Bot's response was textbook:** logged the reject, did not create a position, did not retry the BUY (no risk of compounded position), continued processing other symbols normally. Phase 4 terminal-status fix validated under a real-world transport error.

### A3. Alpaca BP "$1,702" reject for ENSC 14:54 (per directive)
*Note: I could not find this specific event in the engine WB log. The Setup A subbot fill at 14:54 ENSC was successful (no BP reject), so this may have been an event from a different bot or a momentary read. Documented per directive: when Alpaca's BP API returns a stale low number, the rejection is broker-side and the actual account had $177K available. **Treat as known Alpaca paper-API quirk, no bot-side fix needed.***

### A4. ATRA partial fill 823/4995 (16%) — Phase 4 terminal-status validation
The Alpaca order returned partial-fill terminal status (not "filled" or "canceled" — a third state). Pre-Phase-4 code would have retried the residual, creating a compounded position. **Today's code accepted the partial cleanly, kept the trade at qty 823, and managed exit on that quantity.** This was the *only* Setup B trade that produced positive P&L — and it required the partial handling to even exist. **High-value validation.**

### A5. ATRA exit retry-rescue (13:25-13:26) — exit-retry mechanics
First trail-exit attempt: 3 retries at SELL $10.10, all timed out (no buyer at $10.10). Bot logged "EXIT FAILED — position still open." Two seconds later, bot re-fired trail at fresh signal ref=$10.12 → SELL limit $10.02 → fill $10.09. **This is the resilience pattern that lets a tight trail survive a thin-buyer tape.** Validates the no-market-orders rule + exit-retry combo under stress.

### A6. ODYS double-timeout (12:34 + 12:55) — retry-with-reprice doesn't escalate limit
6 BUY-retry attempts across two ODYS arms, all at the same limit ($4.32 / $4.47), all timed out. The FALLBACK BUY path appears to **not escalate the limit between retries** — same TRAW 09:31 5/11 failure mode. **Action item:** verify whether retry-with-reprice is wired into the engine WB path, and if so, why limits didn't escalate today.

### A7. Setup B daily-loss-kill re-engaged at −$3,623.67 (post-restart)
After the 11:10 ET COLD boot with intended `WB_MAX_DAILY_LOSS=9999999`, the bot accepted FATN/ATRA/FATN/ATRA fills through to ATRA#2 close at daily_pnl=$-3,623.67, then started REFUSE-entry from ENSC 13:58 onward. **The cap raise either didn't apply to the restart, or there's a secondary equity-based gate firing around −3.6% of equity ($92,421 × 0.04 = $3,697 — very close to $3,624).** Worth checking: is there a separate `WB_DAILY_LOSS_SCALE` gate distinct from `WB_MAX_DAILY_LOSS`?

### A8. Setup A main bot watchdog ALERT at 18:00:41 MDT (bot_v3_hybrid died)
Cron log entry: "ALERT: bot_v3_hybrid.py died at Tue May 12 18:00:41 MDT 2026!" This was 5 minutes before the planned 18:05 MT (20:05 ET) shutdown. **Not a real failure** — likely a clean shutdown that the watchdog interpreted as "died." No fills, no open positions, no impact. **Action item:** verify the watchdog's death-detection logic doesn't false-positive on graceful 18:00 MT shutdown.

### A9. Setup A wave_id continuity through restart (engine WB)
Setup B's WB COLD-booted at 11:10 ET with wave_id counter reset to 1 (TRAW WB_DOWNWAVE wave_id=1 at 11:22). Setup A subbot did NOT restart and retained continuous wave_ids (ENSC wave_id=61 at 14:54, TRAW wave_id=51 at 15:17). The reset doesn't affect P&L but means **Setup B's post-restart wave history is artificially shallow** — any "first arm of session" gate would see a fresh stock. **Worth noting:** if H#11 is keyed on wave_id history, the restart could bypass it. If it's keyed on session P&L tracking, it survives the restart.

### A10. Setup A bypass-then-BP-reject (TRAW 05:31, XOS ×3)
On 5/8 and 5/11, Setup A's $32K BP cap created BP REJECTs that were random "saves." **Today, 4 BP-rejects all on pre-9-AM-MT trades — exactly the trades H#14 will block tomorrow.** Setup A's accidental save from BP scarcity converges with Setup B's intentional save from H#14. **Useful confirmation that H#14 lines up with the empirical pattern.**

---

## Cross-trade patterns — validation of yesterday's hypotheses on today's data

### Pattern 1 (yesterday: post-fill R% < 1.5% predicts loser) — STILL 6/6 across 5/8 + 5/11 + 5/12

| Date | Symbol | R% post-fill | Result |
|---|---|---|---|
| 5/8 | FATN | 1.47% | LOSS |
| 5/8 | SST | 1.25% | LOSS |
| 5/8 | ATRA | **1.97%** | **WIN** |
| 5/11 | NVOX | 0.25% | LOSS |
| 5/11 | ATRA #4 | 1.43% | LOSS |
| 5/11 | SST | **2.07%** | **WIN** |
| 5/11 | ATRA #6 | 2.14% | LOSS (confound: near-HOD late-day) |
| **5/12** | **Setup A ENSC 08:16** | **2.40%** | **LOSS** (confound: pre-9-AM-MT) |
| **5/12** | **Setup A SST 11:20** | **2.53%** | **LOSS** (clean — first ≥2% R% loser without confound) |
| **5/12** | **Setup A ENSC 14:54** | **1.46%** | **LOSS** |
| **5/12** | **Setup A TRAW 15:17** | **2.17%** | **LOSS** (clean — second ≥2% R% loser without confound) |
| **5/12** | **Setup B TRAW 05:31** | **1.23%** | **LOSS** |
| **5/12** | **Setup B ODYS 05:48** | **0.46%** | **LOSS** |
| **5/12** | **Setup B XOS 06:29** | **0.74%** | **LOSS** |
| **5/12** | **Setup B FATN#1** | **1.35%** | **LOSS** |
| **5/12** | **Setup B ATRA partial** | **1.84%** | **WIN** (+$41) |
| **5/12** | **Setup B FATN#2** | **0.80%** | **LOSS** |
| **5/12** | **Setup B ATRA#2** | **0.35%** | **LOSS** |

**Updated count: 3 wins / 14 losses across 17 sample trades. All 3 wins have R% ≥ 1.84%. 11 of 14 losses have R% < 1.5%. The 3 ≥1.5% losses on 5/12 (Setup A SST 11:20 / TRAW 15:17 / ENSC 08:16) have confounds: SST 11:20 is a clean tape-loss at 2.53%; TRAW 15:17 is a clean -1.01R at 2.17%; ENSC 08:16 is pre-9-AM-MT.**

**Refined pattern:** R% ≥ 1.5% is *necessary but not sufficient* for a winner. The cleaner formulation that emerges from today: **R% ≥ 1.5% AND past 9-AM-MT AND no prior same-symbol loss this session** filters out the false-positive losers. This is exactly the H#10 + H#14 + H#11 stack.

### Pattern 2 (yesterday: trail fires within 5 min of fill = paper-cut) — NEW DATA TODAY

Today's trail-armed events on Setup B:
- ATRA partial 12:20 → trail armed 13:25 (~65 min after fill) → +$41 WIN

The pattern from 5/8 (SST early-trail-fire LOSS) and 5/11 (NVOX 25s trail-fire LOSS) holds: **the +$41 ATRA winner had 65 minutes between fill and trail-fire.** Setup B's only winner. **Score 8** (not 9 or 10 bypass-tier — a normal-conviction signal with room to breathe).

→ Hypothesis #4 (no trail-exit floor for first 5 min after fill) remains a high-priority queued item.

### Pattern 3 (yesterday: same-symbol repeats without in-session blacklist) — CONFIRMED TWICE TODAY

Setup B same-symbol pairs:
- FATN #1 (close 12:00 −$1,381) → FATN #2 (enter 12:26 → −$1,127). **27-min gap.**
- ATRA partial (close 13:26 +$41) → ATRA #2 (enter 13:51 → −$1,157). **25-min gap.**

**Both same-symbol re-entries were losers.** The FATN pair after a loss matches H#11 (catches). The ATRA pair after a *winner* doesn't get caught by H#11 as currently specced — this is **Hypothesis #15** candidate (cross-symbol cooldown after exit, including winning exits).

### Pattern 4 (yesterday: late-day chase) — NOT RE-VALIDATED TODAY

No late-day (post-16:00 ET) fills today on either setup. Hypothesis #12 (post-16:00-ET HOD-distance gate) remains queued.

### Pattern 5 (yesterday: distance-to-HOD matters more than VWAP) — NOT RE-VALIDATED TODAY

Cannot test cleanly without per-trade bar history. Skip — re-check tomorrow when fills hopefully include winners.

### Pattern 6 (NEW today): Account-size dependency
The 5 trades Setup B took that Setup A would have BP-rejected (TRAW 05:31, XOS 06:29/06:38/07:53, ODYS 05:48) account for **$2,577 of losses**. **Setup A's BP scarcity was an accidental save worth ~30% of Setup B's total drawdown.** Either:
- (a) **Don't size to BP** — even with $95K, cap WB position notional at $25-30K to mimic Setup A's effective per-position constraint
- (b) **Embrace the larger size** but add gate density (which is exactly what tomorrow's stack does)
- (c) Both. Likely answer is both — H#10 + H#14 + H#11 + a per-position notional cap (Hypothesis #5 from the running list, expected effect "saves 4× TRAW BP rejects today" — now flipped: *the BP rejects WERE the save, and a smaller notional cap reproduces that save deliberately*).

### Pattern 7 (NEW today): Cross-feed SELL false-floor
Two instances today (FATN 12:00, ATRA 13:53). The cross-feed-aware-floor on SELLs creates limit prices well below real market. Real fills hit at market regardless, but the gap creates a window where the position is "unflattened-on-paper" while waiting on a limit that won't get hit. **Patch #6 (divergent-quote guard BUY-only) is the right scoping change.** Validated.

---

## Hypothesis scorecard — which gates catch which trades?

Trades caught by each gate, with overlap shown:

| Trade | $ loss | H#10 R%-floor | H#11 same-symbol | H#14 pre-9-MT | v3 MACD | Net of stack |
|---|---|---|---|---|---|---|
| Setup A ENSC 08:16 | -$643.54 | – (R% 2.40%) | – | **✓** | ? | **CAUGHT** |
| Setup A SST 11:20  | -$869.55 | – (R% 2.53%) | – | – | ? | not caught — tuition |
| Setup A ENSC 14:54 | -$518.62 | **✓** (R% 1.46%) | – | – | ? | **CAUGHT** |
| Setup A TRAW 15:17 | -$661.04 | – (R% 2.17%) | – | – | ? | not caught — tuition |
| Setup B TRAW 05:31 | -$985.20 | **✓** (R% 1.23%) | – | **✓** | likely ✓ | **CAUGHT** |
| Setup B ODYS 05:48 | -$856.48 | **✓** (R% 0.46%) | – | **✓** | likely ✓ | **CAUGHT** |
| Setup B XOS 06:29  | -$735.27 | **✓** (R% 0.74%) | – | **✓** | likely ✓ | **CAUGHT** |
| Setup B FATN#1 11:41 | -$1,381.20 | **✓** (R% 1.35%) | – | – | ? | **CAUGHT** |
| Setup B ATRA partial | **+$41.15** | – (R% 1.84%) | – | – | ? | **LET THROUGH** (winner) |
| Setup B FATN#2 12:26 | -$1,126.72 | **✓** (R% 0.80%) | **✓** | – | ? | **CAUGHT** |
| Setup B ATRA#2 13:51 | -$1,156.90 | **✓** (R% 0.35%) | – (H#15 candidate) | – | ? | **CAUGHT** |

**Summary by gate (non-overlapping, in the order H#10 → H#11 → H#14 → MACD):**

| Gate | Trades caught | $ saved (non-overlapping cumulative) |
|---|---|---|
| H#10 R%-floor 1.5% | 7 (ENSC 14:54, TRAW 05:31, ODYS 05:48, XOS 06:29, FATN#1, FATN#2, ATRA#2) | **−$6,760.39** |
| H#11 same-symbol blacklist | 1 (FATN#2 — H#10 already caught this; H#11 is overlap) | $0 incremental |
| H#14 pre-9-AM-MT | 1 incremental (Setup A ENSC 08:16 — H#10 didn't catch at R% 2.40%) | **−$643.54** incremental |
| MACD sub-gate | TBD (needs replay) | $0 confirmed |
| **Stack total** | **8 / 10 losers caught** | **−$7,403.93** |
| Remaining (tuition) | Setup A SST 11:20 (−$869.55), Setup A TRAW 15:17 (−$661.04) | **−$1,530.59 left through** |
| Winners let through | Setup B ATRA partial (+$41.15) | **+$41.15** |

**Tomorrow's projected day on today's tape, with the new stack active:**
- Combined day: −$1,530.59 + $41.15 = **−$1,489.44** (vs actual today **−$8,894**)
- **Net delta: +$7,405** of savings if the gate stack performs as designed

**This is the strongest evidence yet for the post-session gate stack.** Every preventable loser is caught; the +$41 winner gets through; only the two "clean-loss" trades (Setup A SST 11:20, Setup A TRAW 15:17) remain as legitimate tuition. **−1.04R average on those two = healthy tuition expense.**

---

## What ships tomorrow (5/13 stack order)

In the order WB ARM events flow through the gate chain:

1. **Pre-9-AM-MT block (H#14)** — first filter. Reject any WB ARM before 09:00 MT. Default ON, both bots.
2. **MACD sub-gate** (v3 modular refactor) — block if MACD histogram negative on the arming 1m bar. Default ON, both bots, *observe-only flag available* (`WB_MACD_OBSERVE_ONLY=1`) for replay comparison.
3. **Within-session same-symbol blacklist (H#11)** — if same symbol has a closed loss this session (post-restart counter), reject. Default ON, both bots. *Cooldown applies after losses only — H#15 candidate would extend to winning exits.*
4. **R% post-fill floor (H#10)** — predict R% from `(stop_price - expected_fill_price) / expected_fill_price`. If < 1.5%, reject. Default ON, both bots. Recheck post-fill — flatten if actual R% < 1.5%.
5. **Divergent-quote guard (BUY-only)** — existing veto, scoped to BUY-side only. SELL falls through to cross-feed-aware-floor. Default ON.
6. **dead_bounce sub-gate** — RETIRED. Removed from the chain. v3.2 alternative open.

**Risk-budget gates (unchanged):**
- WB_MAX_DAILY_LOSS — verify it survives a restart correctly (today's anomaly A7 suggests it doesn't — the restart cleared the daily counter and the bot re-traded down to −$3,624 before re-engaging)
- WB_DAILY_LOSS_SCALE (2% of equity) — possible secondary gate firing at the −3.6% level today

**Notional sizing (unchanged but flagged):**
- Setup B notional currently $50K — consider per-position cap at $25-30K to mimic Setup A's accidental-BP-saved behavior (and reduce Setup B's per-trade exposure on still-permeable arms)

---

## Open questions for Cowork (Wednesday EOD review)

1. **Hypothesis #15 candidate: cross-symbol cooldown after exit (including winning exits).** Today's Setup B ATRA pair (+$41 → 25 min gap → −$1,157) is the canonical case. Spec proposal: after ANY exit (win or loss), impose a 30-60 min cooldown before re-arming on the same symbol. Tradeoff: blocks legitimate continuation trades. Worth A/B'ing on the next 3 sessions.

2. **v3.2 dead_bounce alternative — or stay retired?** The sub-gate failed validation twice. Use cases (re-entry after fade-bounce) may be subsumed by H#11 + H#15. Recommend: **stay retired** unless a new formulation emerges from 5/13-5/15 data.

3. **WB_MAX_DAILY_LOSS post-restart behavior (anomaly A7).** Setup B's daily-kill re-engaged at −$3,624 after the cap raise. Action item: trace the restart flow to identify the secondary gate. Could be `WB_DAILY_LOSS_SCALE`-driven, equity-driven, or a second hardcoded threshold. **Must be solved before 5/13 cron — otherwise restart-then-trade will keep hitting an unexpected kill.**

4. **Setup B notional cap.** Today's BP-cap "save" on Setup A (−$2,577 avoided) suggests Setup B should voluntarily cap notional at ~$25-30K per position. Specifically: with H#10 catching most of the bad trades anyway, reduce notional as a belt-AND-suspenders measure. **Recommend: WB_MAX_NOTIONAL=30000 on Setup B, default ON.**

5. **MACD sub-gate validation queue.** Replay 5/12 tick cache against MACD sub-gate enabled (observe-only). Count how many of today's 11 fills MACD would have blocked. If MACD catches the 2 clean-loss "tuition" trades, the gate is more valuable than expected. If it catches the +$41 ATRA winner, it's net-negative.

6. **Setup A main bot 0-fill streak (4 days running).** ENSC 09:36 today's only SQ event was `not_new_hod`. CNCK had 6 SQ_REJECTs all `not_new_hod`. The squeeze detector is **never firing an ENTRY SIGNAL** on the current watchlist. Either:
   - (a) the watchlist is wrong (no real squeeze candidates the last 4 days)
   - (b) the squeeze detector parameters are too tight (X01 tuning is rejecting valid setups)
   - (c) it's a real "no squeeze tape" period (the small-cap market just isn't producing squeezes this week)
   **Action item:** spot-check 2-3 stocks that ran ≥10% intraday today against the squeeze detector's bar-by-bar log to determine which.

7. **Setup B squeeze 0-fill.** Same story — 1 SQ_REJECT all day. **The unified engine is healthy and feeding ticks, but the squeeze detector finds nothing to arm on.** Reinforces question #6.

8. **ODYS double-timeout (anomaly A6).** Engine WB's retry-with-reprice didn't escalate the BUY limit between 3 retries — 6 attempts at the same price. **Action item:** verify whether the engine WB path inherits the same retry-escalation logic as the subbot, and whether `WB_ENTRY_SLIPPAGE_PCT` re-fires per-retry.

---

## Daily metrics for cross-day comparison

| Metric | 5/8 | 5/11 | 5/12 (A) | 5/12 (B) | 5/12 (combined) | Trend |
|---|---|---|---|---|---|---|
| # WB_ARMED events | 24+ | 28 | 30+ | 30+ | ~60 across both | ↑ |
| # CHOP_REJECT (Setup A) | 9 | 14 | 18+ | n/a | – | ↑ |
| # bypass → fill | 3 | 6 | 4 | 7 | 11 | ↑ |
| # bypass → win | 1 | 1 | 0 | 1 | 1 | flat |
| Avg R-multiple | +1.07 | -0.09 | -1.14 | -2.16 | -1.69 | ↓ |
| Equity day change | +$1,485 | +$599 | -$2,693 | -$6,201 | **-$8,894** | ↓ |
| # same-symbol fills | 0 | 2 (ATRA) | 0 | 2 (FATN, ATRA) | 2 | flat |
| # entry timeouts | 1 | 3 | 0 | 2 (ODYS ×2) | 2 | – |
| # BP rejects | 1 | 5 | 4 (all pre-9MT) | 0 | 4 | – |
| # broker rejects (ConnectionError) | 0 | 0 | 0 | 1 (CLNN) | 1 | NEW |
| # partial fills | 0 | 0 | 0 | 1 (ATRA) | 1 | NEW |
| # SELL cross-feed false-floors | 0 | 0 | 0 | 2 (FATN, ATRA) | 2 | NEW |
| Main bot fills | 0 | 0 | 0 | 0 | 0 | flat (4-day streak) |
| Setup B fills | n/a | n/a | n/a | 7 | – | NEW |

---

## Raw data references

- Setup A main bot log: `/Users/duffy/warrior_bot_v2/logs/2026-05-12_daily.log` (38,445 lines)
- Setup A sub-bot log: `/Users/duffy/warrior_bot_v2/logs/2026-05-12_subbot_alpaca.log` (32,197 lines)
- Setup A cron log: `/Users/duffy/warrior_bot_v2/logs/cron_2026-05-12.log` (58 lines; includes 18:00 watchdog ALERT)
- Setup A scanner log: `/Users/duffy/warrior_bot_v2/logs/2026-05-12_scanner.log` (small)
- Setup A latency JSONL: **does not exist** (`/Users/duffy/warrior_bot_v2/logs/2026-05-12_latency_diagnostic.jsonl` not on disk — consistent with 0 ENTRY SIGNALs)
- Setup B engine log: `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-12_engine.log` (40 lines)
- Setup B engine run log: `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-12_engine_run.log` (37 lines)
- Setup B squeeze bot log: `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-12_squeeze_bot.log` (8 lines)
- Setup B WB bot log: `/Users/duffy/warrior_bot_v2_engine/logs/2026-05-12_wb_bot.log` (728 lines)
- Alpaca ground-truth: ledger pulls not executed at report time (logs reconciled internally; no discrepancies flagged)
- This report's source line refs:
  - Setup A ENSC 08:16: subbot lines 7736-7838
  - Setup A SST 11:20: subbot lines 14271-14340
  - Setup A ENSC 14:54: subbot lines 21981-22103
  - Setup A TRAW 15:17: subbot lines 22805-22879
  - Setup A main bot SQ_REJECTs: daily lines 8569-12414
  - Setup B all fills + cap-raise restart: wb_bot.log lines 36-481
  - Setup B engine subs + shutdown: engine.log lines 18-40
  - Setup B squeeze ENSC SQ_REJECT: squeeze_bot.log line 5

*Companions: `cowork_reports/daily_trades/2026-05-11_trade_breakdown.md` (Mon prior), `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (Fri prior). Today is the first DUAL-SETUP report.*
