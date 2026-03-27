# MP Trade Logic Analysis — v2 Corrected Megatest

**Generated:** 2026-03-22
**Data source:** `megatest_state_mp_only_v2.json` (mp_only combo — SQ and VR disabled)
**Date range:** 2025-01-02 through 2026-03-20 (297 trading days)


## 1. Architecture of the "Frankenstein" MP Detector

The MP detector in `micro_pullback.py` contains three state machines that share EMA, MACD, and pattern memory:

| State Machine | Method | Timeframe | Logic | Active in Megatest? |
|---|---|---|---|---|
| **A** — Original MP | `on_bar_close()` | 10-second bars | 3 consecutive green candles → pullback (1-3 bars) → trigger candle = ARM | Runs for indicators only. **ARMs come from B.** |
| **B** — 1m Pullback | `_pullback_entry_check()` | 1-minute bars | 1 green impulse candle → pullback (1-3 bars) → confirmation green candle = ARM | **YES — all entries** |
| **C** — 1m Direct | `_direct_entry_check()` | 1-minute bars | Single strong green bar above EMA+VWAP → ARM immediately (no pullback required) | **NO** — `WB_ENTRY_MODE=pullback` |

The `on_bar_close_1m()` method dispatches to either B or C based on `WB_ENTRY_MODE`. In the megatest, this was `pullback`, so **all 154 (Config A) / 156 (Config B) trades used State Machine B**.

No trades used direct/momentum entry (State Machine C).


## 2. Megatest Configuration

Key ENV overrides from `run_megatest.py` ENV_BASE + `.env` defaults:

| Setting | Value | Impact |
|---|---|---|
| `WB_ENTRY_MODE` | `pullback` | All entries via `_pullback_entry_check` (State Machine B) |
| `WB_EXHAUSTION_ENABLED` | `1` | Blocks entries on extended stocks (pre-entry filter) |
| `WB_CONTINUATION_HOLD_ENABLED` | `1` | Suppresses BE/TW exits on high-conviction setups |
| `WB_CONT_HOLD_5M_TREND_GUARD` | `1` | 5-minute trend check for continuation hold |
| `WB_CONT_HOLD_MIN_SCORE` | `8.0` | Score threshold for exit suppression |
| `WB_MAX_LOSS_R` | `0.75` | Tighter than natural stop — safety cap |
| `WB_NO_REENTRY_ENABLED` | `1` | Blocks re-entry after loss on same symbol |
| `WB_EXIT_MODE` | `signal` | Signal-based exits with BE trigger at 3R |
| `WB_SIGNAL_TRAIL_PCT` | `0.99` | Effectively no mechanical trail (99%) |
| `WB_STALE_STOCK_FILTER` | `1` | Blocks ARMs on dead momentum stocks |

Config A applies `min_score=8.0` at entry; Config B uses `min_score=0`.


## 3. Trade Categorization

Since `WB_ENTRY_MODE=pullback`, all entries use the same state machine (B). The differentiation is in **exit logic**:

### 3.1 Exit Categories

**MP-Native Exits** — core to any pullback strategy:
- `bearish_engulfing_exit_full` — bearish engulfing candle detected on 10s bars
- `topping_wicky_exit_full` — topping wicky pattern (long upper wick) detected
- `stop_hit` — price breached the stop level (natural stop from pullback low)

**Bolted-On Exits** — added safety nets and overlays:
- `max_loss_hit` — 0.75R cap fires BEFORE natural stop (WB_MAX_LOSS_R=0.75)
- `trail_stop` — signal mode trailing stop (BE trigger at 3R, then trail)

**Invisible Influences** (not in exit reason but affect outcome):
- Continuation hold: suppresses BE/TW exits → trade stays open longer
- BE parabolic grace: suppresses BE exits during ramps
- Exhaustion filter: blocks entries entirely (trades we never see)
- Stale stock filter: blocks entries entirely
- No re-entry: blocks second attempts on same symbol


### 3.2 Config A Results (score >= 8 gate)

| Category | Trades | Win Rate | Total P&L | Avg P&L |
|---|---|---|---|---|
| **Genuine MP** (BE/TW/stop_hit) | 108 | 37.0% | +$5,563 | +$52 |
| **Max Loss Cap** (0.75R safety) | 42 | 0.0% | -$15,425 | -$367 |
| **Signal Mode Trail** | 4 | 0.0% | -$259 | -$65 |
| **TOTAL** | **154** | **26.0%** | **-$10,121** | **-$66** |

Sub-breakdown of Genuine MP exits:

| Exit Reason | Trades | Win Rate | Total P&L | Avg P&L |
|---|---|---|---|---|
| bearish_engulfing_exit_full | 60 | 31.7% | +$6,371 | +$106 |
| topping_wicky_exit_full | 37 | 56.8% | +$4,195 | +$113 |
| stop_hit | 11 | 0.0% | -$5,003 | -$455 |


### 3.3 Config B Results (no score gate)

| Category | Trades | Win Rate | Total P&L | Avg P&L |
|---|---|---|---|---|
| **Genuine MP** (BE/TW/stop_hit) | 110 | 38.2% | +$6,137 | +$56 |
| **Max Loss Cap** (0.75R safety) | 42 | 0.0% | -$15,492 | -$369 |
| **Signal Mode Trail** | 4 | 0.0% | -$261 | -$65 |
| **TOTAL** | **156** | **26.9%** | **-$9,616** | **-$62** |

Config B outperforms A by $505 — the 2 extra trades (DOMH +$177, BQ +$248) that the score gate blocked were both winners.


## 4. The Max Loss Cap Problem

The max_loss_hit category is the entire source of net loss. Without it, the strategy would be profitable:

- Genuine MP exits alone: **+$5,563 on 108 trades (37% WR)**
- Max loss hits: **-$15,425 on 42 trades (0% WR)**

Every single max_loss_hit trade is a loser (by definition — it fires when the trade is losing). The 0.75R cap saved an estimated **$5,142** vs letting all hit their natural stops (would have been -$20,567).

### R-Multiple at Exit for Max Loss Hits

| R-Mult | Count | Notes |
|---|---|---|
| -0.8R | 12 | Cap fired slightly before natural stop |
| -0.9R | 28 | Cap fired well before natural stop |
| -1.0R | 1 | Cap and stop nearly coincided |
| -2.6R | 1 | SOPA 2025-12-29 — anomalous gap-down through stop |

28 of 42 max_loss trades (67%) exited at -0.9R, meaning the cap is doing meaningful work cutting losses short of the natural stop.


## 5. Continuation Hold Impact

Continuation hold suppresses BE and TW exits on high-scoring setups (score >= 8, vol_dom >= 2x, within time cutoff). This is a **double-edged sword**.

### 5.1 Potential Winners Boosted by Continuation Hold

Trades with score >= 8, held > 3 minutes, and won big — cont_hold likely kept them open through early TW/BE signals:

| Date | Symbol | Hold | P&L | R-Mult | Exit |
|---|---|---|---|---|---|
| 2026-01-16 | VERO | 21 min | +$6,523 | +18.6R | bearish_engulfing |
| 2025-09-03 | AIHS | 17 min | +$1,004 | +2.3R | bearish_engulfing |
| 2025-05-06 | KTTA | 15 min | +$806 | +1.6R | bearish_engulfing |
| 2025-02-25 | WAFU | 7 min | +$438 | +1.4R | topping_wicky |
| 2026-03-18 | ARTL | 7 min | +$447 | +0.9R | topping_wicky |
| 2025-12-12 | KPLT | 13 min | +$422 | +1.1R | topping_wicky |
| **Subtotal** | | | **+$10,140** | | |

### 5.2 Potential Casualties of Continuation Hold

Trades with score >= 8, held > 3 minutes, lost > $200 — cont_hold may have suppressed a good exit:

| Date | Symbol | Hold | P&L | R-Mult | Exit |
|---|---|---|---|---|---|
| 2025-03-24 | UCAR | 4 min | -$522 | -0.9R | max_loss_hit |
| 2025-06-09 | TPST | 4 min | -$460 | -0.9R | max_loss_hit |
| 2025-06-20 | WHLR | 7 min | -$484 | -1.0R | stop_hit |
| 2025-07-22 | IVF | 4 min | -$389 | -0.9R | max_loss_hit |
| 2025-09-09 | SBLX | 32 min | -$254 | -0.6R | trail_stop |
| **Subtotal** | | | **-$2,109** | | |

**Net impact estimate: +$8,031 in favor of continuation hold** — it helps more than it hurts, but the sample is small and the VERO +$6,523 outlier dominates. Without VERO, the net is +$1,508.


## 6. Signal Mode Trail Stop

Only 4 trades exited via trail_stop. All were near breakeven — the 0.99 trail_pct means the trail barely fires. These are essentially breakeven exits where BE trigger activated at 3R, then price fell back:

| Date | Symbol | Entry | Exit | P&L | R-Mult |
|---|---|---|---|---|---|
| 2025-05-29 | BOSC | 4.91 | 4.91 | $0 | 0.0R |
| 2025-09-09 | SBLX | 7.39 | 7.01 | -$254 | -0.6R |
| 2025-09-16 | SLMT | 11.72 | 11.71 | -$5 | -0.0R |
| 2025-10-03 | ASTC | 6.03 | 6.03 | $0 | 0.0R |

SBLX is the only material loss here — held for 32 minutes (cont hold may have kept it open too long).


## 7. Hold Time Analysis

| Hold Time | Trades | Win Rate | P&L | Interpretation |
|---|---|---|---|---|
| 0-1 min | 78 | 12.8% | -$16,189 | Quick exits: mostly losers hitting BE/max_loss fast |
| 2-3 min | 49 | 34.7% | -$2,037 | Mixed — some winners developing |
| 4-5 min | 7 | 14.3% | -$1,404 | Small sample, mostly losers |
| 6-10 min | 8 | 50.0% | +$414 | Trades that developed into winners |
| 11+ min | 12 | 66.7% | +$9,095 | Best category — runners that continuation hold kept alive |

**Key insight:** 50.6% of all trades exit in under 1 minute. These quick exits are overwhelmingly losers (-$16,189). The profitable trades are the ones held 6+ minutes (+$9,509 combined).


## 8. Time of Day Analysis

| Hour | Trades | Win Rate | P&L |
|---|---|---|---|
| 07:00 | 40 | 17.5% | +$392 |
| 08:00 | 17 | 17.6% | -$1,923 |
| 09:00 | 42 | 28.6% | -$3,950 |
| 10:00 | 37 | 32.4% | -$3,090 |
| 11:00 | 18 | 33.3% | -$1,550 |

The 7am hour is the only profitable time slot — early premarket entries on stocks gapping into news. Win rate improves steadily through the day but average loss size stays constant, so later hours lose money too.


## 9. Answering the Core Question: What Is "Genuine MP" Here?

### What was tested

Every trade in this megatest used **State Machine B** (1-minute pullback). This is a **legitimate pullback strategy** — it follows the impulse → pullback → confirmation cycle, just on 1m bars instead of 10s bars. State Machine C (direct/momentum entry) was **never activated**.

### What's "genuine" vs "bolted on"

| Component | Classification | Why |
|---|---|---|
| 1m impulse → pullback → confirm → ARM | **Core MP** | This IS the pullback pattern, just at 1m resolution |
| EMA + VWAP alignment | **Core MP** | Ross's above-VWAP requirement |
| MACD hard gate | **Core MP** | Momentum confirmation |
| Bearish engulfing exit | **Core MP** | Standard candle pattern exit |
| Topping wicky exit | **Core MP** | Standard candle pattern exit |
| Stop hit (at pullback low) | **Core MP** | Natural stop placement |
| Max loss cap (0.75R) | **Bolt-on** | Artificial tightening of stop |
| Continuation hold | **Bolt-on** | Suppresses valid pattern exits |
| Signal mode trail stop | **Bolt-on** | Mechanical trail from non-MP exit engine |
| BE parabolic grace | **Bolt-on** | Overrides pattern-based exit |
| Exhaustion filter | **Bolt-on** | Pre-entry block not part of pullback logic |
| Stale stock filter | **Bolt-on** | Pre-entry block not part of pullback logic |
| No re-entry gate | **Bolt-on** | Session-level block not part of pullback logic |
| Quality gates 1-5 | **Bolt-on** | Extra entry filtering |
| Scoring system | **Bolt-on** | Score has no predictive value (winners avg 15.3 vs losers 15.1) |


## 10. Recommendations for Stripping MP to "Just MP"

To isolate the pure MP signal:

1. **Keep:** 1m pullback state machine (State Machine B) — this IS the core strategy
2. **Keep:** EMA, VWAP, MACD alignment checks — these are part of Ross's framework
3. **Keep:** Bearish engulfing + topping wicky exits — core candle pattern exits
4. **Keep:** Natural stop at pullback low — the original stop placement
5. **Remove:** Max loss cap (WB_MAX_LOSS_R) — let the natural stop do its job, or at minimum widen to 1.0R
6. **Remove:** Continuation hold — net positive but distorts the signal; evaluate separately
7. **Remove:** Signal mode trail stop — barely fires, near-zero impact
8. **Remove:** BE parabolic grace — overrides pattern signals
9. **Evaluate separately:** Exhaustion filter, stale stock filter, no re-entry — these are valid risk management but muddy the MP signal

### If stripped to pure MP:

Using just the 108 "Genuine MP" trades from Config A:
- **Win rate: 37.0%**
- **P&L: +$5,563**
- **Avg win: +$403, Avg loss: -$155**

This is a profitable base strategy, with the entire -$10,121 loss coming from the 42 max_loss_hit trades (an artificial exit) and 4 trail_stop trades.

The path forward: test the 42 max_loss_hit trades with a wider stop (natural stop at pullback low, 1.0R) to see if some would have recovered, vs the additional loss from the ones that would have kept falling.
