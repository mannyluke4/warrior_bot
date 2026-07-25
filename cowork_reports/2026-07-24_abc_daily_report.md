# A/B/C Daily Report — 2026-07-24

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$5,610.49 | -$243.90 | 1 / 2 | 2 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,724.54 | +$0.00 | 0 / 0 | 0 | 5997 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 2
- REGIME_SHIFT entries: 0
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: NOWL

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-24_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 5997 (2 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3876
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| CJMB | 554 | 26 | 1 | 0.035 | 2549 / 2513 |
| NOWL | 579 | 1 | 1 | 0.028 | 83361 / 9122 |
| AKAN | 455 | 127 | 0 | 0.166 | 809 / 104 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 44 | +$2,681.19 |
| B | 44 | -$4,183.34 |
| C | 44 | +$238.65 |
