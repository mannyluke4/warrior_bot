# A/B/C Daily Report — 2026-10-08

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-10-08_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 21913
- Symbols flagged HEURISTIC_SUSPECT: 9
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| AAOZ | 214 | 870 | 0 | n/a | n/a |
| APLX | 214 | 870 | 0 | n/a | n/a |
| BEZ | 215 | 870 | 0 | n/a | n/a |
| DKI | 208 | 870 | 0 | n/a | n/a |
| LITZ | 70 | 870 | 0 | n/a | n/a |
| RAMZ | 29 | 870 | 0 | n/a | n/a |
| HKIT | 77 | 674 | 0 | n/a | n/a |
| SHPH | 0 | 574 | 0 | n/a | n/a |
| BIAF | 404 | 323 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 89 | +$1,662.94 |
| B | 89 | -$4,183.34 |
| C | 89 | +$331.63 |
