# A/B/C Daily Report — 2026-06-08

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$34,917.32 | +$785.91 | 7 / 15 | 7 | 26062 | 1 |
| B | FIRESTORM-gate + Track A | +$30,769.83 | +$817.99 | 6 / 13 | 6 | 26062 | 1 |
| C | REENTRY-loss-gate | +$31,426.44 | +$1,042.67 | 10 / 22 | 10 | 6 | 1 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 6
- REGIME_SHIFT entries: 1
- Exits: 6
- Regime-shift partials fired: 2
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 26062 (1 unique symbols)
- Symbols traded: SUNE

### Variant B — FIRESTORM-gate + Track A

- MOVE_STRIKE entries: 5
- REGIME_SHIFT entries: 1
- Exits: 5
- Regime-shift partials fired: 2
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 26062 (1 unique symbols)
- Symbols traded: SUNE

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 9
- REGIME_SHIFT entries: 1
- Exits: 10
- Regime-shift partials fired: 2
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 6 (1 unique symbols)
- Symbols traded: SUNE

## Data Quality Audit

- Audit lines parsed: 3238
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 1

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| FEBO | 606 | 202 | 2 | 0.000 | 1509 / 139 |
| GMHS | 852 | 8 | 0 | 0.291 | 3492 / 2292 |
| FRSX | 737 | 2 | 0 | 0.253 | 7090 / 4620 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 11 | +$5,507.44 |
| B | 11 | -$2,152.91 |
| C | 11 | +$1,786.66 |
