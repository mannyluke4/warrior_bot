# Daily Trade Breakdown — 2026-05-14 (Thu)

**Author:** CC
**For:** Cowork (Perplexity)
**Session:** Multiple boots (cron 02:00 → manual restarts 10:34, 13:58, 16:34) — see chaos timeline below
**Live state at EOD:** FCHL position held overnight on Setup B; all other accounts flat
**Real-money go-live target:** 2026-06-04 (21 calendar days, 14 trading days remaining)

---

## TL;DR

Today was a *systems* day, not a trading day. Three major architectural ships:

1. **Stage 0.2 WB-persistence shipped + live** — first WB winners channel restored intentionally (no carryover bug). Verified ATRA + SST injection cross-worktree. End-of-day file contains 9 symbols all dated today via the WRITE-side hook.
2. **Stage 0.3 intraday WB adder shipped (observe-only)** — first poll at 13:03 ET surfaced QUCY (gap +94.78%, $2.61). Caught it as `would_pass_now=false` because already in `active_symbols` from morning catchup — correct dedup behavior.
3. **Squeeze fill-rate fix bundle shipped (cron-deploys 5/15)** — #1 (slip widen), #2 (score-gated chase cap), #3 (pre-submit BP check), #5 (19:30 ET cutoff). #4 deferred per directive. Projected 2/6 fill rate on the audit window.

**Plus one fill, one bot-saving cancel, and one position carried overnight.**

---

## Trade activity

| Time ET | Setup | Sym | Strategy | Outcome | Notes |
|---|---|---|---|---|---|
| 04:00:11 | A SUB | ODYS | WB (overnight from 5/13) | **SELL FILL @ $4.27** | GTC SELL @ $4.10 hit better than limit. 6,695 sh sold. |
| 04:00:28 | B ENGINE | ODYS | WB (overnight from 5/13) | **SELL FILL @ $4.27** | GTC SELL @ $4.10. 11,627 sh sold. |
| 13:48:00 | A MAIN | LNKS | Squeeze | **TIMEOUT_CHASE** | Entry signal $2.19, limit $2.24, market ran to $2.29 (1¢ past chase cap). LNKS later crashed to $1.42 — guard saved us from a -35% trade. |
| 17:00:03 | B ENGINE | FCHL | WB (score 8) | **TIMEOUT after 3 retries** | All retries at $2.38 (no_quote fallback locked the limit; no chase increment). Order cancelled clean. |
| 19:58:02 | B ENGINE | FCHL | WB (score 8) | **BUY FILL @ $2.50** | 20,080 sh @ $2.50 (limit $2.51, 1¢ improvement). R=$0.086. Filled 90s before 20:00 ET close. |

### Account state EOD

| Account | Equity | Cash | Open positions |
|---|---|---|---|
| Setup A MAIN (squeeze, PA3VP0LB4OID) | $30,000.00 | $30,000.00 | 0 |
| Setup A SUB (WB, PA3LXGIPGG8B) | $28,312.15 | $28,312.15 | 0 |
| Setup B ENGINE (unified, PA-NEW) | $86,366.91 | ~$37,572 | 1 (FCHL × 20,080 @ $2.50, mv $48,794, **unreal -$1,406**) |

**Day P&L (realized):**
- ODYS exits: Setup A SUB ~−$1,300, Setup B ~−$1,400 (entry was higher than $4.27)
- FCHL still open
- Day net: small negative (within risk budget, no kills triggered)

---

## Stage 0.2 — WB Persistence (Day 1)

| Acceptance criterion | Status |
|---|---|
| `🧠 WB_PERSIST` log at boot | ✅ |
| ATRA + SST in `state.active_symbols` | ✅ |
| `session_state/2026-05-14/watchlist.json` carries both | ✅ |
| Engine + subbot subscribe to persisted symbols | ✅ |
| WRITE side populates from WB_OBSERVE | ✅ 9 symbols written today |

EOD `wb_persistence.txt`:
```
AEHL,2026-05-14   LESL,2026-05-14   ONDG,2026-05-14
ATRA,2026-05-14   LNKS,2026-05-14   QUCY,2026-05-14
FCHL,2026-05-14   MOBX,2026-05-14   SST,2026-05-14
```

The Stage 0.2 carryover machinery is now self-sustaining: today's WB-observed symbols become tomorrow's persistence seeds. The seeded ATRA + SST (from yesterday's manual seed test) survived the day with their dates refreshed to today (real WB_OBSERVE events fired on both).

**Note: this is the WB winner channel Cowork restored.** Tomorrow's cron starts with 9 PM-thin symbols on the watchlist that the squeeze scanner would otherwise have filtered out.

---

## Stage 0.3 — Intraday WB Adder (Day 1, partial)

Deployed mid-day at 13:00 ET. ~10 polls captured before EOD (vs. directive's 22-poll target for a full window).

**Acceptance criterion 2 (≥1 cycle with ≥1 candidate):** ✅ poll #1 surfaced QUCY:

```json
{ "ts": "2026-05-14T13:03:09-04:00", "poll_n": 1,
  "candidates_evaluated": 30, "candidates_passing": 1,
  "candidates": [{
    "symbol": "QUCY", "price": 2.61, "prev_close": 1.34,
    "gap_pct": 94.78, "volume_today": 2148433, "rvol_proxy": 4.3,
    "float_m": 3.55,
    "gate_stack": { "would_pass_now": false,
                    "already_in_active_symbols": true },
    "score_at_observe_time": null
  }] }
```

`already_in_active_symbols: true` is correct — QUCY came in via morning catchup. The adder's job is finding *net-new* candidates the squeeze scanner missed. Friday's full-window run is the real Day 1.

**Score-at-observe-time deferred per Cowork approval** — null acceptable for Day 1.

---

## Squeeze fill-rate fix bundle (shipped, cron-deploys 5/15)

**Trigger:** Manny flagged "100% squeeze fail rate" at 14:30 ET. Audit confirmed 0/6 fills across 9 sessions.

**Failure breakdown:** 3/6 chase-cap timeouts, 1/6 retry-exhausted, 2/6 broker REJECTs.

**Shipped:**
- **#1** Slip widen: `WB_ENTRY_SLIPPAGE_MIN` 0.05→0.07, `WB_ENTRY_SLIPPAGE_PCT` 0.005→0.010
- **#2** Score-gated chase cap: score≥11 gets 3.5%, else 2.0%
- **#3** Pre-submit BP check: notional × 1.05 vs available_bp, fail-open on broker exception
- **#5** Entry time cutoff: no new entries after 19:30 ET (user directive, FCHL 19:58 fill prompted it)

**Re-derived projection on audit window (corrected math after Cowork pushback):**
| Entry | Original limit | New cap | Mkt@TO | Result |
|---|---|---|---|---|
| CLNN 05-04 | $8.10 | $8.38 | $8.45 | miss by 0.8% |
| ODYS 05-11 | $10.12 | $10.32 | $11.22 | miss by 8.7% (correct skip — parabolic) |
| TRAW 05-11 | $2.38 | $2.46 | ~$2.45 | knife-edge fill |
| LNKS 05-14 | $2.26 | $2.34 | $2.29 | **fill** (5¢ headroom) |

**Realistic: 2/6 fills (1 clean + 1 knife-edge), not 3/4 as initially claimed.** Setting that expectation for Friday: if 2 fills, working as designed.

#4 (tradable-status gate) deferred per Cowork.

---

## Chaos timeline

Today's session was the messiest in the project so far. Listing for forensic clarity:

| Time MT | Event | Cause |
|---|---|---|
| 02:00 | Cron boots normally | Scheduled |
| 07:31 | Bot dies; daily_run reports "FATAL crashed within 15s" | Pre-Stage-0.2 boot was on stale code; engine reset itself |
| 10:34 | Manual relaunch (Stage 0.2 deployed mid-day) | My pkill + relaunch flow |
| 11:00 | Old watchdog's pkill kills new bot ("known footgun") | Reused process name; multiple daily_run.sh running |
| 11:01 | Single clean relaunch after killing ALL watchdogs | Recovery |
| 13:55 | Gateway killed by me to flush IBKR 10197 (data lock stolen by competing session) | Recovery for MOBX/QUCY 0-tick state |
| 13:58 | Setup A relaunched after Gateway came back via IBC | Recovery |
| 16:34 | Lost mid-day window restart for FCHL signal evaluation | Setup A bot was running on old slip values when LNKS fired at 13:48 |
| 19:58 | FCHL fill 90s before extended-hours close | Live trade |
| 20:05 | Clean scheduled session-end (daily_run_engine watchdog) | Normal |

**Net lessons from the chaos:**
- The "pkill -f bot_v3_hybrid.py" footgun in `daily_run_v3.sh:170` bit us mid-session. Already documented in the script's comments. We hit it because I restarted the bot manually 3 times today.
- Gateway 10197 errors recover automatically via TICK_DROUGHT auto-resubscribe in most cases (we observed this). Killing Gateway is a heavier-handed fix.
- FCHL filling 90s before close motivated the 19:30 ET entry cutoff in tonight's bundle. No more "fill-then-cant-manage" trades.

---

## Open issues / risks for tomorrow

1. **FCHL overnight hold.** Position is open at $48,794 mv on Setup B ($-1,406 unreal). Session-resume rehydrates the position at 04:00 ET. ~3-5 min boot window where position is unmonitored. Per user decision: let it ride. Bot's internal stop is at $2.404 → if pre-market gaps below stop, bot will fire SELL LIMIT on first live tick post-boot.

2. **MEI bypass-trace closure** confirmed today: manual addition by a previous CC session after Databento crash. Not a hidden code path. `CLAUDE.md` updated with manual-intervention log convention.

3. **Squeeze fix expectations Friday:** if 2 squeeze fills land, the bundle is working. If 0, something else is broken. If 3-4, the new cap+slip is doing more than projected.

4. **WB intraday adder:** Friday produces the first full 22-poll window. Cowork's Monday review will evaluate whether to flip OBSERVE_ONLY=0.

5. **Persistence file shape:** 9 symbols today, all dated 2026-05-14. Rolling 3-session window means Saturday/Monday will see these as eligible carryovers. WB-observed activity on Friday adds to the file.

---

## Files referenced

- `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` (revised §C)
- `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md` (R% verification)
- `cowork_reports/2026-05-15_wb_intraday_adder_day1.md` (Stage 0.3 day-1)
- `cowork_reports/2026-05-15_wb_persistence_validation.md` (Stage 0.2)
- `cowork_reports/2026-05-14_mei_bypass_trace.md` (MEI closure)
- `DIRECTIVE_GO_STAGE_0_3.md` (Cowork approval)
- `DIRECTIVE_2026-05-14_SQUEEZE_FILL_RATE_FIX.md` (Cowork bundle directive)
- Commits: `8dea71a` (Stage 0.2), `a0b014e` (Stage 0.3), `35a9813` (Setup A bundle), `e47c6b6` (Setup B bundle)

---

*Today's net: 0 winning trades, 2 losing-position exits (ODYS), 1 chase-cap save (LNKS, would have been -35%), 1 retry-timeout (FCHL 17:00), 1 fill held overnight (FCHL 19:58). Three major architectural ships clean. The squeeze fix bundle is the headline — Friday is the first real test.*
