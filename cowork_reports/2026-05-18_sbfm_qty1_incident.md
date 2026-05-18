# SBFM qty=1 Incident — Sizing Path Silently Floors to 1 on BP=$0

**Date:** 2026-05-18
**Author:** CC
**For:** Cowork (Perplexity) + Manny
**Status:** Live bug found. Patch designed, NOT applied.

---

## TL;DR

Today the squeeze bot took **1 share of SBFM** on a setup where the math should have produced ~4,500 shares. SBFM was a 327%-gap, RVOL-17.48, 4.9M-float, parabolic premarket runner — exactly the kind of trade the bot was built to catch. We got 1 share because **`bot_v3_hybrid.py:3033` got `broker.get_buying_power() == $0` for a single instant**, the qty math correctly produced 0, and then **line 3048 silently floored qty to 1 instead of skipping the trade**.

Today this was a lucky save — SBFM ran to ~$2 then collapsed to $0.57; qty=1 cost us nothing. But the same bug on a different stock that holds its gap could have cost five figures.

**Real cause:** `max(1, int(math.floor(qty * size_mult)))` at line 3048. The `max(1, …)` was probably added as a guard against probe-size rounding-to-zero — but it papers over the case where `qty` is already 0 from the BP/notional cap (BP=$0 → notional cap=$0 → qty=0 → still becomes 1).

**ALPACA_QUOTE_FAIL is a red herring.** Same minute, but only a latency-diagnostic call. Not in the sizing path.

**Proposed fix:** kill the `max(1, …)` floor; if `qty == 0` after caps, skip the entry the same way the existing `if qty <= 0` block at 3050 does. Two-line diff. Stage for post-close tonight or weekend.

**Adjacent, larger improvement:** the bot calls `get_buying_power()` synchronously into IBKR every signal. When the call momentarily returns 0 (which can happen during account re-sync, gateway hiccup, or early-session info propagation), the sizing collapses. Cache last-known good BP, or fall back to `equity * 2` (Reg-T) when `get_buying_power()` returns 0.

---

## 1. The trade — what happened

```
[07:19 ET] SBFM SQ | ARMED entry=2.0200 stop=1.9200 R=0.1000 score=5.2
              level=whole_dollar setup_type=squeeze [PARABOLIC] [PROBE=50%]
[07:19:00 ET] SBFM SQ | ENTRY SIGNAL @ 2.0200 ...
  Sizing: equity=$29,687 risk=$1,039 qty=0 notional=$0 (BP 50% of $0 = max $0)
  [ALPACA_QUOTE_FAIL] SBFM: ... Failed to resolve 'data.alpaca.markets' ...
🟩 ENTRY: SBFM qty=1 limit=$2.09 (slip=$0.070) stop=$1.9200 R=$0.1000 score=5.2
  BROKER ORDER: b25ce5d0-... BUY 1 SBFM @ $2.09
  FILL: SBFM @ $1.9700 qty=1
🟥 EXIT: SBFM qty=1 @ $1.9400 reason=sq_para_trail_exit P&L=$-0 daily=$-0
```

Scanner pre-context:
| Snapshot | Price | Prev close | Gap | PM vol | RVOL | Float |
|---|---:|---:|---:|---:|---:|---:|
| Initial (04:02 ET) | NaN | $0.47 | NaN | 405K | 3.36 | 4.9M |
| Final | $2.005 | $0.47 | **+327%** | 2.11M | **17.48** | 4.9M |

This was a top-tier scanner hit. The bot armed, fired, but only filled 1 share.

---

## 2. Root cause — `bot_v3_hybrid.py:3033-3050`

```python
3032:    if SCALE_NOTIONAL:
3033:        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
3034:        effective_notional = broker_bp * BUYING_POWER_PCT
3035:    else:
3036:        effective_notional = MAX_NOTIONAL
3037:    qty = int(math.floor(risk_dollars / r))
3038:    qty_notional = int(math.floor(effective_notional / max(entry, 0.01)))
3039:    qty = min(qty, qty_notional, MAX_SHARES)
3040:
3041:    notional = qty * entry
3042:    print(f"  Sizing: equity=${current_equity:,.0f} risk=${risk_dollars:,.0f} "
3043:          f"qty={qty} notional=${notional:,.0f}" +
3044:          (f" (BP {BUYING_POWER_PCT*100:.0f}% of ${broker_bp:,.0f} = max ${effective_notional:,.0f})" if SCALE_NOTIONAL else ""),
3045:          flush=True)
3046:
3047:    if size_mult < 1.0:
3048:        qty = max(1, int(math.floor(qty * size_mult)))   # ← the bug
3049:
3050:    if qty <= 0:
3051:        ...
3052:        return                                          # ← never reached
```

**What happened at 07:19 ET on SBFM:**
1. `broker.get_buying_power()` returned **$0** (transient IBKR API state — see §4)
2. `effective_notional = $0 × 50% = $0`
3. `qty_notional = $0 / $2.02 = 0`
4. `qty = min(9,100 [risk-based], 0 [notional], MAX_SHARES) = 0`
5. The Sizing log printed `qty=0 notional=$0 (BP 50% of $0 = max $0)`
6. **Line 3048 fired** (because `[PROBE=50%]` set `size_mult = 0.5 < 1.0`)
7. `qty = max(1, int(math.floor(0 * 0.5))) = max(1, 0) = 1`
8. `if qty <= 0` skipped (qty is now 1)
9. The bot submitted a 1-share BUY

The `max(1, …)` was almost certainly added as defensive coding against probe-rounding producing 0 from a non-zero base qty (e.g., qty=1 × 50% rounds to 0 → bump back to 1). But it interacts catastrophically with the BP/notional cap also producing 0 — the floor silently rescues a "skip this trade" decision into a 1-share placebo.

---

## 3. Why BP=$0 — IBKR premarket margin behavior (CONFIRMED)

The same session shows BP recovers later. Sample Sizing lines from regular hours:

```
Sizing: equity=$29,687 risk=$1,039 qty=7384 notional=$29,684 (BP 50% of $59,374 = max $29,687)
Sizing: equity=$29,207 risk=$1,022 qty=3931 notional=$24,097 (BP 50% of $58,414 = max $29,207)
Sizing: equity=$29,207 risk=$1,022 qty=9671 notional=$29,206 (BP 50% of $58,414 = max $29,207)
```

BP is ~$58-59K (≈ 2× equity, normal Reg-T margin). **Only one Sizing line in the entire day shows BP=$0**, and it's exactly the SBFM moment at 07:19 ET (premarket).

**Root cause confirmed:** `broker.py:515-520` reads `BuyingPower` from `self._ib.accountValues()` and returns 0 if the tag isn't present. **IBKR doesn't extend day-trade margin outside regular hours.** Premarket, IBKR either reports `BuyingPower = $0` or omits the tag entirely.

Evidence in today's log (timestamp-ordered):

| Time | Symbol | BP reported | Phase |
|---|---|---:|---|
| **07:19 ET** | **SBFM** | **$0** | **Premarket — IBKR margin not extended** |
| 09:35 ET | QUCY | $59,374 | RTH — Reg-T 2× active |
| ~10:00 ET | CORD | $58,414 | RTH — Reg-T 2× active |
| (now) | account | ~$57,000 | RTH — Reg-T 2× active |

This is **not an IBKR bug** — it's correct margin behavior on a paper margin account outside RTH. The bug is the bot's sizer assuming `get_buying_power()` always returns a meaningful number.

---

## 3.5. Premarket sizing — the secondary fix

The qty=1 floor (§7) is the primary bug to kill. But fixing only that means premarket signals like SBFM would **skip entirely** instead of trading — also wrong outcome. Premarket gappers are the highest-RVOL, highest-edge setups; we don't want to ship a fix that silently drops them.

### Options for premarket sizing

**(a) NetLiquidation fallback** (recommended)
If `BuyingPower = 0` AND it's outside RTH (09:30-16:00 ET), use `NetLiquidation × 1` as the effective BP. No margin assumed — sizes to cash only. Roughly half normal RTH notional, but meaningful.

```diff
@@ -3032,7 +3032,18 @@
     if SCALE_NOTIONAL:
-        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
+        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
+        if broker_bp <= 0:
+            # IBKR doesn't extend day-trade margin in premarket / extended hours.
+            # Fall back to NetLiquidation (no margin — cash-only sizing).
+            now_et = datetime.now(ET).time()
+            in_rth = time_obj(9, 30) <= now_et < time_obj(16, 0)
+            if in_rth:
+                # RTH BP=$0 is a real transient — log and use last-known-good or 2× equity
+                broker_bp = state.last_known_bp if getattr(state, "last_known_bp", 0) > 0 else current_equity * 2
+                print(f"  BP_FALLBACK_RTH: get_buying_power()=0 transient; using ${broker_bp:,.0f}", flush=True)
+            else:
+                # Outside RTH — IBKR margin not extended yet. Cash-only sizing.
+                broker_bp = current_equity
+                print(f"  BP_FALLBACK_EXT_HOURS: extended-hours sizing (NetLiq cash-only): ${broker_bp:,.0f}", flush=True)
+        else:
+            state.last_known_bp = broker_bp
         effective_notional = broker_bp * BUYING_POWER_PCT
     else:
         effective_notional = MAX_NOTIONAL
```

Effect on SBFM today (counterfactual):
- `current_equity ≈ $29,687`
- `effective_notional = $29,687 × 50% = $14,843`
- `qty_notional = $14,843 / $2.02 = 7,348`
- `qty = min(9,100, 7,348, MAX_SHARES) = 7,348`
- Probe 50% → `qty = 3,674 shares`
- Real trade instead of placebo.

**(b) Skip premarket signals entirely** (rejected)
Defer all entries to RTH open. Loses the premarket-gapper edge entirely. SBFM-class setups are exactly what we want to catch — skipping them is the wrong fix.

**Recommended: ship (a).** Two-paragraph diff covers both the RTH transient case (last_known_bp fallback) and the premarket-margin-not-extended case (cash-only sizing).

### Edge cases

- **Cash account** (no margin): NetLiquidation × 50% is correct anyway — same behavior, no risk increase
- **Post-close extended hours** (16:00-20:00 ET): same as premarket — IBKR doesn't extend margin. The fallback handles it.
- **Equity drops mid-day**: `last_known_bp` could become stale upward. Mitigation: clamp `last_known_bp` to `current_equity × 4` before use. Or invalidate the cache on every fill (would update on next call).

---

## 4. The ALPACA_QUOTE_FAIL — red herring

Line 9980 of the log shows `[ALPACA_QUOTE_FAIL] SBFM: ... Failed to resolve 'data.alpaca.markets'`. My first read was that the fail caused the qty=1.

I was wrong. Tracing through `bot_v3_hybrid.py:2540-2584`, `_alpaca_quote_and_trade` / `_alpaca_snapshot` is only called from the **latency-diagnostic** path at line 3066-3074, **after** the qty has already been computed. The Sizing log prints `qty=0` *before* the diagnostic call. The DNS failure is unrelated to sizing — it's a diagnostic side-info call that the comment at line 2579 explicitly says is non-blocking: `"Never block on Alpaca quote-call failure"`.

The two events landed in the log near each other (same minute) but they're independent. The sizing bug exists with or without the DNS issue.

That said, the broader point still stands: **the bot is calling Alpaca quote APIs for diagnostic purposes when IBKR is the primary execution path.** Phase 4 of the IBKR migration (per CLAUDE.md) was supposed to delete AlpacaBroker + alpaca-py. This `_alpaca_snapshot()` is residual diagnostic code that could be ripped out, but it's not on today's critical path.

---

## 5. Today's actual impact

SBFM intraday:
- ARMED + filled 07:19 ET at $1.97 (1 share)
- Para-trail exit 07:22 ET at $1.94 (-$0.03/share = -$0.03 total)
- Scanner final snapshot showed SBFM peaking around $2.00
- Heartbeat near session-end shows `last_price=$0.57` — SBFM collapsed back through its prev close ($0.47)

**Today's qty=1 actually saved us money** — at full size (4,500 shares per probe-50% sizing, or 9,100 at full size) the bot would have hit the trail exit at $1.94 and exited near-flat, OR potentially scaled higher and given back more on the collapse. Today's outcome was a coincidence of timing — the trail-exit fired before the collapse mattered, so we'd have been near-flat regardless of size.

**But the bug is still real.** Different stock, different day, same `BP=$0` transient, fresh PM 327% gap that *holds* → qty=1 instead of 4,500-9,000 shares.

---

## 6. Frequency — how often does this fire?

| Pattern | Count |
|---|---|
| `qty=1` ENTRY in all 30-day logs | **1** (SBFM today) |
| `Sizing: ... qty=0 notional=$0` in all 30-day logs | **1** (SBFM today; rest were valid) |
| `ALPACA_QUOTE_FAIL` in 2026-05 logs | 1-8 per day typically, 132 spike on 2026-04-17 |
| `ALPACA_QUOTE_FAIL` total 2026-04-17 | 132 (network event, unrelated to sizing) |

So the **BP=$0 transient is rare** (1× in 30 days). But every time it hits AND a signal is firing AND `size_mult < 1.0` (parabolic / no-prior-winner probe), we get a qty=1 placebo trade.

The probability is roughly:
- BP=$0 transient: rare (~1× per 30 days)
- Conditional on transient hitting at a signal moment: rarer (~0.1× per 30 days)
- But when it does hit, the cost ceiling is *uncapped* (any size of winner missed)

This is a **low-frequency, high-magnitude tail risk.** It hadn't bitten until today, and today we got lucky.

---

## 7. Proposed fix — two-line diff (NOT applied)

`bot_v3_hybrid.py` and any sibling files (`bot_alpaca_subbot.py`, `simulate.py`) that have the same pattern:

```diff
@@ -3046,7 +3046,7 @@
           flush=True)
 
     if size_mult < 1.0:
-        qty = max(1, int(math.floor(qty * size_mult)))
+        qty = int(math.floor(qty * size_mult))
 
     if qty <= 0:
         try:
@@ -3053,6 +3053,7 @@
             if latency_record is not None:
                 latency_record["armed_qty"] = 0
                 _finalize_latency_record(
                     latency_record, terminal_state="no_order",
                     no_order_reason="qty_zero",
                 )
         except Exception:
             pass
         return
```

Effect:
- Probe sizing × small base qty → 0 → skip the trade (previously bumped to 1)
- BP=$0 → qty_notional=0 → qty=0 → skip the trade (previously bumped to 1)
- Any other code path that produces qty=0 → skip cleanly

**Risk:** any legitimate path that *intentionally* wanted to fire qty=1 (e.g., absolute-minimum-size probe) will now skip. None such exist in the codebase — every "probe" path expects a meaningful share count.

**Sibling fix (optional, recommended):** at line 3033, defend against BP=$0 by falling back to a conservative estimate:

```diff
@@ -3032,7 +3032,12 @@
     if SCALE_NOTIONAL:
-        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
+        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
+        if broker_bp <= 0:
+            # Transient — fall back to last-known-good or 2× equity (Reg-T proxy)
+            broker_bp = state.last_known_bp if getattr(state, "last_known_bp", 0) > 0 else current_equity * 2
+            print(f"  BP_FALLBACK: get_buying_power() returned 0; using ${broker_bp:,.0f}", flush=True)
+        else:
+            state.last_known_bp = broker_bp
         effective_notional = broker_bp * BUYING_POWER_PCT
     else:
         effective_notional = MAX_NOTIONAL
```

This handles the underlying transient gracefully *and* makes the qty=0 → skip fix the only defense needed.

**Tests to add:**
1. `test_sizing_floors_to_zero_skips_trade` — set `broker_bp=0`, `size_mult=0.5`, assert no order submitted
2. `test_sizing_probe_rounding_skips_trade` — base qty=1, size_mult=0.5, assert skipped (verify no legitimate path relies on the floored-to-1 behavior)
3. `test_bp_zero_fallback_uses_last_known` — if optional fallback fix shipped

---

## 8. Rollout plan

Per the methodology established by the resume-boot fix and R-floor patches:

- **Post-close Tuesday 2026-05-19 (after 20:00 ET)** OR **weekend 2026-05-24**, applied with VERO + ROLR backtest regression first
- Sibling files: `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `simulate.py`, plus the EPL graduation path at `bot_v3_hybrid.py:3206-3207` (same `qty = min(..., MAX_SHARES)` shape — check for the same bug)
- Escape hatch: env var `WB_SIZING_NO_QTY_FLOOR=1` enables the new behavior (start with it on, can flip off if regression breaks)
- Or simpler: deploy unconditionally; the floor was undocumented and almost certainly unintentional

---

## 9. Severity ranking vs other open items

| Item | Frequency | Per-event $ ceiling | Severity |
|---|---|---|---|
| **SBFM qty=1 sizing floor** | ~1× / month | **Uncapped — any missed winner** | **HIGH (tail)** |
| Resume-boot stale-signal | 6 events / 30 sessions | -$500 each (chase-cap losers) | MEDIUM (controlled by chase-cap) |
| WB_MIN_ABSOLUTE_R floor | ~1× / month | +$750 saved | LOW (small +EV) |
| Backtest tick-realism | 30+ sessions | ±$84/session noise | LOW (punted) |
| Broker switch (Alpaca→IBKR) | N/A | $0 recovered | NOT WARRANTED |

The qty=1 floor is the highest-severity item in the open list **because the upside ceiling is uncapped**. The other items have bounded P&L exposure; this one's exposure is "how big was the move we missed?"

---

## 10. Decisions for Manny + Cowork

1. **Approve the two-line diff** (remove `max(1, …)` from line 3048) — the primary fix.
2. **Approve the BP-fallback + premarket-cash-only diff** (§3.5 option (a)) — the structural fix that makes premarket gappers like SBFM size correctly without margin.
3. **Rollout window** — post-close Tuesday 5/19 or weekend 5/24?
4. **Bundle with the resume-boot patch and R-floor patch** into a single Wave-of-bug-fixes deployment, or deploy independently?

Recommendation: **bundle all three patches** into a single post-close Tuesday or Saturday weekend deploy with full regression (VERO + ROLR + 30-session replay). All three are low-risk one-to-ten-liners. Single deploy minimizes the number of "did we break it this time?" cycles.

**Bundled deploy contents:**
- qty=1 floor removal (§7) — `bot_v3_hybrid.py:3048` + sibling files
- BP-during-premarket fallback (§3.5) — `bot_v3_hybrid.py:3033` + sibling files
- Resume-boot stale-signal fix — per `2026-05-18_resume_boot_stale_signal_fix.md`
- R-floor gate (`WB_MIN_ABSOLUTE_R=$0.10`) — per `2026-05-18_r_floor_gate_design.md`

Two regression dimensions to check before push:
- **VERO 2026-01-16** target +$34,479 (X01 baseline) — no premarket entries → BP fallback shouldn't trigger; qty=1 fix shouldn't affect; R-floor unlikely to affect (R was probably $0.12+).
- **ROLR 2026-01-14** target +$54,654 — same logic.
- Plus a 30-session replay to confirm no historical trades have their behavior changed unexpectedly.

---

## 11. Files referenced

- `bot_v3_hybrid.py:2540-2584` — `_alpaca_quote_and_trade` (red herring)
- `bot_v3_hybrid.py:3026-3060` — the sizing path with the bug
- `bot_v3_hybrid.py:3033` — `get_buying_power()` call
- `bot_v3_hybrid.py:3048` — the `max(1, …)` floor (the bug)
- `bot_v3_hybrid.py:3050-3060` — the `if qty <= 0: return` skip path (currently unreachable for size_mult<1.0 paths)
- `logs/2026-05-18_daily.log:9980-10005` — SBFM event sequence
- `scanner_results/live_2026-05-18_final.json` — scanner snapshot showing SBFM as the day's top hit

---

**No code modified. Patch documented for Cowork + Manny review. Live bots untouched.**

---

## 12. CORRECTION (2026-05-18 PM) — wrong-field reframing supersedes §3 and §3.5

The §3 / §3.5 framing — "IBKR doesn't extend day-trade margin in premarket, so BuyingPower correctly reads $0; the fix is a time-of-day branch in `bot_v3_hybrid.py:3033`" — is **incomplete and lands in the wrong place**. The corrected diagnosis:

**The bot is reading the wrong IBKR field.**

`BuyingPower` is one specific tag in `ib.accountValues()` — it reports the day-trade margin extension (typically ~4× NLV during RTH on PDT-eligible accounts). It is intentionally absent / $0 outside RTH because there is no day-trade extension outside RTH. **It is not a synonym for "capital available to trade."**

Actual spendable capital lives in adjacent tags:
- `AvailableFunds` — Reg-T cash + margin available right now
- `EquityWithLoanValue` — total equity counted toward margin
- `ExcessLiquidity`, `TotalCashValue`, etc.

Probed against the live IBKR Gateway at 2026-05-18 15:48 ET (RTH, account DUQ143444, paper):

| Tag | Value (USD) | Notes |
|---|---|---|
| `BuyingPower` | $122,125.04 | 4× NLV — day-trade extension (RTH only) |
| `AvailableFunds` | $30,531.26 | Reg-T cash. Populated. |
| `EquityWithLoanValue` | $30,531.26 | Populated. |
| `ExcessLiquidity` | $30,531.26 | Populated. |
| `NetLiquidation` | $30,555.76 | Total account equity. |
| `TotalCashValue` | $30,531.26 | Populated. |
| `SMA` | $31,718.84 | Populated. |

Probe script: `scripts/probe_account_values.py` (clientId=99, read-only, no market data, no orders).

### 12.1 Why this matters for the fix

The §3.5 fix branches on `is_extended_hours()` in `bot_v3_hybrid.py:3033`. That branch is structurally wrong for two reasons:

1. **The wrong-field bug repeats at any caller of `get_buying_power()`.** Sibling files (`bot_alpaca_subbot.py`, `simulate.py`, EPL graduation path at `bot_v3_hybrid.py:3206-3207`) would each need their own time-of-day branch — multiple copies of the same logic, each free to drift.
2. **It still uses `BuyingPower` as the canonical signal.** The branch only fires when `BuyingPower == 0`; if IBKR ever ships a partial extension (e.g., overnight margin programs) or a small non-zero value in extended hours, the branch fails to engage and the bot sizes against a misleading number anyway.

### 12.2 Corrected fix — `broker.py:get_buying_power()`

Centralize the field-selection logic in the one place that owns the IBKR connection. Tag hierarchy, first non-zero wins:

```python
def get_buying_power(self) -> float:
    for tag in ("BuyingPower", "AvailableFunds", "EquityWithLoanValue"):
        v = self._account_value(tag)
        if v > 0:
            return v
    return 0.0
```

Behavior:
- **RTH:** `BuyingPower` populated → returns the day-trade extension. No regression vs. today.
- **Premarket / after-hours:** `BuyingPower == 0` → falls through to `AvailableFunds` → bot sees real spendable cash.
- **Total gateway failure:** all three are 0 → returns 0.0 → existing skip path in `bot_v3_hybrid.py:3050-3060` correctly refuses the trade (assuming the qty=1 floor from §7 is also removed).

No new env var. No time-of-day branch. No caller-side changes. The fix is invisible to every consumer of `get_buying_power()` other than that they get the right number.

### 12.3 Status

- **Applied 2026-05-18 PM** to `broker.py:515-520` (this session, post-power-outage). Bot was already down for an unrelated reboot; no live-traffic impact. Tomorrow's 02:00 MT cron picks it up.
- **§3.5's bot-side fallback diff is SUPERSEDED** — do not apply. The broker-side fix obsoletes it.
- **§7's qty=1 floor removal is still UNAPPLIED.** That fix is independent and still required: it's the failsafe for any future BP=$0 case the hierarchy can't rescue (e.g., gateway down during a signal).

### 12.4 Decisions for Manny (updates §10)

| §10 item | Status |
|---|---|
| 1. Two-line `max(1, …)` removal | Still pending. Independent of this correction. |
| 2. BP-fallback diff (§3.5) | **Withdrawn** — replaced by broker.py hierarchy applied 2026-05-18 PM. |
| 3. Rollout window | qty=1 floor still recommended for post-close Tuesday 5/19 or weekend 5/24 deploy. |
| 4. Bundle with resume-boot + R-floor | Still recommended for the qty=1 fix. BP-hierarchy already shipped. |

### 12.5 What the original framing got right vs. wrong

**Right:** the symptom (BP=$0 sized to qty=1), the trigger (premarket / extended hours), the per-event $ ceiling (uncapped — any missed runner).

**Wrong:** the location of the fix (caller-side, time-of-day-branched) and the framing of the IBKR behavior (described as a margin policy, but actually a question of which tag the bot reads). The original framing would have worked, but at the cost of duplicating logic across every caller and leaving the door open to future drift.

**Original framing preserved above for audit trail.** This section is the operative one going forward.

---

## 13. RE-CORRECTION (2026-05-18 PM, post-Cowork audit) — §12 was also wrong; SBFM ran on `AlpacaBroker`, not `IBKRBroker`

§12's "wrong IBKR tag" framing is **also incomplete and lands in the wrong file**. Cowork's audit caught the misdiagnosis: the SBFM signal never touched `IBKRBroker.get_buying_power()`. The bot was running `Broker: ALPACA` at the moment of the trade.

### 13.1 Evidence — which broker ran today

**`.env` (pre-correction):** `WB_BROKER=ibkr`

**`daily_run_v3.sh:208-211` (the actual launcher):**
```bash
APCA_API_KEY_ID="$MAIN_APCA_KEY" \
APCA_API_SECRET_KEY="$MAIN_APCA_SECRET" \
WB_BROKER=alpaca \
  python3 bot_v3_hybrid.py >> "$LOG_FILE" 2>&1 &
```
The cron-launched bot inherits `WB_BROKER=alpaca` from the command-line injection, which overrides the `.env` value. The comment at line 193-197 documents the 2026-05-07 switch back to Alpaca (IBKR paper margin was rejecting squeeze entries — ATRA $202-short reject on 2026-05-07).

**`logs/2026-05-18_daily.log:63` (runtime print from `bot_v3_hybrid.py:4651`):**
```
Broker: ALPACA
```

So `state.broker = AlpacaBroker(state.alpaca)`. The `state.broker.get_buying_power()` call at `bot_v3_hybrid.py:3033` resolved to `broker.py:253-259` (Alpaca path) — NOT the `broker.py:515-520` IBKR path that §3 / §3.5 / §12 all analyzed.

### 13.2 Smoking gun — `AlpacaBroker.get_buying_power()` is a silent two-line failure

```python
def get_buying_power(self) -> float:
    """Current buying power for position sizing."""
    try:
        acct = _with_timeout(self._c.get_account, timeout=5)
        return float(acct.buying_power)
    except Exception:
        return 0.0
```

Any exception from `_c.get_account()` → returns 0.0 with **no log line**. The operator has no visibility into the failure. The qty=1 floor downstream papers over the symptom.

### 13.3 What actually happened at 07:19 ET — the DNS-outage correlation

The SBFM entry log:
```
[ALPACA_QUOTE_FAIL] SBFM: HTTPSConnectionPool(host='data.alpaca.markets', port=443):
  Max retries exceeded with url: /v2/stocks/quotes/latest?symbols=SBFM
  (Caused by NameResolutionError(... Failed to resolve 'data.alpaca.markets'
  ([Errno 8] nodename nor servname provided, or not known)))
🟩 ENTRY: SBFM qty=1 limit=$2.09 ...
  BROKER ORDER: b25ce5d0-2831-4682-bace-4c6aa72b2e9c BUY 1 SBFM @ $2.09
```

Alpaca DNS resolution (`data.alpaca.markets`) was failing at the exact moment SBFM signaled. `api.alpaca.markets` shares the same DNS resolver path; almost certainly the `_c.get_account()` call inside `get_buying_power()` failed the same way during the same window. Because the order-submission call happened a fraction of a second later, DNS had recovered by then — only the BP fetch caught the outage, and it was swallowed silently.

**§4's claim that ALPACA_QUOTE_FAIL is a "red herring" was wrong.** It is the smoking gun. The quote-fetch failure and the account-fetch failure are the same network event; one was logged loudly, the other was logged not at all.

### 13.4 Corrected fix — `AlpacaBroker.get_buying_power()` (broker.py:253-274 after patch)

Replace the silent `except Exception: return 0.0` with: cache last-known-good BP on every success, log the exception visibly on failure, return the cached value. Same treatment for `get_account_equity()` since it has the identical failure mode.

```python
def get_buying_power(self) -> float:
    try:
        acct = _with_timeout(self._c.get_account, timeout=5)
        v = float(acct.buying_power)
        self._last_known_bp = v
        self._last_known_bp_ts = time.time()
        return v
    except Exception as e:
        age = time.time() - self._last_known_bp_ts if self._last_known_bp_ts > 0 else -1
        print(f"  ⚠️ BP_FETCH_FAIL: {type(e).__name__}: {e} — "
              f"using last_known_bp=${self._last_known_bp:,.2f} (age={age:.0f}s)",
              flush=True)
        return self._last_known_bp
```

Why this is the right shape:
- **Visible failure.** The next SBFM-class event leaves a forensic trail at the moment of the bug, not a $0 BP that requires reconstructing the network state hours later.
- **Survivable transient.** A 5-second DNS blip no longer collapses sizing to placebo. The cached BP from the previous successful call (typically seconds earlier) carries through the window.
- **Stale-data safety.** The cache age is logged with each failure so the operator can decide whether the cached value is still trustworthy. For real-money sizing, the qty=1 floor removal (§7) is the second line of defense if cache age becomes alarming.
- **No env gate.** Pre-existing behavior was "silently return 0 on failure"; new behavior is "loudly return last-known on failure." No backwards-compatibility concern — the previous behavior was a bug.

`get_account_equity()` gets the same treatment because it shares the failure path verbatim.

### 13.5 `.env` vs `daily_run_v3.sh` drift — fixed in same commit

`.env` saying `WB_BROKER=ibkr` while the cron launcher injects `WB_BROKER=alpaca` is a latent footgun: a manual launch (`python bot_v3_hybrid.py` for debugging or recovery) would silently use the IBKR path — different broker, different account, different code path, different bugs. Fixed in this commit by updating `.env` to `WB_BROKER=alpaca` and adding a comment pointing future readers at `daily_run_v3.sh:210` as the authoritative override location.

### 13.6 Status — what shipped, what's open

| Item | Status |
|---|---|
| IBKRBroker tag hierarchy (§12) | **REVERTED 2026-05-18 PM.** Misdiagnosed the broker. Re-apply when WB_BROKER actually flips back to ibkr. |
| AlpacaBroker BP + equity log+cache (§13.4) | **Applied 2026-05-18 PM** to `broker.py:253-303` and `__init__`. |
| `.env` WB_BROKER drift (§13.5) | **Applied 2026-05-18 PM** — `.env:503` now matches the runtime override. |
| qty=1 floor removal (§7) | Still **UNAPPLIED.** Independent fix, scheduled for the bundled post-close Tuesday 5/19 or weekend 5/24 deploy. |
| Runtime broker-mismatch assert | **TODO.** Add a check at boot that fails loud if WB_BROKER ≠ alpaca for the squeeze-paper window. Defer to bundled deploy. |

### 13.7 What §12 got wrong vs. right

**Right:** the *shape* of a tag-hierarchy fix to `IBKRBroker.get_buying_power()` is still correct **for any future IBKR-execution path**. Re-apply it the day `WB_BROKER` flips back to ibkr (or as a defensive patch before any IBKR-execution flip).

**Wrong:** the diagnosis of the SBFM incident itself. SBFM ran through `AlpacaBroker`. The IBKR-path probe (probe_account_values.py) was useful for verifying tag names exist, but irrelevant to the actual incident.

**Right framing for SBFM:** transient Alpaca API failure was silently swallowed by `AlpacaBroker.get_buying_power()`. The fix is visibility + cache, not field selection.

### 13.8 Lessons (for the audit trail)

1. **Verify which code path runs before diagnosing it.** "What does `state.broker` resolve to at runtime?" should have been the first question, not the last. The boot-line `Broker: ALPACA` was sitting in the same log file the whole investigation.
2. **`.env` is not the source of truth** if a launcher overrides it on the command line. Trust runtime evidence over config-file evidence.
3. **A silent `except: return 0.0` is a forensic bomb.** It buries failures at the moment they happen and forces reconstruction hours later from circumstantial evidence (correlated quote failures, DNS conditions). The visibility patch in §13.4 is more valuable than the BP fallback itself — it makes the next incident debuggable in minutes instead of hours.

§13 is the operative diagnosis. §12 is preserved above for audit trail.

