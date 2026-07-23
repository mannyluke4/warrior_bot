# A/B/C Daily Report — 2026-07-22

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$5,854.81 | -$370.67 | 3 / 6 | 3 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,724.54 | +$0.00 | 0 / 0 | 0 | 11344 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 3
- REGIME_SHIFT entries: 0
- Exits: 3
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: LABT, RKLX, SXTC

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-22_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 11344 (1 unique symbols)

## Data Quality Audit

- Audit lines parsed: 2663
- Symbols flagged HEURISTIC_SUSPECT: 1
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| INM | 867 | 0 | 1 | 0.000 | 2768 / 1958 |
| LABT | 753 | 0 | 1 | 0.000 | 17550 / 23992 |
| SXTC | 1030 | 11 | 0 | 0.231 | 10530 / 10359 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 42 | +$2,925.09 |
| B | 42 | -$4,183.34 |
| C | 42 | +$238.65 |
