# A/B/C Daily Report — 2026-06-18

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | +$3,000.00 | +$0.00 | 0 / 0 | 0 | 5 | 0 |
| B | FIRESTORM-gate + Track A | err: {"message": "unautho | err: {"message": "unautho | err: {"message": "unautho | — | — | — |
| C | REENTRY-loss-gate | +$3,000.00 | +$0.00 | 0 / 0 | 0 | 5 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 5 (2 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-06-18_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)
- FIRESTORM-gate blocks: 5 (2 unique symbols)

## Data Quality Audit

- Audit lines parsed: 7496
- Symbols flagged HEURISTIC_SUSPECT: 7
- Symbols with DIRECT_QUERY_WEDGE events: 4

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| IHT | 807 | 10 | 2 | 0.000 | 1412 / 1341 |
| PMEC | 630 | 57 | 1 | 0.093 | 18990 / 1989 |
| WPRT | 797 | 5 | 1 | 0.000 | 1092 / 1314 |
| APWC | 941 | 0 | 1 | 0.000 | 7351 / 2784 |
| AMBO | 554 | 268 | 0 | 0.223 | 2151 / 1124 |
| SPCQ | 457 | 26 | 0 | 0.253 | 111513 / 13654 |
| LPA | 953 | 14 | 0 | 0.251 | 2022 / 600 |
| SNK | 626 | 2 | 0 | 0.565 | 45820 / 5002 |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 17 | +$3,323.82 |
| B | 17 | -$4,183.34 |
| C | 17 | +$1,513.37 |
