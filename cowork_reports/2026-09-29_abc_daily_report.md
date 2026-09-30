# A/B/C Daily Report — 2026-09-29

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-09-29_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 24280
- Symbols flagged HEURISTIC_SUSPECT: 12
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| BKYI | 200 | 890 | 0 | n/a | n/a |
| EGG | 200 | 890 | 0 | n/a | n/a |
| ETHT | 193 | 890 | 0 | n/a | n/a |
| MTNB | 51 | 890 | 0 | n/a | n/a |
| RAM | 30 | 890 | 0 | n/a | n/a |
| SKHX | 11 | 890 | 0 | n/a | n/a |
| DAIC | 154 | 725 | 0 | n/a | n/a |
| DCOY | 149 | 701 | 0 | n/a | n/a |
| SSTI | 0 | 696 | 0 | n/a | n/a |
| MF | 0 | 488 | 0 | n/a | n/a |
| MSGY | 818 | 78 | 0 | n/a | n/a |
| IMCC | 688 | 32 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 82 | +$1,662.94 |
| B | 82 | -$4,183.34 |
| C | 82 | +$331.63 |
