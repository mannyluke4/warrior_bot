# FIRESTORM-gate Implementation Notes

**Date**: 2026-05-28 (afternoon)
**Owner**: CC
**Source**: Live-week tick-rate hypothesis (47 closed trades, 5/26-5/28) + YTD bucket audit (219 trades, 2026-01-02 → 2026-05-28). Both indicate strong tier separation by prior-bar tick rate. Live week: ≥100/s = 100% WR / +$3,854. YTD-sim: ≥100/s = 50% WR / -$147 avg vs <5/s = 19% WR / -$469 avg. Strategy bleeds on quiet bars; gate stops the bleeding without (yet) producing a profitable subset.

---

## TL;DR

Block any sub-bot entry (REGIME_SHIFT, MOVE_STRIKE, REENTRY GREEN) when
the prior completed 1m bar's tick count is below threshold. Default
threshold: 6000 ticks/min = 100 ticks/sec. Variant A is the live test
slot starting tomorrow's 02:00 MT cron.

---

## Code changes

### `bars.py`

- New per-symbol dict `_last_completed_bar_tick_count` on
  `TradeBarBuilder`. Persists the most recently CLOSED bar's tick count
  (does NOT reset at bar boundary — that's its whole purpose).
- New getter `get_last_completed_bar_tick_count(symbol) -> int`. Returns
  0 if no bar has closed yet for symbol.
- Bar-close path (line ~298): save `_tick_count_in_bar[symbol]` to
  `_last_completed_bar_tick_count[symbol]` BEFORE the in-progress reset.

### `move_strike_subbot.py`

- `__init__` (~line 322): added `firestorm_gate_enabled` + threshold attrs.
  Env vars `WB_MOVE_FIRESTORM_GATE_ENABLED` (default 0) and
  `WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN` (default 6000).
- New method `_firestorm_gate_blocks(symbol, setup) -> bool`. Returns
  False if gate disabled. Else queries
  `self.bar_builder.get_last_completed_bar_tick_count(symbol)` and
  compares against threshold. On block, emits
  `FIRESTORM_GATE_BLOCK <sym> setup=<type> prior_bar_ticks=<N> threshold=<T>`.
- Call sites:
  - `_maybe_fire_regime_shift` — after the existing require_armed +
    max_per_symbol checks, BEFORE the REGIME_SHIFT_TRIGGER log line.
    Setup label: `regime_shift`.
  - `_open_position_with_tag` — at the very top. Setup label:
    `move_strike` or `reentry_<tag>` depending on `is_reentry` flag.
    Covers both MOVE_STRIKE and REENTRY GREEN code paths.

### `daily_run_v3.sh`

- Variant A launch env updated:
  ```
  WB_MOVE_FIRESTORM_GATE_ENABLED=1
  WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000
  ```
- Variant A is no longer a pure control; the cleanest A/B/C signal
  attribution slot was sacrificed in favor of testing the highest-EV
  hypothesis the audit produced. Variants B and C unchanged.

### `scripts/abc_compare_daily.py`

- `FIRESTORM_GATE_BLOCK_RE` regex added.
- Aggregation keys: `firestorm_blocks_total`,
  `firestorm_blocks_unique_syms`. `gate_blocks_total` rolls firestorm
  blocks in alongside fade-gate + loss-gate blocks.
- `VARIANTS[A]` label `"control"` → `"FIRESTORM-gate"`.
- Per-variant detail line in the daily markdown report:
  `- FIRESTORM-gate blocks: <count> (<N> unique symbols)`.

---

## Smoke test results

Out-of-bot Python smoke test:

| Case | Setup | Prior-bar ticks | Threshold | Expected | Actual |
|------|-------|-----------------|-----------|----------|--------|
| HOT (above threshold) | regime_shift | 8,000 | 6,000 | PASS | PASS ✅ |
| COLD (below) | move_strike | 100 | 6,000 | BLOCK | BLOCK ✅ |
| EDGE (=threshold) | reentry_green | 6,000 | 6,000 | PASS | PASS ✅ |
| UNKNOWN (no bar closed yet) | regime_shift | 0 | 6,000 | BLOCK | BLOCK ✅ |
| Gate disabled | any | any | any | PASS | PASS ✅ |

Bar-builder smoke test:
- Empty: `get_last_completed_bar_tick_count(sym) = 0` ✅
- Before bar 1 closes: still 0 ✅
- After bar 1 closes (50 ticks accumulated): returns 50 ✅

Parser smoke test:
- New log format `FIRESTORM_GATE_BLOCK NCT setup=regime_shift prior_bar_ticks=523 threshold=6000` → parses ✅
- Setup variants `move_strike`, `reentry_GREEN` → parse ✅
- `VARIANTS[A]` shows `FIRESTORM-gate` ✅

---

## What does NOT change

- **No threshold tuning beyond default.** 6000/min = 100/sec is the
  FIRESTORM lower bound from the bucket audit. Live data will tell us
  if it should tighten (≥150/sec) or loosen (≥50/sec).
- **No variant B / C touch.** Fade-gate and REENTRY-loss-gate tests
  continue in their current slots.
- **No bypass for any setup type.** All three (REGIME_SHIFT, MOVE_STRIKE,
  REENTRY GREEN) gate identically. If the live data shows one setup
  class is hurt disproportionately by the gate, we can per-setup the
  threshold later.
- **No symbol whitelist.** Gate is universal.

---

## Validation criteria

**Day 1 (tomorrow 2026-05-29)**:
- Variant A should emit ≥1 `FIRESTORM_GATE_BLOCK` line if any
  arming-class event fires on a sub-100/s symbol. If no setups arm,
  no blocks expected.
- Variant A's entry count should be LOWER than B and C.
- The blocked symbols' subsequent live behavior (did they pump? did
  they die?) is the key observation.

**Cumulative criterion (~10 trading days)**:
- **A beats B and C on net P&L AND blocks a meaningful fraction (≥30%)
  of would-be entries**: gate is working as designed.
- **A trails B/C significantly**: gate over-fires — blocking would-be
  winners. Loosen threshold or restrict to specific setup classes.
- **A close to B/C with much fewer trades**: gate is mostly filtering
  break-even noise; tighten threshold to be more selective and re-test.

---

## Open questions for review after Day 1-5 data

1. **Per-setup thresholds?** REGIME_SHIFT requires a 4× body bar which
   itself implies recent volume; the gate may be redundant for it.
   REENTRY GREEN may be the only place the gate has to do work.
2. **Window other than the prior 60s?** Live-week and YTD audits both
   used the prior 1m bar. An average of the previous 5 bars might be
   more stable but lose responsiveness to fresh firestorms.
3. **Tier-2 snapshot subscriptions** report 250ms-throttled prints,
   inflating tick counts artificially relative to tick-by-tick subs.
   Should the threshold be subscription-tier-aware?

---

## Cross-references

- Live week audit: in-conversation `/tmp/trades_week_v2.py` output
  (47 closed trades).
- YTD bucket analysis: `/tmp/ytd_bucket_audit.py` reading
  `backtest_status/replay_subbot_YTD_v3_tickcache_universe_2026-01-02_2026-05-28.json`
  (219 trades).
- Prior gate impls for pattern reference:
  - `cowork_reports/2026-05-27_reentry_loss_gate_impl_notes.md`
  - `cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md` (superseded)
