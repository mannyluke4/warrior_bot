# A/B/C Daily Report — 2026-05-27

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | control | +$29,595.74 | -$815.28 | 6 / 13 | 0 | 0 | 0 |
| B | V1 VWAP | +$26,930.86 | -$451.63 | 4 / 9 | 0 | 0 | 0 |
| C | REENTRY-HWM-gate | +$26,471.51 | -$636.97 | 6 / 13 | 0 | 0 | 0 |

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

### Variant C — REENTRY-HWM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3297
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| AMSS | 826 | 19 | 1 | 0.000 | 5887 / 4444 |
| ASTC | 748 | 0 | 1 | 0.000 | 28878 / 21877 |
| ZIEXT | 126 | 569 | 0 | n/a | n/a |
| FGL | 1005 | 2 | 0 | 0.300 | 6054 / 5530 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 3 | -$153.88 |
| B | 3 | -$3,065.80 |
| C | 3 | -$3,521.16 |
