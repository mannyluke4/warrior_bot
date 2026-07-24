# A/B/C Daily Report — 2026-07-23

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$5,854.39 | +$0.00 | 0 / 0 | 1 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,724.54 | +$0.00 | 0 / 0 | 0 | 11981 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 1
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: NEUP

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-23_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 11981 (2 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3505
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 4

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| NEUP | 599 | 101 | 1 | 0.087 | 3808 / 400 |
| JEM | 687 | 13 | 1 | 0.003 | 13071 / 14838 |
| NOWL | 698 | 2 | 1 | 0.067 | 7924 / 7835 |
| SKYQ | 700 | 0 | 1 | 0.002 | 32362 / 46820 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 43 | +$2,925.09 |
| B | 43 | -$4,183.34 |
| C | 43 | +$238.65 |
