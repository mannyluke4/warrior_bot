# A/B/C Daily Report — 2026-06-10

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$32,904.10 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | 0 | 0 | 0 |
| C | REENTRY-loss-gate | +$31,349.06 | +$0.00 | 0 / 0 | 0 | 0 | 0 |

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

- Audit lines parsed: 5909
- Symbols flagged HEURISTIC_SUSPECT: 9
- Symbols with DIRECT_QUERY_WEDGE events: 8

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| DSY | 289 | 7 | 3 | 0.000 | 1014959 / 1047659 |
| BGLC | 345 | 162 | 2 | 0.000 | 11811 / 530 |
| DOGZ | 290 | 10 | 1 | 0.000 | 13939 / 18135 |
| WCT | 342 | 7 | 1 | 0.033 | 6934 / 5306 |
| CIIT | 888 | 2 | 1 | 0.081 | 14767 / 12724 |
| SMCZ | 347 | 2 | 1 | 0.039 | 4783 / 5792 |
| HWH | 534 | 0 | 1 | 0.000 | 98068 / 48789 |
| VSME | 355 | 0 | 1 | 0.046 | 374327 / 727911 |
| CRMT | 302 | 49 | 0 | 0.804 | 16680 / 2849 |
| FLYE | 196 | 17 | 0 | 0.780 | 3433 / 5298 |
| NVNI | 224 | 1 | 0 | 0.244 | 5926 / 5046 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 13 | +$3,494.94 |
| B | 13 | -$4,183.34 |
| C | 13 | +$1,722.74 |
