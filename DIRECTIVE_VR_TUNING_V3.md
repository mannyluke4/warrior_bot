# Directive: VWAP Reclaim Tuning V3 — Code Fix + Better Candidates

## Priority: HIGH
## Created: 2026-03-20 by Cowork (Opus)
## Depends on: V2 report (0 trades across 9 stocks — 2 root causes identified)

---

## Context

V2 widened thresholds but still produced 0 VR trades. Two concrete blockers emerged:

1. **GRI had a legitimate reclaim at R=$0.87 — blocked by $0.80 cap** (missed by $0.07)
2. **`severe_vwap_loss` at 5% is hardcoded** (line 168 of `vwap_reclaim_detector.py`) and resets the detector on normal small-cap volatility. This killed APVO (11-14% below VWAP) before it ever had a chance to reclaim.

V3 fixes both with a code change + threshold widening.

---

## Phase 0: Git Pull

```bash
cd ~/warrior_bot && git pull origin main
```

---

## Phase 1: Code Change — Parameterize `severe_vwap_loss`

In `vwap_reclaim_detector.py`:

### 1a. Add env var in `__init__` (after `self.max_attempts` line ~36):
```python
self.severe_vwap_loss_pct = float(os.getenv("WB_VR_SEVERE_VWAP_LOSS_PCT", "20.0"))
```

### 1b. Replace hardcoded 5.0 with the new param (line ~168):

**Current code:**
```python
                # Give up if price drops severely below VWAP (>5%)
                vwap_dist_pct = (vwap - c) / vwap * 100
                if vwap_dist_pct > 5.0:
```

**Replace with:**
```python
                # Give up if price drops severely below VWAP
                vwap_dist_pct = (vwap - c) / vwap * 100
                if vwap_dist_pct > self.severe_vwap_loss_pct:
```

That's it — one new env var, one line changed. Default 20% (was 5%).

---

## Phase 2: Regression (MUST PASS before proceeding)

Run with VR OFF first (baseline), then VR ON (no regression impact expected):

```bash
source venv/bin/activate

# Regression — VR OFF (standard)
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$6,444
```

If regression fails, STOP. Do not proceed to Phase 3.

---

## Phase 3: V3 Threshold Tests

### Env vars for ALL V3 runs:
```bash
export WB_VR_ENABLED=1
export WB_SQUEEZE_ENABLED=1
export WB_VR_MAX_R=1.00                    # Was 0.80. GRI's $0.87 now passes.
export WB_VR_MAX_R_PCT=5.0                 # Keep from V2
export WB_VR_RECLAIM_WINDOW=5              # Keep from V2
export WB_VR_MAX_BELOW_BARS=20             # Keep from V2
export WB_VR_MAX_ATTEMPTS=3                # Keep from V2
export WB_VR_SEVERE_VWAP_LOSS_PCT=20.0     # NEW. Was hardcoded 5%. Allows 20% dip before reset.
```

### Tier 1: Re-run V2 stocks with fixed thresholds

These are the same stocks from V2, now with R-cap $1.00 and severe_loss at 20%:

```bash
# GRI — THE key test. R=$0.87 was blocked by $0.80. NOW UNBLOCKED.
# If this doesn't produce a VR trade, VR may not be viable for micro-caps.
python simulate.py GRI 2026-01-28 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# APVO — was killed by severe_vwap_loss at 11-14%. Now 20% threshold lets it stay alive.
python simulate.py APVO 2026-01-09 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# TWG — collapsed 28-33% below VWAP. Even 20% won't save this (correctly resets).
# But TWG has a V-recovery pattern ($8.03→$7.77→$10.28) — worth checking if
# the 20% window catches ANY reclaim before the 28% collapse.
python simulate.py TWG 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# CHNR — R=$1.04 reclaim. NOW passes $1.00 cap (was blocked at $0.50, then $0.80).
python simulate.py CHNR 2026-03-19 07:16 12:00 --ticks --tick-cache tick_cache/ -v
```

### Tier 2: New cached candidates (never tested before)

```bash
# TNMG — 3 VWAP crosses, 20% above, max VWAP distance 30.7%
# Warning: trajectory shows pure fade ($4.01→$2.48). May get 0 trades.
# But 20% severe_loss threshold means it stays alive longer.
python simulate.py TNMG 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# ELAB — 2 VWAP crosses, 17% above, 4 volume spikes, 59% range
python simulate.py ELAB 2026-01-06 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# ENVB — 2 VWAP crosses, 3% above, 101% range. Nearly all time below VWAP
# but price jumped from $2.29 to $2.80 between 15m and 30m. Late reclaim?
python simulate.py ENVB 2026-02-19 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

### Tier 3: Regression controls with VR ON

```bash
# VERO — must still be +$18,583 with VR ON (stayed above VWAP, VR should never activate)
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# ROLR — must still be +$6,444 with VR ON
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

---

## Phase 4: Fetch Tick Data for Non-Cached V-Recovery Candidates

If Phase 3 produces >0 VR trades (good sign — detector works mechanically), fetch tick data for these stocks that showed strong V-recovery patterns but aren't in our tick cache:

```bash
# FLYX 2026-01-08 — 12 VWAP crosses, strong V-recovery: $3.04→dip→$3.73
# This was our BEST V-recovery candidate from trajectory analysis.
python simulate.py FLYX 2026-01-08 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# XWEL 2026-02-27 — 2 VWAP crosses, 4 trades on the day
python simulate.py XWEL 2026-02-27 07:00 12:00 --ticks --tick-cache tick_cache/ -v

# BATL 2026-02-18 — 14 VWAP crosses (!), cascading stock (avg +$2,043)
python simulate.py BATL 2026-02-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

Note: These will auto-fetch tick data from Alpaca if not cached. The `--tick-cache` flag caches it for future runs. If Alpaca rate limits or data is unavailable, skip and note in report.

**If Phase 3 produces 0 VR trades, SKIP Phase 4** — no point fetching data for a detector that can't fire.

---

## Phase 5: Report

Write report to `cowork_reports/2026-03-20_vr_tuning_v3.md` with:

1. **Code change confirmation** — severe_vwap_loss parameterized, default 20%
2. **Regression status** — VERO +$18,583, ROLR +$6,444 (must pass)
3. **Per-stock results table:**

| Stock | Date | Tier | VR P&L | VR Trades | Key VR Events | Notes |
|-------|------|------|--------|-----------|---------------|-------|
| GRI | 2026-01-28 | T1 | ? | ? | ? | R=$0.87 — should ARM now |
| APVO | 2026-01-09 | T1 | ? | ? | ? | 20% severe_loss — stays alive? |
| TWG | 2026-01-20 | T1 | ? | ? | ? | V-recovery test |
| CHNR | 2026-03-19 | T1 | ? | ? | ? | R=$1.04 — should ARM now |
| TNMG | 2026-01-16 | T2 | ? | ? | ? | New candidate |
| ELAB | 2026-01-06 | T2 | ? | ? | ? | New candidate |
| ENVB | 2026-02-19 | T2 | ? | ? | ? | New candidate |
| VERO | 2026-01-16 | Ctrl | ? | ? | ? | Must be +$18,583 |
| ROLR | 2026-01-14 | Ctrl | ? | ? | ? | Must be +$6,444 |

4. **VR detector log snippets** — full state transition chains for any stock that reached RECLAIMED or ARMED state
5. **Decision matrix:**
   - If VR trades > 0 AND net positive → Phase 4 (fetch new candidates)
   - If VR trades > 0 BUT net negative → analyze exit rules, may need tuning
   - If VR trades == 0 → VR may not be viable for micro-cap momentum. Recommend shelving in favor of Strategy 5 (Curl/Extension)

**STOP after Phase 5. Do NOT run full YTD. Do NOT proceed to Phase 4 without Manny's review if Phase 3 produced 0 trades.**

---

## Key Differences from V2

| Parameter | V1 | V2 | V3 |
|-----------|-----|-----|-----|
| `WB_VR_MAX_R` | $0.50 | $0.80 | **$1.00** |
| `WB_VR_MAX_R_PCT` | 3.0% | 5.0% | 5.0% |
| `WB_VR_RECLAIM_WINDOW` | 3 | 5 | 5 |
| `WB_VR_MAX_BELOW_BARS` | 10 | 20 | 20 |
| `WB_VR_MAX_ATTEMPTS` | 2 | 3 | 3 |
| `severe_vwap_loss` | 5% (hardcoded) | 5% (hardcoded) | **20% (env var)** |
| Test stocks | CHNR, ARTL | 9 stocks | **9 stocks + 3 new** |
| Code change | None | None | **Yes — parameterize severe_loss** |

The two changes that matter most:
1. **R-cap $0.80 → $1.00** — directly unblocks GRI ($0.87) and CHNR ($1.04)
2. **severe_loss 5% → 20%** — stops premature resets on APVO-type stocks (11-14% dips)

---

## If V3 Also Produces 0 Trades

This is a real possibility. If so, the strategic recommendation is:

1. **Shelve VR for micro-cap momentum** — the dip-and-reclaim pattern may be genuinely rare in gap-up small-caps
2. **Pivot to Strategy 5 (Curl/Extension)** — this was already HIGH priority in MASTER_TODO and may capture more of Ross's non-MP trades
3. **Revisit VR later** for mid-cap stocks or late-session plays (10-11 AM) where the pattern is more common
4. Keep VR code in place (env var OFF) — it's mechanically correct and may be useful as we expand the stock universe

---

*Directive by Cowork (Opus) — 2026-03-20*
