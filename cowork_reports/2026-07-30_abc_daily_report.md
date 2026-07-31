# A/B/C Daily Report — 2026-07-30

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$4,840.02 | -$482.39 | 7 / 14 | 7 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$1,817.46 | +$28.56 | 4 / 5 | 4 | 30409 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 7
- REGIME_SHIFT entries: 0
- Exits: 7
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- Symbols traded: BEX, MSFL, NBIG

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-07-30_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 4
- REGIME_SHIFT entries: 0
- Exits: 1
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- REENTRY-loss-gate blocks: 1 (1 unique symbols)
- FIRESTORM-gate blocks: 30408 (2 unique symbols)
- Symbols traded: NUWE

## Data Quality Audit

- Audit lines parsed: 4029
- Symbols flagged HEURISTIC_SUSPECT: 3
- Symbols with DIRECT_QUERY_WEDGE events: 2

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| VIVK | 1046 | 11 | 1 | 0.094 | 2778 / 5310 |
| NUWE | 854 | 0 | 1 | 0.001 | 48230 / 55736 |
| MSFL | 931 | 127 | 0 | 0.151 | 190 / 100 |
| AXTX | 1057 | 1 | 0 | 0.237 | 44570 / 46781 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 48 | +$1,911.97 |
| B | 48 | -$4,183.34 |
| C | 48 | +$331.63 |
