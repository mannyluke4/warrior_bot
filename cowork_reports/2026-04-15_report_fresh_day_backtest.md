# Report — 2026-04-15 fresh-day backtest (BIRD chop)

**Author:** CC (Opus)
**Date:** 2026-04-15 afternoon
**For:** Cowork
**Status:** Diagnostic — no action items yet, surfacing a pattern worth discussing.

---

## Context

Today's live session had multiple infrastructure interruptions (watchdog kills earlier in the morning, then session-resume shipping work starting late morning). Live P&L: $0 on 0 trades. Manny wanted to know what the bot *would* have done with a clean day.

The first pass used the live bot's locally-written tick cache, which was incomplete (several symbols had only 8:47-era snapshots from a prior crash) and included Databento-bridge symbols that aren't reproducible in backtest — it returned a misleading `-$8 / 2 trades`. Redone as a fresh-day emulation per the methodology below.

---

## Methodology — how the backtest was run

**Step 1 — regenerate scanner results for today using Alpaca full-day ticks.**

```bash
source venv/bin/activate
python scanner_sim.py --date 2026-04-15
```

This replays the scanner at every checkpoint against today's actual tick data, producing `scanner_results/2026-04-15.json` with per-candidate fields: `symbol`, `discovery_time` (earliest checkpoint the symbol passed filters), `gap_pct`, `float_millions`, `profile`, and the `sim_start` the backtest should use.

Output: 3 candidates discovered — CIIT (07:00), BIRD (08:15), VNCE (09:30). The 5 extra symbols the live bot had subscribed to via Databento bridge (CRCG, CRWG, KIDZ, MNTS, NICM, OKLL) are not in scanner output by construction — the scanner sim doesn't model the external `watchlist.txt` bridge.

**Step 2 — cache Alpaca full-day ticks for the scanner-discovered symbols.**

```bash
python cache_tick_data.py --dates 2026-04-15 --force
```

`--force` re-downloads even if cached (today had partial/stale entries from the live-bot crashes). Result:

```
[2026-04-15] Caching 3 stocks: CIIT, BIRD, VNCE
  CIIT: 37,289 ticks cached (md5: 4ced46cd2ea6)
  BIRD: 2,094,744 ticks cached (md5: 727798eeeeda)
  VNCE: 3,431 ticks cached (md5: 7ec4e29d2abe)
```

**Step 3 — run `simulate.py` per symbol, starting at each symbol's discovery time.**

Standard form from CLAUDE.md, with `sim_start` set to the discovery_time from scanner_results (not the regression-default 07:00). BIRD window extended to 16:00 since its tape kept moving past noon.

```bash
# CIIT — discovered 07:00, standard window
WB_MP_ENABLED=1 python simulate.py CIIT 2026-04-15 07:00 12:00 \
  --ticks --tick-cache tick_cache/ --no-fundamentals

# BIRD — discovered 08:15, extended to 16:00 for afternoon action
WB_MP_ENABLED=1 python simulate.py BIRD 2026-04-15 08:15 16:00 \
  --ticks --tick-cache tick_cache/ --no-fundamentals

# VNCE — discovered 09:30, standard window
WB_MP_ENABLED=1 python simulate.py VNCE 2026-04-15 09:30 12:00 \
  --ticks --tick-cache tick_cache/ --no-fundamentals
```

Flags per CLAUDE.md conventions:
- `--ticks` / `--tick-cache tick_cache/` — tick mode, matches live bot tick-by-tick replay
- `--no-fundamentals` — matches batch-runner behavior, avoids the standalone-sim stale-fundamentals bug (Alpaca-refetched float returning 0.0M on certain symbols)
- `WB_MP_ENABLED=1` — required to reach regression parity; live bot has MP gated OFF but sim keeps it on to preserve VERO/ROLR targets and exercise MP V2 (post-SQ re-entry), which is what produced T10 on BIRD today

**Environment state** — whatever is in `.env` at run time. All today's live-deployed gates were active in the sim: X01 tuning (VOL_MULT 2.5, MAX_ATTEMPTS 5, RISK_PCT 3.5%, TARGET_R 1.5), stale-seed gate, winsorize. Entry-retry changes from earlier today are live-only (see commit `080baf2`) and do not affect sim behavior — simulate.py uses legacy instant-fill.

---

## Scanner-discovered symbols (3 total)

| Symbol | Discovery | Gap | Float | Profile | Notes |
|---|---|---|---|---|---|
| CIIT | 07:00 | +64.5% | 8.1M | B | criteria met 04:00, early rip |
| BIRD | 08:15 | +20.1% | 5.25M | B | criteria met 08:01 |
| VNCE | 09:30 | +11.3% | 2.61M | A | discovered late, 09:15 actual |

Databento-bridge symbols the live bot subscribed to today (CRCG, CRWG, KIDZ, MNTS, NICM, OKLL) are not in the scanner output — they came via the external `watchlist.txt` bridge and don't emulate cleanly in backtest.

---

## Results

| Symbol | Window | Armed | Trades | P&L |
|---|---|---|---|---|
| CIIT | 07:00-12:00 | 0 | 0 | — |
| BIRD | 08:15-16:00 | 6 | 10 (4W/6L) | **-$1,909** |
| VNCE | 09:30-12:00 | 0 | 0 | — |
| **Total** | | 6 | 10 | **-$1,909** |

Live: $0 / 0 trades. Today's crashes saved $1,909.

---

## BIRD trade sequence — a chop-day profile

```
WINNERS (08:21-09:01) — caught the rip from $3 → $6:
  T1  08:21  $3.04 → $3.25   sq_target_hit        +$675    +1.3R
  T2  08:27  $3.94 → $4.33   topping_wicky        +$975    +1.0R
  T3  08:48  $4.04 → $4.48   sq_target_hit      +$1,958    +3.9R  ⭐
  T4  08:49  $5.04 → $4.98   sq_para_trail        -$214    -0.4R
  T5  09:01  $6.04 → $6.29   sq_target_hit        +$803    +1.6R
                                                  ────────
                                           MORNING +$4,197

COLLAPSE (09:03-10:20) — chopped at the top:
  T6  09:03  $7.04 → $6.90   sq_stop_hit          -$500    -1.0R
  T7  09:22  $6.99 → $6.97   bearish_engulfing    -$171    -0.1R
  T8  09:57 $11.77 →$11.47   topping_wicky      -$1,298    -0.4R
  T9  10:13 $11.38 →$11.12   topping_wicky      -$1,131    -0.2R
  T10 10:20 $11.50 →$10.81   epl_mp_stop_hit    -$3,005    -1.0R  💀
                                                  ────────
                                           CHOP   -$6,105

                                           NET    -$1,909
```

### Arc interpretation

- Morning through T5 was textbook: bot rode the $3→$6 cascade, T3 alone was +$1,958 / +3.9R. This is exactly the pattern V1/SQ was tuned for.
- T6 marked the inflection. BIRD ripped further (gap to $11+) on what looks like a second catalyst leg — we have no book visibility here, but the price-action sequence (low volatility near $7, then vertical to $11) suggests news or a related-name sympathy move.
- T8-T10 are the cost of chasing the second leg: all three entered at local highs ($11+), all three got reversed immediately. Two `topping_wicky` exits in a row (T8, T9) followed by an EPL MP re-entry taking the biggest single loss on T10.

---

## Three things worth discussing

### 1. The EPL MP re-entry after two consecutive topping-wicky exits (T8, T9 → T10)

T8 and T9 were back-to-back losing `topping_wicky_exit_full` signals within 16 minutes. T10 was an EPL MP re-entry that immediately hit stop for -$3,005. The EPL framework fired after consecutive signal-driven losses on the same symbol — is that correct behavior, or should EPL throttle when the underlying sequence is losing?

There's a clean question here: **does EPL re-entry logic consider the P&L trajectory of prior trades on the symbol, or just the graduation event?** If it's the latter, adding a "don't re-enter if the two previous trades on this symbol are losers" gate could have saved ~$3,000 today.

Reality-check: this is n=1. Today's BIRD arc may not repeat. But the *mechanism* — re-entering after the symbol signaled "topping" twice — is worth auditing separately from this specific day.

### 2. Trade sizing on T10 was unchanged despite the morning's +$4,197

Dynamic risk (3.5% of equity) would have sized T10 larger given the morning's gains. The -1R on T10 came out as $3,005, which on equity ~$34K equity post-morning is about 9% — bigger than the per-trade 3.5% cap. This might be because the dollar stop was large ($11.50 → ~$10.81 = $0.69 × qty) relative to a low-volatility morning, not a sizing bug. Worth confirming.

Not a bug, but a note: **-1R is not a fixed dollar amount**, it's whatever the setup's R happens to be. T10's R was $0.69 (huge) vs T1's $0.14 (normal). Chasing high-$-risk setups late in a chop amplifies drawdown.

### 3. The 11:00 ET window cutoff wouldn't have saved today

Our trading window is `04:00-11:00, 16:00-20:00 ET`. T8 (09:57), T9 (10:13), T10 (10:20) all fell within window. So the standard "stop trading after 11:00" gate doesn't protect this sequence. A tighter intra-day cutoff (e.g., "no new entries after first R × 2 giveback" or "no new entries after 2 consecutive losses on the same symbol") would've.

---

## Non-action items (context for Cowork)

- **Scanner-sim vs Databento bridge:** 5 of today's 8 live-subscribed symbols never appear in scanner_sim output. That means for crash-free days, the live bot has more symbols under watch than a backtest can reproduce. Something to keep in mind when live-vs-sim divergence comes up as a signal.
- **KIDZ backtest from earlier today:** the `-$429` KIDZ "loss" I reported in the quick first-pass sim was against *partial* locally-cached ticks (only what the live bot had persisted pre-crash). With proper Alpaca full-day data, KIDZ produced 0 arms and 0 trades — it never qualified as a scanner candidate today. First-pass numbers were misleading; fresh-day numbers are authoritative.
- **Session-resume shipped today:** `WB_SESSION_RESUME_ENABLED=0` default, validated end-to-end via crash-injection test. Separate report: see commits `e9cfd20` through `033fb57` on `v2-ibkr-migration`.

---

## Ask for Cowork

No decisions required. But if any of the three discussion points above warrant a follow-up directive, the EPL-re-entry-after-losing-sequence one feels the most concrete — it's a deterministic gate that'd have eliminated the worst single trade of the day. Open questions:

- Does EPL even consider recent-trade P&L on the same symbol, or is graduation the only trigger?
- Would "no EPL re-entry within N minutes of 2+ losses on same symbol" be a clean, gated feature to prototype?
- Is BIRD-like chop common enough (across the 49-day dataset) to pick up a meaningful signal, or is this an n=1 that dies in the noise?

CC is happy to prototype the gate as a gated feature if Cowork wants to quantify the YTD impact first.

---

*CC (Opus), 2026-04-15 afternoon. Quiet live day, noisy counterfactual.*
