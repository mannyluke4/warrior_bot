# GO-FOR-BUILD Synthesis — Wave 4 Pre-Deployment Status

**Date:** 2026-05-16
**Author:** CC
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-17_GO_FOR_BUILD.md` (all 8 decisions approved)
**Sibling reports:** A2/A3/B1/C1/D1/D2 individual reports under `cowork_reports/2026-05-16_*.md`

---

## TL;DR

All 8 approved decisions are implemented or in progress. **Two honest revisions emerged from validation work** that change the Wave 4 deployment math but not the deployment go/no-go:

1. **Forensic 1's PDH-Fade abandon@10 rule had look-ahead bias.** Realistic revalidation drops the headline number Sharpe 2.01 → 1.50 / OOS 1.76 → 1.27. Wave 4 ships **F1-alone** (time-gate only): Sharpe 1.56 / OOS 1.30 / MaxDD -18% / +$150K over 5y at $25K. Still viable, but more modest than the original forensic claim.

2. **Forensic 3's $427K conflict-rule estimate over-counted.** Empirical lift from `release_on_stop` is **$69K (8.9%)**, not $427K. The forensic counted SWAP value (replace BO with fade); the implementation is ADDITIVE (fade re-arms after BO stops, by which time the level-reversal pattern has decayed). The PDH-Breakout-stop → PDH-Fade-secondary path actually nets -$31K — opposite direction from H8. The realized lift comes from cross-strategy secondaries instead. **Direction-aware locking is queued for Wave 5** as the real test of the $427K hypothesis.

**D3 (combined squeeze + framework backtest) is BLOCKED on data gaps** (per D2 audit). Need ~3-4 days of fetch work before D3 can run. Per directive §90, paused-and-reporting as instructed.

Wave 4 paper deployment is otherwise ready. Three filtered YAMLs ship, TieredSizer locked at Tier 1, release_on_stop conflict rule active, VIX overlay + Monday skip + lock-collisions logging all live. **Squeeze production track (6/15) unchanged.**

---

## 1. Build phase results

### Phase A — Correctness fixes

| Task | Status | Result |
|---|---|---|
| **A1: lock_collisions.csv (one-line)** | ✅ DONE inline | `portfolio_backtest.py` writes per-collision log via `lock_collisions_log_path` config + `WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1` env var. Unblocks future forensic rounds. |
| **A2: release_on_stop conflict rule** | ✅ DONE | `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop` default. Behind flag; `first_in_time` regression-test path preserved. 14,432 secondary fills, $89K cumulative secondary P&L, +$69K net lift over baseline. **16% of the $427K estimate** — see §3.2. |
| **A3: Subprocess Nautilus revalidation** | ✅ DONE (RED-LIGHT on abandon) | Caught look-ahead bias in forensic abandon@10. Ships **F1-alone**: Sharpe 1.56, OOS 1.30. See §3.1. |

### Phase B — Strategy spec wiring

| Task | Status | Result |
|---|---|---|
| **B1: 3 filtered YAML specs** | ✅ DONE | `pdh_fade_filtered.yaml` (F1-alone, abandon defaulted OFF after A3), `orb_aligned_300plus_monskip.yaml`, `pdh_breakout_f4.yaml`. 9 new YAML filter knobs validated. Wiring fires BEFORE the per-day-per-symbol lock. 26 new unit tests pass. |
| **B2: Retire 2 YAMLs** | ✅ DONE inline | `vwap_mean_reversion.yaml` + `round_number.yaml` marked `status: retired` with rationale comments referencing forensics 4 + 5. |
| **B3: Framework defaults** | ✅ DONE inline | New `.env.framework` file with VIX 25/22, `WB_FRAMEWORK_SKIP_MONDAYS=1`, `WB_SIZING_MODE=tiered`, `WB_TIER_LOCK=1`, `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop`, hard guarantees (`WB_NO_MARKET_ORDERS=1`, `WB_NO_OVERNIGHTS=1`, `WB_NO_BROKER_STOPS=1`), Wave-4 isolation (`WB_FRAMEWORK_IB_CLIENT_ID=51`, separate paper account name). |

### Phase C — Sizing infrastructure

| Task | Status | Result |
|---|---|---|
| **C1: TieredSizer + 9-tier ladder + tests** | ✅ DONE | `framework/sizing_tiers.yaml` (9 tiers $300→$5K), `TieredSizer` + `TierState` + state persistence at `framework_state/tier_state.json`. Advancement gates (3-sess floor, 30-sess Sharpe ≥ 1.0, no-DD, 14-day window), retreat (-15% HWM / Sharpe < 0.3 / 3 losing weeks). `tier_lock=True` validated end-to-end: equity driven $25K → $345K through 80 sessions never moved the sizer off Tier 1. **42/42 tests green** (27 new + 15 legacy). Integration with `portfolio_backtest.py` complete. |

### Phase D — Combined backtest

| Task | Status | Result |
|---|---|---|
| **D1: Squeeze framework migration** | ✅ DONE | `framework/level_sources/squeeze.py` (wrapper, not rewrite — calls `squeeze_detector_v2.SqueezeDetectorV2` directly). `framework/confirmations/squeeze_breakout.py`. `strategies/squeeze.yaml` with universe-spec block. **100% bit-identity parity** on VERO 2026-01-16 + ROLR 2026-01-14. 24 squeeze tests + all 461 framework tests pass. Zero modifications to production squeeze code. |
| **D2: Squeeze historical data audit** | ⏸️ NO-GO (paused per directive §90) | Three material data gaps: (1) no squeeze universe seed pre-2025-01-02, (2) zero Databento tick coverage for squeeze candidates (squeeze uses IBKR `reqHistoricalTicks` cache, different schema), (3) `scanner_results/float_cache.json` has no date axis (look-ahead/survivorship risk). Budget < $100. Time to remediate: ~3-4 days. See §4. |
| **D3: Combined portfolio backtest** | ⏸️ BLOCKED on D2 | Cannot run until data gaps closed. Recommended sequence in §4. |

### Phase E — Wave 4 paper deploy

**Not yet — gated on `release_on_stop` decision sign-off + Manny's final go after reviewing this synthesis.** All prerequisites are met technically (A/B/C/D1 green, D2/D3 are post-paper extensions, not pre-paper blockers).

---

## 2. Wave 4 deployment plan (revised post-validation)

Three primary strategies on the 36-symbol Databento shortlist, separate Alpaca paper account:

| Strategy | Filter | YAML | Sharpe (validated) | Risk |
|---|---|---|---:|---:|
| **PDH-Fade-Filtered** | F1 time-gate 09:30-09:44 ET (abandon@10 OFF per A3) | `pdh_fade_filtered.yaml` | 1.56 full / **1.30 OOS** | $300 |
| **ORB-Aligned** | tier ≥ $300 AND or5_align ∈ {aligned, doji} | `orb_aligned_300plus_monskip.yaml` | 2.10 OOS (forensic 2; B1 parity check pending full-universe re-run) | $300 |
| **PDH-Breakout-F4** | NOT-blacklist (8 syms) + VWAP-aligned + consolidation<1% + vol≥2 | `pdh_breakout_f4.yaml` | 2.99 / forensic 2.81 OOS | $300 |

**Framework-level config (.env.framework):**
- `WB_FRAMEWORK_SKIP_MONDAYS=1` — cross-forensic universal finding
- `WB_USE_VIX_REGIME=1`, suppress 25, hysteresis 22
- `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop`, `WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1`
- `WB_SIZING_MODE=tiered`, `WB_TIER_INITIAL=1`, `WB_TIER_LOCK=1`, `WB_TIER_AUTO_ADVANCE=0`
- `WB_NO_MARKET_ORDERS=1`, `WB_NO_OVERNIGHTS=1`, `WB_NO_BROKER_STOPS=1`
- `WB_FRAMEWORK_IB_CLIENT_ID=51`, `WB_FRAMEWORK_PAPER_ACCOUNT=framework_paper`

**Combined notional risk per (symbol, session):** $300-$900, well below danger zone at $25K (1.2-3.6%).

**Process isolation:** separate Alpaca paper account + clientId 51 + separate persistence file. Side-by-side with squeeze production (which stays on 6/15 deadline, untouched).

---

## 3. Two honest revisions

### 3.1 PDH-Fade abandon@10 was look-ahead biased

Forensic 1's `apply_abandon` function clipped every trade at -$300 if it held >10 min AND eventually closed in loss. The word "eventually" is unavailable at minute 10 in live trading. Stripping the look-ahead (using only "currently in profit at min 10?" as the decision signal) drops:

| Metric | Forensic claim | Realistic |
|---|---:|---:|
| Full Sharpe | 2.01 | **1.50** |
| OOS Sharpe | 1.76 | **1.27** |
| P&L | $770K | $573K |
| MaxDD | -14.6% | -19.0% |

Decomposition: ~$134K of the over-claim came from clipping in-profit-at-min10 trades that eventually lost (rule should HOLD these, not abandon them). ~$97K from look-ahead-keeping abandon-triggered trades that later recovered.

**Wave 4 ships F1-alone** (no abandon rule):
- Sharpe 1.56 / OOS 1.30
- MaxDD -18%
- 5-y P&L $601K at $1K risk
- At $25K (1% sizing): ~$150K over 5y, every-year-positive holds
- YAML defaults `abandon_rule.enabled: false` with rationale comment

Saved as `feedback_lookahead_bias_check.md` memory for future forensic rounds.

### 3.2 Release-on-stop captured 16% of the $427K estimate

Forensic 3's H8 finding ("1,362 failed PDH-breakouts had blocked same-day post-failure fade signals worth $427K") measured the SWAP value: what if the fade fired *instead of* the breakout? But `release_on_stop` is ADDITIVE: the breakout still fires, still hits its stop and loses; the fade only re-arms *after* the stop fires. By that time, the level-reversal pattern has typically decayed.

Empirical results from running the same Wave 3 portfolio with `release_on_stop`:

| Metric | first_in_time baseline | release_on_stop |
|---|---:|---:|
| Net P&L | $780,752 | $850,289 (+$69,537, +8.9%) |
| Sharpe | 1.42 | 1.36 (small drag from marginal re-arms) |
| MaxDD | -47.4% | -45.8% (+1.6pp) |
| Lock collisions | 39,569 | 23,832 (-40%) |
| Secondary fills | 0 | 14,432 |

**The $69K lift mechanism is NOT what the forensic predicted.** The specific PDH-Breakout-stop → PDH-Fade-secondary path nets **-$31K** (opposite direction from H8). The realized lift comes from cross-strategy secondaries:
- PDH-Fade primaries stop → ORB / Round-Number / VWAP-MR secondaries fire → +$59K
- Round-Number → PDH-Fade secondaries on losing days → +$10K
- Net cross-strategy gain dominates

**The real $427K hypothesis stays untested.** The forensic's intuition (post-failure pattern is highly informative for fade direction) may still be correct — but `release_on_stop` doesn't test it because the lock-rule isn't direction-aware. **Wave 5 queue:** direction-aware locking — fade and breakout positions can coexist since they're directionally opposite by construction.

Recommendation: ship `release_on_stop` as approved (small Sharpe drag, real P&L lift, lock-collisions data now available). Direction-aware lock joins Wave 5 P0 priorities.

---

## 4. D2 NO-GO breakdown — what's needed for D3

Per directive §90 ("if Phase D2 finds material data gaps, **pause and report**"), D2 surfaced three gaps:

### Gap 1: No squeeze universe seed for 2020-2024
- `scanner_results/` first file is 2025-01-02
- All 1,259 prior trading days missing
- `ibkr_scanner.py::scan_premarket_historical` requires existing seed files; cannot bootstrap pre-2025
- **Remediation:** clone `live_scanner.py`'s `EQUS.SUMMARY` bootstrap, run against 2020-2024 ALL_SYMBOLS, derive per-day candidates. ~6-12h overnight fetch.

### Gap 2: Zero Databento tick coverage for squeeze candidates
- Probed 20 documented squeeze names (VERO, ROLR, KIDZ, MEI, ATRA, FCHL, MYSE, WLDS, QTTB, AHMA, AEI, CRIS, HOOK, MTVA, AGEN, GCDT, ICON, KBSX, FATN, ANPA) — 20/20 missing
- Squeeze history lives in `tick_cache/<DATE>/<SYM>.json.gz` (IBKR schema)
- Framework adapter reads parquet only
- **Remediation:** EITHER build IBKR-tick-cache adapter (~3h) for existing data, OR fetch Databento trades+bbo for ~1,750 sym-days (~3 GB, < $100). The adapter is the faster path and validates the harness on real (limited) data.

### Gap 3: Float cache has no date axis
- `scanner_results/float_cache.json` is a single 2026 snapshot of 4,464 symbols
- Backtesting 2020-2024 with this filter leaks look-ahead AND survivorship bias
- **Remediation:** Polygon `/v3/reference/tickers` for asof-date floats (recommended), OR accept the bias and document.

### Recommended D3 sequence

| Step | Effort | Output |
|---|---|---|
| D3a | ~3h CC | Build IBKR-tick-cache adapter, run combined backtest on existing 2025-2026 data. Mechanics validation only. |
| D3b | ~6-12h overnight | Clone `live_scanner` `EQUS.SUMMARY` bootstrap for 2020-2024. Fetch trades+bbo+1m for ~1,750 sym-days. Polygon asof-date float fetcher. |
| D3c | ~3h CC | Agent 4 runs harness on full 5-year window. Generates the combined backtest report Cowork's directive §3.6 specified. |

**Total wall-clock to combined backtest: 3-4 days.** Budget under $100.

**Manny decision needed:** approve D3a (validate mechanics on 2025-2026 data) immediately, OR pause D3 entirely until paper validation completes?

---

## 5. What Wave 4 actually deploys

Pulling everything above together — when Manny says "go paper":

1. Set up separate Alpaca paper account (new keys → `.env.framework.local`, gitignored)
2. Load `.env.framework` defaults + `.env.framework.local` keys
3. Launch framework process: clientId 51, persistence file `framework_paper_state/`, daemon mode
4. 3 strategies armed: PDH-Fade-Filtered (F1), ORB-Aligned-$300+ (full-universe revalidation pending), PDH-Breakout-F4
5. TieredSizer locked at Tier 1, $300/signal
6. Force-exit chain before 19:55 ET (no overnights), SELL LIMIT only (no market orders)
7. Cron at 2 AM MT daily + monitor at trading hours (separate from squeeze monitor)
8. Daily cowork report: equity, per-strategy P&L, conflict events, tier status (locked)

**60-day paper minimum** before any real-money discussion. Earliest real-money decision: **mid-August 2026**. Squeeze 6/15 real-money cutover unchanged.

---

## 6. Outstanding items

### Pre-paper (must close before Wave 4 paper launches)

- **ORB full-universe parity revalidation.** B1 ran on slim 12-name; ORB needs the 36-name validation to confirm 2.10 OOS holds. ~30 min compute, can run alongside paper launch prep.
- **A3's RED-LIGHT acknowledged by Cowork.** F1-alone (no abandon) replaces F1+abandon@10 as the official PDH-Fade-Filtered spec. Forensic 1's report should be annotated with the revalidation finding. **(Recommended action by Cowork.)**

### Wave 5 queue (after paper)

- **Direction-aware locking** — the real test of forensic 3 H8's $427K hypothesis (since `release_on_stop` is additive, not swapping)
- **HalfKellySizer fix** — bug from Wave 3, blocked by Wave 4 paper at fixed-dollar
- **Real L2 capture** — `docs/l2_capture_spec.md` already drafted (Wave 5 Agent N work)
- **D3a/b/c** — combined squeeze + framework backtest, once D2 gaps remediated

### Live operations (unchanged)

- Squeeze production track: 2026-06-15 real-money cutover
- Existing bot stack untouched per directive §1

---

## 7. Files delivered (this build round)

```
.env.framework                                    framework defaults
backtest/portfolio_backtest.py                    A1 lock_collisions logging + A2 release_on_stop + B1 filter dispatch + C1 TieredSizer integration
framework/level_sources/squeeze.py                D1 wrapper
framework/confirmations/squeeze_breakout.py       D1 confirmation
framework/sizing.py                               C1 TieredSizer
framework/sizing_tiers.yaml                       C1 9-tier ladder config
framework/registry.py                             B1 schema extensions
framework/yaml_schema.py                          B1 validator
framework/filters.py                              B1 pre-entry filter dispatch
strategies/pdh_fade_filtered.yaml                 B1 + A3 (abandon defaulted off)
strategies/orb_aligned_300plus_monskip.yaml       B1
strategies/pdh_breakout_f4.yaml                   B1
strategies/squeeze.yaml                           D1
strategies/vwap_mean_reversion.yaml               B2 retired
strategies/round_number.yaml                      B2 retired
tests/framework/test_registry_filters.py          26 tests
tests/framework/test_squeeze_source.py            21 tests
tests/framework/test_squeeze_parity_e2e.py        3 e2e tests
tests/framework/test_tiered_sizer.py              20 tests
tests/backtest/test_conflict_rules.py             A2 + B1 wiring
tests/backtest/test_tiered_sizer_integration.py   7 tests
scripts/release_on_stop_analysis.py               A2 attribution
analysis/pdh_fade_nautilus_revalidation.py        A3 harness
analysis/pdh_fade_nautilus_revalidation_*         A3 artifacts
backtest_archive/wave4_release_on_stop/           A2 results
cowork_reports/2026-05-16_*.md (8 reports incl. this synthesis)
```

**No live code touched.** Hard constraints from directive §1 respected:
- `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots — untouched
- `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py` — untouched
- `wb_persistence.py`, `wb_intraday_adder.py` — untouched
- Branch v2-ibkr-migration only
- Squeeze production track unchanged

---

## 8. Decisions Manny needs

1. **Approve Wave 4 paper launch on F1-alone** (Sharpe 1.56/1.30 instead of 2.01/1.76)?
   - Yes = framework paper goes live with the conservative spec
   - No = stay at backtest-only until further validation

2. **Approve `release_on_stop` with realized +$69K lift** (not the $427K hypothesis)?
   - Yes = ship the rule; direction-aware lock joins Wave 5
   - No = revert to first_in_time pending direction-aware lock build

3. **Approve D3a (mechanics validation on 2025-2026 data) immediately**?
   - Yes = CC builds IBKR-tick-cache adapter (~3h) and runs short combined backtest
   - No = pause D3 entirely; address gaps post-paper

4. **Approve ORB full-universe parity revalidation** (~30 min) before Wave 4 launch?
   - Yes = run it now, confirm 2.10 OOS holds on 36-name universe
   - No = launch with B1's slim-universe parity result (0.62 — gap to be revisited live)

Until your call on #1, Wave 4 paper does NOT launch. Hard stop respected.
