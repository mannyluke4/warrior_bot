# A/B/C Daily Report — 2026-06-02

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$30,179.79 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | +$30,000.00 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| C | REENTRY-loss-gate | +$26,198.64 | -$0.99 | 0 / 0 | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

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

## Data Quality Audit

- Audit lines parsed: 277
- Symbols flagged HEURISTIC_SUSPECT: 1
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| BJDX | 37 | 0 | 1 | 0.000 | 1865163 / 3453712 |
| VSA | 46 | 0 | 1 | 0.000 | 60246 / 37684 |
| ZJYL | 191 | 1 | 0 | 0.223 | 23185 / 28902 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 7 | +$431.36 |
| B | 7 | -$2,923.11 |
| C | 7 | -$3,795.01 |
