# A/B/C Daily Report — 2026-08-18

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-18_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 12190
- Symbols flagged HEURISTIC_SUSPECT: 8
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| EJH | 200 | 863 | 0 | n/a | n/a |
| PFSA | 200 | 863 | 0 | n/a | n/a |
| SGLY | 199 | 863 | 0 | n/a | n/a |
| SNDQ | 193 | 863 | 0 | n/a | n/a |
| WFF | 42 | 863 | 0 | n/a | n/a |
| XOS | 12 | 863 | 0 | n/a | n/a |
| VOGX | 194 | 718 | 0 | n/a | n/a |
| SXTC | 612 | 201 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 61 | +$1,662.94 |
| B | 61 | -$4,183.34 |
| C | 61 | +$331.63 |
