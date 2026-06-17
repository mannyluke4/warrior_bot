# A/B/C Daily Report — 2026-06-16

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$32,732.85 | +$637.76 | 1 / 4 | 1 | 44145 | 1 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$31,139.56 | +$606.77 | 1 / 4 | 1 | 44145 | 1 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 2
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)
- FIRESTORM-gate blocks: 44144 (2 unique symbols)
- Symbols traded: CRVO

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-16_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 2
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)
- FIRESTORM-gate blocks: 44144 (2 unique symbols)
- Symbols traded: CRVO

## Data Quality Audit

- Audit lines parsed: 4531
- Symbols flagged HEURISTIC_SUSPECT: 2
- Symbols with DIRECT_QUERY_WEDGE events: 4

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| NXTS | 726 | 241 | 2 | 0.000 | 2813 / 384 |
| UPC | 658 | 146 | 1 | 0.000 | 602 / 736 |
| GDHG | 900 | 0 | 1 | 0.084 | 6756 / 2589 |
| RRGB | 0 | 0 | 1 | 0.000 | 0 / 100 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 15 | +$3,323.82 |
| B | 15 | -$4,183.34 |
| C | 15 | +$1,513.37 |
