# WB v2 Stage 0 Synthesis — Research Foundation Complete

**Date:** 2026-05-18
**Author:** CC
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-18_WB_V2_STAGE_0.md`
**Sources:** 6 deliverables under `/Users/duffy/warrior_bot_v2/wb_v2/`

---

## TL;DR

Stage 0 research foundation is complete. WB v2 is **a strategy reverse-engineered from how Manny actually trades, using the same playbook that turned Ross Cameron's discretionary squeeze into the squeeze bot.** No code changes. No live deployment. Ready for Manny review and Stage 1 directive.

**Headline finding:** Manny saying *"stocks with the most ticks"* is operationally equivalent to *"highest dollar-volume stocks"* — Spearman rank correlation **0.91** across 81 sessions. RVOL is the meaningful outlier (0.63) and surfaces a different stock population. **Universe selector for Stage 1: ticks-or-volume as primary, RVOL as parallel secondary track.**

**Two questions for Manny that gate Stage 1:**
1. Primary universe selector — `tick_rate_rank` (matches your eye-ball metric exactly) or `composite_score` (averages all 4 ranking metrics)?
2. Universe size — top-10 (deeper signal-to-noise) or top-20 (wider opportunity set)?

Both answers feed directly into the Stage 1 directive.

---

## 1. The six deliverables — what landed

| # | File | Purpose | Status |
|---|---|---|---|
| 1 | `wb_v2/research_methodology.md` (1,890 words) | Methodology mirror — 12-row table mapping squeeze v1 playbook to WB v2 | ✅ |
| 2 | `wb_v2/operationalization_candidates.md` (3,200 words) | 7 levels + 5 MACDs + 5 universe selectors with parameters and build status | ✅ |
| 3 | `wb_v2/tick_audit_universe_extraction.md` (3,738 words) + `extracted_universe.csv` (993 rows, 81 sessions, 583 symbols) | Mined tick-audit logs into ranked universe data | ✅ |
| 4 | `wb_v2/trade_intake_template.csv` + example | Schema Manny fills going forward to build the v2 trade log | ✅ |
| 5 | `wb_v2/setup_taxonomy_seed.md` (1,475 words) | Wave-Reversal Long/Short + 4 sub-type axes | ✅ |
| 6 | `wb_v2/exit_reuse_audit.md` (2,400 words) | File:line audit of 10 squeeze exit primitives + reuse plan | ✅ |

Total Stage 0 output: ~13,000 words of research + ~1,000 rows of universe extraction data + 4 templates. Zero modifications to Setup A sacred files.

---

## 2. The strategy in one paragraph

Manny watches the squeeze bot's tick audit each morning to find the most active stocks of the day. He opens the chart on the highest-tick names, waits for price to pull back to a support level, and adds when MACD turns green near the wave low. He scales out around the midpoint of the recovery. He runs the mirror on the short side — sell resistance when MACD turns red near a wave high. He's intraday only, no overnights. *"Ride the fluctuation."*

That's the strategy. Three discrete components to operationalize:
1. **Universe** = top-N by ticks (= top-N by dollar volume per §3 below)
2. **Setup** = level + MACD signal (long: support + MACD-green-near-low; short: resistance + MACD-red-near-high)
3. **Exit** = reuse the squeeze bot's exit stack (already proven, no new code)

---

## 3. The 0.91 finding — universe selector is mostly solved

Spearman rank correlation across 2,400 (session, symbol) observations:

| Metric pair | Correlation | Interpretation |
|---|---:|---|
| `tick_rate_rank` ↔ `volume_rank` | **0.91** | Effectively the same metric |
| `tick_rate_rank` ↔ `range_rank` | 0.88 | Closely related (volume drives range) |
| `volume_rank` ↔ `range_rank` | 0.84 | Same family |
| `rvol_rank` ↔ `tick_rate_rank` | **0.63** | **Distinct — surfaces sleeper stocks** |
| `rvol_rank` ↔ `volume_rank` | 0.65 | Same family as ticks vs RVOL |

**What this means for Stage 1:**
- **Primary selector** = ticks or dollar-volume (pick one — they produce nearly identical universes; ticks matches Manny's verbatim more literally)
- **Parallel secondary track** = RVOL (different population — *previously sleepy stocks waking up* vs *consistently active stocks*)
- Stage 1 backtests both selectors. If RVOL universe produces different P&L, we run both in production.

**Universe is daily-fresh:** the most frequent occupant of any day's top-20 only appears 16% of the time. Adjacent-session top-5 turnover is 95.8% (median 100%). The selector MUST rebuild every session — there's no static watchlist version.

Top-5 most-frequent across the 81-session window: **FATN (13), SST (13), KIDZ (12), ELAB (7), BATL (7).** None of these are mega-caps — Manny's universe lives in small-cap-gapper territory, which is also where the squeeze bot trades. **Implication for Stage 1:** the WB v2 universe is *adjacent to* the squeeze universe, not disjoint. Conflict-rule design (per-symbol-per-day lock generalized) matters.

---

## 4. Operationalization menu — what Stage 1 picks from

### Levels (7 candidates, 5 already built in `framework/`)
| # | Level type | Built? | Stage 1 cost |
|---|---|---|---|
| 1 | PDH/PDL | ✅ `framework/level_sources/pdh_pdl.py` | $0 |
| 2 | Session VWAP + bands | ✅ `framework/level_sources/vwap.py` | $0 |
| 3 | Anchored VWAP (gap/earnings/FOMC) | ✅ `framework/level_sources/anchored_vwap.py` | $0 (session_open variant is a 1-line tweak) |
| 4 | Pivot points (classic / Fib / Camarilla) | ❌ | ~150 LOC |
| 5 | Round-number tiered | ✅ `framework/level_sources/round_number.py` (retired as standalone, primitive available) | $0 |
| 6 | Swing-high/low fractals (n=3, 60min) | ❌ | ~200 LOC |
| 7 | Volume profile (POC/HVN/LVN) | ✅ `framework/level_sources/volume_profile.py` | $0 |

### MACD operationalizations (5 candidates, 0 framework-built)
A `MACDState` math primitive exists at `macd.py:MACDState` (12/26/9 hardcoded, 4-bar rolling history). For Stage 1, need a proper `framework/indicators/macd.py` module + `framework/confirmations/macd_*.py` for the 5 variants.

- Zero-cross (12/26/9 standard)
- Signal-line cross near multi-bar low/high
- Histogram momentum (consecutive decreasing-magnitude negative + turn)
- Fast 5/13/5 variant
- Composite "MACD-at-level" (literal encoding of Manny's spoken rule)

**Library choice:** custom EMA recurrence (no `talib`/`pandas-ta` in `requirements.txt`). ~250 LOC.

### Universe selectors (5 candidates, mostly data-ready)
- Top-N by dollar volume (1m bars)
- **Top-N by tick rate (Manny's original eye-ball trigger)** — sourced from `bot_v3_hybrid.py:audit_tick_health` heartbeat lines (10,582 entries on 2026-05-15)
- Top-N by RVOL (current vol / 30-day avg)
- Top-N by intraday range %
- Composite blend

Tick-rate variant needs ~50 LOC log parser. Other 4 are pure pandas on existing data.

**Total Stage 1 new code estimate: ~600 LOC + tests. No new market-data subscription required.**

---

## 5. Exit reuse — the squeeze cascade WB v2 inherits

Squeeze's exit cascade is documented at `bot_v3_hybrid.py:3299-3376` (live IBKR path) and mirrored at `trade_manager.py:2907-2974` (Alpaca paper path). Both are READ ONLY for WB v2.

**10 primitives audited** (full file:line in `wb_v2/exit_reuse_audit.md`):
1. Force-exit session-end SELL LIMIT chain — `force_exit.py:64-79, 104-193`
2. Dollar loss cap, hard stop, tiered max-loss (paper only)
3. `sq_para_trail_r` pre-target trail
4. 2R target + `SQ_CORE_PCT` partial
5. Runner trail
6. Bail timer
7. Peak update / persist
8. `exit_trade` async-verify submission

**Reuse plan:**
- **Direct call:** `should_force_exit_now`, `force_exit_position`, `state.broker.submit_limit` — no wrapper needed.
- **Adapter (~150 LOC):** `wb_v2_manage_exit` and `wb_v2_exit_trade` mirror the squeeze control flow but target `state.wb_v2_positions` (not `state.open_position`), book P&L to WB-v2-local counters, and add the short-side mirror (squeeze is long-only).
- **Two non-obvious findings flagged:**
  1. Live IBKR bot **lacks tiered max-loss** that exists in `PaperTradeManager` — deliberate divergence, WB v2 must respect it
  2. Squeeze 2R-target branch has **EPL graduation coupling** WB v2 adapter must drop

The "no new exit code" directive is honored: Stage 1 + Stage 2 reuse the squeeze cascade verbatim. WB v2 is an **entry-side** strategy with a borrowed exit stack.

---

## 6. Setup taxonomy seed — discussion only

Two top-level setups derived from Manny's verbatim:
- **Wave-Reversal Long:** support level + MACD green near wave bottom
- **Wave-Reversal Short:** resistance level + MACD red near wave top (mirror)

Four sub-type axes for Stage 1+ clustering (free-text in trade intake → cluster post-hoc):
- **Level type** — PDH/PDL / VWAP / anchored VWAP / pivots / round / vol profile
- **Wave depth** — deep pullback / shallow chop / failed-breakout reversal
- **Time of day** — premarket / open hour / midday / power hour
- **MACD variant** — zero-cross / line-signal cross / histogram bottoming, parameter set 12/26/9 vs 5/13/5

This is **not a final taxonomy** — Manny edits or replaces. The intake template's free-text `level_type` and `macd_state` columns are designed to let real trade data drive clustering, not the other way around.

---

## 7. Trade intake template — Manny's forward log

`wb_v2/trade_intake_template.csv` ships with 14 columns and a sibling `trade_intake_template_example.csv` with 5 realistic rows (WLDS / FATN / KBSX / MYSE / ATRA) covering long + short, 1m + 5m, winners + a stop. Load-tested with `pandas.read_csv()`; free-text fields with commas (level_type, macd_state, exit_reason, notes) round-trip clean with double-quote escaping.

**Workflow once Stage 1 starts:** Manny logs every WB v2 trade with the free-text fields filled in. CC mines the log periodically to cluster the taxonomy, refine level/MACD operationalizations, and identify filter candidates.

---

## 8. Methodology mirror — the squeeze v1 playbook re-applied

The methodology doc (`wb_v2/research_methodology.md`) lays out a 12-row side-by-side table mapping every stage of squeeze v1's development to its WB v2 analog:

| Stage | Squeeze v1 (Ross) | WB v2 (Manny) |
|---|---|---|
| Setup description | "vol spike + level break, ride to 2R" | "support + MACD green near bottom, snip profits halfway up the wave" |
| Data source | Live tick audit + Databento bars | Live tick audit + intra-session forward log + Manny's chart screenshots |
| Tagging | Setup tags in trade logs | Free-text level/MACD/exit-reason fields in intake CSV |
| Filter discovery | Per-trade feature mining (gap %, RVOL, time-of-day, etc.) | Same playbook applied to WB v2 trade log |
| Backtest | `simulate.py` with tick replay | `backtest/portfolio_backtest.py` adapted |
| Exits | V1 mechanical exits proven best | **Same V1 exits, reused** |
| Sizing | Fixed-dollar conservative start | Fixed-dollar conservative start ($200 proposed) |
| Paper validation | 60+ days | TBD per Stage 1 |
| Live cutover | After paper validates | Conditional on paper validation |

**The exploration license is explicit:** if Stage 1 finds the rule doesn't pay off, we honestly walk back, just like we did with WB v1. Future strategies get the same license. Reverse-engineering Manny's discretionary process is not a guarantee of edge — it's an iteration of the methodology that produced the squeeze bot.

---

## 9. Questions for Manny

These two answers gate the Stage 1 directive:

**Q1 — Primary universe selector:**
- (a) `tick_rate_rank` — literal match for "stocks with the most ticks" from your verbatim
- (b) `volume_rank` — 0.91-correlated with ticks, slightly cleaner (no log parser needed)
- (c) `composite_score` — average of normalized ticks/volume/RVOL/range ranks

Cowork recommendation: **(a) ticks-rate** to match your eye-ball intuition literally. We can ablate against (c) composite in Stage 1 if you want.

**Q2 — Universe size:**
- (a) Top-10 per session — deeper signal-to-noise, fewer setups per day
- (b) Top-20 per session — wider opportunity set, more noise

Cowork recommendation: **top-15** as a middle ground, or **top-20** if you want maximum opportunity for the bot to find your wave-reversal patterns. Stage 1 can ablate this trivially.

---

## 10. Stage 1 readiness checklist

- [x] Methodology documented
- [x] Operationalization candidates enumerated with build status
- [x] Universe extraction done (981 rows, 81 sessions, 583 symbols)
- [x] Trade intake schema fixed (Manny starts logging immediately)
- [x] Setup taxonomy seeded (subject to Manny edits)
- [x] Exit primitives audited (10 functions, reuse plan documented)
- [ ] **Manny answers Q1 and Q2**
- [ ] **Manny starts logging WB v2 trades to `wb_v2/trade_intake.csv`** (rolling forward log → Stage 1 + Stage 2 cluster source)
- [ ] **Cowork issues Stage 1 directive** (backtest combinations, filter discovery, paper-deploy gate)

---

## 11. Hard constraints honored

Per the directive:
- ✅ Setup A is sacred — zero modifications to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`. Squeeze exit primitives referenced READ ONLY.
- ✅ Old WB stays at `WB_STRATEGY_ENABLED=0`. WB v2 lives under new `wb_v2/` directory.
- ✅ Branch `v2-ibkr-migration` only.
- ✅ No live deployment. Research only.
- ✅ WB paper Alpaca account stays idle until Stage 1 produces a deploy-eligible spec.

---

## 12. Account allocation (recap)

| Alpaca paper account | Strategy | Status |
|---|---|---|
| Squeeze paper | Squeeze v3 | LIVE — 6/15 real-money cutover unchanged |
| Engine paper ($69K) | Healthy Fluctuation Framework | LIVE this morning 5/18 (Monday-skip filter on, no entries today by design; first signals 5/19) |
| **WB paper ($27K)** | **WB v2 (fluctuation-hunter)** | **RESEARCH ONLY — not deployed until Stage 1 passes** |

---

**Ride the fluctuation. Stage 0 done. Manny + Cowork — your move.**
