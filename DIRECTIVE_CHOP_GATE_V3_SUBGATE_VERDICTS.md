# Chop Gate v3 — Sub-Gate Validation Verdicts & Rollout Decisions

**Date:** 2026-05-12
**Author:** Cowork (Perplexity)
**For:** CC
**Inputs reviewed:**
- `cowork_reports/2026-05-13_chop_gate_v3_macd_only_validation.md`
- `cowork_reports/2026-05-13_chop_gate_v3_hod_recent_validation.md`
- `cowork_reports/2026-05-13_chop_gate_v3_dead_bounce_validation.md`
- `cowork_reports/2026-05-13_chop_gate_v3_xsession_validation.md`
- Code: `chop_gate_v3.py` (refactored), `session_history.py`, `scripts/validate_chop_gate_v3.py`

**Dataset:** 21 closed WB trades, 2026-05-05 → 2026-05-12 (4 winners, 17 losers).

---

## TL;DR — verdicts per sub-gate

| Sub-Gate | Verdict | Wed 5/13 | Thu 5/14 | Fri 5/15 | Mon 5/18 |
|---|---|---|---|---|---|
| `macd` | **SHIP** | live paper ON | keep | keep | keep |
| `hod_recent` | **SHIP** | observe | live paper ON | keep | keep |
| `dead_bounce` | **REWORK** | observe | observe | observe | observe (until patch + re-validation) |
| `xsession_bl` | **SHIP per plan** | observe | observe | observe | live paper ON |
| `vol_followthrough` | **DEFER** | observe | observe | observe | observe (until 30+ trade sample) |

The interim patches `WB_MIN_R_PCT_ENABLED=1` and `WB_SAME_SESSION_BLACKLIST_ENABLED=1` keep running upstream unchanged throughout.

---

## 1. `macd` — SHIP Wednesday 5/13 ✅

**Result:** PASS all 4 acceptance criteria.
- 2 CLNN losses blocked (-$653 + -$515 = -$1,168 saved)
- 4/4 winners preserved
- Zero false positives
- Top-3 winners all preserved

**Action:**
- Wednesday 2026-05-13 market open: flip `WB_CG3_MACD_ENABLED=1` in both Setup A (`bot_alpaca_subbot.py`) and Setup B (`wb_bot.py`)
- No code change required — gate is built per `DIRECTIVE_CHOP_GATE_V3_MODULAR_ROLLOUT.md` and already passes validation
- Telemetry: every arm logs MACD verdict; daily EOD report aggregates

**No further work needed on this sub-gate before rollout.**

---

## 2. `hod_recent` — SHIP Thursday 5/14 ✅

**Result:** PASS all 3 advisory criteria.
- 2 losers blocked (FATN 5/5 11:56 -$955, SST 5/8 15:01 -$250)
- 4/4 winners preserved (FATN 5/5 14:39 winner passed via `recent_attempts=1<2`)
- Top-3 winners preserved
- Interesting case: FATN 5/12 11:41 loser passed because 2/3 bottom-fish discriminators triggered (`vwap=Y, macd_up=Y, below_mid=N`). That's the right behavior — false-negative on a single loser is the safer direction than false-positive on a winner. And same-session blacklist (#11) catches the 12:26 re-attempt anyway.

**Action:**
- Wednesday 5/13 EOD review: confirm no surprises from MACD-only day-1 paper data
- Thursday 2026-05-14 market open: flip `WB_CG3_HOD_RECENT_ENABLED=1` in both setups
- No code change required

**No further work needed on this sub-gate before rollout.**

---

## 3. `dead_bounce` — REWORK before any rollout ❌

**Result:** FAIL — blocked 2 winners including the dataset's biggest single P&L (ATRA 5/8 +$2,499.59).

### What broke

Per-trade evidence:

| Trade | Outcome | Verdict | Drift | Cum drift | Vol ratio |
|---|---|---|---|---|---|
| ATRA 5/8 17:09 | **WIN +$2,500** | **BLOCK** | 1 | $2.08 | 0.18 |
| ATRA 5/12 12:20 | **WIN +$41** | **BLOCK** | 0 | $1.02 | 0.41 |
| XOS 5/12 06:29 | LOSS | block | 0 | $1.05 | 0.02 |
| ENSC 5/12 08:16 | LOSS | block | 1 | $0.07 | 0.17 |
| FATN 5/12 12:26 | LOSS | block | 0 | $0.24 | 0.18 |

The directive specified an exemption when the drift wasn't real: "if drift_bars < 5 AND cum_drift < 1.5×ATR → PASS (no_drift)." The implementation reports `drift=0` or `drift=1` on every blocked case — meaning the implementation is **firing despite a trivial drift count**. The "no drift" guard is either not running or its AND condition is letting one branch slip through.

### Root cause hypothesis

The `dead_bounce_no_drift` exemption requires BOTH `drift_bars < 5` AND `cum_drift < 1.5×ATR`. On low-priced names with elevated ATR, a single big-range bar can push `cum_drift` above `1.5×ATR` even when there's no actual sustained-drift pattern. The metric then proceeds to step 3 (midpoint reclaim) and step 4 (volume), and one of those vetoes.

Stated differently: the gate should require **both** "stock had a multi-bar slow-motion death" **and** "current bounce is technically weak." It currently fires when only the second condition is true.

### Fix — `dead_bounce` v2 spec

Change step 2 of the spec from AND to OR, and replace the absolute cum_drift threshold with a percentage-of-day-range threshold:

```python
def sub_gate_dead_bounce(symbol, bars_1m, macd_state, today):
    # 1. HOD set early?
    hod_bar_idx = argmax([b.high for b in bars_1m])
    session_start = bars_1m[0].timestamp
    hod_age_min = (bars_1m[hod_bar_idx].timestamp - session_start).total_seconds() / 60
    if hod_age_min > 90:
        return (True, "dead_bounce_hod_not_early")

    # 2. Sustained drift after HOD?  (CHANGED: AND → OR; ATR → day-range %)
    post_hod = bars_1m[hod_bar_idx + 1:]
    if not post_hod:
        return (True, "dead_bounce_no_post_hod_data")

    drift_bars = consecutive_lower_closes(post_hod)
    hod = bars_1m[hod_bar_idx].high
    lod = min(b.low for b in bars_1m)
    day_range = hod - lod
    cum_drift = hod - min(b.low for b in post_hod)
    drift_pct_of_range = cum_drift / day_range if day_range > 0 else 0

    no_meaningful_drift = (drift_bars < 5) or (drift_pct_of_range < 0.30)
    if no_meaningful_drift:
        return (True, f"dead_bounce_no_drift(bars={drift_bars},pct={drift_pct_of_range:.2f})")

    # 3. Bounce hasn't reclaimed midpoint? (unchanged)
    drift_low = min(b.low for b in post_hod)
    midpoint = (hod + drift_low) / 2
    current_price = bars_1m[-1].close
    if current_price >= midpoint:
        return (True, "dead_bounce_reclaimed")

    # 4. Bounce volume weaker than drift volume? (unchanged)
    bounce_vol = sum(b.volume for b in bars_1m[-5:])
    drift_vol = sum(b.volume for b in post_hod[:drift_bars])
    if drift_vol == 0 or bounce_vol >= 0.7 * drift_vol:
        return (True, f"dead_bounce_strong_volume(ratio={bounce_vol/max(drift_vol,1):.2f})")

    return (False, f"dead_bounce_pattern(drift={drift_bars},pct={drift_pct_of_range:.2f},vol_ratio={bounce_vol/drift_vol:.2f})")
```

**Two changes only:**
1. Line in step 2: `(drift_bars < 5) AND (cum_drift < 1.5*ATR)` → `(drift_bars < 5) OR (drift_pct_of_range < 0.30)`
2. Removed ATR dependency entirely — using `(hod - lod)` ratio is scale-invariant and matches what the metric is actually trying to measure ("did the stock retrace a meaningful fraction of its day-range after HOD?")

### Expected behavior after fix

| Trade | Step 2 outcome | Final verdict | Was |
|---|---|---|---|
| ATRA 5/8 17:09 (WIN) | drift=1 < 5 → exempt | PASS | was BLOCK ❌ → now PASS ✅ |
| ATRA 5/12 12:20 (WIN) | drift=0 < 5 → exempt | PASS | was BLOCK ❌ → now PASS ✅ |
| XOS 5/12 06:29 (LOSS) | drift=0 < 5 → exempt | PASS | was BLOCK → now PASS (acceptable; already caught by R% floor since XOS had R% = ?, check) |
| ENSC 5/12 08:16 (LOSS) | drift=1 < 5 → exempt | PASS | was BLOCK → now PASS |
| FATN 5/12 12:26 (LOSS) | drift=0 < 5 → exempt | PASS | was BLOCK → now PASS (already caught by same-session BL #11) |
| FATN 5/8 13:58 (LOSS, the target case) | TBD — re-validate | should still BLOCK (this is the original design target) | — |

**Important verification:** the patch must still catch FATN 5/8 13:58 (the target loser this sub-gate was built for, -$771.60). If the patch lets FATN 5/8 slip through, dead_bounce loses its reason to exist. Re-validate carefully.

### Acceptance criteria for `dead_bounce` v2

| # | Criterion | Threshold |
|---|---|---|
| 1 | All 4 winners preserved | 100% |
| 2 | Top-3 winners preserved | 100% |
| 3 | FATN 5/8 13:58 loser blocked | yes |
| 4 | Zero new false positives vs MACD+HOD_RECENT combined | yes |

### Action

1. CC patches `chop_gate_v3.py` per the v2 spec above. Comment the line change with `# COWORK 2026-05-12 verdict directive — AND→OR + day-range %`.
2. Re-run validation: save to `cowork_reports/2026-05-XX_chop_gate_v3_dead_bounce_v2_validation.md`.
3. If acceptance criteria pass → propose flipping `WB_CG3_DEAD_BOUNCE_ENABLED=1` Monday 5/18 or following Wednesday 5/20.
4. If still failing → return to Cowork with specifics before any further code changes.

**Until then: `WB_CG3_DEAD_BOUNCE_ENABLED=0` (observe-only).**

---

## 4. `xsession_bl` — SHIP per plan (Monday 5/18) ✅

**Result:** "FAIL" on advisory criterion 2 ("at least 1 loser blocked"), but this is a sample-size artifact, NOT a rule defect.

### Why the "fail" is actually fine

Looking at the verdicts: **every single trade** passed with reason `xbl_insufficient_history(N<3)` or `xbl_ok(...)`. The rule requires 3+ prior-day closed trades on a symbol before it can blacklist. In the 21-trade dataset:

- No symbol has 3+ prior-day trades closed before any other arm fires
- Closest cases: FATN at 5/12 11:41 had `rsum=-0.84, w=1, l=2` → passed because `losses > 2×wins` requires strict `2 > 2` which is false
- One additional FATN loss on a prior day (i.e. an earlier closing) would have flipped it on

The rule is correctly conservative. Loosening it now (e.g. dropping to 2 prior trades or `losses >= 2×wins` instead of `>`) would create false positives that the dataset doesn't yet justify.

### Action

- Keep rule unchanged: `R-sum < 0 AND losses > 2×wins AND ≥3 prior trades`
- Monday 2026-05-18 market open: flip `WB_CG3_XSESSION_BL_ENABLED=1` after weekend's accumulated paper-test data may grow the history pool
- Wednesday 5/13 — Sunday 5/17: continue running in observe-only; `session_history` keeps recording every trade outcome
- If by Friday 5/15 EOD the observe-only telemetry shows the rule is *too* tight (e.g. would have blacklisted zero symbols even with the new paper-week data), consider a follow-up directive to loosen to `losses >= 2×wins`. Do not pre-emptively change.

---

## 5. `vol_followthrough` — DEFER

No validation report supplied this round (sample too small / hasn't triggered enough times). Keep observe-only indefinitely until a 30+ trade sample exists where it has fired at least 5 times. Revisit then.

---

## 6. Updated rollout calendar

| Date | Action | Env Flags Flipped |
|---|---|---|
| Tue 5/12 EOD | This directive merged. Patch `dead_bounce` per §3 + re-validate. | none in live |
| Wed 5/13 open | **`macd` → live paper** | `WB_CG3_MACD_ENABLED=1` |
| Wed 5/13 EOD | Daily report. Confirm MACD verdicts match expectations. If `dead_bounce` v2 validation passed Tue night, ready to flip. | |
| Thu 5/14 open | **`hod_recent` → live paper** | `WB_CG3_HOD_RECENT_ENABLED=1` |
| Thu 5/14 EOD | Daily report. | |
| Fri 5/15 EOD | Decision: are MACD + HOD_RECENT carrying their weight? Any false positives? | |
| Mon 5/18 open | **`xsession_bl` → live paper** | `WB_CG3_XSESSION_BL_ENABLED=1` |
| Wed 5/20 open (tentative) | **`dead_bounce` v2 → live paper** IF Tue/Wed night re-validation passed | `WB_CG3_DEAD_BOUNCE_ENABLED=1` |
| Ongoing | `vol_followthrough` stays observe-only until 30+ trade / 5+ fire sample | |

`WB_MIN_R_PCT_ENABLED=1` and `WB_SAME_SESSION_BLACKLIST_ENABLED=1` run upstream throughout. Setup A's strategy logic unchanged.

---

## 7. Daily EOD report contract (for Wed–Fri paper-test)

Each EOD report `cowork_reports/daily_trades/2026-05-XX_v3_paper_test.md` must include:

1. **Headline stats:** total arms, total chop_gate_v2 rejects, total chop_gate_v3 rejects (by sub-gate), total fills, total wins/losses, day P&L.
2. **Per-arm log:** for every WB arm fired today, a row showing: time, symbol, score, MACD verdict, HOD_RECENT verdict, DEAD_BOUNCE verdict (observe), VOL_FT verdict (observe), XSESSION_BL verdict (observe). Whether arm proceeded or was blocked. If proceeded, outcome (win/loss/$$).
3. **Sub-gate hit-rate table:** how many times each sub-gate would have vetoed, how many enabled vetoes actually fired, how many disabled ones would have.
4. **Notable cases:** any winner false-blocked by an enabled sub-gate (drop the gate immediately and report). Any obvious loser that NO sub-gate caught (candidate for next iteration).
5. **Cumulative since 5/13:** running totals to compare against the 5/5–5/12 baseline.

This is the only artifact I need to evaluate Friday's go/no-go decision.

---

## 8. Failsafe — abort triggers during paper-test

If ANY of the following occur during Wed–Fri paper-test, kill the offending sub-gate immediately (`*_ENABLED=0`) and report:

1. An enabled sub-gate blocks a trade that closes positive within 5 minutes of arm-time on its eventual exit path.
2. An enabled sub-gate blocks ≥ 2 trades on the same day that would each have been ≥ +1.5R winners.
3. Cumulative paper-test P&L Wed+Thu is worse than the 5-day pre-rollout baseline by more than $1,000 with v3 enabled vs without.
4. Any sub-gate fires on > 50% of arms (it's probably mis-calibrated).

Reporting: post a `cowork_reports/2026-05-XX_v3_subgate_abort.md` with the offending log lines and the env change.

---

## 9. Files referenced

- `chop_gate_v3.py` — modular refactor confirmed shipped per `DIRECTIVE_CHOP_GATE_V3_MODULAR_ROLLOUT.md`
- `session_history.py` — blacklist rule confirmed per §5 of modular rollout directive
- `scripts/validate_chop_gate_v3.py` — extended for per-sub-gate runs ✅
- 4 sub-gate validation reports listed at top

---

**Tone note:** Three of four sub-gates landed correctly on first build. `dead_bounce` failed in a specific, fixable way — a single-line spec change (AND → OR + day-range %) should resolve it. The architecture pivot is working: we ship MACD and HOD_RECENT this week without waiting on DEAD_BOUNCE, and DEAD_BOUNCE re-enters the rollout when its patch validates. This is exactly the behavior the modular design was supposed to enable.
