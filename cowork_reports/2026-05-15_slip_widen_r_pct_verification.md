# R% Pass-Flip Verification — Slip Widen 0.05/0.005 → 0.07/0.010

**Date:** 2026-05-14
**Author:** CC
**For:** Cowork (Perplexity)
**Per:** `DIRECTIVE_2026-05-14_SQUEEZE_FILL_RATE_FIX.md` §2 #1

---

## TL;DR

**No R% pass-flips will occur from the slip widen.** The R% gate is evaluated on the **signal price**, not the post-slip **limit price**. Widening slip changes the order-submit limit but does not change the R% computation that the gate keys off. All 7 audited entries retain identical R% pass/fail status under the new config.

Cowork's directive expected wider slip to *increase* R% (making the gate more restrictive). That logic assumes R% is computed on the limit price. The code computes it on the signal price, so the slip widen is neutral to R%.

---

## Code path (verified)

### bot_alpaca_subbot.py (Setup A WB)

`enter_wb_position()` reads `entry_price` and `stop_price` directly from the detector's `WB_ENTER:` message at line 902:

```python
entry_price = float(parts["entry"])     # signal price (prov_entry from detector)
stop_price = float(parts["stop"])       # detector-derived stop

# H#10 R% floor — line 901
r_pct = (entry_price - stop_price) / entry_price * 100.0
if r_pct < WB_MIN_R_PCT:                # WB_MIN_R_PCT = 1.5
    print(f"[CHOP_REJECT] {symbol}: r_pct_below_floor (R%={r_pct:.2f} ...")
    return
```

Slip is applied *afterward* at line 1038:

```python
slippage = max(ENTRY_SLIPPAGE_MIN, entry_price * ENTRY_SLIPPAGE_PCT)
limit_price = round(entry_price + slippage, 2)
```

So `r_pct` is fixed before `slippage` is even computed. The slip widen affects `limit_price`, not `r_pct`.

### bot_v3_hybrid.py (Setup A squeeze)

Squeeze uses an absolute dollar floor (`WB_MIN_R=0.06`), not a percentage gate. Same logic applies: `r` is read from the detector's signal output before slip:

```python
r = armed.entry - armed.stop          # detector-derived, slip-independent
if r < MIN_R:
    return  # reject
```

`MIN_R=0.06` (the dollar floor) is also slip-independent.

### Engine bots

`squeeze_bot.py` and `wb_bot.py` both use signal price for R, mirroring Setup A. Slip is applied via `get_priced_limit()` after the gate decision.

---

## Audited entries — R% unchanged

For the 7 audited entries from the squeeze fill-rate audit (`cowork_reports/2026-05-14_squeeze_fill_rate_audit.md`), R% is purely a function of (signal_price, stop) — both invariant under slip changes. So every entry keeps its gate status:

| Entry | Signal | Stop | R% (old slip) | R% (new slip) | Gate (1.5% floor) |
|---|---|---|---|---|---|
| CLNN 05-04 | 8.02 | 7.91 | 1.37% | 1.37% | FAIL (unchanged) |
| ATRA 05-07 | 8.02 | 7.90 | 1.50% | 1.50% | PASS (unchanged, knife-edge) |
| ODYS 05-11 | 10.02 | 9.90 | 1.20% | 1.20% | FAIL (unchanged — squeeze MIN_R dollar floor passes at $0.12) |
| TRAW 05-11 | 2.31 | 2.21 | 4.12% | 4.12% | PASS (unchanged) |
| ATRA 05-13 | 9.81 | 9.75 | 0.59% | 0.59% | FAIL (unchanged — this was the R-gate skip) |
| ATRA 05-08 | 8.65 | 8.50 (est) | 1.73% | 1.73% | PASS (WB winner, unchanged) |
| LNKS 05-14 | 2.19 | 2.13 | 2.74% | 2.74% | PASS (unchanged) |

All 7 entries retain their gate status. **Zero pass-flips.** The slip widen is neutral to R% in both directions.

---

## Why the slip widen still matters (despite being R%-neutral)

Slip affects `limit_price`, which is what the broker sees. Widening it doesn't change which signals *fire* (R% gate decisions), but it changes which fires *fill*. Specifically:

- LNKS 05-14: old limit $2.24, market ran to $2.29 (5¢ past); new limit $2.27 (with 1.0% slip on $2.19) — would have been hit by the same $2.29 print if the bot were faster. Still tight, but reduces the geometric guarantee-of-miss.
- TRAW 05-11: old limit $2.36, retries at same price (no chase); new limit $2.36 (1.0% pad = 2¢, ENTRY_SLIPPAGE_MIN=7¢ floor wins → $2.38). Wider initial limit increases chance the first attempt fills.

The slip widen is a fill-rate fix, not an arm-rate fix. Verified.

---

## Conclusion

✅ **Safe to ship.** The slip widen does not impact R% gate decisions. No surprise pass-flips. Cowork's concern about "borderline trade flipping into passing R% floor" is structurally not possible under the current code layout.

If at some future point R% is recomputed on `limit_price` rather than `signal_price`, this analysis would need to be revisited. Current code does not do that.

---

## Files referenced

- `bot_alpaca_subbot.py:895-908` (R% gate computation)
- `bot_alpaca_subbot.py:1038` (slip application — *after* gate)
- `bot_v3_hybrid.py:_verify_fill_with_retry` (slip on retry — still uses signal-derived R)
- `cowork_reports/2026-05-14_squeeze_fill_rate_audit.md` (the 7 audited entries)
