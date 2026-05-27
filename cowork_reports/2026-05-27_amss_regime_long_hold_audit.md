# Audit: AMSS Regime-Shift Long-Hold Loss (2026-05-27 Variant A)

**Owner:** CC
**Date:** 2026-05-27
**Subject:** Variant A's 13:32 ET regime_shift entry on AMSS that held 1h 42m before hard-stopping at -$720, immediately re-entered, and hard-stopped again within 1 second for -$577. Manny's read: entry fired during a consolidation phase, not a real regime shift. **Audit confirms.**

---

## TL;DR

Sub-bot A entered AMSS via REGIME_SHIFT at 13:32 ET with `bar_body=$0.43 baseline=$0.07 ratio=6.14`. The high ratio fired because the prior 5 bars had bodies of $0.05-$0.20 each — a tight consolidation around $6.00-$6.50 going back to at least 12:30 ET. A normal $0.43 body in that context looked "huge" relative to baseline, but it was actually a continuation breakdown after an hour-long chop — not a real regime shift.

The bot then sat in the position for 1h 42m with no drawdown exit available (regime_shift positions don't engage HWM trail pre-partial), waiting for either hard_stop or 1.5R target. Price never reached target ($6.33); slowly bled to stop and exited at -$720.

Then the immediate REENTRY GREEN at 15:16 filled at $5.88 (negative slippage from $6.05 limit) and **hard-stopped within ONE SECOND** for another -$577.

Combined AMSS loss on Variant A today: **-$1,649**.

**Root cause analysis identifies two structural issues:**
1. **`regime_shift_baseline_min` defaults to $0.02** — too low. When baseline drops below ~$0.10 the ratio gate becomes meaningless because any directional 1m bar looks "huge" relative to flat chop.
2. **Regime_shift positions have NO drawdown exit pre-partial** (`move_strike_subbot.py:891` `return  # no trail pre-partial`). When entry is weak and price doesn't reach 1.5R target, the only exit is hard-stop or session-end.

Plus the REENTRY-HWM-gate we shipped today (`WB_MOVE_REENTRY_HWM_GATE_ENABLED=1` on Variant C, not yet live elsewhere) would have **blocked the 15:16 re-entry** — that trade is exactly the pattern the gate was designed to catch.

---

## Pre-entry context (15+ minutes of consolidation)

From main bot's `AMSS CHART` log lines (5-min bars, 12:30 - 13:30 ET):

| Time | O / H / L / C | Body | V | vol_ratio | Notes |
|---|---|---|---|---|---|
| 12:30 | 6.45/6.45/6.26/6.26 | 0.19 | 8,563 | 1.0x | dead chop |
| 12:35 | 6.44/6.50/6.35/6.41 | 0.15 | 1,728 | 0.2x | tight range |
| 12:40 | 6.48/6.52/6.48/6.52 | 0.04 | 5,736 | 0.8x | tighter |
| 12:45 | 6.44/6.44/6.41/6.41 | 0.03 | 1,814 | 0.3x | tighter |
| 13:00 | 6.29/6.39/6.24/6.38 | 0.15 | 2,270 | 0.4x | range |
| 13:05 | 6.46/6.49/6.46/6.49 | 0.03 | 2,133 | 0.4x | flat |
| 13:10 | 6.51/6.51/6.40/6.41 | 0.11 | 13,116 | 2.6x | slight vol uptick |
| 13:15 | 6.32/6.44/6.32/6.36 | 0.12 | 11,224 | 2.0x | still ranging |
| 13:20 | 6.22/6.22/6.04/6.05 | 0.18 | 8,331 | 1.5x | first breakdown |
| 13:25 | 6.18/6.21/6.15/6.21 | 0.06 | 3,663 | 0.6x | bounce |
| 13:30 | 6.15/6.16/6.04/6.10 | 0.12 | 5,000 | 0.9x | going down |

**Pattern**: AMSS was range-bound between $6.04-$6.52 with declining volume for over an hour before the regime_shift entry. Price was already in a clear downtrend from the morning HOD of $15.50, with VWAP at ~$10.20 (price 40% below VWAP). This was NOT a setup for a long entry of any kind — it was either consolidation-before-further-decline, or distribution.

**The 13:31 bar (the trigger bar)** wasn't captured in main bot's 5-min CHART, but per sub-bot's log it had `bar_body=$0.43 baseline=$0.07 ratio=6.14`. So in a 1-min frame, the body of that single bar was $0.43 — about 7.3% of price. In the context of the consolidation, that's a meaningful single-bar move, but it's NOT a "regime shift" — it's the continuation of the breakdown that started at 13:20.

---

## Trigger analysis

Live log:
```
[13:32:00] REGIME_SHIFT_TRIGGER AMSS bar_body=$0.4300 baseline=$0.0700 ratio=6.14
[13:32:02] 🚀 ENTRY REGIME_SHIFT AMSS qty=2000 limit=$5.95 (anomaly@$5.86) stop=$5.61 R=$0.2500
[13:32:04] AMSS regime_shift entry FILLED @ $5.9200 qty=2000
```

**Detector params (from `move_strike_subbot.py:RegimeShiftDetector` + env):**
- `ratio_threshold = 4.0` (default; fired with 6.14 ✓)
- `baseline_bars = 5` (median of last 5 bar bodies)
- `baseline_min = 0.02` (skip if baseline below this)
- `body_min = 0.05` (skip if absolute body below this)
- `require_green = True` (require close > open)

The detector fired because:
1. baseline = $0.07 ≥ baseline_min ($0.02) ✓
2. body = $0.43 ≥ body_min ($0.05) ✓
3. ratio = 6.14 ≥ ratio_threshold (4.0) ✓
4. close > open (bar was green per `require_green` gate) ✓

All gates passed. But the gates don't capture the CONTEXT — that the baseline was tight specifically because of consolidation, not because of "low volatility on a stable stock."

**The structural flaw**: when a stock is consolidating, baseline (= median of last 5 bar bodies) collapses toward zero. A normal-magnitude move becomes a "ratio:infinity" event because the denominator is unusually small. The detector then false-triggers on any ordinary directional bar that interrupts the consolidation. **This is the same failure mode as dividing by a near-zero — the signal becomes noise.**

---

## Hold period (1h 42m of slow bleed)

Entry: $5.92. Stop: $5.61. R = $0.25. Target = $5.92 + 1.5 × $0.25 = $6.34.

Looking at main bot's 5-min CHART for the hold period:

| Time | C | Below entry by | Closest to stop? |
|---|---|---|---|
| 13:35 | 5.86 | -1.0% | L=$5.81 |
| 13:40 | 5.98 | -0.7% (bounced) | |
| 13:45 | 5.85 | -1.2% | |
| 13:50 | 5.98 | -0.7% | |
| 13:55 | 6.00 | -0.3% | |
| 14:00 | 5.85 | -1.2% | **L=$5.62** (1 cent above stop!) |
| 14:05 | 5.97 | -0.8% | |
| 14:10 | 5.89 | -1.0% | |
| 14:30 | 5.90 | -0.3% | L=$5.81 |
| 15:00 | 5.85 | -1.2% | L=$5.84 |
| 15:10-ish | … (final breakdown) | | hit stop @ 15:14 |

**Price never went above $6.04** during the entire 1h 42m hold. The bot's 1.5R target ($6.34) was a 7.4% move from entry on a stock that was already in a clear downtrend — unrealistic.

**Why didn't the bot exit earlier?** Per `move_strike_subbot.py:_maintain_position` (lines 882-891):

```python
if p.setup_type == "regime_shift" and not p.move_partial_fired:
    # Hard stop
    if price <= p.stop:
        self._close_position("regime_shift_hard_stop", price)
        return
    # Target = entry + target_R * R. Fire partial when crossed.
    target_price = p.entry + self.regime_shift_target_r * p.r
    if price >= target_price:
        self._fire_regime_shift_partial(p, price)
    return  # no trail pre-partial
```

**The comment is the smoking gun: `# no trail pre-partial`**. Regime_shift positions don't engage HWM drawdown exit until the partial fires. If price never reaches target, there's no drawdown protection. Bot sits and waits.

The reasoning (per code comment elsewhere): "PCLA-class trades need runway." Translation: don't trail-stop too early because some regime shifts have minutes of base-building before the move continues.

But on a CONSOLIDATION-PHASE false trigger (this trade), there's no "runway" coming — the move was over before it started. The bot has no way to detect that and bail.

---

## Exit + immediate re-entry disaster

Live log:
```
[15:14:04] 🟥 EXIT REGIME_SHIFT AMSS qty=2000 limit=$5.56 (ref=$5.61) reason=regime_shift_hard_stop
[15:14:06] AMSS REENTRY WATCH set: high=5.970 stop=5.720 expires_in=30min
[15:16:06] 🟩 ENTRY REENTRY(GREEN) AMSS qty=1923 limit=$6.05 (anomaly@$5.98) stop=$5.72 R=$0.2600 score=99.0
[15:16:07] AMSS entry FILLED @ $5.8800 qty=1923 (limit was $6.05)
[15:16:07] 🟥 EXIT MOVE_STRIKE AMSS qty=1923 limit=$5.58 (ref=$5.70) reason=move_hard_stop
```

After the regime_shift exit:
- A REENTRY WATCH was set with high=$5.97, stop=$5.72
- Within 2 minutes a green 1m bar closed (close > open) within the watch window
- REENTRY GREEN fired at $6.05 limit price
- BUT the actual fill landed at $5.88 (a $0.17 NEGATIVE slippage)
- Price was already breaking down — the next tick hit $5.70 (below stop $5.72)
- Hard stop fired ONE SECOND after entry, exit limit $5.58
- Net: ($5.58 - $5.88) × 1923 = **-$577**

**The new REENTRY-HWM-gate (shipped today, currently only ON for Variant C) would have BLOCKED this re-entry** because the prior exit was `move_hwm_exit`... wait, the prior exit was `regime_shift_hard_stop`, not `move_hwm_exit`. The gate's current code only blocks when prior exit was `move_hwm_exit*`. So the gate **would NOT have caught this specific failure** — the prior exit was a different reason.

The gate's current scope is too narrow. **The pattern that hurt here is "re-entry on green bar immediately after hard-stop"** — which is a similar shape to "re-entry after HWM exit" but with a different prior reason. Worth flagging as a possible gate broadening, but separate directive.

---

## Two structural findings worth a follow-up directive

### Finding 1: `regime_shift_baseline_min` is too low

The current `WB_REGIME_SHIFT_BASELINE_MIN=0.02` default lets the detector fire when baseline is essentially zero (consolidation). A baseline of $0.07 on a $6 stock = 1.2% of price; that's near-flat. The detector should require baseline to be a meaningful percentage of price OR an absolute floor like $0.15-$0.25.

Better gates to consider:
- `baseline_min = max(0.05, price * 0.005)` — scales with price
- Add `bar_body_pct_of_price_min` — require absolute body ≥ N% of current price (filters out small moves that only look big due to tiny baseline)

### Finding 2: regime_shift positions need a drawdown exit pre-partial

Current: bot holds until hard_stop or target. For weak entries this means full -R loss before any exit.

Options:
- Engage HWM trail at a SHALLOWER threshold (e.g., 50% drawdown from peak) pre-partial
- Add a "time-since-entry" stop (e.g., if no progress toward target after 60 min, bail)
- Add a "no-new-high" stop (if N bars pass without making a new high, bail)

The MOVE_STRIKE path has `move_stop_prox_bail` which fires when price approaches stop with buffer. That's a smaller-loss exit than the hard stop. Regime_shift could borrow this.

### Finding 3: REENTRY-HWM-gate scope may be too narrow

The gate (shipped today, Variant C only) blocks REENTRY when prior exit was `move_hwm_exit*`. Today's re-entry disaster was after a `regime_shift_hard_stop`. Same failure pattern (chase a green bar into a continuation downtrend), different prior reason. Worth considering broader gate: block REENTRY when prior exit was ANY hard-stop-class reason on the same symbol within window.

---

## Damage roll-up

Variant A AMSS day-trades (today, 2026-05-27):

| Trade | Entry | Exit | Reason | P&L |
|---|---|---|---|---|
| 07:32 MOVE_STRIKE 357@$12.66 | $12.66 | $12.79 (hwm_exit) | small winner | **+$46** |
| 07:34 REENTRY GREEN 320@$12.79 | $12.79 | $11.55 (stop_prox_bail) | -3.1R chop | **-$398** |
| 13:32 REGIME_SHIFT 2000@$5.92 | $5.92 | $5.56 (hard_stop) | consolidation false-trigger | **-$720** |
| 15:16 REENTRY GREEN 1923@$5.88 | $5.88 | $5.58 (move_hard_stop) | 1-sec stopout | **-$577** |
| **Total** | | | | **-$1,649** |

**The 13:32 + 15:16 pair accounts for $1,297 of the $1,649 total damage.** Both stem from the same root: regime_shift fired on a consolidation-context bar, the position couldn't exit cleanly, and the re-entry mechanism added insult.

---

## Variant comparison on this specific symbol

Per the deep-dive AND today's broker check, Variants B and C had similar AMSS trade lifecycles:
- All three armed the morning move_strike entries
- B's V1 VWAP fade-gate blocked the morning AMSS pair entirely (saved -$352 on B that A/C took)
- All three took the 13:32 regime_shift entry (regime not subject to fade-gates)
- All three hit the same hard_stop at 15:14
- All three took the 15:16 REENTRY which immediately hard-stopped

Variant C (now repurposed to REENTRY-HWM-gate for tomorrow's run) would have blocked the 15:16 REENTRY... but ONLY if the prior exit was `move_hwm_exit`. The actual prior exit was `regime_shift_hard_stop`, so the current gate would NOT have caught it. Today's lesson: the gate's scope may need to extend to ALL hard-stop-class prior exits, not just HWM-drawdown ones.

---

## Recommendations for follow-up

### Immediate (no code change, evidence-gathering)

Tomorrow's bar-stream logger output (Phase 3c, just shipped) will tell us what the 13:31 1-min bar looked like to live's sub-bot in real-time vs what the cache replay shows. If the bars match, the false-trigger was real and the detector needs the baseline-floor fix. If they don't, the cache may be inflating bodies (we've seen 5x volume difference before).

### Short-term directive (high priority — straight to a directive)

Tighten regime_shift gates:
- `WB_REGIME_SHIFT_BASELINE_MIN_PCT_OF_PRICE` (new env var, default 0.005 = 0.5% of price). Adds an additional floor: skip if baseline < max(baseline_min, price × baseline_min_pct_of_price).
- `WB_REGIME_SHIFT_BODY_MIN_PCT_OF_PRICE` (new env var, default 0.02 = 2% of price). Adds bar_body floor relative to price.

Both default to off when env not set. Live unchanged unless we opt-in. Backtest sweeps to find the right thresholds before live deploy.

### Medium-term directive

Pre-partial drawdown exit for regime_shift positions:
- Engage HWM trail with `wide_dd_pct` from entry (e.g., 50% drawdown of R from entry peak) BEFORE partial fires.
- Add a no-new-high time-bail (e.g., 60 minutes without new peak above entry).

### Broaden REENTRY-gate scope

Today's 15:16 REENTRY disaster wasn't caught by the new HWM-gate because prior exit was `regime_shift_hard_stop`, not `move_hwm_exit`. Consider broadening to ANY hard-stop-class prior exit on the same symbol within window. Run on Variant C with the broader gate for 5+ days first.

---

## Cross-references

- `cowork_reports/2026-05-27_subbot_trade_deep_dive.md` — original deep-dive that only captured the morning AMSS trades; today's audit extends to the afternoon disasters
- `cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md` — the gate that ALMOST would have helped, but scope is too narrow
- `cowork_reports/2026-05-27_phase3c_bar_construction_results.md` — tomorrow's bar-stream data will let us audit the 13:31 trigger bar directly

---

*Audit complete. Standing by — recommend prioritizing the regime_shift baseline-floor directive next.*
