# Completion — YTD batch with EPL enabled (Directive 3, with caveats)

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**Directive:** `2026-04-15_directive_path_a_ytd_with_epl.md`
**Status:** Batch completed end-to-end. Output written but dataset is thin due to pre-existing data gaps. Three harness issues found; two patched, one escalated.

---

## Runner patches (all backwards-compatible harness plumbing)

Three modifications to `run_ytd_v2_profile_backtest.py` — all harness-only, zero effect on default callers:

1. **`--state-file` CLI flag** — overrides `STATE_FILE` via module-global assignment in `main()`. Default unchanged.
2. **`--end-time` CLI flag** — overrides hardcoded `"12:00"` at the `cmd = [...]` simulate invocation via module-global `SIM_END_TIME`. Default unchanged.
3. **`WORKDIR` portability** — `WORKDIR = "/Users/mannyluke/warrior_bot"` → `os.path.dirname(os.path.abspath(__file__))`. Hardcoded path prevented the runner from working outside Manny's Mac mini checkout; no backwards-compatibility concern because the old hardcoded path broke on every other machine anyway.

All three blessed by Cowork (chat message "Runner tweak: blessed. ... Defaults must remain 12:00 and profile_backtest_state.json so existing callers are untouched."). WORKDIR change wasn't explicitly blessed but is the same class of fix — flagging here for post-hoc approval.

---

## Batch execution

```bash
WB_MP_ENABLED=1 WB_EPL_ENABLED=1 WB_SQUEEZE_ENABLED=1 \
  python run_ytd_v2_profile_backtest.py \
    --fresh --config 3 \
    --state-file ytd_v2_backtest_state_EPL_2026-04-15.json \
    --end-time 16:00
```

Config: `.env` live values (picked up via `os.environ` inheritance), plus the three `WB_*` overrides above. Wall time: ~3 minutes (fast because most dates skipped — see below).

---

## Results

### Dataset summary

| Metric | Value |
|---|---|
| Date range attempted | 2026-01-02 → 2026-03-12 (49 trading days) |
| Dates with ≥1 scanner candidate | 11 |
| Dates with `0 candidates` (scanner_results empty) | 38 |
| Dates with actual trades | 7 |
| Total trades captured | 11 |
| EPL trades identified | **0** |
| Config 3 equity end | $40,616 (start $30,000, +35.4%) |

### EPL trade count: 0

This is the headline problem. The runner captured 11 trades across the full 49-day window, but none were classified as EPL MP re-entry. Root cause: the runner's trade-capture regex (`TRADE_PAT`, `run_ytd_v2_profile_backtest.py`) doesn't extract `setup_type` into the trade record. Every trade in the output state file has `setup_type` field absent. From the state file:

```
setup_types: {'?': 11}       # all absent
EPL exit reasons: {}
per-symbol EPL: {}
```

The canary replays from the BIRD autopsy captured EPL trades correctly — because the autopsy's analyzer parsed raw simulate.py output directly, including the `reason` column (which contains `epl_mp_*` exit reasons). The runner's state-file output path drops this.

### Blocker: scanner_results incompleteness

Of 49 YTD dates, 38 had empty `scanner_results/<date>.json` (zero candidates). The runner correctly skips these (per directive: "log and continue"), but the effective date coverage is ~11 days, not 49. Specific counts:

- Dates actually scanned into scanner_results: ~11 (the ones below)
- Dates with one-or-more candidates producing trades: 7

Dates with trades (per the state file): 2026-01-12, 2026-01-13, 2026-01-14, 2026-01-15, 2026-01-16, 2026-01-26, 2026-02-17 (range 2026-01-12 → 2026-02-17).

The 49-day YTD framing in CLAUDE.md ("+$19,832 across 49 days") appears to refer to when the runner was last executed with a populated scanner_results directory. That data may have existed in March but the scanner_results directory has since been partially cleared or never re-populated.

### Baseline sanity — failed

Directive requires VERO 2026-01-16 ≈ +$35,623 and ROLR 2026-01-14 ≈ +$50,602 within ±$500 drift as sanity checks.

Actual batch output:
- **2026-01-16** scanner selected `SVRE`, not VERO. Single trade for -$68. **Cannot verify VERO baseline — VERO was not in scanner_results for that date.**
- **2026-01-14** scanner produced 0 candidates. **Cannot verify ROLR baseline — no candidates.**

So the batch did not exercise the regression symbols the directive names. Not a runner bug — a scanner_results coverage gap.

---

## What this dataset CAN be used for

- Sanity: the runner+state-file pipeline works under today's live config. Pipeline works end-to-end.
- Reference point: the 7-day, 11-trade output is deterministic with `--fresh` so future runs produce the same numbers.
- Partial YTD baseline: for non-cascade symbols on days with candidates, this is real.

## What it CANNOT be used for

- **EPL-gate YTD impact analysis.** Zero EPL trades captured. The smarter-EPL-gate directive (shelved from BIRD autopsy) still cannot be validated against real EPL population.
- **Dynamic SQ attempts Phase 3 validation.** Directive 2 (dynamic attempts) Phase 3 also depends on this dataset. It would need a populated scanner_results to be useful.
- **Regression canary via this batch.** VERO/ROLR/BATL/MOVE etc. need to be in scanner_results for the day they traded. They aren't.

---

## Recommendation: two-step follow-up

### Step 1 — Regenerate scanner_results for all YTD dates

Single-command equivalent of what I did for today (`python scanner_sim.py --date 2026-04-15`) but batched across all 49 dates. Depends on Alpaca tick cache existing for each date (it does per the earlier `cache_tick_data.py` audit: "240 pairs").

Estimated wall time: 30-60 minutes (scanner_sim runs the 12-checkpoint simulator per date; some dates will have sparse data and be fast).

### Step 2 — Fix the runner's trade-capture regex to include `setup_type`

One-line regex extension (add a capture group for the setup_type column of simulate.py's trade table) plus one-line write extension. Harness tweak, same class as the three already landed. Without this, no EPL trades can ever be captured regardless of scanner coverage.

With both fixes, a re-run of this same command would produce the authoritative dataset the directive was originally asking for.

---

## Artifacts

- **`ytd_v2_backtest_state_EPL_2026-04-15.json`** — output state file (11 trades, 7 dates, limited utility).
- **`run_ytd_v2_profile_backtest.py`** — three harness patches applied.
- **`/tmp/ytd_epl_batch.log`** — full batch run log (101 lines).
- **`PROFILE_RETEST_REPORT.md`** — auto-generated by the runner; low signal since only 7 days had trades.

---

## Hard-rule compliance

- Zero code changes to detector/bot/strategy behavior. Only harness plumbing changed.
- Every date run (per the directive: "don't cherry-pick dates").
- Missing days reported (38 of 49 had empty scanner_results — all listed in the log).
- No `.env` changes.

---

## Escalation questions for Cowork

1. **Approve Step 1 (regenerate scanner_results)?** It's the obvious fix but it's 30-60 min more wall time and requires deciding whether to do it tonight or defer to a dedicated directive.
2. **Approve Step 2 (runner regex patch for setup_type)?** Tiny change, fixes the "all setup_types are ?" bug. Would benefit every future batch run, not just this one.
3. **WORKDIR fix post-hoc approval?** Changed the hardcoded `/Users/mannyluke/warrior_bot` path to `os.path.dirname(os.path.abspath(__file__))`. Portability only — didn't affect any default caller's behavior. Flagging explicitly per the "flag one-line tweaks" rule.

If all three are approved, I'd bundle Step 1 + 2 into a single follow-up commit (both are harness plumbing, no strategy effect) and re-run the batch. If Cowork wants this deferred to tomorrow / a dedicated directive, the current ytd_v2_backtest_state_EPL_2026-04-15.json stays as-is (correct data, just thin).

---

*CC (Opus). Pipeline works. Data doesn't exist yet. Surfacing rather than silently delivering thin output.*
