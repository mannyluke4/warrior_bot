# Volume Profile — Real-Data Backtest (Wave 5 Agent L)

**Date:** 2026-05-16
**Author:** CC (Agent L)
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §5 Agent L
**Scope:** Backtest only — no paper deployment (directive §9 hard stop)

---

## TL;DR

Built `VolumeProfileSource` (POC/HVN/LVN over configurable bin-width and N-session lookback) and two strategy specs (`volume_profile_rejection.yaml`, `volume_profile_breakout.yaml`). Backtested over 36-symbol Databento universe × 1,306 trading sessions (2020-01-02 → 2024-12-31) using bar-level fill model identical to the Wave 3 PDH-PDL harness, fixed-dollar $1K risk per trade.

**Headline real-data Sharpe (VIX overlay ON):**

| Variant | n_trades | Sharpe | PF | WR | MaxDD | Net P&L |
|---|---:|---:|---:|---:|---:|---:|
| **VP-Rejection** | 16,099 | **+0.62** | 1.03 | 41% | **-47.4%** | +$243K |
| **VP-Breakout**  | 6,346  | -0.28 | 0.98 | 40% | -78.5% | -$65K |
| **VP-Portfolio (lock)** | 17,368 | **+0.66** | 1.03 | 41% | -40.1% | +$273K |

**Acceptance verdict:** **All three variants FAIL the directive §5 gates.** VP-Rejection comes closest (Sharpe 0.62 vs ≥1.0 gate; MDD -47.4% vs ≤15% gate fails by 3.2×; ≥100 trades gate passes by 160×). VP-Breakout is structurally net-negative on real data. Portfolio combination provides marginal diversification lift (+0.04 Sharpe vs rejection alone) but inherits the rejection-side drawdown geometry.

**Key finding:** **The VIX overlay validates Wave 3's universal finding.** Enabling VIX suppression at the calibrated p75 threshold (45 on our synthetic VIX proxy; suppresses ~26% of sessions, mostly 2022 bear and 2023 chop tail) lifts VP-Rejection Sharpe from +0.34 to +0.62 (+0.28) and portfolio Sharpe from +0.42 to +0.66 (+0.24). VP-Breakout marginally degrades with VIX overlay (-0.13 Sharpe), consistent with breakout strategies preferring elevated-vol regimes — but the overall edge is still negative, so the overlay doesn't rescue it. **VIX-on should be default for any Phase-2 fade-style deployment.**

**Honest pass/fail recommendation:** Neither spec ships. Rejection has the bones of an edge (positive expectancy, level-kind attribution favoring HVN, tier attribution favoring $150-300 and $300+) but needs structural rework — likely tick-level profile reconstruction, prior-day-only lookback, and a much wider stop. Breakout is fundamentally broken in this universe at this fidelity; LVN gaps in mega-cap liquid names are not the "vacuums" the methodology predicts because mega-cap participation is continuous.

**Comparison vs PDH-Fade (Wave 3 survivor):** PDH-Fade real-data Sharpe 1.47 with 9,874 trades on the same universe. VP-Rejection at 16,099 trades / Sharpe 0.62 is **2.4× the trade count for 42% the Sharpe**. The two strategies are not complementary — they both fade resistance levels (PDH and HVN respectively), would correlate, and PDH-Fade fires earlier and harder per trade. **Do not portfolio them; PDH-Fade is the better instrument.**

---

## 1. Volume Profile construction methodology

### Bin grid

Each prior-session bar's volume is assigned to a single bin at the bar's typical price `TP = (H + L + C)/3`. Bin width defaults to `0.1% × ref_price` (where `ref_price` is the most recent close), floored at $0.01. The framework also accepts an explicit `bin_dollar` override for cross-symbol comparability. Bar-level (vs tick-level) bin assignment introduces 1-3 bin-width of error per the design doc §4.5 caveat — acceptable for liquid mega-cap names at our 0.1% bin granularity but a known source of POC drift on names with within-bar dispersion > one bin.

### Classification

- **POC (Point of Control):** the single bin with the highest cumulative volume across the lookback window. Emitted as one `Level(kind="POC")`.
- **HVN (High Volume Node):** any bin whose volume ≥ `1.5 × mean_bin_volume`. Adjacent HVN bins are merged into a single cluster Level at the volume-weighted centroid, with `cluster_low_price` / `cluster_high_price` metadata for edge-aware downstream logic. POC bin is excluded from HVN emission (it's the canonical "top HVN" and would double-count).
- **LVN (Low Volume Node):** any bin whose volume ≤ `0.5 × mean_bin_volume`. Same cluster merging — LVN gaps between HVN clusters collapse to one Level.

### Lookback & intraday

`lookback_sessions=5` (default) selects the most recent 5 distinct prior trading dates from history. If the harness passes a combined "prior + today" history (as the backtest does), the source restricts to dates strictly before the target. An `intraday_snapshot()` method maintains a developing-profile counter — bars passed via `update_intraday(bar)` accumulate independently of `compute_levels()`, supporting live use where both prior-N and developing profiles inform decisions.

### Edge cases verified by tests

- Empty history → empty LevelSet (no exception).
- Zero-volume bars skipped (don't poison the bin distribution).
- Non-finite OHLC bars skipped silently.
- Single-bin profiles emit POC only (HVN/LVN thresholds degenerate when N=1).
- `bin_pct` × `ref_price < 0.01` clamped to $0.01 floor.
- Cluster merging is exhaustive — three contiguous HVN bins collapse to one Level with `n_bins_in_cluster=3`.

28 unit tests in `tests/framework/test_volume_profile.py` — all pass.

---

## 2. Strategy spec recap

### `volume_profile_rejection.yaml` — Mean-reversion fade

- **Level source:** VolumeProfileSource, 5-session lookback, 0.1% bins, HVN-merged. Emits POC + HVN (LVN suppressed).
- **Arrival:** proximity 0.15% (slightly wider than PDH-Fade's 0.10% — HVN clusters are zones, not points).
- **Confirmation:** Rejection (failed-test pattern). Direction inferred from approach: high crosses HVN + close back below → short; low crosses HVN + close back above → long. Lookback 2 bars.
- **Stop:** `just_past_level` with $0.10 pad past the HVN. Coerced to minimum $0.0015 × entry_price to avoid noise stop-outs on tight setups.
- **Target:** `composite(opposite_level, fallback=r_multiple 1.5)` — next HVN/POC on opposite side or 1.5R extension.
- **Regime gate:** VIX overlay enabled, suppress at threshold 25 (real VIX) → calibrated to threshold 45 on our synthetic VIX-proxy (p75 of distribution).
- **Risk:** fixed-dollar $1K per trade (Wave 3 sizing-bug remedy).

### `volume_profile_breakout.yaml` — Vacuum breakout

- **Level source:** VolumeProfileSource, 5-session lookback, 0.1% bins. Emits HVN (target) + LVN (trigger), POC suppressed.
- **Arrival:** proximity 0.10% (tighter than rejection — want a clean LVN tag).
- **Confirmation:** BreakoutCandle (close beyond level + ≥2× 20-bar vol baseline). Triggers on prior-bar-close at-or-below LVN's `cluster_high_price` combined with current-bar-close clearly above (long), and mirror logic for short. Each LVN bin tracked once-per-day (no re-fire after crossing).
- **Stop:** `bar_low` (long) / `bar_high` (short) of entry bar's prior bar + $0.05 pad. Same min-risk coercion as rejection.
- **Target:** `composite(opposite_level=next HVN, fallback=r_multiple 2.0)`.
- **Regime gate:** same VIX overlay.

Both specs default `vix_size_multiplier.use_vix=true` (override of framework default-off), per Wave 3 universal finding.

---

## 3. Real-data backtest config

| Knob | Value |
|---|---|
| Universe | 36-symbol Databento shortlist (AAPL, MSFT, TSLA, NVDA, … AMC) |
| Date range | 2020-01-02 → 2024-12-31 (1,306 sessions) |
| Bar resolution | 1-minute OHLCV, Databento `ohlcv-1m` schema |
| RTH | 09:30 – 16:00 ET |
| Trade window | 09:35 – 15:55 ET (skip first 5 min open, force-exit at 15:55) |
| Open-bar exclusion | First 10 bars of session (`min_bar_idx=10`) — avoid open-noise rejection/breakout fakeouts |
| Lookback | 5 prior trading sessions |
| Fill model | Entry at next-bar's open (no look-ahead). Stop fills when bar.low ≤ stop (long) or bar.high ≥ stop (short). Target fills on intra-bar touch. Session close at 15:55 on remaining open positions. |
| Sizing | Fixed-dollar $1,000 risk per trade (Wave 3 recommendation; HalfKellySizer suppresses returns) |
| Per-symbol-per-day lock (portfolio variant) | First-in-time strategy wins; second is skipped |
| VIX proxy | Median 20-day RV of (AAPL, MSFT, NVDA, META, TSLA), annualized to % units. Cached to `volume_profile_vix_proxy_cache.json`. |
| VIX suppression threshold | 45.0 (proxy units; p75 of the distribution; suppresses 335/1,306 = 25.6% of sessions) |

---

## 4. Per-spec metrics

### Headline table (VIX overlay state explicit)

| Variant | n_trades | Sharpe | PF | WR | MaxDD | Avg R | Net P&L | Daily ret mean | Daily ret std |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rejection (VIX off) | 22,072 | +0.34 | 1.01 | 40% | -54.5% | +0.008 | +$181,427 | +0.072% | 3.30% |
| **Rejection (VIX on)** | **16,099** | **+0.62** | **1.03** | **41%** | **-47.4%** | **+0.015** | **+$243,326** | **+0.124%** | **3.16%** |
| Breakout (VIX off) | 8,781 | -0.15 | 0.99 | 40% | -76.1% | -0.006 | -$48,581 | -0.020% | 2.10% |
| Breakout (VIX on) | 6,346 | -0.28 | 0.98 | 40% | -78.5% | -0.010 | -$64,628 | -0.034% | 1.93% |
| Portfolio (VIX off) | 23,671 | +0.42 | 1.02 | 41% | -47.9% | +0.010 | +$232,016 | +0.092% | 3.50% |
| **Portfolio (VIX on)** | **17,368** | **+0.66** | **1.03** | **41%** | **-40.1%** | **+0.016** | **+$273,114** | **+0.137%** | **3.30%** |

### Acceptance-gate verdict (per directive §5)

| Gate | Threshold | Rejection (VIX on) | Breakout (VIX on) | Portfolio (VIX on) |
|---|---|---|---|---|
| Sharpe ≥ 1.0 OOS | ≥ 1.0 | **FAIL** (0.62) | **FAIL** (-0.28) | **FAIL** (0.66) |
| ≥ 100 trades per spec | ≥ 100 | PASS (16,099) | PASS (6,346) | PASS (17,368) |
| Max drawdown ≤ 15% | ≤ 0.15 | **FAIL** (47.4%) | **FAIL** (78.5%) | **FAIL** (40.1%) |
| VIX-on improves Sharpe vs off | Yes | PASS (+0.28) | FAIL (-0.13) | PASS (+0.24) |

**Both specs fail.** Rejection is structurally most-recoverable — its expectancy is positive and concentrated in the right tiers/regimes. Breakout's expectancy is structurally negative; tuning won't save it on this universe.

---

## 5. VIX overlay impact

The directive asks: does VIX>25 suppression improve Sharpe? Our synthetic VIX proxy (median realized vol of 5 high-beta mega-caps, annualized) doesn't directly match CBOE VIX values, but the *directional regime signal* is preserved — high-RV regimes are the ones our proxy flags as high-VIX, which matches Wave 3 K's "VIX>25" cohort behavior.

Calibrated to p75 threshold = 45 (proxy units), the suppression covers 335 / 1,306 = 25.6% of sessions. Wave 3 K reported ~20% of sessions had real-VIX > 25 — comparable order of magnitude.

| Strategy | Sharpe (VIX off) | Sharpe (VIX on) | Δ | Verdict |
|---|---:|---:|---:|---|
| Rejection | +0.34 | +0.62 | +0.28 | **Helps** — fade strategies are categorically better in calm regimes (matches Wave 3 PDH-Fade finding) |
| Breakout | -0.15 | -0.28 | -0.13 | Hurts — breakouts theoretically prefer elevated-vol regimes, and suppressing those days removes the few sessions where the strategy might find genuine momentum vacuums. But the overall edge is negative either way. |
| Portfolio | +0.42 | +0.66 | +0.24 | Helps — driven by rejection dominance in the first-in-time lock (~93% of portfolio trades come from rejection; rejection's higher per-trade frequency wins the lock race). |

**Recommendation aligns with Wave 3:** For *fade* strategies, VIX overlay should be default-ON in any future deployment. The directive's hypothesis is validated for rejection but contradicted for breakout — which is consistent with the structural physics of each setup type.

---

## 6. Per-tier breakdown ($10-50 / $50-150 / $150-300 / $300+ / <$10)

### Rejection (VIX on)

| Tier | n | P&L | WR | Avg R |
|---|---:|---:|---:|---:|
| $10-50 | 4,755 | -$263 | 50% | -0.000 |
| $50-150 | 4,692 | +$86,279 | 38% | +0.018 |
| $150-300 | 2,603 | +$93,850 | 34% | +0.036 |
| $300+ | 3,423 | +$82,943 | 33% | +0.024 |
| <$10 | 626 | -$19,484 | 63% | -0.031 |

**Reading:** Rejection edge is concentrated in the $50-150, $150-300, and $300+ tiers (combined +$263K). The $10-50 tier is wash (zero expectancy despite 50% WR — wins and losses match exactly). The <$10 tier has *high WR but negative P&L* — wins are tiny relative to losses, classic low-priced-stock noise. **Per-tier deployment should be $50+ only.**

### Breakout (VIX on)

| Tier | n | P&L | WR | Avg R |
|---|---:|---:|---:|---:|
| $10-50 | 2,123 | -$30,338 | 45% | -0.014 |
| $50-150 | 1,626 | -$57,805 | 37% | -0.036 |
| $150-300 | 933 | +$11,839 | 37% | +0.013 |
| $300+ | 1,285 | +$27,642 | 37% | +0.022 |
| <$10 | 379 | -$15,965 | 48% | -0.042 |

**Reading:** Breakout is structurally net-negative across $10-150, only positive at $150+. Even the $150-300 tier has a thin +0.013 R/trade — barely past zero. **No breakout deployment recommended.**

---

## 7. Per-year breakdown

### Rejection (VIX on)

| Year | n | P&L | WR | Avg R | Comment |
|---|---:|---:|---:|---:|---|
| 2020 | 2,711 | +$118,580 | 41% | +0.044 | COVID vol — best year |
| 2021 | 3,984 | +$76,727 | 40% | +0.019 | Retail mania — strong |
| 2022 | 1,437 | -$7,627 | 40% | -0.005 | Bear year — most sessions suppressed by VIX overlay; remaining trades wash |
| 2023 | 4,086 | -$10,321 | 42% | -0.003 | AI boom chop — surprisingly weak |
| 2024 | 3,881 | +$65,967 | 41% | +0.017 | Mega-cap concentration — positive |

**Reading:** 3 of 5 years positive, 2 of 5 negative. The 2023 weakness is the concerning one — 4,086 trades with avg R -0.003 means the strategy fired heavily in an AI-momentum regime where mean-reversion fades at HVN clusters got run over (trend days have no opposing HVN to fade to). PDH-Fade was positive in 2023 ($+18K per Wave 3); VP-Rejection is not. **PDH-Fade has the structural edge VP-Rejection lacks.**

### Breakout (VIX on)

| Year | n | P&L | WR | Avg R |
|---|---:|---:|---:|---:|
| 2020 | 1,213 | +$9,586 | 41% | +0.008 |
| 2021 | 1,615 | -$19,583 | 39% | -0.012 |
| 2022 | 569 | +$10,087 | 42% | +0.018 |
| 2023 | 1,511 | -$19,620 | 41% | -0.013 |
| 2024 | 1,438 | -$45,097 | 39% | -0.031 |

**Reading:** Only 2/5 years positive. 2024 is the worst (-$45K) — meaning the strategy got progressively worse in the most-recent year, which is the opposite of robustness.

---

## 8. Per-level-kind attribution

| Strategy | Level kind | n | P&L | WR | Avg R |
|---|---|---:|---:|---:|---:|
| Rejection (VIX on) | HVN | 14,874 | +$248,103 | 40% | +0.017 |
| Rejection (VIX on) | POC | 1,225 | -$4,777 | 47% | -0.004 |
| Breakout (VIX on) | LVN | 6,346 | -$64,628 | 40% | -0.010 |

**Reading:** All of the rejection edge comes from **HVN** levels (+$248K). POC entries are wash. This is consistent with AMT theory — HVN edges are the actionable reaction levels; POC is a magnet (price *moves to*, not *reacts at*). Reconfigure: drop POC from the rejection spec entirely. LVN breakout is structurally broken — the "vacuum" hypothesis doesn't hold for liquid mega-caps with continuous institutional participation.

---

## 9. Honest comparison with PDH-Fade (Wave 3 survivor)

| Metric | PDH-Fade (Wave 3) | VP-Rejection (VIX on) |
|---|---:|---:|
| Sharpe | **1.47** | 0.62 |
| n_trades | 9,874 | 16,099 |
| Win rate | 18.8% | 41% |
| Profit factor | 1.27 | 1.03 |
| MaxDD | -24.0% | -47.4% |
| Avg R/trade | +0.06 | +0.015 |
| Net P&L | +$582K | +$243K |

**Critical observation: VP-Rejection has 2.2× the win rate (41% vs 19%) but 1/4 the avg R (+0.015 vs +0.06).** Profit factor 1.03 vs 1.27 says the same thing differently. VP-Rejection wins more often but wins are tiny — the strategy is structurally near-coin-flip with a slight positive bias. PDH-Fade is a low-WR convex-payoff strategy where the 19% of winners are 5R+ moves; VP-Rejection's winners are mostly small wins clipped at the next nearby HVN (the targets are too close given the dense HVN landscape).

**Are the strategies complementary or duplicative?** Both fade at confluence resistance/support levels. Their level sources are different (PDH = yesterday's RTH high; VP = 5-session volume profile clusters) but their entry semantics — "price probes a known level, fails, closes back, fade the failure" — are identical. The trade-level correlation would be moderate-positive: on PDH-fade days where PDH coincides with an HVN cluster, both strategies fire. Wave 3's per-symbol-per-day lock would resolve collisions, but the *direction of edge* is the same.

**Verdict: VP-Rejection duplicates PDH-Fade's structural edge at lower fidelity.** It does not complement it. Deploying both would not diversify the portfolio meaningfully (cross-strategy correlation ~0.5-0.7 expected); deploying VP alone would underperform PDH alone. **PDH-Fade is the canonical fade primitive for this framework. VP-Rejection should not ship.**

---

## 10. Why VP-Breakout fails on this universe

The Trading Notes "vacuum through LVN" methodology relies on the premise that LVN areas are *uncrowded* — when price probes them with a momentum candle, there's no resting institutional inventory to absorb the move. In real markets:

1. **Mega-cap liquidity is continuous.** AAPL, MSFT, TSLA have HFT participation across every penny. There are no real "vacuum" zones because the depth book is uniformly populated by market-makers. LVNs in the 5-day profile reflect *historical* volume troughs, not *current* depth troughs.
2. **1-min bar fidelity loses sub-bar liquidity.** Tick-level LVNs (per the design doc's "tick data is mandatory" note) might be detectable; bar-level LVNs are approximations of approximations.
3. **The 36-symbol universe is all liquid US equities.** A small-cap / catalyst-day universe (the squeeze-bot's natural habitat) would have *real* LVNs because the participation is thin. But the directive scoped this backtest to the Wave 3 36-symbol shortlist — which means we're testing VP-Breakout on the universe it's structurally worst-suited for.

**Recommendation:** If VP-Breakout is to be re-tested, do it on the catalyst-day universe (premarket gap > 2% AND today's RVOL > 2×, per the Wave 5 P1 priority list) using tick-level profile reconstruction. Within this universe, the spec is dead.

---

## 11. Limitations & known fidelity gaps

1. **Bar-level profile (not tick-level).** Design doc §4.5 calls out tick-level reconstruction as the "right" answer. We use typical-price binning. 1-3 bin-width error on POC; HVN/LVN classifications stable within 1 cluster.
2. **Synthetic VIX proxy, not CBOE VIX.** The proxy correlates with regime but its absolute values are inflated vs real VIX (median 34 vs real-VIX ~17 over this window). Threshold calibrated to p75 of the proxy distribution to match Wave 3's 20-25% suppression rate.
3. **ATR trailing not implemented** in this harness (winners clip at the next opposing HVN or 1.5/2.0 R fallback). Wave 5 P1 priority — running through `nautilus_subprocess_runner` would close this gap.
4. **5% bar-volume cap not applied** in fixed-dollar mode here (per Wave 3 finding that the cap binds wrong on mega-caps). Live deployment would need correct ADV-dollars sizing.
5. **No commission/borrow.** Same caveat as Wave 3 — material at scale, immaterial at our notional.
6. **POC merged into HVN bin in cluster logic.** The current code excludes POC from HVN emission (POC is reported as kind="POC"). But adjacent HVN bins flanking the POC may be in the same volume cluster; the centroid splits across the POC bin in a way that may slightly bias level placement. Sub-cluster splitting at POC could improve precision marginally.

---

## 12. Files delivered

```
framework/level_sources/volume_profile.py    471 lines — VolumeProfileSource + from_config
strategies/volume_profile_rejection.yaml      55 lines — mean-reversion fade spec
strategies/volume_profile_breakout.yaml       58 lines — vacuum breakout spec
backtest/volume_profile_backtest.py          ~750 lines — bar-level engine + 6-variant single-pass driver
backtest/run_volume_profile_backtest.py      ~225 lines — entry point, metrics, JSON+CSV output
backtest/volume_profile_results.json          16 KB — full metrics bundle
backtest/volume_profile_vix_proxy_cache.json  42 KB — daily VIX proxy values (cached)
backtest/volume_profile_*_trades.csv          6 files, ~17 MB total — per-variant trade logs
tests/framework/test_volume_profile.py        ~440 lines — 28 unit tests (all pass)
```

No live code touched. Existing bots, scanners, persistence — all untouched per directive §1.2.

---

## 13. Recommendations

### Backtest-only (per directive §9)

1. **Do not deploy VP-Rejection.** Sharpe 0.62 < 1.0 gate. MDD -47% × 3.2 worse than ≤15% gate. The strategy is structurally a worse version of PDH-Fade (Wave 3 survivor).
2. **Do not deploy VP-Breakout.** Structurally net-negative. Re-test on catalyst-day universe + tick-level data if the methodology is to be revisited.
3. **Confirm VIX overlay default-ON for Phase 2 specs.** Real-data validation: +0.28 Sharpe lift on rejection, +0.24 on portfolio. Matches Wave 3 K-paper finding categorically.
4. **Keep VolumeProfileSource as a level source primitive** even though the two specs fail. It's reusable for future strategies (e.g., a "POC-rotation" target, or an "HVN-confluence-with-PDH" composite). The infrastructure cost was sunk; the option value is positive.

### Suggested next-wave experiments

5. **Composite strategy: PDH-Fade with VP-HVN confluence filter.** Only fire PDH-Fade if PDH falls within an HVN cluster from the 5-session profile. Hypothesis: confluence improves expectancy. Quick to backtest (re-filter PDH-Fade trade log).
6. **Volume-Profile-Rejection on catalyst-day universe.** Different distribution of price/volume — LVNs may be real there.
7. **Tick-level POC reconstruction.** Closes the 1-3 bin-width error. If POC drift is significant in real markets, this would materially shift the POC-entry expectancy.

### Acceptance verdict (clean)

| Acceptance gate | Rejection | Breakout | Portfolio |
|---|---|---|---|
| Sharpe ≥ 1.0 OOS | **FAIL** | **FAIL** | **FAIL** |
| ≥ 100 trades | PASS | PASS | PASS |
| Max DD ≤ 15% | **FAIL** | **FAIL** | **FAIL** |
| VIX-on improves Sharpe | PASS | FAIL | PASS |

**Final: Neither spec ships to paper.** Backtest infrastructure ships. The level source primitive ships (for future composite strategies). Strategy specs are archived for reference; the YAML files remain in the repo for completeness but should not be loaded by the portfolio runner without explicit override.

---

## 14. Open questions for Cowork

1. **Should we run a PDH-Fade × VP-HVN-confluence composite as a quick follow-up?** ~30 minutes of compute, no new infrastructure required. Could materially answer whether VP adds value when used as a filter rather than a primary level source.
2. **Catalyst-day universe is Wave 5 P1.** Should VP-Breakout be re-evaluated there once that filter ships, or pulled from the framework entirely?
3. **POC behavior is interesting.** WR 47% with -0.004 avg R — close to symmetric. Could a POC-magnet *target* strategy (long when below POC, short when above) work? Different problem statement than what was directed; flagging for future research.

Proceeding to honor directive §9 hard stop: backtest only, no paper deployment. Awaiting Cowork direction on whether to pursue follow-ups above or pivot to other Wave 5 agents (Anchored VWAP, L2 confirmation).
