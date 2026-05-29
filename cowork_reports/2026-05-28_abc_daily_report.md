# A/B/C Daily Report — 2026-05-28

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## ⚠️ Bot vs Broker P&L divergence detected

| Variant | Bot reported | Broker truth | Gap |
|---|---:|---:|---:|
| A ⚠️ | -$22.00 | +$585.24 | +$607.24 |
| B ⚠️ | -$22.00 | +$142.69 | +$164.69 |
| C ⚠️ | -$22.00 | +$580.45 | +$602.45 |

Divergence threshold: ±$50. Investigate any flagged variant — likely partial-fill or orphan-class accounting issue. Bot's daily_pnl is no longer the canonical signal; broker truth is.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$30,179.98 | +$585.24 | 4 / 9 | 4 | 0 | 3 |
| B | V1 VWAP | +$27,072.67 | +$142.69 | 6 / 13 | 6 | 1 | 5 |
| C | REENTRY-loss-gate | +$27,050.96 | +$580.45 | 3 / 7 | 3 | 1 | 3 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 1
- REGIME_SHIFT entries: 3
- Exits: 3
- Regime-shift partials fired: 1
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: IOTR, NCT, SPRC

### Variant B — V1 VWAP

- MOVE_STRIKE entries: 1
- REGIME_SHIFT entries: 5
- Exits: 501
- Regime-shift partials fired: 1
- Fade-gate blocks: 1 (1 unique symbols)
- Symbols traded: IOTR, NCT, SPRC

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 3
- Exits: 2
- Regime-shift partials fired: 1
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)
- Symbols traded: IOTR, NCT, SPRC

## Data Quality Audit

- Audit lines parsed: 3602
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| IOTR | 162 | 0 | 1 | 0.000 | 92851 / 106091 |
| MASK | 611 | 0 | 1 | 0.022 | 13680 / 12499 |
| CODX | 604 | 8 | 0 | 0.207 | 10025 / 3240 |
| ATPC | 611 | 1 | 0 | 0.362 | 7156 / 7390 |
| NCT | 848 | 1 | 0 | 0.243 | 5077 / 2123 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 4 | +$431.36 |
| B | 4 | -$2,923.11 |
| C | 4 | -$2,940.71 |
