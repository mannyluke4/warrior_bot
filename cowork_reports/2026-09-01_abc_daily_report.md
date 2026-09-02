# A/B/C Daily Report — 2026-09-01

Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.

⚠️ **DATA QUALITY DEGRADED** — one or more symbols had `DIRECT_QUERY_WEDGE` audit events today. Variant comparison below reflects partial data. See Data Quality Audit section.

## Account / log snapshot

| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Gate blocks | Regime triggers |
|---|---|---:|---:|---:|---:|---:|---:|
| A | FIRESTORM-gate | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | 0 | 0 | 0 |
| B | FIRESTORM-gate + Track A | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | — | — | — |
| C | REENTRY-loss-gate | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | err: HTTPSConnectionPool( | 0 | 0 | 0 |

### Variant A — FIRESTORM-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

### Variant B — FIRESTORM-gate + Track A

- log error: `no_log` (path: `/Users/duffy/warrior_bot_v2/logs/2026-09-01_move_strike_subbot_B.log`)

### Variant C — REENTRY-loss-gate

- MOVE_STRIKE entries: 0
- REGIME_SHIFT entries: 0
- Exits: 0
- Regime-shift partials fired: 0
- Fade-gate blocks: 0 (0 unique symbols)

## Data Quality Audit

- Audit lines parsed: 3976
- Symbols flagged HEURISTIC_SUSPECT: 11
- Symbols with DIRECT_QUERY_WEDGE events: 5

| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |
|---|---:|---:|---:|---:|---|
| BTCT | 45 | 38 | 1 | 0.000 | 0 / 1273 |
| INTW | 44 | 38 | 1 | 0.000 | 0 / 100 |
| LABT | 292 | 38 | 1 | 0.000 | 34110 / 28457 |
| RAM | 36 | 38 | 1 | 0.000 | 0 / 1672 |
| SNDQ | 36 | 38 | 1 | 0.000 | 0 / 5660 |
| PXS | 110 | 109 | 0 | n/a | n/a |
| CNCK | 183 | 88 | 0 | n/a | n/a |
| FLYE | 77 | 77 | 0 | n/a | n/a |
| RDAC | 30 | 38 | 0 | n/a | n/a |
| SSM | 279 | 38 | 0 | n/a | n/a |
| WETO | 278 | 38 | 0 | n/a | n/a |

## Running totals (cumulative)

| Variant | Days | Cumulative P&L |
|---|---:|---:|
| A | 71 | +$1,662.94 |
| B | 71 | -$4,183.34 |
| C | 71 | +$331.63 |
