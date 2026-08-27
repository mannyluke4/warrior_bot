# A/B/C Daily Report — 2026-08-26

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-26_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 16148
- Symbols flagged HEURISTIC_SUSPECT: 9
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| DAIC | 196 | 866 | 0 | n/a | n/a |
| AKAN | 232 | 754 | 0 | n/a | n/a |
| CRE | 147 | 690 | 0 | n/a | n/a |
| SDOT | 600 | 248 | 0 | n/a | n/a |
| BMNZ | 705 | 166 | 0 | n/a | n/a |
| BRNX | 867 | 50 | 0 | n/a | n/a |
| SMTK | 861 | 50 | 0 | n/a | n/a |
| WVVIP | 864 | 50 | 0 | n/a | n/a |
| XPON | 861 | 50 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 67 | +$1,662.94 |
| B | 67 | -$4,183.34 |
| C | 67 | +$331.63 |
