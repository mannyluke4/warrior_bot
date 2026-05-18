# Setup A vs Setup B comparison — 2026-05-15

Generated: 2026-05-18T17:18:12

- **Setup A:** IBKR data (main bot) — `logs/2026-05-15_daily.log` (64,344 lines)
- **Setup B:** IBKR data (sub-bot, baseline) — `logs/2026-05-15_subbot_alpaca.log` (58,317 lines)

> **Baseline mode.** Both feeds are IBKR; near-identity is expected. Use this report as a control for tomorrow's Databento-vs-IBKR run.

## Verdict

- **Tick density:** Setup B median 15 ticks/min vs Setup A 15 → B is 0% denser
- **First-tick timing:** Setup B median 97s slower than A to first nonzero tick (N=15)
- **Trigger latency:** no matched signals (likely no overlap in entries)
- **Signal→fill latency:** Setup A median 0s (N=3); Setup B had no fills
- **Trade counts:** A=12, B=0, shared=0, A-only=4, B-only=0

## 1. Tick density per symbol per minute

| Symbol | A median | A p95 | A max | A minutes | B median | B p95 | B max | B minutes | B/A density |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AEHL | 15 | 94 | 332 | 841 | 15 | 85 | 337 | 878 | 1.00× |
| ATRA | 1 | 16 | 49 | 716 | 0 | 14 | 49 | 800 | 0.00× |
| CORD | 19 | 120 | 257 | 638 | 49 | 110 | 172 | 683 | 2.58× |
| FCHL | 4 | 27 | 88 | 762 | 4 | 27 | 54 | 764 | 1.00× |
| LESL | 15 | 103 | 625 | 832 | 15 | 98 | 610 | 864 | 1.00× |
| LNKS | 5 | 28 | 70 | 799 | 6 | 25 | 48 | 812 | 1.20× |
| MOBX | 25 | 135 | 520 | 854 | 33 | 110 | 308 | 882 | 1.32× |
| ONDG | 14 | 104 | 397 | 835 | 21 | 98 | 255 | 875 | 1.50× |
| PIII | 38 | 176 | 502 | 209 | 36 | 118 | 229 | 208 | 0.95× |
| QUCY | 48 | 1470 | 11921 | 891 | 61 | 440 | 821 | 928 | 1.27× |
| SKK | 4 | 13 | 22 | 182 | 3 | 12 | 23 | 177 | 0.75× |
| SKYQ | 2 | 8 | 22 | 181 | 1 | 7 | 22 | 172 | 0.50× |
| SLE | 89 | 3083 | 14323 | 662 | 92 | 549 | 817 | 690 | 1.03× |
| SST | 2 | 36 | 100 | 705 | 2 | 35 | 55 | 734 | 1.00× |
| TEST | 16 | 38 | 72 | 130 | 15 | 34 | 44 | 134 | 0.97× |

**Overall median-of-per-symbol-medians:** Setup A = 15 ticks/min, Setup B = 15 ticks/min

## 2. First-tick timing (subscribe → first nonzero tick)

| Symbol | A: subscribe → first tick (s) | B: subscribe → first tick (s) | Δ (B − A) |
|---|---:|---:|---:|
| AEHL | -8 | +89 | +97 |
| ATRA | -1 | +124 | +125 |
| CORD | +188 | +18 | -170 |
| FCHL | -8 | +89 | +97 |
| LESL | -13 | +93 | +106 |
| LNKS | -15 | +89 | +104 |
| MOBX | -8 | +94 | +102 |
| ONDG | +51 | +79 | +28 |
| PIII | +185 | +410 | +225 |
| QUCY | -8 | +94 | +102 |
| SKK | +46 | +290 | +244 |
| SKYQ | +20 | +98 | +78 |
| SLE | +90 | +80 | -10 |
| SST | +82 | +142 | +60 |
| TEST | +17 | +31 | +14 |

**Median Δ:** +97.0 s (positive = B slower to first tick than A; N=15)

## 3. Trigger detection latency

Match key: (symbol, price ±$0.01), |Δt| ≤ 5 min. Resolution is 1 second (logs are second-grained).

| Symbol | Price | A signal time | B signal time | Δ (B − A, s) |
|---|---:|---|---|---:|

### Setup A only (12)

| Symbol | Price | A signal time |
|---|---:|---|
| SLE | $6.0200 | 08:32:00 |
| LESL | $4.0200 | 08:58:00 |
| SLE | $7.0200 | 09:19:06 |
| ONDG | $7.2400 | 09:31:00 |
| QUCY | $3.0200 | 10:10:00 |
| SLE | $6.0200 | 10:46:00 |
| SLE | $5.0200 | 16:17:15 |
| SLE | $5.0200 | 16:25:36 |
| SLE | $5.0200 | 17:16:38 |
| SLE | $5.0200 | 17:25:46 |
| SLE | $5.0200 | 17:46:16 |
| SLE | $5.0200 | 17:50:14 |

## 4. Signal-to-fill latency

Time from `🟩 ENTRY:` line to next matching `FILL:` line, anchored to the nearest preceding `[HH:MM:SS ET]` heartbeat. Both bots use Alpaca for execution — divergence here is informational (broker-side variance) and not data-feed signal.

### Setup A

N = 3, median = 0.0 s, p90 = 0.8 s, p99 = 1.0 s, max = 1 s

| Symbol | Entry time | Fill time | Δ (s) | Limit | Fill px |
|---|---|---|---:|---:|---:|
| SLE | 08:32:00 | 08:32:01 | 1 | $6.09 | $6.1229 |
| LESL | 08:58:00 | 08:58:00 | 0 | $4.09 | $4.0400 |
| SLE | 09:19:06 | 09:19:06 | 0 | $7.09 | $7.0615 |

### Setup B

_No entry→fill pairs in this log._


## 5. Trade counts and symbol overlap

- Setup A entries: **12** across 4 symbols
- Setup B entries: **0** across 0 symbols
- Shared symbols: **0** — (none)
- A only (4): LESL, ONDG, QUCY, SLE
- B only (0): (none)

| Symbol | A entries | B entries |
|---|---:|---:|
| LESL | 1 | 0 |
| ONDG | 1 | 0 |
| QUCY | 1 | 0 |
| SLE | 9 | 0 |

## Methodology notes

- TICK AUDIT lines lack inline timestamps; the per-minute bucket is derived from the `last_tick_time=` field when count>0, and from the nearest preceding heartbeat when count=0.
- `🟩 ENTRY:` and `FILL:` lines also lack inline timestamps; we back-fill from the nearest preceding `[HH:MM:SS ET]` line. On a busy day this is accurate to ±1 second.
- `Subscribed` and `[TIER] PROMOTE` are treated as equivalent first-tick anchors.
- Resolution caveats: trigger-latency reporting is per-second, since the source `ENTRY SIGNAL` timestamps are HH:MM:SS only. Sub-second precision is unavailable without a code-side change.
