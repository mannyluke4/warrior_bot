# A/B/C Daily Report — 2026-05-26

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

## ⚠️ Variant P&L — 2026-05-26 (DATA CORRUPTED BY ORPHAN BUG)

| Variant | Bot reported | Broker truth | Gap | Note |
|---|---:|---:|---:|---|
| A | -$1,549.00 | +$661.40 | +$2,210.40 | Bot under-reported by $2,210 |
| B | -$2,904.00 | -$2,614.17 | +$289.83 | Bot under-reported by $290 |
| C | -$1,762.00 | -$2,884.19 | -$1,122.19 | Bot over-reported by $1,122 |

**Variant comparison excluded for 2026-05-26.** Orphan-position accounting bug (audit: `2026-05-26_sub_bot_orphan_audit.md`, fix: `2026-05-26_sub_bot_orphan_fix_directive.md`) silently corrupted bot's reported P&L. Broker-truth numbers above are documented for historical record; they should NOT be used to inform the variant decision because per-variant orphan exposure varied (different exits = different orphan timing = different lucky-flatten outcomes).

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Fade blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | control | +$30,419.33 | +$661.40 | 19 / 48 | 0 | 0 | 0 |
| B | V1 VWAP | +$27,385.83 | -$2,614.17 | 8 / 19 | 0 | 0 | 0 |
| C | V4 BodyCV | +$27,115.81 | -$2,884.19 | 17 / 44 | 0 | 0 | 0 |

### Variant A — control

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — V1 VWAP

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant C — V4 BodyCV

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- No `SUBSCRIPTION_AUDIT` lines found in the main bot log. Watchdog likely disabled (`WB_SUB_WATCHDOG_ENABLED=0`) or bot not started.

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 2 | +$661.40 |
| B | 2 | -$2,614.17 |
| C | 2 | -$2,884.19 |
