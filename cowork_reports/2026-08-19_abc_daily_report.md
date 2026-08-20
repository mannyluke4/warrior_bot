# A/B/C Daily Report — 2026-08-19

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-19_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 8352
- Symbols flagged HEURISTIC_SUSPECT: 13
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| MSS | 351 | 320 | 0 | n/a | n/a |
| RCON | 87 | 320 | 0 | n/a | n/a |
| SKHX | 80 | 320 | 0 | n/a | n/a |
| TGL | 45 | 320 | 0 | n/a | n/a |
| TNON | 289 | 320 | 0 | n/a | n/a |
| RDAC | 334 | 297 | 0 | n/a | n/a |
| ADIU | 62 | 262 | 0 | n/a | n/a |
| ASPC | 317 | 262 | 0 | n/a | n/a |
| BLSG | 62 | 262 | 0 | n/a | n/a |
| UUU | 47 | 220 | 0 | n/a | n/a |
| EVAX | 36 | 167 | 0 | n/a | n/a |
| INLF | 278 | 42 | 0 | n/a | n/a |
| MSGY | 251 | 24 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 62 | +$1,662.94 |
| B | 62 | -$4,183.34 |
| C | 62 | +$331.63 |
