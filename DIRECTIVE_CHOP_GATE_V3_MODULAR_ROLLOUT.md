# Chop Gate v3 — Modular Rollout Directive

**Date:** 2026-05-12
**Author:** Cowork (Perplexity)
**For:** CC
**Supersedes:** Composite-gate sections of `DIRECTIVE_CHOP_GATE_V3_BUILD.md` (the build directive's metric definitions are kept; the AND-composite is replaced with parallel OR sub-gates)
**Trigger:** v3 validation FAILED all 4 acceptance criteria on the 20-trade 5/5–5/12 dataset. The metrics are not equally good — `macd_rolling_over` is clean, `failed_hod_attempts` is too coarse, `volume_followthrough` is too quiet. Architecture pivot: ship the good metric now, fix the bad ones in parallel, never gate a winner because a half-broken sibling vetoed it.

---

## 1. Architecture change — single composite → N parallel sub-gates

**Old (build directive):**
```
chop_gate_v3 = AND(metric1, metric2, metric3)  # any veto = block
```
Failure mode: one noisy metric blocks winners; one quiet metric lets losers through; you cannot ship a partial improvement.

**New (this directive):**
```
chop_gate_v3 = parallel sub-gates, each with own env flag
  - SUB_GATE_MACD              (env: WB_CG3_MACD_ENABLED)
  - SUB_GATE_HOD_RECENT        (env: WB_CG3_HOD_RECENT_ENABLED)
  - SUB_GATE_DEAD_BOUNCE       (env: WB_CG3_DEAD_BOUNCE_ENABLED)
  - SUB_GATE_VOL_FOLLOWTHROUGH (env: WB_CG3_VOL_FT_ENABLED)
  - SUB_GATE_XSESSION_BL       (env: WB_CG3_XSESSION_BL_ENABLED)

decision: BLOCK iff ANY enabled sub-gate vetoes
         (OR-of-enabled, with each gate independently shippable)
```

Each sub-gate is a pure function returning `(passes: bool, reason: str)`. The outer `chop_gate_v3()` becomes a thin orchestrator that iterates enabled sub-gates and returns the first veto. All sub-gates always *compute* and always *log* their metric value at arm time (telemetry) — only their veto power is gated by the env flag. This is critical: we want continuous evidence on the disabled metrics so the next iteration has data.

**Master kill switch:** `WB_CHOP_GATE_V3_ENABLED=1` still gates the whole stack. If `=0`, no sub-gate runs, no veto happens. If `=1`, only the sub-gates with their own flag `=1` can veto.

---

## 2. Ship-this-week plan

### Wednesday 2026-05-13 — MACD-only sub-gate to live paper

**Build steps:**

1. **Refactor `chop_gate_v3.py`** into the new modular shape:
   - File now contains `chop_gate_v3()` orchestrator + N sub-gate functions
   - Each sub-gate: `sub_gate_macd(symbol, bars_1m, macd_state, today) -> (bool, str)`
   - Orchestrator reads env flags, calls only enabled sub-gates, returns first veto
   - Disabled sub-gates still execute in **observe-only** mode (log metric value with prefix `[CG3_OBSERVE]`) so we keep collecting evidence

2. **Defaults for Wednesday paper-test:**
   ```
   WB_CHOP_GATE_V3_ENABLED=1
   WB_CG3_MACD_ENABLED=1               # SHIP — clean on validation
   WB_CG3_HOD_RECENT_ENABLED=0         # observe-only, see §3 for rebuild
   WB_CG3_DEAD_BOUNCE_ENABLED=0        # observe-only, new metric per §4
   WB_CG3_VOL_FT_ENABLED=0             # observe-only, deferred
   WB_CG3_XSESSION_BL_ENABLED=0        # observe-only, see §5
   ```

3. **Keep the interim patches running underneath:**
   - `WB_MIN_R_PCT_ENABLED=1`, `WB_MIN_R_PCT=1.5` (Hypothesis #10)
   - `WB_SAME_SESSION_BLACKLIST_ENABLED=1` (Hypothesis #11)
   - These run BEFORE chop_gate_v3 and are unchanged.

4. **Apply to both Setup A and Setup B**: `bot_alpaca_subbot.py` and `wb_bot.py` both read the same env flags. `chop_bypass` (score ≥ 9) path still goes through chop_gate_v3 (per build directive line 311–325). Setup A is otherwise unchanged.

5. **Validation gate before paper-test:** Re-run `scripts/validate_chop_gate_v3.py` with the new env defaults on the 20-trade dataset. Expected outcome:
   - 2 CLNN losses blocked by MACD sub-gate
   - 0 winners blocked
   - All other losers pass through (acceptable — R% floor + same-session blacklist catch most of those)
   - Save to `cowork_reports/2026-05-13_chop_gate_v3_macd_only_validation.md`

**Acceptance criteria — MACD sub-gate (lower than full-v3 because it's one metric):**
| # | Metric | Threshold |
|---|---|---|
| 1 | Top-3 winners by P&L preserved | 100% |
| 2 | All 4 winners in dataset preserved | 100% |
| 3 | At least 2 losers blocked by MACD sub-gate alone | yes |
| 4 | Zero false positives | yes |

If criterion 1, 2, or 4 fails → do not ship; investigate.

### Wednesday EOD — Friday 2026-05-15 — observe in paper

- Daily EOD report: `cowork_reports/daily_trades/2026-05-XX_v3_macd_paper_test.md`
- Required content per day:
  - Count of arms, count of MACD-veto, count of `[CG3_OBSERVE]` records per disabled sub-gate
  - For every arm: tabulated values of all 5 sub-gate metrics (even disabled ones)
  - For every fill and exit: did MACD veto correctly predict outcome?
- Friday EOD decision: keep MACD-only on, or extend to next sub-gate

---

## 3. Sub-gate rebuild — `HOD_RECENT` (replaces `failed_hod_attempts`)

**Problem:** Old metric counted whole-session HOD failures → blocked FATN 5/5 14:39 (+$1,074 winner) because the morning's 4 HOD failures lingered into a legitimate afternoon bottom-fishing setup.

**Rebuild (Q2 answer = both a + b, but b is tightened):**

```python
def sub_gate_hod_recent(symbol, bars_1m, macd_state, today):
    """
    Veto if the symbol has failed HOD repeatedly in the LAST 60 MINUTES
    AND the current setup is not a bottom-fishing reclaim.

    Bottom-fishing reclaim discriminator (any 2 of 3 → not a reattempt):
      - VWAP slope positive over last 15 min
      - MACD histogram curling UP (negative-and-rising)
      - Current price > 0.5 × (HOD - LOD) from below (true bottom-fishing
        arms from sub-midrange, not from re-testing HOD)
    """
    # 1. Count HOD attempts in last 60 min only
    cutoff = now() - timedelta(minutes=60)
    recent_hod_attempts = count_hod_rejects(bars_1m, since=cutoff)

    if recent_hod_attempts < 2:
        return (True, "hod_recent_ok")

    # 2. Check bottom-fishing discriminators
    discriminators_met = sum([
        vwap_slope_positive_15m(bars_1m),
        macd_curling_up(macd_state),
        price_below_midrange(bars_1m),
    ])

    if discriminators_met >= 2:
        return (True, f"hod_recent_attempts={recent_hod_attempts}_but_bottom_fish")

    return (False, f"hod_recent_attempts={recent_hod_attempts}_no_bottom_fish")
```

**Build steps:**

1. Add the three discriminator helper functions to `chop_gate_v3.py`. Keep them pure (input bars + macd state, output bool).
2. Replay against the 20-trade dataset.
3. Expected behavior:
   - FATN 5/5 14:39 winner → PASS (2+ discriminators met after morning's HOD failures)
   - FATN 5/12 12:26 loser → BLOCK (recent attempts ≥ 2, no bottom-fishing)
   - FATN 5/12 11:41 loser → BLOCK
4. If expected behavior matches, flip `WB_CG3_HOD_RECENT_ENABLED=1` in Friday paper-test or following Monday.
5. Save to `cowork_reports/2026-05-XX_chop_gate_v3_hod_recent_validation.md`.

---

## 4. New sub-gate — `DEAD_BOUNCE` (FATN 5/8 pattern)

**Problem:** FATN 5/8 13:58 loss (-$771.60) scored 10 (chop_bypass). No existing v3 metric caught it because: HOD attempts = 0 (one decisive rejection earlier), MACD was neutral (rolled over hours ago), volume follow-through hadn't happened yet at arm time. The chart shape was "stock died slow + weak technical bounce."

**Define the pattern in measurable terms:**

A "dead bounce" setup is one where:
1. The stock made HOD in the FIRST 90 MINUTES of the session
2. There has been ≥ 1 HOD rejection followed by a sustained drift down (≥ 5 consecutive bars closing below the previous bar's close, OR cumulative drift > 1.5 × ATR)
3. The current arm is on a bounce that has NOT reclaimed the midpoint between HOD and the drift's low
4. Volume on the bounce is < 0.7 × volume on the drift

```python
def sub_gate_dead_bounce(symbol, bars_1m, macd_state, today):
    """
    Veto: stock died in slow motion, current arm is a weak technical bounce.
    """
    # 1. HOD set early?
    hod_bar_idx = argmax([b.high for b in bars_1m])
    session_start = bars_1m[0].timestamp
    hod_age_min = (bars_1m[hod_bar_idx].timestamp - session_start).total_seconds() / 60
    if hod_age_min > 90:
        return (True, "dead_bounce_hod_not_early")

    # 2. Sustained drift after HOD?
    post_hod = bars_1m[hod_bar_idx + 1:]
    drift_bars = consecutive_lower_closes(post_hod)
    atr = compute_atr(bars_1m, period=14)
    cum_drift = bars_1m[hod_bar_idx].high - min(b.low for b in post_hod)
    if drift_bars < 5 and cum_drift < 1.5 * atr:
        return (True, "dead_bounce_no_drift")

    # 3. Bounce hasn't reclaimed midpoint?
    drift_low = min(b.low for b in post_hod)
    midpoint = (bars_1m[hod_bar_idx].high + drift_low) / 2
    current_price = bars_1m[-1].close
    if current_price >= midpoint:
        return (True, "dead_bounce_reclaimed")

    # 4. Bounce volume weaker than drift volume?
    bounce_vol = sum(b.volume for b in bars_1m[-5:])
    drift_vol = sum(b.volume for b in post_hod[:drift_bars])
    if bounce_vol >= 0.7 * drift_vol:
        return (True, "dead_bounce_strong_volume")

    return (False, f"dead_bounce_pattern_drift={drift_bars}_vol_ratio={bounce_vol/drift_vol:.2f}")
```

**Build steps:**

1. Add `sub_gate_dead_bounce` to `chop_gate_v3.py`.
2. Add helpers `consecutive_lower_closes`, `compute_atr` (if not present).
3. Validate on the 20-trade dataset. Expected:
   - FATN 5/8 13:58 loser → BLOCK (the target case)
   - FATN 5/5 14:39 winner → PASS (afternoon bottom-fish, HOD not in first 90 min OR midpoint reclaimed)
   - ATRA 5/8 winner → PASS
   - SST 5/11 winner → PASS
4. If FATN 5/8 blocks and no winners block, ship to paper with `WB_CG3_DEAD_BOUNCE_ENABLED=1` Friday or Monday.
5. Save to `cowork_reports/2026-05-XX_chop_gate_v3_dead_bounce_validation.md`.

---

## 5. Cross-session blacklist refinement

**Q3 answer:** Combine **(a) R-multiple sum** AND **(c) win-rate ratio**. Drop **(b) recency decay** — adds complexity and the lookback window already bounds recency.

**Rule (replaces directive lines 295–325):**

```python
def sub_gate_xsession_blacklist(symbol, session_history, today):
    """
    Blacklist symbol for next session iff over last LOOKBACK closed trades on
    this symbol (across days, excluding today):
      - sum(R_multiple) < 0
      AND
      - losses > 2 × wins
      AND
      - at least 3 closed trades exist
    """
    trades = session_history.get_trades(symbol, lookback_days=7, exclude_today=today)
    if len(trades) < 3:
        return (True, "xbl_insufficient_history")

    r_sum = sum(t.r_multiple for t in trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    losses = sum(1 for t in trades if t.pnl <= 0)

    if r_sum < 0 and losses > 2 * wins:
        return (False, f"xbl_blacklist_rsum={r_sum:.2f}_w={wins}_l={losses}")

    return (True, f"xbl_ok_rsum={r_sum:.2f}_w={wins}_l={losses}")
```

**Why R-sum AND win-rate-ratio (not OR):**
- R-sum alone would blacklist a 1-big-loss / 1-small-win symbol (variance noise).
- Win-rate-ratio alone would blacklist a 3-tiny-losses / 1-tiny-win symbol with neutral EV.
- AND requires *both* "bleeding money" and "losing more often than winning."

**Sanity-check against dataset:**
- CLNN (5/5 only, no prior days, 2 losses, 0 wins, R-sum < 0): only 2 trades → fails `len ≥ 3` → not blacklisted by THIS gate. CLNN is correctly blocked by MACD sub-gate same-day; cross-session is for repeat-bleeders only.
- ATRA (1 huge win 5/8, 2 losses 5/11): R-sum likely POSITIVE (the +$2,499 win is ~+3R, losses are ~-1R each → +1R net). Passes blacklist. ✅
- FATN (1 winner 5/5, 1 loser 5/5, 1 loser 5/8, 2 losers 5/12): R-sum negative, losses=4, wins=1 → losses > 2 × wins → BLACKLIST. ✅

**Build steps:**

1. Replace `session_history.py`'s blacklist check with the new rule.
2. Keep `record_trade` API unchanged (we're already populating history per directive line 296–307).
3. Set defaults: `WB_CG3_XSESSION_LOOKBACK_DAYS=7`, `WB_CG3_XSESSION_MIN_TRADES=3`.
4. Validate on dataset. Expected: FATN blacklisted by 5/12, ATRA never blacklisted, CLNN not blacklisted by this gate (but handled by MACD).
5. Save to `cowork_reports/2026-05-XX_chop_gate_v3_xsession_validation.md`.
6. Ship with `WB_CG3_XSESSION_BL_ENABLED=1` after MACD sub-gate proves out in paper.

---

## 6. Telemetry — observe-only logging for disabled sub-gates

Every disabled sub-gate still runs and logs:

```
[CG3_OBSERVE] symbol=FATN sub=hod_recent value=2 would_veto=Y enabled=N
[CG3_OBSERVE] symbol=FATN sub=dead_bounce value=pattern_drift=7_vol_ratio=0.45 would_veto=Y enabled=N
[CG3_OBSERVE] symbol=FATN sub=vol_followthrough value=insufficient_data would_veto=N enabled=N
[CG3_OBSERVE] symbol=FATN sub=xsession_bl value=rsum=-2.1_w=1_l=4 would_veto=Y enabled=N
```

The EOD report must aggregate these. We're collecting evidence to promote each sub-gate independently when its data supports it.

---

## 7. Rollout sequence (concrete)

| Date | Action | Env Flags Flipped |
|---|---|---|
| Tue 5/12 EOD | Refactor `chop_gate_v3.py` into modular shape; add `dead_bounce` + `hod_recent` rebuild + xsession rule. Run all sub-gate validations. | none in live |
| Wed 5/13 open | Ship MACD-only sub-gate to paper if MACD validation passes. | `WB_CG3_MACD_ENABLED=1` |
| Wed 5/13 EOD | Daily report w/ observe-only telemetry for other 4 sub-gates. | |
| Thu 5/14 open | If HOD-recent and dead-bounce validations passed Tue night, flip them on for paper. | `WB_CG3_HOD_RECENT_ENABLED=1`, `WB_CG3_DEAD_BOUNCE_ENABLED=1` |
| Fri 5/15 EOD | Decision point: which sub-gates to keep enabled for following week. | |
| Mon 5/18 | Flip `WB_CG3_XSESSION_BL_ENABLED=1` if dataset supports it. | |
| Wk of 5/18 | Continue observe-only on `vol_followthrough` until 30+ trade sample exists. | |

**Setup A is not modified during this rollout.** Setup A continues running its own copy of WB. The chop_gate_v3 changes land in BOTH Setup A's `bot_alpaca_subbot.py` and Setup B's `wb_bot.py` — but Setup A's existing strategy logic (entry, exit, sizing) remains untouched. Only the chop_gate_v3 module is swapped.

---

## 8. Acceptance criteria for the full modular v3 (when all sub-gates enabled)

When `WB_CG3_MACD_ENABLED=1`, `WB_CG3_HOD_RECENT_ENABLED=1`, `WB_CG3_DEAD_BOUNCE_ENABLED=1`, `WB_CG3_XSESSION_BL_ENABLED=1`:

| # | Metric | Threshold |
|---|---|---|
| 1 | All 4 winners (ATRA 5/8, SST 5/11, FATN 5/5 14:39, any new winner) preserved | 100% |
| 2 | All 3 FATN losers blocked (5/8, 5/12 11:41, 5/12 12:26) | 100% |
| 3 | All CLNN losers blocked | 100% |
| 4 | Total losers blocked / total losers | ≥ 70% |
| 5 | Zero winner false positives across rolling 30-trade window | yes |

`vol_followthrough` may remain observe-only indefinitely if its sample never grows enough.

---

## 9. Files to modify

1. `chop_gate_v3.py` — full refactor into modular shape (orchestrator + 5 sub-gate functions + 3 discriminator helpers + ATR + consecutive-lower-closes helpers).
2. `session_history.py` — replace blacklist rule per §5.
3. `bot_alpaca_subbot.py` (Setup A) — re-wire to read individual sub-gate flags; no other change.
4. `wb_bot.py` (Setup B) — same as #3.
5. `scripts/validate_chop_gate_v3.py` — extend to run per-sub-gate validation reports.
6. `cowork_reports/2026-05-13_chop_gate_v3_macd_only_validation.md` — output of MACD-only run.
7. `cowork_reports/2026-05-XX_chop_gate_v3_hod_recent_validation.md`
8. `cowork_reports/2026-05-XX_chop_gate_v3_dead_bounce_validation.md`
9. `cowork_reports/2026-05-XX_chop_gate_v3_xsession_validation.md`

---

## 10. What this is NOT

- Not a re-implementation of any v3 metric except `failed_hod_attempts` (rebuilt as `hod_recent` with discriminators).
- Not a change to the chop_bypass score-≥9 path — chop_gate_v3 still vetoes bypass (build directive line 311–325 still applies).
- Not a change to the R% floor or within-session blacklist (Hypotheses #10/#11) — they continue running upstream of chop_gate_v3.
- Not a change to Setup A's strategy logic outside the chop_gate_v3 swap.
- Not a deferral of the June 4 PDT-rule live-money deadline — modular rollout *accelerates* the path because each sub-gate ships when it's ready instead of waiting on the slowest one.

---

## 11. Tone note

The build directive's monolithic-composite was the right *starting* design — we needed one place to centralize the failure-mode logic. The validation step (which fired correctly) revealed that the metrics are not equally mature, and the architecture has to reflect that. This directive keeps every metric we already wrote and adds two more (`hod_recent` rebuild, `dead_bounce`), but lets the good ones ship while the others continue collecting evidence in observe-only mode. We don't lose the work; we get the wins faster.
