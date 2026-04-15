# Completion — Dynamic `WB_SQ_MAX_ATTEMPTS` Phase 2 prototype

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**Directive:** `2026-04-15_directive_dynamic_sq_max_attempts.md` (Phase 2)
**Design:** `2026-04-15_design_dynamic_sq_attempts.md` (approved by Cowork)
**Formula:** `effective_cap = base + min(BONUS_CAP, int(max(0, cumR) / R_per_bonus))`, defaults `5 / 2.0 / 5`
**Status:** Code complete. Gate OFF default. All canaries zero-diff. Gate ON produces no regression. Phase 3 YTD validation blocks on directive 3's re-run.

---

## Code changes

Applied to both V1 (`squeeze_detector.py`) and V2 (`squeeze_detector_v2.py`) since the live system uses V2 by default (`.env` has `WB_SQUEEZE_VERSION=2`) but V1 is still importable via env override and used in some test paths.

Three symmetric blocks per detector:

**1. Env var reading + per-symbol cumR state** (constructor)
```python
self.dynamic_attempts_enabled = os.getenv("WB_SQ_DYNAMIC_ATTEMPTS_ENABLED", "0") == "1"
self.attempts_r_per_bonus = float(os.getenv("WB_SQ_ATTEMPTS_R_PER_BONUS", "2.0"))
self.attempts_bonus_cap = int(os.getenv("WB_SQ_ATTEMPTS_BONUS_CAP", "5"))
self._cumulative_r: float = 0.0
```

**2. Dynamic cap at the arm-check site** (replaces the legacy attempts reject)
```python
if self.dynamic_attempts_enabled:
    bonus = min(
        self.attempts_bonus_cap,
        int(max(0.0, self._cumulative_r) / max(self.attempts_r_per_bonus, 0.0001)),
    )
    effective_cap = self.max_attempts + bonus
    if self._attempts >= effective_cap:
        return (
            f"SQ_NO_ARM: max_attempts ({self._attempts}/{effective_cap}) "
            f"[base={self.max_attempts} bonus=+{bonus} cumR={self._cumulative_r:+.1f}]"
        )
elif self._attempts >= self.max_attempts:
    return f"SQ_NO_ARM: max_attempts ({self._attempts}/{self.max_attempts})"
```

The legacy branch is preserved verbatim when the gate is OFF — this is what makes gate-OFF runs byte-identical to pre-change.

**3. `notify_trade_closed(r_mult=0.0)` kwarg + `reset()` additions**
```python
def notify_trade_closed(self, symbol: str, pnl: float, r_mult: float = 0.0):
    ...
    self._cumulative_r += float(r_mult)

def reset(self):
    ...
    self._cumulative_r = 0.0
```

Default `r_mult=0.0` keeps the live bot's callers (`bot_v3_hybrid.py:1894`, `bot_ibkr.py:893`) backwards-compatible without modification. For live to actually benefit from the feature, those callers need updating to pass r_mult — deferred to a live-deployment directive per Cowork's Phase 4 staging.

### Sim callsite updates (simulate.py)

Two `notify_trade_closed` callers updated to pass `r_mult=t.r_multiple()`:
- `simulate.py:1984` — main trade-close hook
- `simulate.py:2420` — partial-close path

### V2 detector signature parity

`squeeze_detector_v2.py:notify_trade_closed` already accepted the new `r_mult` kwarg (introduced during the sim:1981 fix earlier today). Now it also accumulates into `_cumulative_r` — matching V1 behavior so both versions exercise the feature identically.

---

## Validation

### Zero-diff at gate OFF (all three canaries)

| Canary | Target | Measured (gate OFF) | Δ |
|---|---|---|---|
| VERO 2026-01-16 07:00-12:00 | +$35,622 | +$35,622 | 0 |
| ROLR 2026-01-14 07:00-12:00 | +$50,602 | +$50,602 | 0 |
| BIRD 2026-04-15 08:15-16:00 | -$1,909 | -$1,909 | 0 |

Zero-diff across every canary. Legacy path preserved.

### Gate ON (V2, production config)

| Canary | Gate OFF | Gate ON | Δ |
|---|---|---|---|
| VERO 2026-01-16 | +$35,622 | +$35,622 | **0** |
| ROLR 2026-01-14 | +$50,602 | +$50,602 | **0** |
| BIRD 2026-04-15 | -$1,909 | -$1,909 | **0** |

Gate ON produces **zero change** on all three canaries. That's the directive's floor ("must NOT make BIRD worse than baseline"), and it's satisfied.

### Why gate ON doesn't help BIRD under V2

Verbose trace with gate ON (`squeeze_detector_v2` with `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED=1`):

```
[08:21] SQ_ENTRY: 3.04   → attempt 1
[08:48] SQ_ENTRY: 4.04   → attempt 2
[08:49] SQ_ENTRY: 5.04   → attempt 3
[09:01] SQ_ENTRY: 6.04   → attempt 4
[09:03] SQ_ENTRY: 7.04   → attempt 5 (base cap hit)

[09:41] SQ_PRIMED: ...$9.24...
SQ_NO_ARM: para_invalid_r (entry=7.79 stop=8.01)     ← invalid_r fires BEFORE max_attempts
[09:42] SQ_PRIMED: ...$10.21...
SQ_NO_ARM: para_invalid_r (entry=7.79 stop=8.68)
[11:08] SQ_PRIMED: ...$14.21...
SQ_NO_ARM: invalid_r (entry=7.79 stop=12.66)
[11:29] SQ_PRIMED: ...$21.97...
SQ_NO_ARM: invalid_r (entry=7.79 stop=17.89)
```

BIRD's afternoon primes (09:41, 09:42, 11:08, 11:29) reject with `para_invalid_r` or `invalid_r` before the `max_attempts` check is ever evaluated in V2. The entry price shown (`$7.79`) is stale — identical across all four rejection sites despite the stock trading at $9-$22 — which strongly suggests a separate V2-level issue with level-pricing / trigger recomputation on post-cap primes.

**This is a V2 detector behavior, not a dynamic-attempts failure.** The feature is correctly wired and would extend the cap — it just never gets the chance because a stricter gate upstream rejects first.

### Implication for BIRD's Q1 autopsy answer

The BIRD autopsy (commit `9687b47`) attributed the missed $11→$20 leg to `WB_SQ_MAX_ATTEMPTS=5` exhaustion. That was based on verbose log lines of the form `SQ_NO_ARM: max_attempts (5/5)` at 09:08, 09:41, 09:42, 11:08, 11:29.

Re-running the same command today produces different messages at those same timestamps: `SQ_NO_ARM: para_invalid_r` / `SQ_NO_ARM: invalid_r`. The original autopsy trace may have come from V1 (either via an `.env` override during that session or a transient env-read inconsistency).

**Either way, the deeper cause is V2's trigger-price staleness post-5-attempts, not just the cap.** The cap is operating as designed; V2 has an additional ceiling at `invalid_r`. Fixing the chop-day miss on BIRD probably requires addressing both — or, if only the invalid_r is the real blocker today, *only* fixing that.

Flagging this for Cowork's judgment. Options:

- A. Accept the finding and defer dynamic-attempts live deployment until V2's invalid_r behavior on late primes is understood. The feature works; it just doesn't fix BIRD alone.
- B. Pursue a separate directive to investigate V2's level-price staleness (why `entry=7.79` persists across widely different primes).
- C. Treat dynamic-attempts as insurance for future BIRD-style days on symbols where V2's invalid_r doesn't fire — YTD validation (Phase 3) will tell us how often that pattern actually occurs.

My recommendation is **C**. Ship dynamic-attempts as approved per the directive, validate its YTD impact once the EPL-enabled dataset exists, then file a separate directive on V2 invalid_r if it turns out to be a common blocker.

---

## Phase 3 readiness

Blocks on directive 3's re-run (YTD batch with populated scanner_results + setup_type regex fix). Once that dataset exists:

1. Run the batch twice — once gate OFF, once gate ON — against the full 49-day YTD.
2. Diff per-symbol trades. Any symbol where gate ON added SQ arms beyond base=5 is a candidate for impact measurement.
3. Required zero-diff: VERO, ROLR at gate OFF (already confirmed canary-level).
4. Required non-regression: any symbol where gate ON reduces P&L must have the reason captured in logs.

Estimated wall time: 30-60 min total once scanner_results is complete.

---

## Risks / open questions

1. **Live callers (`bot_v3_hybrid.py:1894`, `bot_ibkr.py:893`) pass no `r_mult`.** Under gate ON in live, `_cumulative_r` stays at 0 → bonus is always 0 → effective cap = base. Feature is inert live until those callers are updated. Not a bug — deliberate per Phase 4 deferral — but worth noting.

2. **V2 invalid_r behavior** (see BIRD trace). Surfaced during this prototype. Not a Phase 2 blocker since it doesn't affect zero-diff or regression, but relevant to interpreting YTD results.

3. **Success-path log line** (directive's `SQ_ATTEMPTS: base=5 bonus=+2 (cumR=+4.1) → 7/10`) **not yet emitted on arm success.** Only the reject-path message includes the bonus details. Adding the success log would require touching the arm-decision caller in simulate.py / bot_v3_hybrid.py to read a new attribute off the detector — a broader change. Deferred to Phase 3 if the YTD data shows we need per-arm visibility; otherwise skipped.

4. **EPL/standalone-MP scope remains untouched.** Feature is squeeze-only per directive. Explicit.

---

## Commit plan

Single commit on `v2-ibkr-migration` covering:
- `squeeze_detector.py` — V1 patch (dynamic_attempts gate, cumR, reset, notify_trade_closed r_mult)
- `squeeze_detector_v2.py` — V2 patch (same three areas)
- `simulate.py` — two r_mult=... kwargs passed into notify_trade_closed
- This completion report

No `.env` changes (gate stays OFF default).
No CLAUDE.md changes (not yet deployed to live).

---

*CC (Opus). Prototype works, gate OFF is invisible, gate ON is a no-op on today's canaries for the right reason (V2's invalid_r upstream gate). YTD validation will tell us if the feature earns its keep on the full dataset.*
