# A/B/C Daily Report — 2026-08-27

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-27_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 12711
- Symbols flagged HEURISTIC_SUSPECT: 15
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| BMRA | 97 | 460 | 0 | n/a | n/a |
| VNCE | 110 | 431 | 0 | n/a | n/a |
| UMAL | 81 | 386 | 0 | n/a | n/a |
| AAOG | 86 | 379 | 0 | n/a | n/a |
| AAOX | 92 | 379 | 0 | n/a | n/a |
| AXTX | 91 | 379 | 0 | n/a | n/a |
| CRMG | 600 | 379 | 0 | n/a | n/a |
| MIMI | 590 | 379 | 0 | n/a | n/a |
| WNW | 519 | 379 | 0 | n/a | n/a |
| TJGC | 69 | 332 | 0 | n/a | n/a |
| AIOS | 59 | 286 | 0 | n/a | n/a |
| YJ | 82 | 273 | 0 | n/a | n/a |
| YAAS | 0 | 187 | 0 | n/a | n/a |
| PPCB | 514 | 127 | 0 | n/a | n/a |
| AXTL | 232 | 47 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 68 | +$1,662.94 |
| B | 68 | -$4,183.34 |
| C | 68 | +$331.63 |
