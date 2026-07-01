# A/B/C Daily Report — 2026-06-30

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$2,032.21 | -$362.22 | 1 / 2 | 1 | 62680 | 1 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$2,005.13 | -$365.03 | 1 / 2 | 1 | 62589 | 1 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 62680 (6 unique symbols)
- Symbols traded: JEM

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-30_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 62589 (6 unique symbols)
- Symbols traded: JEM

## Data Quality Audit

- Audit lines parsed: 4692
- Symbols flagged HEURISTIC_SUSPECT: 4
- Symbols with DIRECT_QUERY_WEDGE events: 3

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| PAVS | 621 | 158 | 2 | 0.040 | 2791 / 2963 |
| CUPR | 767 | 2 | 1 | 0.024 | 7062 / 3049 |
| JEM | 668 | 0 | 1 | 0.002 | 728074 / 950502 |
| GVH | 910 | 41 | 0 | 0.383 | 7855 / 6195 |
| SVRE | 715 | 8 | 0 | 0.270 | 1883 / 1640 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 25 | +$2,356.60 |
| B | 25 | -$4,183.34 |
| C | 25 | +$519.07 |
