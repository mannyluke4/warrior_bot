# A/B/C Daily Report — 2026-07-10

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$2,032.14 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$2,005.06 | +$0.00 | 0 / 0 | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-10_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 990
- Symbols flagged HEURISTIC_SUSPECT: 2
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| SNAL | 183 | 15 | 0 | 0.667 | 4148 / 1359 |
| WOK | 194 | 4 | 0 | 0.482 | 8085 / 12364 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 33 | +$2,356.60 |
| B | 33 | -$4,183.34 |
| C | 33 | +$519.07 |
