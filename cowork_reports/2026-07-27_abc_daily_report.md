# A/B/C Daily Report — 2026-07-27

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$5,609.65 | +$0.00 | 0 / 0 | 2 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,724.54 | +$0.00 | 0 / 0 | 0 | 21244 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 2
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: KORU

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-27_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 21244 (1 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3442
- Symbols flagged HEURISTIC_SUSPECT: 2
- Symbols with DIRECT_QUERY_WEDGE events: 4

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| EDBL | 565 | 27 | 1 | 0.042 | 12569 / 8004 |
| DFNS | 592 | 0 | 1 | 0.072 | 39494 / 37701 |
| KORU | 476 | 0 | 1 | 0.035 | 532772 / 382696 |
| LVWR | 592 | 0 | 1 | 0.073 | 12730 / 5460 |
| VEEE | 385 | 208 | 0 | 0.274 | 2623 / 840 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 45 | +$2,681.19 |
| B | 45 | -$4,183.34 |
| C | 45 | +$238.65 |
