# A/B/C Daily Report — 2026-10-02

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

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-10-02_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 17898
- Symbols flagged HEURISTIC_SUSPECT: 8
- Symbols with DIRECT_QUERY_WEDGE events: 0

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| TNON | 313 | 527 | 0 | n/a | n/a |
| AMOD | 822 | 77 | 0 | n/a | n/a |
| CRCG | 863 | 77 | 0 | n/a | n/a |
| GOW | 856 | 77 | 0 | n/a | n/a |
| SDEV | 863 | 77 | 0 | n/a | n/a |
| SMX | 32 | 77 | 0 | n/a | n/a |
| SORA | 806 | 77 | 0 | n/a | n/a |
| CRCA | 823 | 63 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 85 | +$1,662.94 |
| B | 85 | -$4,183.34 |
| C | 85 | +$331.63 |
