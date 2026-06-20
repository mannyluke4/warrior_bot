# A/B/C Daily Report — 2026-06-19

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$3,000.00 | +$0.00 | 0 / 0 | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$3,000.00 | +$0.00 | 0 / 0 | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-19_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3486
- Symbols flagged HEURISTIC_SUSPECT: 0
- Symbols with DIRECT_QUERY_WEDGE events: 9

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| ATPC | 247 | 0 | 29 | 0.000 | 0 / 24954 |
| BESS | 247 | 0 | 26 | 0.000 | 0 / 1034 |
| AMBO | 247 | 0 | 24 | 0.000 | 0 / 2988 |
| CRVO | 79 | 0 | 18 | 0.000 | 0 / 22197 |
| LNKS | 203 | 0 | 17 | 0.000 | 0 / 12035 |
| QSU | 203 | 0 | 16 | 0.000 | 0 / 547 |
| SMU | 160 | 0 | 11 | 0.000 | 0 / 3126 |
| LEUX | 160 | 0 | 10 | 0.000 | 0 / 2995 |
| WPRT | 156 | 0 | 10 | 0.000 | 0 / 3789 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 18 | +$3,323.82 |
| B | 18 | -$4,183.34 |
| C | 18 | +$1,513.37 |
