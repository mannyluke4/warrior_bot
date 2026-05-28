# A/B/C Daily Report — 2026-05-28

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## ⚠️ Bot vs Broker P&L divergence detected

| Variant | Bot reported | Broker truth | Gap |
|---|---:|---:|---:|
| A ✓ | +$838.00 | +$838.12 | +$0.12 |
| B ⚠️ | -$449.00 | +$397.46 | +$846.46 |
| C ✓ | +$833.00 | +$833.34 | +$0.34 |

Divergence threshold: ±$50. Investigate any flagged variant — likely partial-fill or orphan-class accounting issue. Bot's daily_pnl is no longer the canonical signal; broker truth is.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | control | +$30,432.86 | +$838.12 | 2 / 5 | 0 | 0 | 0 |
| B | V1 VWAP | +$27,327.44 | +$397.46 | 4 / 9 | 0 | 0 | 0 |
| C | REENTRY-loss-gate | +$27,303.85 | +$833.34 | 1 / 3 | 0 | 1 | 0 |

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

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)

## Data Quality Audit

- Audit lines parsed: 542
- Symbols flagged HEURISTIC_SUSPECT: 0
- Symbols with DIRECT_QUERY_WEDGE events: 1

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| IOTR | 162 | 0 | 1 | 0.000 | 92851 / 106091 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 4 | +$684.24 |
| B | 4 | -$2,668.34 |
| C | 4 | -$2,687.82 |
