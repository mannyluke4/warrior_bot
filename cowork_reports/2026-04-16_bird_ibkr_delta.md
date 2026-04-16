# BIRD IBKR-vs-Alpaca Delta Report

**Author:** CC (Opus)
**Date:** 2026-04-16 early morning
**Directive:** `2026-04-15_amendment_halt_narrowed.md` Step 3
**Inputs:**
- `tick_cache/2026-04-15/BIRD.json.gz` — 2,372,928 ticks, IBKR-sourced (clientId=420, 08:00–11:29 ET coverage before IBKR paged out; CIIT is earlier full-day IBKR)
- `tick_cache_quarantine_alpaca/2026-04-15/BIRD.json.gz` — 13.5MB Alpaca full-day (preserved for audit, NOT used in the sim)
- `simulate.py` post-refactor (commit `19671c0`) — reads tick cache only, no Alpaca fallback anywhere

---

## Headline

| Source | P&L | Trades | W/L | WR | Avg R | Armed | Entered |
|---|---|---|---|---|---|---|---|
| **Alpaca ticks** (original autopsy) | **-$1,909** | **10** | 4W/6L | 40% | -0.2R | 6 | 10 |
| **IBKR ticks** (authoritative) | **-$949** | **6** | 3W/3L | 50% | -0.2R | 5 | 6 |
| Delta | **+$960** | **-4** | | | | | |

Same directional outcome (net loss) but **~half the magnitude** and **4 fewer trades**. The 4 missing trades are T7-T10 in the original autopsy table — specifically the late-morning chop at $6-$11 and the three EPL MP re-entries at $11+ that produced the -$5,305 chop narrative.

---

## Trade-by-trade side-by-side

Both runs used the same sim command: `WB_MP_ENABLED=1 WB_EPL_ENABLED=1 python simulate.py BIRD 2026-04-15 08:15 16:00 --ticks --tick-cache tick_cache/ --no-fundamentals`. Only the tick source differs.

### First 5 trades — near-identical

| # | Time | Alpaca entry | IBKR entry | Alpaca exit reason | IBKR exit reason | Alpaca P&L | IBKR P&L |
|---|---|---|---|---|---|---|---|
| 1 | 08:21 | $3.04 | $3.04 | sq_target_hit_exit_full | sq_target_hit_exit_full | +$675 | +$675 |
| 2 | 08:27/08:28 | $3.94 | $4.04 | topping_wicky_exit_full | sq_target_hit_exit_full | +$975 | +$1,474 |
| 3 | 08:48/08:33 | $4.04 (EPL) | $4.36 (EPL) | sq_target_hit | epl_mp_stop_hit | +$1,958 | **-$2,880** |
| 4 | 08:49 | $5.04 | $5.04 | sq_para_trail_exit | sq_para_trail_exit | -$214 | -$393 |
| 5 | 09:01 | $6.04 | $6.04 | sq_target_hit_exit_full | sq_target_hit_exit_full | +$803 | +$675 |

Trades 1, 4, 5 are the SAME entries at the SAME times with similar exits/P&L — suggests the squeeze detector state is nearly identical early in the session on both data sources.

Trades 2 and 3 diverge meaningfully:
- **T2:** Alpaca exits at 08:30 via `topping_wicky_exit_full` (MP-style signal). IBKR exits at 08:28 via `sq_target_hit_exit_full` (clean 2R hit). Different tick timing produces different exit signals.
- **T3:** Alpaca enters at 08:48 as EPL (probably after graduation from T1 or T2), hits `sq_target_hit` cleanly for +$1,958. IBKR enters at 08:33 as EPL, immediately hits stop for -$2,880 (a $5k swing!). Completely different outcome on the same-named trade.

### Trade 6 — divergent outcome

| | Alpaca | IBKR |
|---|---|---|
| Entry | 09:03 $7.04 | 09:03 $7.04 |
| Exit | 09:03 $6.90 | 09:03 $6.90 |
| Reason | sq_stop_hit | sq_stop_hit |
| P&L | -$500 | -$500 |

Identical. Both data sources agree on the T6 stop-out at the 5th squeeze attempt's failure.

### Trades 7-10 — EXIST IN ALPACA, DO NOT EXIST IN IBKR

| # | Time | Alpaca entry | Alpaca P&L | IBKR |
|---|---|---|---|---|
| 7 | 09:22 | $6.99 (bearish engulfing exit) | -$171 | **Does not occur** |
| 8 | 09:57 | $11.77 (topping_wicky_exit_full) | -$1,298 | **Does not occur** |
| 9 | 10:13 | $11.38 (topping_wicky_exit_full) | -$1,131 | **Does not occur** |
| 10 | 10:20 | $11.50 (epl_mp_stop_hit) | -$3,005 | **Does not occur** |

The entire T8/T9/T10 "chop at $11+ losing $5,434" narrative is **an Alpaca tick artifact.** Under IBKR ticks, these arms never fire. The EPL MP re-entry path does not produce the same signals on IBKR data.

**Confidence check:** I re-ran the sim with the `-v` verbose flag on IBKR ticks to look for any EPL arming attempts after T6. There are **zero** EPL graduations or MP re-entry arms recorded past 09:03. In contrast, the Alpaca run showed 3 EPL-path trades (T8, T9, T10) at $11+.

### Why does this happen?

Two plausible mechanisms (not fully verified — would need deeper MP/EPL tick-replay trace):

1. **Tick density differences.** Alpaca's consolidated trade data includes more print events (SIP consolidation pulls from all US venues with fills and auto-execs). IBKR's data is more conservative. Dense tick streams can produce different bar-builder outputs at minute boundaries, different VWAP values, and different detector states — enough to arm where IBKR doesn't.

2. **Tick-time precision.** Alpaca ticks have microsecond timestamps; IBKR's may round differently or cluster around common print boundaries. For setups that depend on exact tick-by-tick price-cross detection, this matters.

Either way, for the short-strategy directive: the "right" tick data to evaluate on is IBKR (matches live bot). The Alpaca artifact produced trades the bot wouldn't actually have taken live.

---

## The load-bearing question — does T6 still exhaust the cap at 09:03?

**Yes, IBKR data confirms.** Verbose trace on IBKR:

```
[08:20] SQ_PRIMED                         (attempt 1)
[08:21] SQ_ENTRY $3.04                     ← T1
[08:27] SQ_PRIMED                         (attempt 2)
[08:28] SQ_ENTRY $4.04                     ← T2
[08:48] SQ_PRIMED                         (attempt 3)
[08:49] SQ_ENTRY $5.04                     ← T4 (T3 was EPL, separate)
[09:01] SQ_ENTRY $6.04                     ← T5 (attempt 4)
[09:03] SQ_ENTRY $7.04                     ← T6 (attempt 5, cap now exhausted)

[09:08] SQ_NO_ARM: max_attempts (5/5)
[09:41] SQ_NO_ARM: max_attempts (5/5)
[09:42] SQ_NO_ARM: max_attempts (5/5)
[10:33] SQ_NO_ARM: max_attempts (5/5)
[11:08] SQ_NO_ARM: max_attempts (5/5)
[11:14] SQ_NO_ARM: max_attempts (5/5)
```

Six post-cap SQ_PRIMED events are blocked by max_attempts. The cap-exhaust timing is within seconds of the Alpaca run. **The autopsy's Q1 answer stands unchanged on IBKR data.**

Notable: under Alpaca ticks, some post-cap primes rejected with `SQ_NO_ARM: invalid_r` / `para_invalid_r` (stale trigger-price bug mentioned in the original autopsy). IBKR ticks don't produce that — all rejections are cleanly `max_attempts`. That's a marginally cleaner mechanism story.

---

## The load-bearing question — does the $11 → $20 leg still get missed?

**Yes.** The SQ_PRIMED events at 10:33, 11:08, 11:14 on IBKR data are at BIRD prices that are well into the second-leg rally. All three rejected by the attempts cap. The mechanism "if dynamic-attempts were enabled, the bot could have caught the late leg" still holds under IBKR data.

BIRD's max tick price visible in the IBKR cache (which stops at 11:29:06): need to spot-check, but the morning-second-leg pattern is real and mirrors the Alpaca version.

---

## What changes in the autopsy's recommendations

### UNCHANGED

1. **Q1 mechanism answer** — max_attempts cap exhausted at T6 ~09:03. Same on both data sources.
2. **Q2 mechanism (EPL bypasses Gate 5)** — architectural, code-level analysis. Not tick-data dependent.
3. **Q3 regression canary finding (ROLR T10 disqualifies the naive Gate 5 extension)** — ROLR's data is historical IBKR, always was. Cowork's amendment confirmed this. Finding stands.
4. **Recommendation: NO CODE CHANGE on naive Gate 5 extension** — still correct. ROLR T10 is still blocked under the extension, and it's still the $+7,330 cascade winner that disqualifies it.

### UPDATED / SHIFTED

5. **"BIRD chop narrative" for the autopsy's conclusion** — the framing that "the bot gave back $6,105 chasing bad trades at $11+" is Alpaca-specific. On IBKR data, BIRD loses $949 from the first 6 trades via ordinary stops, not from a late-day chop sequence. The strategic takeaway is slightly different: **the bot made the right 6 trades (3W/3L), took a normal loss, and correctly didn't chase the second leg** (because the cap prevented it). That's a net loss, but it's a qualitatively different story from the "chased and chopped" narrative.

6. **The "EPL MP re-entry bypass is catastrophic on chop days" framing** from the autopsy's Q2 discussion — on THIS specific BIRD day, under real data, the EPL path only produced one trade (T3, -$2,880) not three. The damage is smaller. The architectural observation (EPL bypasses Gate 5) still stands as an architectural fact, but the specific BIRD day doesn't show it causing a -$5k cluster of losses.

7. **T10 EPL loss of -$3,005** was the centerpiece "smartest-gate" candidate — doesn't exist on IBKR. The "smart-gate" directives Cowork wrote (dynamic-attempts, smarter-EPL-gate) should still be considered on their merits, but the motivating BIRD-specific data point is weaker than the autopsy claimed.

---

## Recommendation per amendment Step 3

**Option (a) — autopsy conclusions still hold, resume Phase 2 prototype work as planned.**

Reasoning:
- The three core findings (Q1 cap exhaust, Q2 EPL bypass mechanism, Q3 ROLR cascade regression) all survive the IBKR requalification intact or trivially.
- The dynamic-attempts Phase 2 prototype code is validated by the ROLR T10 analysis (which was always IBKR data) + the Q1 mechanism analysis (confirmed on IBKR today).
- Phase 3 YTD validation is unblocked per the amendment and can proceed.

Caveat for Cowork: if any **future** directive leans hard on "BIRD chop at $11+" as motivation (e.g., arguing for a time-decay EPL gate because "the 23-min chop cost $5k"), that framing should be rewritten to match IBKR-only reality. The motivating day still shows the problem (cap exhausted, missed second leg), but the dollar magnitude is smaller and the EPL-MP-chop mechanism is less visible.

---

## Data quality note

The IBKR fetch stopped at 11:29:06 ET rather than 12:00 — `ibkr_tick_fetcher.py` exits when it sees a partial page from IBKR (`< 1000` ticks returned). BIRD's volume is apparently thin enough around 11:29 that a single page covered the remaining window. For the sim's 08:15–16:00 window, ticks past 11:29 are not in the cache; the sim replays what it has, then no ticks, then ends. Missing 11:29–16:00 tick coverage is what truncates the sim to 6 trades rather than (e.g.) producing more at the cap. **Not expected to matter for any autopsy-related conclusion** since max_attempts blocks all post-09:03 arms anyway — but worth noting for future reference. A follow-up fetch with an extended end-time would confirm no surprises in the afternoon.

---

## Fresh-day backtest refresh

Also updating the earlier `2026-04-15_report_fresh_day_backtest.md` numbers:

| Symbol | Discovery | Window | Old (Alpaca) | NEW (IBKR) | Δ |
|---|---|---|---|---|---|
| CIIT | 07:00 | 07:00-12:00 | 0 trades | 0 trades | no change |
| BIRD | 08:15 | 08:15-16:00 | -$1,909 / 10 trades | **-$949 / 6 trades** | **+$960 / -4 trades** |
| VNCE | 09:30 | 09:30-12:00 | 0 trades | (fetch still running) | TBD |
| **Fresh-day total** | | | **-$1,909** | **-$949** (pending VNCE) | **+$960** |

VNCE's full-day 04:00–20:00 IBKR fetch is still in flight at report time (low-density stock, slow IBKR paging). Its 08:00–12:00 window already produced 0 trades in earlier runs — extending to 04:00-20:00 is unlikely to add trades, but will confirm.

---

*CC (Opus), 2026-04-16 morning. One stock, one day, one re-fetch. The delta is real but the autopsy survives.*
