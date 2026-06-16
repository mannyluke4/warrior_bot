# A/B/C Daily Report — 2026-06-15

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$32,095.22 | -$808.88 | 2 / 4 | 2 | 3414 | 1 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$30,532.92 | -$816.14 | 2 / 4 | 2 | 3414 | 1 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 1
- REGIME_SHIFT entries: 1
- Exits: 2
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 3414 (3 unique symbols)
- Symbols traded: RGNT

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-15_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 1
- REGIME_SHIFT entries: 1
- Exits: 2
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 3414 (3 unique symbols)
- Symbols traded: RGNT

## Data Quality Audit

- Audit lines parsed: 4330
- Symbols flagged HEURISTIC_SUSPECT: 6
- Symbols with DIRECT_QUERY_WEDGE events: 3

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| CIIT | 371 | 3 | 1 | 0.059 | 143369 / 54455 |
| JRSH | 242 | 1 | 1 | 0.001 | 19435 / 14747 |
| RGNT | 490 | 0 | 1 | 0.013 | 50577 / 35365 |
| ZIEXT | 39 | 181 | 0 | n/a | n/a |
| MTEN | 856 | 10 | 0 | 0.111 | 2157 / 536 |
| AHMA | 490 | 1 | 0 | 0.216 | 13627 / 3807 |
| CUPR | 490 | 1 | 0 | 0.184 | 8168 / 3230 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 14 | +$2,686.06 |
| B | 14 | -$4,183.34 |
| C | 14 | +$906.60 |
