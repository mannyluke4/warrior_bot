# A/B/C Daily Report — 2026-11-13

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-11-13_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 15285
- Symbols flagged HEURISTIC_SUSPECT: 10
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| BKHA | 200 | 894 | 0 | n/a | n/a |
| CBRX | 199 | 894 | 0 | n/a | n/a |
| CORD | 194 | 894 | 0 | n/a | n/a |
| SNAL | 71 | 894 | 0 | n/a | n/a |
| VTSI | 55 | 894 | 0 | n/a | n/a |
| XLAB | 11 | 894 | 0 | n/a | n/a |
| FCUV | 145 | 682 | 0 | n/a | n/a |
| SHIM | 137 | 610 | 0 | n/a | n/a |
| XCH | 0 | 355 | 0 | n/a | n/a |
| CIIT | 488 | 33 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 94 | +$1,662.94 |
| B | 94 | -$4,183.34 |
| C | 94 | +$331.63 |
