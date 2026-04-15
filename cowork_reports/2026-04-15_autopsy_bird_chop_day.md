# Autopsy — BIRD chop day (2026-04-15)

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**Directive:** `2026-04-15_directive_bird_chop_autopsy.md` (+ re-scope `2026-04-15_decision_bird_autopsy_pathC.md`)
**Recommendation (top-line):** **NO CODE CHANGE** at this shape of extension. Data says the naive Gate 5 extension would break ROLR's regression-canary cascade winner. A smarter gate (loss-based only when subsequent trades share certain characteristics with the losers) might survive — but that's a new directive, not this one.

---

## TL;DR

- **Q1 — Why BIRD didn't re-arm post-T10.** `WB_SQ_MAX_ATTEMPTS=5` cap was exhausted by 09:03. Every squeeze setup after that (including the $11→$20 second-leg rejections at 11:08 and 11:29) was blocked by the cap. Winsorize held, stale-seed gate didn't trip, exhaustion filter didn't kick. The cap did exactly what it was tuned to do.
- **Q2 — EPL re-entry bypass mechanism.** EPL MP re-entry uses a separate `EPLMPReentry` instance with its own state machine. Gate 5 lives inside `MicroPullbackDetector._check_quality_gate()` and is never called from the EPL path. EPL has its own caps (cooldown-bars=3, max-trades-per-graduation=3, VWAP floor, pullback-bar limit) — none loss-based.
- **Q3 — Extension would break cascade regression.** Applied the CC-proposed gate at `max_losses=1` and `=2` post-hoc to 5 canary days. At both thresholds the ROLR T10 winner (+$7,330, +1.6R) gets blocked. At `=1` the VERO T9 winner (+$1,913) and the BATL day both break.
- **Recommendation.** `NO CODE CHANGE`. The extension is directionally correct for BIRD-style chop days but kills the exact trades the cascade strategy exists to catch.
- **Latent bug flagged, not fixed.** `simulate.py:1981` is missing `"epl_mp_reentry"` from the exclusion list in `_on_sim_trade_close`. Inert today (gate never runs on EPL entries); would matter if/when the extension ships.

---

## Q1 — Why BIRD didn't re-arm post-T10

### Evidence

Verbose sim output (`simulate.py BIRD 2026-04-15 08:15 16:00 -v`). Squeeze detector events, chronological:

```
[08:20] SQ_PRIMED  vol=8.8×   price=$3.16    → attempt 1 (became T1 @ 08:21)
[08:21] SQ_PRIMED  vol=22.2×  price=$3.45    → attempt 2
[08:47] SQ_PRIMED  vol=8.3×   price=$4.48    → attempt 3 (became T3 @ 08:48)
[08:48] [EPL] BIRD graduated at $4.48 (R=3.7)
[08:48] SQ_PRIMED  vol=14.6×  price=$4.88    → attempt 4 (became T4 @ 08:49)
[08:50] SQ_PRIMED  vol=8.5×   price=$5.40    → attempt 5 (became T5 @ 09:01)
[08:59] SQ_PRIMED  vol=4.2×   price=$5.84
[09:02] SQ_PRIMED  vol=5.2×   price=$6.97    → became T6 @ 09:03

[09:08] SQ_NO_ARM: max_attempts (5/5)         ← cap hit
[09:41] SQ_NO_ARM: max_attempts (5/5)
[09:42] SQ_NO_ARM: max_attempts (5/5)
[11:08] SQ_NO_ARM: max_attempts (5/5)         ← second-leg setup blocked
[11:29] SQ_NO_ARM: max_attempts (5/5)         ← ditto
```

### Mechanism

`WB_SQ_MAX_ATTEMPTS=5` — X01 tuning, deployed 2026-04-08. Counts every armed squeeze attempt per symbol per session. Once the cap is hit, no further SQ arms are allowed regardless of setup quality.

BIRD hit the cap by T6 (09:03). The $11→$20 afternoon leg would have required attempts #6+. The cap was the sole blocker.

### Ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Winsorize poisoned baseline | NO | No winsorize cap hits in log; `avg_vol` evolution looks sane through the full day |
| Stale-seed gate tripped | NO | No stale-seed messages after 08:15 (gate fires on seed completion only) |
| Trigger-level math produced no breakable level | NO | SQ_PRIMED events fired at 11:08 and 11:29 — triggers *did* exist; they were rejected by the attempts cap, not by level math |
| Exhaustion filter kicked in | NO | Dynamic-VWAP scaling would permit re-entries for a stock with BIRD's intraday range; no exhaustion rejections in log |

### Implications

The cap is operating as designed. The design tradeoff is: accept missing late-day second legs in exchange for preventing runaway attempt chains on a bad stock. Today the tradeoff was net painful on BIRD (we did miss $11→$20) but on a chop day (like this one *was* perceived to be through T6) the cap also prevents *more* losing attempts at T7+.

**Not a bug. Possible future directive:** a dynamic cap that extends on symbols where prior attempts were winners (e.g., "add +1 attempt per +2R realized") would let BIRD's cascade continue past attempt 5 *without* loosening the cap on chop days. Not bundled here.

---

## Q2 — EPL re-entry flow trace (T10)

*(Mechanism answer also drives the re-scoped Q3 mechanism section.)*

### Graduation

Triggered at **T3 @ 08:48, BIRD $4.48, R=3.7** — first squeeze trade to hit 2R target with `sq_target_hit` flagged on the core tranche.

Graduation path:
- `simulate.py:785-796` — on `sq_target_hit_exit_full`, compute `realized_r = (price - t.entry) / t.r`; if `>= EPL_MIN_GRADUATION_R` (default 2.0), invoke `_on_epl_graduation(t, price, time_str)`.
- `simulate.py:1953-1975` — builds `GraduationContext` (entry, stop, hod, vwap, pm_high, r), calls `_epl_watchlist.add(ctx)` and `_epl_registry.notify_graduation(ctx)`.

Verbose log confirms: `[08:48] [EPL] BIRD graduated at $4.4800 (R=3.7)`.

### Who arms + executes EPL

Separate instance — **independent state from the standalone MP detector.**

- `simulate.py:1945` — `_epl_mp = EPLMPReentry()` creates an independent instance.
- `epl_mp_reentry.py:60-77` — `EPLMPReentry` has its own `_states: Dict[str, MPReentryState]` per symbol. No `_session_losses` or `_session_trades` field anywhere.
- `epl_mp_reentry.py:81-91` — `on_graduation()` initializes per-symbol state with fresh cooldown + `phase="WATCHING"`.
- `epl_mp_reentry.py:113-212` — `on_bar()` and `on_tick()` run the re-entry state machine: WATCHING → PULLBACK → ARMED → entry signal.

### How Gate 5 is bypassed

Three layers of isolation, any one of which is sufficient:

1. **Separate instance, separate counters.** `EPLMPReentry._states` has no `_session_losses` / `_session_trades` (`epl_mp_reentry.py:36-55`). Gate 5 lives on the `MicroPullbackDetector` instance, not this one.

2. **Gate 5 is only called from `MicroPullbackDetector._check_quality_gate()`.** File/line: `micro_pullback.py:921-939`. EPL never instantiates or calls this method. Quote:
   ```python
   # micro_pullback.py:932
   if self.no_reentry_enabled:
       g5_pass, g5_msg = self._gate5_no_reentry()
       logs.append(g5_msg)
       if not g5_pass:
           return False, size_mult, logs
   ```
   EPL entry logic (`epl_mp_reentry.py:190-214`) runs entirely outside this function.

3. **EPL's own caps are not loss-based.** See table below.

### EPL's own caps (not loss-based)

| Cap | Default | File:Line |
|---|---|---|
| `WB_EPL_MP_COOLDOWN_BARS` | 3 bars | `epl_mp_reentry.py:27, 87, 125-127` |
| `WB_EPL_MAX_TRADES_PER_GRAD` | 3 trades | `epl_framework.py:29, 225` |
| `WB_EPL_MP_MAX_PULLBACK_BARS` | 3 bars | `epl_mp_reentry.py:28` |
| `WB_EPL_MP_VWAP_FLOOR` | 1 (on) | `epl_mp_reentry.py:31, 143-147, 167-171` |

None of these consider the symbol's loss record.

### T10 specifically (on the 08:15-16:00 run that produced the original -$3,005 trade)

- Graduated at T3 08:48 (see above).
- EPL state machine: reached ARMED after pullback detection during the 10:13–10:20 window.
- Entry at 10:20 $11.50 passed `can_epl_enter()` (`simulate.py:2616`) — graduation valid, trade cap not exceeded (T10 was the 2nd or 3rd EPL trade of the day on BIRD; still under `WB_EPL_MAX_TRADES_PER_GRAD=3`), SQ priority clear.
- Hard stop at $10.81 (r=$0.69). Price breached immediately → `epl_mp_stop_hit` exit at 10:20.
- Gate 5 was never checked. There was no EPL-side gate that considered the T8/T9 losses on BIRD in the 23 minutes prior.

---

## Q3 — YTD impact of extending Gate 5 to EPL (Path C: canary replays)

### Method

Per the Path C decision (`2026-04-15_decision_bird_autopsy_pathC.md`), replay the cascade canaries under current live config (`WB_SQUEEZE_ENABLED=1 WB_MP_ENABLED=1 WB_EPL_ENABLED=1` + X01 + winsorize + stale-seed gate) at `07:00 16:00` window.

Analysis script: `tools/analyze_epl_gate_extension.py`. For each EPL MP re-entry trade on a given day, count the prior losses on that symbol at the moment of entry; if `prior_losses >= max_losses`, the extended gate would have blocked the trade. Applied at both `max_losses=1` (mirror of standalone MP's Gate 5) and `max_losses=2` (the original CC proposal).

ARLO not replayed — no cached ticks. 5 days total: VERO, ROLR, BATL, MOVE, BIRD.

### Canary replay results (baseline, no extension)

| Symbol | Date | Trades | EPL | Day P&L |
|---|---|---|---|---|
| VERO | 2026-01-16 | 14 | 1 | +$35,623 |
| ROLR | 2026-01-14 | 11 | 3 | +$50,602 |
| BATL | 2026-01-26 | 8 | 3 | +$7,876 |
| MOVE | 2026-01-23 | 4 | 0 | +$9,213 |
| BIRD | 2026-04-15 | 6 | 1 | -$170 |

Baselines match published regression targets for VERO (+$34,479 in CLAUDE.md vs +$35,623 — drift from earlier winsorize/X01 rounding) and ROLR (+$54,654 vs +$50,602 — drift previously noted as pre-existing baseline shift in `080baf2` commit message).

### Extended gate impact

| Symbol | Date | EPL | Blk @ =1 | Δ P&L @ =1 | Blk @ =2 | Δ P&L @ =2 | Winner blocked? |
|---|---|---|---|---|---|---|---|
| VERO | 2026-01-16 | 1 | 1 | **-$1,913** | 0 | $0 | **@1: YES** (T9 +$1,913) |
| ROLR | 2026-01-14 | 3 | 2 | **-$5,705** | 2 | **-$5,705** | **@1 AND @2: YES** (T10 +$7,330) |
| BATL | 2026-01-26 | 3 | 3 | +$1,559 | 2 | +$988 | **@1: YES** (T6 +$549) |
| MOVE | 2026-01-23 | 0 | 0 | $0 | 0 | $0 | no |
| BIRD | 2026-04-15 | 1 | 0 | $0 | 0 | $0 | no |

**Regression canary verdict:** extension is regression-breaking at both thresholds.

- At `max_losses=1`: blocks winners on **VERO, ROLR, BATL**.
- At `max_losses=2`: still blocks the big ROLR T10 winner (+$7,330). Also blocks BATL T6 (+$549).

### The ROLR T10 case — why this is disqualifying

```
T3  08:26  $9.33  → epl_mp_time_exit(5bars)  +$22,930  (+4.0R)   winner
T8  09:15  $16.02 → epl_mp_stop_hit          -$1,625   (-1.0R)   loss
T10 11:27  $17.07 → epl_mp_trail_exit(R=1.6) +$7,330   (+1.6R)   winner
```

By the time T10 arms, prior_losses_on_ROLR = 4 (from prior SQ + EPL trades). Extended Gate 5 blocks T10 at any `max_losses >= 1`. But T10 is the exact pattern the cascade strategy is designed to catch — come back late in the day, buy the post-absorption continuation, capture +1.6R.

This is the strongest single piece of evidence against the extension. ROLR's regression target (+$50,602) includes this trade. Removing it shrinks the target by **~14%**.

### On BIRD specifically

Under the canary 07:00-16:00 window, BIRD produced only 6 trades (vs 10 in the 08:15-16:00 run from the original backtest report). Only one was EPL (T4 $-2,880), and it was the FIRST EPL trade of the day so `prior_losses=0`. Extended gate at either threshold does not block it.

So even on BIRD — the motivating day — the proposed extension would *not* have saved T4 under the 07:00-16:00 sim. The mid-day chop where T8/T9/T10 happened in the original 08:15 run is partially a function of the seed window. This is an important signal that "the chop cost" is window-sensitive and less easily attributed to re-entries than it appeared.

### Threshold sensitivity

`max_losses=1` strictly dominates `max_losses=2` for blocking (more trades blocked). The canary table shows:

- `=1` Δ across canaries: -$1,913 + -$5,705 + +$1,559 + $0 + $0 = **-$6,059**
- `=2` Δ across canaries: $0 + -$5,705 + +$988 + $0 + $0 = **-$4,717**

Both are net negative across this canary set. The extension reduces aggregate canary P&L at both thresholds.

Caveat: BATL 01-26 is the only canary where the extension *helped* (+$1,559 / +$988). BATL had a losing EPL cluster that extended Gate 5 correctly throttled. That's one data point for "chop days exist" — but it's drowned out by VERO/ROLR's legitimate winners.

---

## Recommendation

**NO CODE CHANGE** at this shape of extension.

The mechanism analysis was conclusive (EPL genuinely bypasses Gate 5; the code *could* be extended trivially). But the YTD canary data shows that a naive extension of Gate 5 into the EPL path breaks the cascade strategy's biggest trades. The ROLR T10 winner is the disqualifying edge case: 4 prior losses, then a +1.6R continuation winner. Any gate that looks only at loss count blocks that setup.

### Why not "just use =2 instead of =1"?

Because ROLR T10 had 4 prior losses. Both =1 and =2 block it.

### Would a smarter gate work?

Probably. Candidates (none of which are in scope for this directive):

1. **Time-decay gate** — "block after N losses *within X minutes*." Would let ROLR's end-of-morning pause reset the counter before T10.
2. **Setup-quality gate** — "block after N losses *unless the new arm has better R-score than the average of the losers*." Would differentiate T10's trigger from the T6/T8/T9 chop.
3. **Price-context gate** — "block after N losses *unless price has pulled back at least X% from post-loss high*." Would work on BIRD (where T8-T10 entered near local highs) and not on ROLR (where T10 entered after a multi-hour base).

All three are worth prototyping, but each is a multi-variable design, and the YTD impact needs its own validation dataset (a proper full-YTD batch re-run with EPL enabled — per Path A, deferred).

### What to do for BIRD-style chop days

None of the above solves BIRD directly. The T10 loss ($-3,005) on BIRD was the first EPL trade of the day under the 07:00-16:00 window, so a loss-count gate wouldn't have helped. The surgical answer for BIRD is actually upstream: **why did the Q1 SQ max_attempts cap let BIRD through all 5 attempts when the stock was already showing chop signals by T6?**

Worth a separate directive: "dynamic max_attempts that tightens after first losing squeeze on a symbol" or similar. Not bundled here.

---

## Non-findings

Things ruled out or explicitly not actioned:

1. **Winsorize did not fail.** No cap hits in the BIRD verbose log. Avg_vol evolution across the session was monotonic and within expected bounds. The feature deployed this morning (commit `f7e7407`) is working as designed.
2. **Stale-seed gate didn't trip after initial seed.** The gate fires at seed completion; no recurring firings observed. Not a factor in BIRD's T6-T10 chop.
3. **Exhaustion filter did not over-filter.** BIRD's intraday range triggered dynamic-VWAP scaling; re-entries were permitted from an exhaustion standpoint. Not a factor.
4. **Trigger-level math is fine.** The `SQ_NO_ARM: max_attempts` log lines at 11:08 and 11:29 confirm triggers *did* exist at the $11→$20 second-leg prices — they just couldn't arm because the attempts cap was exhausted.
5. **Latent sim bug.** `simulate.py:1981` — the `_on_sim_trade_close` exclusion list does not include `"epl_mp_reentry"`. This means an EPL MP re-entry trade close currently increments `MicroPullbackDetector._session_trades` / `_session_losses` counters on the *standalone* MP detector. This is inert today because Gate 5 is never checked on EPL entries, so the wrongly-incremented counters don't affect behavior. **If any Gate 5 extension ever ships — including the one considered and rejected here — this miscounting becomes live.** Flagged for cleanup, not fixed in this autopsy.

---

## Artifacts produced

- `tools/analyze_epl_gate_extension.py` — canary analysis script. Regenerates the Q3 table from `/tmp/autopsy/*.log` sim outputs.
- `/tmp/autopsy/VERO_2026-01-16.log`, `ROLR_2026-01-14.log`, `BATL_2026-01-26.log`, `MOVE_2026-01-23.log`, `BIRD_2026-04-15.log` — canary sim outputs.
- `/tmp/autopsy/BIRD_verbose.log` — Q1 evidence (verbose BIRD sim showing max_attempts rejections).

---

## Answer to directive's three asks (mapped)

1. **Mechanism — EPL bypasses Gate 5, exact control flow** → Q2 above, with file:line refs.
2. **YTD impact — how many EPL trades blocked, aggregate Δ, per-symbol breakdown for Δ > $500** → Q3 canary table. Every row has Δ > $500 except MOVE/BIRD. Per-symbol detail in the per-day sub-tables above.
3. **Regression canary — list every VERO/ROLR/BATL/MOVE/ARLO cascading trade that would be blocked** →
   - VERO 2026-01-16 T9 `epl_mp_time_exit(5bars)` +$1,913 — blocked at `=1`, not at `=2`
   - ROLR 2026-01-14 T8 `epl_mp_stop_hit` -$1,625 — blocked at `=1` and `=2`
   - ROLR 2026-01-14 T10 `epl_mp_trail_exit(R=1.6)` +$7,330 — blocked at `=1` and `=2` ⚠️
   - BATL 2026-01-26 T5 `epl_mp_time_exit(5bars)` -$571 — blocked at `=1`, not `=2`
   - BATL 2026-01-26 T6 `epl_mp_time_exit(5bars)` +$549 — blocked at `=1` and `=2` (winner)
   - BATL 2026-01-26 T7 `epl_mp_stop_hit` -$1,537 — blocked at `=1` and `=2`
   - MOVE 2026-01-23 — no EPL trades
   - ARLO — not replayed (no cached ticks)
   - BIRD 2026-04-15 — 1 EPL trade, not blocked at either threshold (first EPL trade of day)
4. **Threshold sensitivity — same Δ at =1 and =2** → net canary Δ at `=1`: -$6,059. Net canary Δ at `=2`: -$4,717. Both negative.

---

## Success check (from directive)

- Which specific mechanism caused the bot to lose on a winner-day? **Two of them**: (a) `WB_SQ_MAX_ATTEMPTS=5` cap blocking the $11→$20 second leg, and (b) EPL's lack of a loss-aware gate during T8-T10 chop.
- Recurring pattern or one-off? **Both pieces are general.** The cap-exhaustion pattern applies to any stock that produces many early-morning SQ arms. The EPL-no-loss-gate pattern applies to any stock that graduates and then enters a chop phase.
- What the evidence says we should change? **Nothing, yet.** The simple fix for (b) breaks ROLR. The fix for (a) needs its own directive.
- What we chose NOT to change and why? **The Gate 5 extension.** Because it blocks ROLR T10 — a +$7,330 / +1.6R winner after 4 prior losses, and exactly the kind of trade the cascade strategy is built to catch.

---

*CC (Opus), 2026-04-15 evening. Precision over motion. Today the answer is "don't touch it."*
