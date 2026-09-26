# A/B/C Daily Report — 2026-09-25

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,817.41 | +$0.00 | 0 / 0 | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-09-25_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 20761
- Symbols flagged HEURISTIC_SUSPECT: 12
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| AAOX | 209 | 878 | 0 | n/a | n/a |
| BRNX | 209 | 878 | 0 | n/a | n/a |
| BYAH | 203 | 878 | 0 | n/a | n/a |
| CRDU | 210 | 878 | 0 | n/a | n/a |
| INLF | 85 | 878 | 0 | n/a | n/a |
| SNDG | 22 | 878 | 0 | n/a | n/a |
| WHLR | 16 | 878 | 0 | n/a | n/a |
| MGLD | 0 | 723 | 0 | n/a | n/a |
| KITT | 0 | 608 | 0 | n/a | n/a |
| CNET | 124 | 579 | 0 | n/a | n/a |
| TDIC | 0 | 467 | 0 | n/a | n/a |
| NCT | 529 | 237 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 80 | +$1,662.94 |
| B | 80 | -$4,183.34 |
| C | 80 | +$331.63 |
