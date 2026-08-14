# A/B/C Daily Report — 2026-08-13

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-08-13_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 21849
- Symbols flagged HEURISTIC_SUSPECT: 14
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| CBRZ | 259 | 807 | 0 | n/a | n/a |
| FRGT | 258 | 807 | 0 | n/a | n/a |
| NBIZ | 258 | 807 | 0 | n/a | n/a |
| ONDG | 228 | 807 | 0 | n/a | n/a |
| ONDL | 105 | 807 | 0 | n/a | n/a |
| SFHG | 39 | 807 | 0 | n/a | n/a |
| WVVIP | 77 | 807 | 0 | n/a | n/a |
| OPEG | 0 | 750 | 0 | n/a | n/a |
| ONDU | 0 | 708 | 0 | n/a | n/a |
| LNSR | 153 | 704 | 0 | n/a | n/a |
| SSM | 0 | 651 | 0 | n/a | n/a |
| STEM | 0 | 567 | 0 | n/a | n/a |
| EDBL | 541 | 122 | 0 | n/a | n/a |
| IREG | 661 | 2 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 58 | +$1,662.94 |
| B | 58 | -$4,183.34 |
| C | 58 | +$331.63 |
