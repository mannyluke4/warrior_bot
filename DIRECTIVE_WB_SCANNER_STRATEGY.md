# WB Scanner Strategy — Directive Response to Filter Gap Investigation

**Date:** 2026-05-14
**Author:** Cowork (Perplexity)
**For:** CC
**Source:** `cowork_reports/2026-05-14_wb_filter_gap_feedback.md` + `cowork_reports/2026-05-14_wb_vs_squeeze_filter_analysis.md`
**Trigger:** Manny's question: "Is WB only viable as a second-hand squeeze play, or does it warrant its own scan/watchlist?"

---

## TL;DR — the answer

**WB is NOT a clean second-hand squeeze play.** The data shows that 3 of 4 recent WB winners arrived on the watchlist by *accident* (stale `watchlist.txt` carryover from prior days, just fixed yesterday). The squeeze filter has been actively *blocking* most WB-shaped setups; the carryover bug was the channel keeping WB profitable. With that channel closed, WB needs a deliberate candidate source.

**But — do NOT build a full parallel WB scanner on n=4 winners.** The sample is too small and the loser set also came from the squeeze watchlist. Loosening the universe likely brings in more losers per winner unless intraday filters separate them. We need real backtest evidence before forking the scanner architecture.

**Rollout: 3 stages.** Stage 0 ships in the next 24 hours and is essentially free; Stage 1 ships once the backtest validates; Stage 2 is only built if the data supports it.

| Stage | Ship | Timing |
|---|---|---|
| 0 | Trace MEI 05-13 bypass + ship minimal intraday WB adder + restore *targeted* carryover for WB-observed symbols | this week |
| 1 | WB backtest Jan-Apr 2026 on relaxed universe; decide WB-specific intraday filter set | next 2-3 weeks |
| 2 | Parallel WB scanner with tagged-watchlist architecture (if Stage 1 says yes) | conditional |

---

## 1. Why the n=4 finding matters more than it looks

CC framed it as "n=4 is small." That's correct — but the *structural* finding is independent of sample size: **the carryover mechanism is the only reason WB has been profitable, and it's a bug, not a feature.** Three observations make this conclusion robust:

1. **4 of 4 winners had PM volume below 30K floor.** Not "most." Not "some." All four. That's not noise; that's a pattern of strategy-mismatched-filter.
2. **The mechanism is the same as the bug we just fixed.** FATN 05-05 and SST 05-11 both came from `watchlist.txt` lines that should have been wiped between sessions. We didn't intentionally route WB candidates through carryover — it was a side effect of an unrelated bug.
3. **The fix is intentional, the side effect is not.** Yesterday's `watchlist.txt` wipe at boot (commit `a38ce72`) was correct for squeeze integrity. We didn't realize at the time that we were also closing WB's main candidate channel.

So the question isn't "is WB viable on squeeze candidates?" — empirically, it's been the opposite, **squeeze candidates are not where WB wins.** The question is now: **what IS the right candidate source for WB, and how do we discover it without building expensive infrastructure on noisy data?**

---

## 2. Answers to CC's 6 questions

### Q1 — Is n=4 enough to act on, or do we need a backtest?

**Both.** The structural finding (PM-volume mismatch) is enough to act on at the candidate-source level: it's clear the squeeze PM-volume floor is the wrong filter for WB. But the SHAPE of the right filter — what intraday gates, what RVOL window, what time-of-day cutoffs — requires backtest data.

**Minimum sample for filter design:** I want **≥80 WB-shaped trades** before locking any specific intraday filter (gap, RVOL, time-of-day). At current rate (~2.5 WB trades/day), that's 32 trading days — too long. **Run a Jan-Apr 2026 backtest** against a synthetic relaxed universe to get the sample in 1-2 weeks of compute work.

Backtest spec:
- Universe: every small-cap (price $2-30, float ≤30M) that traded ≥1M shares on the day
- Apply WB detector to 1m bars 09:30-20:00 ET each day
- Record every WB_ARM event with the score, R%, intraday context (gap-from-prev-close, intraday RVOL, time-of-day, VWAP relationship, HOD distance, MACD direction)
- Compute P&L per ARM using simulated entry + the post-Wed gate stack (R% floor, MACD sub-gate, same-session blacklist, pre-9MT block)
- Stratify wins vs losses on the intraday features

This gives us the data to design Stage 1's intraday filter without guessing.

### Q2 — What's the optimal intraday WB filter?

**Don't pick one yet — let the backtest pick.** But here are the candidates the backtest must score, ranked by my prior:

| Filter | Expected effect | Why |
|---|---|---|
| **Intraday RVOL ≥ 3× at WB_ARM time** | Strong winner | All 4 winners showed elevated bar-volume; the losers often armed in thin tape |
| **Score ≥ 8** | Already in place | Existing filter |
| **Time-of-day ≥ 09:45 ET AND ≤ 15:30 ET** | Likely winner | All 4 winners were 11:08-19:37; the pre-market and late-day arms were losers |
| **Gap-from-prev-close ≥ 3% (NOT premarket gap)** | Moderate | Captures the "intraday trender" pattern (FATN, SST). Misses ATRA-class +68% gappers — but ATRA-class would still get through the existing squeeze huge-gap bypass. |
| **VWAP relationship: price > VWAP (above for longs)** | Moderate | Standard wave-breakout setup |
| **HOD-distance ≤ 5% (price within 5% of HOD)** | Possible filter | But ATRA 05-08 was at 17:09 well below HOD — risk this kills the "afternoon reclaim" winners |
| **MACD histogram positive on ARM** | Already shipping (Wed) | v3 sub-gate |

The backtest should run a 2^N gate-combination analysis and report the Pareto-best filter set by net P&L per trade. **Hard requirement: zero winner false positives in the validation set across the 4 known winners FATN 05-05 / ATRA 05-08 / SST 05-11 / MEI 05-13.**

### Q3 — Should we restore the carryover deliberately?

**Yes — but only for WB-observed symbols, not all squeeze candidates.** The right primitive is a "WB watchlist persistence" layer separate from squeeze.

Spec:
- Track every symbol that had a `WB_OBSERVE` (any wave_id) during a session in a new file: `wb_observed_today.txt`
- At EOD, write `wb_observed_today.txt` → `wb_persistence.txt` keeping the last 3 sessions of WB-observed symbols
- At boot, `wb_persistence.txt` symbols are added to the watchlist with a tag `[wb_persist=1]`
- Symbols on the watchlist via `wb_persist` skip the squeeze PM-volume filter (since they earned their spot via prior-day WB activity, not via PM action)
- Symbols expire after 3 sessions of no further WB_OBSERVE activity

This restores the FATN/SST winners' channel without re-introducing the stale-everything bug. It's narrow: only WB-active symbols carry over, only for 3 sessions, only for WB consideration.

**Why 3 sessions:** FATN 05-05 winner came from a 1-day-old carryover. SST 05-11 came from a 4-day-old carryover (last fresh scan 05-07). 3 sessions covers most cases without indefinite drift.

### Q4 — Trace MEI 05-13's bypass path

**This is the highest-priority diagnostic this week.** A winner appearing without trace in the scanner log means there's a code path nobody documented. We need to know whether it's:

- (a) An intraday rescan path in `bot_v3_hybrid.py` that adds symbols mid-day from a different source (e.g., Polygon top-gainers, IBKR-scanner-via-TWS, etc.)
- (b) A manual addition you or somebody made to `watchlist.txt` directly
- (c) A scanner code path that *did* run but failed to log to `scanner.log`
- (d) The squeeze scanner ran a midday loop nobody knew about
- (e) `bot_v3_hybrid.poll_watchlist` is fetching from somewhere other than the daily scan output

**Action:** trace it with these specific commands:

```bash
# 1. Find every reference to MEI on 05-13 across all logs/state
grep -rn "MEI" warrior_bot/logs/2026-05-13_*.log warrior_bot/scanner_results/ warrior_bot/state/ 2>/dev/null

# 2. Check if MEI was in watchlist.txt at any point on 05-13
ls -la warrior_bot/watchlist*.txt warrior_bot/state/
git log -p --all -- warrior_bot/watchlist.txt 2>/dev/null | grep -A2 -B2 MEI

# 3. Find every code path that writes to watchlist.txt or adds symbols
grep -rn "watchlist" warrior_bot/*.py warrior_bot/**/*.py | grep -i "write\|append\|add\|update"

# 4. Check cron and run scripts for any rescan loop
grep -rn "rescan\|poll\|refresh" warrior_bot/daily_run_v3.sh warrior_bot/scripts/*.sh
```

Report findings to `cowork_reports/2026-05-15_mei_bypass_trace.md`. If we find an undocumented code path, document it. If we find a bug, fix it. If we find a manual addition, note it in the run-book and move on.

**Until MEI's path is traced, we cannot have confidence in any WB scanner architecture** — there may be other hidden channels feeding the bot.

### Q5 — Are losers on the watchlist that a WB-aware filter would have rejected?

**Yes, likely most of them — but the backtest must confirm.** Quick eyeball of the 15-loser list:

- **CLNN losers** (5/5 ×4): Score 7-9, but CLNN never made the WB-feature winners list. **A WB-specific filter requiring "WB_OBSERVE wave_id ≥ N in recent history" would have excluded CLNN as a WB candidate** — CLNN was a squeeze candidate fundamentally.
- **ENSC losers** (5/12 + 5/13): pre-9MT or low R%. The new gate stack (H#10 + H#14) catches these. A WB-specific scanner wouldn't have added much.
- **TRAW 05-12 loss**: post-9MT, R% 2.17%, "clean loss" — would have passed any reasonable WB filter. Tuition.
- **ATRA losers** (5/11 ×3): ATRA WAS a known WB-active symbol. Filtering on "intraday RVOL ≥ 3× at ARM time" might separate the +$2,090 SST winner from the ATRA losers, but this needs the backtest.
- **NVOX loss** (5/11): price $16+, far above the squeeze sweet spot, score 9 but immediate stop-out. Was a 25-second trade. WB-RVOL filter might catch this.

The non-rigorous estimate: maybe 8-10 of the 15 losers would have been excluded by a properly-designed WB-specific intraday filter (RVOL + time-of-day + WB-history). If true, dropping the PM-volume floor net-saves us ~$3-4K across the same window. **The backtest answers this rigorously.**

### Q6 — Multi-strategy scanner architecture

**Tagged-watchlist architecture, not parallel scanners.** Rationale:

- Parallel scanners = 2× the IBKR snapshot load, 2× the state files to manage, 2× the failure surface
- Tagged watchlist = one scanner runs N filter sets, writes one annotated file: each row is `symbol, passed_squeeze, passed_wb, passed_wb_persist, source, scan_ts`
- Bot subscribes to the watchlist and filters per-strategy: squeeze_bot only reads `passed_squeeze=True` rows, wb_bot only reads `passed_wb=True OR passed_wb_persist=True` rows
- Adding a 3rd strategy later = adding a column, not adding a service

Specifically for the .env / config:
```
SCANNER_PM_FILTER_SQUEEZE='{"gap_min":5,"pm_vol_min":30000,"float_max":20,"price_min":2,"price_max":20,"rvol_min":1.5}'
SCANNER_PM_FILTER_WB='{"gap_min":3,"pm_vol_min":0,"float_max":30,"price_min":2,"price_max":30,"rvol_min":0}'
SCANNER_INTRADAY_WB_FILTER='{"poll_min":15,"gap_min":3,"rvol_intraday_min":3,"price_min":2,"price_max":30,"time_start":"09:45","time_end":"15:30"}'
```

The intraday WB filter is the NEW component — a separate poll loop at 15-min intervals during RTH that adds `passed_wb_intraday=True` rows to the watchlist.

---

## 3. The 3-stage rollout

### Stage 0 — ships this week (no backtest needed)

**0.1. Trace MEI 05-13 bypass** (P0 — blocks everything else):
- Owner: CC
- Report: `cowork_reports/2026-05-15_mei_bypass_trace.md`
- Acceptance: known mechanism, documented, no other hidden channels

**0.2. Targeted WB-persistence carryover** (per Q3 spec):
- New file: `wb_persistence.txt` tracks WB-observed symbols for last 3 sessions
- At boot, these symbols are added to the watchlist with `passed_wb_persist=True` tag (treating the watchlist as already tagged even before full Stage 2 architecture lands — for now this is just `wb_persistence.txt` read as a supplemental file by `wb_bot.py`)
- The `wb_bot` accepts these symbols regardless of squeeze PM-volume floor
- Default: ON. Env: `WB_PERSIST_ENABLED=1`, `WB_PERSIST_SESSIONS=3`

**0.3. Minimal intraday WB adder** (provisional spec, no backtest yet):
- 15-min RTH polling loop (09:45-15:30 ET)
- Filter: `gap_from_prev_close ≥ 3% AND intraday_rvol_5m ≥ 3× AND price 2-30`
- Appends matches to `wb_observed_today.txt` (which feeds `wb_persistence.txt`)
- `wb_bot.py` reads from `wb_observed_today.txt` in addition to the main watchlist
- **Default: OFF for first 3 trading days.** Run in observe-only — log what it WOULD have added, don't actually add to the live watchlist. Compare against actual wins/losses. Flip to ON only if it would have caught ≥1 of the 4 winners in a re-run scenario.
- Env: `WB_INTRADAY_ADDER_ENABLED=0` (observe), `WB_INTRADAY_ADDER_OBSERVE_ONLY=1`, polling params per `.env`

**0.4. Restore CLNN to losers blocklist if appropriate:**
- CLNN had 4 WB losses on 05-05 alone (-$2,893 total). It's a squeeze candidate that scored well for WB. The cross-session blacklist (`xsession_bl`) due to ship Mon should catch this. Confirm CLNN ends up blacklisted when xsession_bl flips on 5/18.

### Stage 1 — ships in 2-3 weeks (backtest-driven)

**1.1. WB backtest Jan-Apr 2026** (per Q1 spec):
- Owner: CC (or you, if you want to run it locally with the existing backtest framework)
- Universe: relaxed (gap≥3%, no PM floor, price $2-30, float ≤30M, traded ≥1M shares)
- Apply WB detector + post-Wed gate stack
- Output: per-arm record with all intraday features + outcome
- Report: `cowork_reports/2026-05-XX_wb_backtest_jan_apr.md`

**1.2. Filter design from backtest:**
- Pareto analysis of gate combinations: net P&L per trade vs # trades
- Lock the intraday WB filter set
- Validate against the n=4 winners + 15 losers from May (must preserve ≥3/4 winners, reject ≥10/15 losers)

**1.3. Production rollout:**
- Flip `WB_INTRADAY_ADDER_ENABLED=1` with the backtest-validated filter set
- Update `WB_PERSIST_ENABLED` parameters if backtest suggests different session count

### Stage 2 — conditional, only if Stage 1 backtest supports it

**2.1. Tagged-watchlist architecture (per Q6 spec):**
- Refactor `live_scanner.py` to run multiple filter sets, write one tagged watchlist
- Refactor `wb_bot.py` and `squeeze_bot.py` and `bot_v3_hybrid.py` to read tagged rows
- This is the big infrastructure piece — only ship if the data supports the complexity

**2.2. Multi-strategy scanner integration:**
- Each strategy declares its filter requirements in `.env`
- Scanner runs all of them in one IBKR snapshot pass
- Tagged watchlist is the single source of truth

---

## 4. What ships this week — concrete checklist

- [ ] **Tonight / Thu PM:** CC traces MEI 05-13 bypass per §Q4. Report: `cowork_reports/2026-05-15_mei_bypass_trace.md`
- [ ] **Fri 5/15:** CC ships targeted WB-persistence (§0.2). Owner: CC. Acceptance: synthetic test where yesterday's `wb_observed_today.txt` contains "ATRA, SST" → these appear on today's watchlist with `[wb_persist=1]` tag → `wb_bot.py` accepts them even when their PM volume is 0.
- [ ] **Fri 5/15 EOD:** CC ships intraday adder in observe-only mode (§0.3). Owner: CC. Daily reports tabulate what the adder WOULD have added.
- [ ] **Mon 5/18:** Review observe-only intraday adder output for Fri 5/15. If it would have surfaced ≥1 known winner pattern, flip to live for week of 5/18.
- [ ] **Mon 5/18:** xsession_bl ships per existing plan; verify CLNN ends up blacklisted.
- [ ] **Tue 5/19:** Cowork reviews 5 days of new data + intraday-adder telemetry, decides whether to commission the Jan-Apr backtest.

---

## 5. What we are NOT doing this week

1. **Not building a parallel WB scanner** (Stage 2). The data doesn't support the infrastructure cost yet.
2. **Not dropping the squeeze PM-volume filter** for everyone. The squeeze strategy still depends on it.
3. **Not loosening the squeeze filter generally.** Squeeze losses haven't been the problem; WB candidate discovery is the problem.
4. **Not committing to specific intraday filter values** beyond the provisional Stage 0 set. Backtest will refine.
5. **Not refactoring the watchlist file format** until Stage 2 (if at all). For now we use parallel files (`watchlist.txt`, `wb_persistence.txt`, `wb_observed_today.txt`).

---

## 6. Risk and what could go wrong

**Risk 1: WB-persistence brings back losers we just got rid of.**
Mitigation: persistence only carries forward symbols with prior WB_OBSERVE activity, not all squeeze candidates. The stale-watchlist bug carried EVERY prior symbol; this carries only WB-active ones. Sample size is too small to be sure but the mechanism is narrower.

**Risk 2: Intraday adder surfaces only chaff in observe-only.**
Acceptable. If after 3 sessions the adder hasn't surfaced anything that looked like a winner candidate, we kill it and lean on persistence + the backtest-driven Stage 1 work.

**Risk 3: MEI 05-13 trace reveals a known-bad code path we can't easily fix.**
If MEI came via manual addition, fine — document and move on. If MEI came via an undocumented `bot_v3_hybrid.poll_watchlist` rescan, we trace its filter logic and decide whether to formalize it as Stage 0.5 or rip it out.

**Risk 4: Backtest results are noisy / inconclusive.**
Mitigation: ≥80 trades required for filter design. If Jan-Apr produces ~80 trades and the gate-combination analysis shows no clear Pareto front, we either expand to 2023+2024+2025 (more compute) or accept that the squeeze-derived universe is "good enough" with persistence and intraday adder.

**Risk 5: We're solving the wrong problem.**
The big finding today was that WB has been winning on accident. The honest reading is: WB's edge is currently unclear. The backtest may reveal WB has no real edge at all once filter accidents are removed. If that happens, we deprioritize WB and lean on squeeze + future strategies. **This is a real possibility worth naming.** The +$2,500 ATRA winner is doing a lot of heavy lifting in the 4-winner set; remove ATRA and we're at 3 winners totaling $3,530 vs 15 losers totaling $8,411 = clearly unprofitable.

---

## 7. Tone note

CC's investigation here was *exactly* the kind of work that prevents weeks of wasted iteration. Finding that the watchlist carryover bug was the main thing keeping WB profitable is a P0 insight that changes our entire understanding of where WB's edge is — or isn't.

The right reaction is NOT to scramble to rebuild what we just broke. It's:
1. Trace the remaining mystery (MEI bypass)
2. Restore the narrow, intentional version of what was accidental (WB-persistence)
3. Get real data via the backtest before building infrastructure
4. Be open to the possibility that WB doesn't have an edge once accidents are removed

If the backtest comes back negative for WB, that's not a failure — it's the cheapest possible discovery that we should be spending engineering time elsewhere. **The whole point of the gate stack + analytics work this week has been to give us the tools to know quickly whether each strategy is actually working.** This is what those tools are for.

---

## 8. Files referenced

- `cowork_reports/2026-05-14_wb_filter_gap_feedback.md` (CC's investigation)
- `cowork_reports/2026-05-14_wb_vs_squeeze_filter_analysis.md` (underlying data)
- `cowork_reports/2026-05-13_engine_seed_gap_feedback.md` (related — engine-side context)
- `live_scanner.py`, `wb_bot.py`, `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `daily_run_v3.sh`
- `watchlist.txt` (current; to be supplemented with `wb_persistence.txt` and `wb_observed_today.txt`)

**Reports CC owes Cowork:**
1. **By Thu EOD 5/14:** `cowork_reports/2026-05-15_mei_bypass_trace.md` (the MEI investigation)
2. **By Fri EOD 5/15:** `cowork_reports/2026-05-15_wb_persistence_validation.md` (synthetic test of WB-persistence layer)
3. **By Mon EOD 5/18:** `cowork_reports/2026-05-18_wb_intraday_adder_observe_3day.md` (3 days of observe-only intraday adder telemetry)
4. **By Tue 5/19:** decision memo on whether to commission Jan-Apr backtest
