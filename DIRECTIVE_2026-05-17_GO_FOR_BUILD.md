# GO FOR BUILD — All 8 Decisions Approved

**Date:** 2026-05-17
**Branch:** `v2-ibkr-migration`
**Status:** APPROVED — execute Wave 4 build immediately

---

## Manny's approvals (verbatim: "All 8 approved")

| # | Decision | Status |
|---|---|---|
| 1 | 3-strategy paper deployment (PDH-Fade-filtered, ORB-aligned $300+ Mon-skip, PDH-Breakout-F4) | ✅ APPROVED |
| 2 | `release_on_stop` conflict rule (recovers $427K structural finding) | ✅ APPROVED |
| 3 | `WB_FRAMEWORK_SKIP_MONDAYS=1` default ON | ✅ APPROVED |
| 4 | VIX overlay default ON at 25/22 thresholds | ✅ APPROVED |
| 5 | Retire VWAP-MR and Round-Number (`status: retired` in YAML) | ✅ APPROVED |
| 6 | 9-tier sizing ladder ($300 → $2,500 at $250K, ladder up to $5K) | ✅ APPROVED |
| 7 | No auto-advancement during Wave 4 paper (Tier 1 fixed for 60 days) | ✅ APPROVED |
| 8 | Combined squeeze + framework backtest workstream (5-year, tier-aware) | ✅ APPROVED |

---

## Hard constraints (do not violate)

1. **Setup A is sacred.** Do NOT modify any production file. Specifically untouchable:
   - `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots
   - `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`
   - `wb_persistence.py`, `wb_intraday_adder.py`
2. **Branch:** all work on `v2-ibkr-migration`. Do not merge to main.
3. **Execution venue:** Alpaca only (paper for Wave 4). No IBKR paper.
4. **No overnights.** Force-exit before close on all framework strategies.
5. **No market orders.** Force-exit uses SELL LIMIT chains.
6. **Production track unchanged.** Squeeze real-money cutover stays on **June 15**.
7. **Wave 4 paper runs on a separate Alpaca paper account with a separate clientId.**

---

## Execution order (CC, parallelize where independent)

### Phase A — Correctness fixes (must land before any backtest)

A1. **One-line fix:** `portfolio_backtest.py:909` lock_collisions.csv path.
A2. **Implement `release_on_stop`** in the conflict resolver. Existing first-in-time rule kept available behind a flag for regression testing only.
A3. **Subprocess Nautilus revalidation** of the abandon-rule (~1.5hr). Confirms PDH-Fade F1+abandon@10 numbers reproduce out of harness.

### Phase B — Strategy spec wiring (parallel with Phase A)

B1. Wire 3 filtered YAML specs:
   - `pdh_fade_filtered.yaml` (F1 entry-window + abandon@10)
   - `orb_aligned_300plus_monskip.yaml` ($300+ tier, Mon-skip, VIX gate)
   - `pdh_breakout_f4.yaml` (NOT-blacklist + VWAP-aligned + consolidation<1% + vol≥2)
B2. Mark `vwap_mr.yaml` and `round_number.yaml` as `status: retired`.
B3. Set framework defaults: `WB_FRAMEWORK_SKIP_MONDAYS=1`, `WB_VIX_OVERLAY=1`, VIX thresholds 25/22.

### Phase C — Sizing infrastructure

C1. **Build `TieredSizer`** with the 9-tier ladder.
   - Reads **combined equity** across squeeze + framework.
   - Advancement gates: equity floor ≥3 sessions, rolling 30-session Sharpe ≥1.0, no active drawdown, max 1 tier per 14 days.
   - Retreat: -15% from tier high → automatic; rolling Sharpe <0.3 → retreat one tier.
   - **Wave 4 paper override:** `WB_TIER_LOCK=1` pins Tier 1 for 60 days regardless of gates (Decision 7).
C2. Unit tests for advancement, retreat, and the lock flag.

### Phase D — Combined backtest workstream (Decision 8)

D1. **Squeeze framework migration:** wrap squeeze as a YAML strategy spec inside the framework architecture. Logic stays bit-identical to `squeeze_detector_v2.py` — this is a wrapper, not a rewrite. Production squeeze code is NOT modified.
D2. **Squeeze historical data audit:** verify Databento coverage for small-cap gappers 2020–2024 ($2-$30, premarket gap, RVOL>2x, float<30M). Report any gaps before harness runs.
D3. **Combined portfolio backtest harness:**
   - 2020-01-01 → 2024-12-31
   - $25K start, compounding
   - Squeeze + 3 framework strategies running concurrently
   - TieredSizer driving sizing off combined equity
   - Tier transitions, drawdowns, and conflict events logged
   - Output: `cowork_reports/2026-05-1?_combined_portfolio_backtest.md` + per-strategy CSVs

### Phase E — Wave 4 paper deploy

E1. Separate Alpaca paper account (new keys), separate clientId.
E2. 60-day minimum paper run.
E3. Real-money decision earliest **mid-August**.
E4. Daily cowork report: equity, per-strategy P&L, conflict events, tier status (locked).

---

## Reporting

- Every phase produces a dated cowork report under `warrior_bot/cowork_reports/`.
- Combined backtest results land before Wave 4 paper goes live so we can sanity-check the 5-year tier path against expectations (Tier 7 ~Year 4).
- If Phase D2 finds material data gaps, **pause and report** before running the harness.

---

## Reminders

- "What I do isn't exactly codable or repeatable... we should learn from this and work the bot out to perform best as a bot, not like a human."
- "Prices fluctuate. Our goal is to find the healthiest fluctuation."
- "We have until about June 15th before we can go live" (squeeze production cutover — unchanged).
- "Never assume workload time with CC."

GO.
