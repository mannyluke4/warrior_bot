# A/B/C Daily Report — 2026-07-29

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$5,322.41 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,788.96 | +$64.42 | 4 / 5 | 4 | 12049 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-29_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 4
- REGIME_SHIFT entries: 0
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)
- FIRESTORM-gate blocks: 12048 (3 unique symbols)
- Symbols traded: AMIX

## Data Quality Audit

- Audit lines parsed: 1686
- Symbols flagged HEURISTIC_SUSPECT: 1
- Symbols with DIRECT_QUERY_WEDGE events: 1

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| AMIX | 962 | 3 | 1 | 0.031 | 27953 / 16718 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 47 | +$2,394.36 |
| B | 47 | -$4,183.34 |
| C | 47 | +$303.07 |
