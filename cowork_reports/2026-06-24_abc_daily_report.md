# A/B/C Daily Report — 2026-06-24

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$2,663.42 | -$404.10 | 1 / 2 | 1 | 21629 | 1 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$2,649.65 | -$418.54 | 1 / 2 | 1 | 21629 | 1 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 21629 (3 unique symbols)
- Symbols traded: PLSM

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-24_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 1
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 21629 (3 unique symbols)
- Symbols traded: PLSM

## Data Quality Audit

- Audit lines parsed: 4226
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 3

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| FRTT | 802 | 0 | 2 | 0.003 | 11435 / 17325 |
| CUPR | 853 | 7 | 1 | 0.005 | 1745 / 2072 |
| EHGO | 859 | 1 | 1 | 0.013 | 6278 / 5313 |
| QNRX | 845 | 16 | 0 | 0.232 | 6735 / 3454 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 21 | +$2,987.61 |
| B | 21 | -$4,183.34 |
| C | 21 | +$1,163.39 |
