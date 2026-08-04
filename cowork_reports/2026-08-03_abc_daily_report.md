# A/B/C Daily Report — 2026-08-03

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$4,588.98 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,817.41 | +$0.00 | 0 / 0 | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-03_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 20810
- Symbols flagged HEURISTIC_SUSPECT: 9
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| FCUV | 204 | 880 | 0 | n/a | n/a |
| KORU | 205 | 880 | 0 | n/a | n/a |
| RUBI | 115 | 880 | 0 | n/a | n/a |
| UPC | 64 | 880 | 0 | n/a | n/a |
| VIVK | 43 | 880 | 0 | n/a | n/a |
| PUSA | 141 | 661 | 0 | n/a | n/a |
| EDBL | 140 | 656 | 0 | n/a | n/a |
| CRMU | 74 | 352 | 0 | n/a | n/a |
| BABU | 613 | 180 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 50 | +$1,662.94 |
| B | 50 | -$4,183.34 |
| C | 50 | +$331.63 |
