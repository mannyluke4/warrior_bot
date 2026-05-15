# Squeeze Entry Fill-Rate Forensic Audit — 2026-05-04 to 2026-05-14

**Window:** 9 trading days (5/4, 5/5, 5/6, 5/7, 5/8, 5/11, 5/12, 5/13, 5/14)
**Scope:** Main bot (`bot_v3_hybrid.py`, IBKR) squeeze ENTRY attempts. Engine sub-bot (`bot_v2_engine`, Alpaca) included for contrast.
**Verdict:** Main-bot squeeze fill rate = **0/6 (0%)**. Manny's report is confirmed.

---

## A. Per-attempt table (main bot, IBKR)

| Date | Symbol | Entry time (ET) | Signal $ | Limit $ | R $ | Score | Outcome | Mkt @ TO | Notes |
|------|--------|-----------------|----------|---------|------|-------|---------|----------|-------|
| 05-04 | CRE | 14:58:01 | 4.0200 | 4.07 | 0.1200 | 11.0 | **REJECTED** | — | IBKR Err 201: "closing-only status — no new opens" (security restricted) |
| 05-04 | CLNN | 15:40:00 | 8.0200 | 8.07 | 0.2700 | 11.0 | **TIMEOUT_CHASE** | 8.45 | mkt +4.7% past limit, +2.7% past chase cap of $8.23 |
| 05-07 | ATRA | 10:49:00 | 8.0200 | 8.07 | 0.1200 | 9.6 | **REJECTED** | — | IBKR Err 201: insufficient funds (need $30,649 init margin vs $30,447 ELV — TRAW position open) |
| 05-11 | ODYS | 08:48:00 | 10.0200 | 10.07 | 0.1200 | 10.0 | **TIMEOUT_CHASE** | 11.22 | mkt +11.4% past limit, +9.2% past chase cap of $10.27. Pre-market parabolic. |
| 05-11 | TRAW | 09:31:00 | 2.3052 | 2.36 | 0.0952 | 12.0 | **TIMEOUT_RETRIES** | ~2.45+ | 3 chases ($2.36→$2.40→$2.44→$2.45), still no taker. Open-bell illiquid limit. |
| 05-13 | ATRA | 14:34:00 | 9.8088 | — | 0.0588 | 12.0 | SKIP (pre-order) | — | `R=0.0588 < min 0.06` — sizing gate; never reached broker |
| 05-14 | LNKS | 13:48:00 | 2.1904 | 2.24 | 0.0604 | 12.0 | **TIMEOUT_CHASE** | 2.29 | mkt +2.2% past limit, +0.4% past chase cap of $2.28 — knife-edge miss |

**Engine sub-bot (Alpaca, for contrast):** 5/13 ATRA filled @ $10.50 (limit $10.59, 1.0% buffer), VNET filled @ $11.29 (limit $11.40). The same ATRA setup the main bot skipped on R-gate, engine took 44 min earlier with R=$0.27 because it priced off Alpaca's last trade ($10.49), not IBKR's $9.81 ARM level. Both engine fills used `buffer_pct=1.0` (1% over signal), vs main bot's `slip=$0.05` (~0.5–2.5% over signal depending on price).

## B. Aggregate stats

- Total squeeze ENTRY signals (main bot): 7
- Reached broker as BUY limit: 6 (1 skipped by R-gate)
- **Fills: 0 / 6 = 0% fill rate**
- Failure breakdown:
  - **TIMEOUT_CHASE (price ran past 2% cap): 3 / 6 (50%)** — CLNN, ODYS, LNKS
  - **TIMEOUT_RETRIES (no taker after 3 chases): 1 / 6 (17%)** — TRAW
  - **REJECTED (broker-side): 2 / 6 (33%)** — CRE (closing-only), ATRA (insufficient margin)

## C. Pattern analysis

**Dominant failure mode: "price ran past chase ceiling" — 4 / 6 (67%, counting TRAW's retry-exhaust as the same root cause: tight initial limit + chases that can't catch a moving market).**

1. **Cap is tighter than initial slip on low-priced names.** Slip floor = `max($0.05, price*0.5%)`. LNKS at $2.19: initial slip = +2.3%, chase cap = +2.0%. **Geometrically guaranteed to miss any forward tick.** LNKS missed by 1¢ ($2.29 vs $2.28 cap).
2. **2% chase cap too tight for HOD breakouts.** Fresh-HOD squeezes can move 5–15% in 60s. ODYS went +11% in 30s.
3. **Stale-signal contribution is secondary.** Signal fires on bar close; retry window is ~30s (10s × 3 retries). Parabolic moves outrun retries — partly stale, mostly cap-too-tight.
4. **Two REJECTs are infra failures, not signal bugs:** CRE 05-04 SCM closing-only restriction; ATRA 05-07 Reg-T margin breach with TRAW open (same pattern as `project_alpaca_bp_constrained.md`).
5. **Engine sub-bot proves signals fill when priced wider.** Alpaca sub-bot uses `buffer_pct=1.0` (1% over signal) and filled ATRA @ $10.50 / VNET @ $11.29 on 5/13. Main bot's combo of tight slip + 2% cap + retry overhead is the culprit, not the signal.

## D. Specific recommendations

**Bundle decision (Cowork directive 2026-05-14_SQUEEZE_FILL_RATE_FIX): ship #1 + #2 + #3 together this week. #4 deferred (n=1).** Plus a new #5 — user directive 19:30 ET entry cutoff bundled into the same PR.

1. **Widen entry slip:** `WB_ENTRY_SLIPPAGE_MIN` `0.05 → 0.07`, `WB_ENTRY_SLIPPAGE_PCT` `0.005 → 0.010`. Matches engine sub-bot. Effective limit = max(7¢, 1% of price).
2. **Score-gated chase cap:** for score ≥ 11, raise `WB_ENTRY_MAX_CHASE_PCT` `2.0 → 3.5` via 1-line guard at entry call site (`bot_v3_hybrid.py:2796`). 5 of 6 attempts had score ≥ 10; cap-misses were all ≤ 1.4% over cap.
3. **Pre-submit BP check** (kill ATRA-style rejects): query buying_power pre-BUY, reject internally with typed reason instead of letting IBKR Err 201 cancel.
4. **Tradable-status gate** (kill CRE-style rejects): DEFERRED per Cowork — n=1 in audit window.
5. **NEW — 19:30 ET entry cutoff** (user directive after FCHL 5/14 filled 90s before extended-hours close). Symmetrical with H#14 morning gate.

### Re-derived projection (per Cowork §2 caveat)

CC's original claim was "3/4 fills." Cowork pushed back: realistic projection is 2/6 to 3/6 with the new config. Re-deriving with explicit math:

**New config in effect:**
- Initial slip: `max($0.07, 1% × signal_price)`
- Chase cap: 3.5% if score ≥ 11, 2.0% otherwise

| Entry | Signal | Score | New limit (slip rule) | New cap | Market@TO | Result |
|---|---|---|---|---|---|---|
| CRE 05-04 | 4.02 | 11 | $4.09 (1% = $0.04, floor $0.07 wins) | 3.5% = $4.23 | n/a (REJECT) | **REJECT** (closing-only — #4 needed; or BP check fires first) |
| CLNN 05-04 | 8.02 | 11 | $8.10 (1% = $0.08) | 3.5% = $8.39 | 8.45 | **MISS** ($8.45 is 0.7% past $8.39 cap) |
| ATRA 05-07 | 8.02 | 9.6 | $8.10 | 2.0% = $8.26 (score<11) | n/a (REJECT) | **REJECT_PREVENTED** (#3 BP check fires pre-submit, typed reason) |
| ODYS 05-11 | 10.02 | 10 | $10.12 (1% = $0.10) | 2.0% = $10.32 (score<11) | 11.22 | **MISS** ($11.22 is +8.7% past cap — correctly skipped on parabolic) |
| TRAW 05-11 | 2.31 | 12 | $2.38 ($0.07 floor wins; 1% = $0.023) | 3.5% = $2.39 | ~2.45+ | **MISS** (market $2.45+ past $2.39 cap) |
| ATRA 05-13 | 9.81 | 12 | n/a (R=$0.0588 < MIN_R=$0.06) | n/a | n/a | **R-GATE SKIP** (unchanged — pre-broker) |
| LNKS 05-14 | 2.19 | 12 | $2.26 ($0.07 floor wins) | 3.5% = $2.27 | 2.29 | **MISS** ($2.29 is 0.9% past $2.27 cap — still knife-edge) |

**Realistic projection: 0 fills, possibly 1 if TRAW or LNKS knife-edge resolves favorably.** Worse than original "3/4 claim."

Wait — re-reading the cap math. The directive says "abort if new_limit > original_limit × (1 + max_chase_pct/100)." That's `original_limit × 1.035`. Recompute:

| Entry | Signal | Score | original_limit | Cap (×1.035) | Mkt@TO | Result |
|---|---|---|---|---|---|---|
| CLNN 05-04 | 8.02 | 11 | $8.10 | $8.38 | 8.45 | **MISS by 0.8%** |
| ODYS 05-11 | 10.02 | 10 | $10.12 | $10.32 | 11.22 | **MISS by 8.7%** (correct skip) |
| TRAW 05-11 | 2.31 | 12 | $2.38 | $2.46 | ~2.45+ | **KNIFE-EDGE FILL** (1¢ headroom) |
| LNKS 05-14 | 2.19 | 12 | $2.26 | $2.34 | 2.29 | **FILL** ($2.29 < $2.34 cap) |

Under this corrected reading: **2 of 4 strategy-eligible fills (TRAW knife-edge, LNKS clean fill).** Matches Cowork's "2/6 to 3/6" honest expectation.

CRE and ATRA become 0 broker submits (BP check catches ATRA pre-submit; CRE still REJECTs via closing-only — #4 needed for that one, deferred).

**Bottom line — projection of 0/6 → 2/6 fill rate.** Still a major improvement, but not the 3/4 I claimed initially. Setting expectation correctly: if Friday produces 2 fills, the fix is working. If 3, knife-edges favored us. If 0, something else is broken.

**Do not** remove the cap or push slip beyond 2% floor — that re-introduces unbounded chase.

### Pre-flight verification status

- ✅ R% pass-flip check: `cowork_reports/2026-05-15_slip_widen_r_pct_verification.md` — no flips (R% is on signal price, slip is irrelevant)
- ✅ Compile clean on all 5 modified files
- ✅ Unit tests pass: entry_time_allowed (6 cases), presubmit_bp_check (4 cases + fail-open + disabled)
- ⏳ Daily breakdown 2026-05-14: pending
- ⏳ Live verification: next session (cron at 02:00 MT 5/15)

---
*Author: CC. Date: 2026-05-14. Logs: `~/warrior_bot_v2/logs/2026-05-{04,07,11,13,14}_daily.log`, `~/warrior_bot_v2_engine/logs/2026-05-13_squeeze_bot.log`. Config refs: `bot_v3_hybrid.py:169-174`.*
