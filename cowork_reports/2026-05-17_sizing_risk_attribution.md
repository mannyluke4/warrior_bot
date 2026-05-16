# Wave 1 Agent E — Sizing / Risk / Attribution / VIX Regime

**Date:** 2026-05-17 (Agent E build, dated 2026-05-15 wall-clock)
**Author:** CC
**Status:** Wave 1 deliverable complete. All unit tests pass. Existing
live code untouched.

---

## 1. Module summaries

### 1.1 `framework/sizing.py`
`HalfKellySizer` dataclass.

- Config: `risk_per_trade_pct` (e.g. `1.0` = 1% of equity), `max_bar_volume_pct` (default `0.05` = 5% participation cap).
- Formula:
  - `raw_shares = (equity * risk_pct/100 / 2) / abs(entry - stop)`
  - `cap_shares = max_bar_volume_pct * recent_bar_volume / entry_price`
  - return `floor(min(raw_shares, cap_shares))`
- Defensive: any invalid input (zero equity, zero R, NaN, non-finite, negative bar volume) returns `0` shares. Never raises.

### 1.2 `framework/risk.py`
`RiskManager` with four kill switches (per-strategy daily loss %, per-strategy drawdown %, consecutive losses, portfolio daily loss %).

- State persisted to `framework_state/risk_state.json` via the same per-PID tmp + atomic rename pattern from `wb_persistence.py` (Setup A / Setup B safe).
- `record_trade(strategy, pnl, equity_at_entry)` — single mutator. Updates daily P&L, peak, consecutive losses, and persists.
- `check_strategy_kill(strategy, equity)` — evaluates all three per-strategy switches; once tripped, stays tripped (sticky) and writes the trigger reason to disk for forensics.
- `check_portfolio_kill(equity)` — portfolio-wide aggregated loss.
- `reset_daily()` — clears all counters; also auto-rolls inside `record_trade` if calendar day changes.

### 1.3 `framework/attribution.py`
`StrategyAttribution`. Appends every closed trade as a JSON line to `framework_state/trade_log_<YYYY-MM-DD>.jsonl`.

Per-trade fields: `strategy_name`, `symbol`, `entry_time`, `exit_time`, `entry_price`, `exit_price`, `qty`, `side`, `exit_reason`, computed `pnl`, computed `r_multiple` (if `risk_per_share` provided), computed `hold_seconds`.

Aggregator `strategy_attribution_summary(date)` returns per-strategy: trades, wins/losses, win_rate, gross_pnl, avg_pnl, avg_r, sharpe (annualized, n-1 std, sqrt(252)), max_drawdown (equity-curve), profit_factor (∞ on no-losses), total_hold_seconds. Includes `__portfolio__` row.

### 1.4 `framework/vix_regime.py`
`VIXRegime`. DEFAULT OFF per Manny 5/17.

- `enabled` defaults to env `WB_USE_VIX_REGIME` (default `"0"` → disabled).
- `current_regime(vix)` returns one of `low`, `optimal`, `high`, `extreme` using thresholds `<16`, `[16,28)`, `[28,40)`, `>=40`.
- `size_multiplier(vix, base_size)`: when disabled returns `base_size` unchanged (truly inert — no IO, no side effects). When enabled, scales by `{optimal: 1.0, low: 0.5, high: 0.75, extreme: 0.0}` and floors.
- `get_vix_value()`: returns `None` when disabled (no Databento import, no network). When enabled, attempts a Databento import check and returns `None` until Wave 4 wires a real feed.

---

## 2. Sample sizing calculations

```
eq=$  30000 ent=$5.00 stop=$4.75 bar_vol= 1,000,000 ->  600 sh  (raw HK, uncapped)
eq=$  30000 ent=$5.00 stop=$4.75 bar_vol=    15,000 ->  150 sh  (cap binds: directive sample)
eq=$ 150000 ent=$20.00 stop=$19.50 bar_vol= 500,000 -> 1250 sh  ($150K acct / $20 stock)
eq=$  30000 ent=$5.00 stop=$5.00 bar_vol= 1,000,000 ->    0 sh  (zero R → safe invalid)
eq=$      0 ent=$5.00 stop=$4.75 bar_vol= 1,000,000 ->    0 sh  (zero equity → safe invalid)
```

Half-Kelly on $30K @ 1% with $0.25 R = `(30000*0.01/2)/0.25 = 600 sh`. With a thin $15K bar dollar-volume, the 5% participation cap (`0.05 * 15000 / 5 = 150`) binds → 150 shares (matches directive acceptance).

Doubling risk to 2% doubles share count (1200 vs 600 on the uncapped case). Test `test_higher_risk_pct` enforces this.

---

## 3. Sample kill-switch sequence

Synthetic 3-trade losing sequence on a $10K account at `per_strategy_daily_loss_pct=3.0`:

```
ORB pnl=-100  cum=-100   killed=False
ORB pnl=-150  cum=-250   killed=False
ORB pnl=- 80  cum=-330   killed=True   reason="daily_loss_3.30%>=3.0%"
```

After a fresh `RiskManager(state_path=...)` reload (simulating bot restart), the persisted state survives: `daily_pnl=-330.0`, `killed=True`, `kill_reason="daily_loss_3.30%>=3.0%"`. The strategy stays halted for the session (sticky kill).

Other kill paths verified by unit tests:
- **Drawdown:** +$1000 then −$600 → peak $11K, current $10.4K → 5.45% DD trips the 5% switch.
- **Consecutive losses:** 3 losses with `consecutive_losses_kill=3` trips the switch; a win in between resets the counter.
- **Portfolio:** Strategy A −$300 + Strategy B −$300 = $600 = 6% of $10K → portfolio kill fires.

---

## 4. Sample multi-strategy attribution

Five synthetic trades across two strategies (ORB and VWAP). Computed values:

```
         ORB: trades=3 wins=2 gross=$ 60.00 avg_R= 1.00 sharpe=8.81 max_dd=$20.00 PF=4.00
        VWAP: trades=2 wins=1 gross=$ 40.00 avg_R= 0.50 sharpe=3.74 max_dd=$40.00 PF=2.00
__portfolio__: trades=5 wins=3 gross=$100.00 avg_R= 0.80 sharpe=6.41 max_dd=$40.00 PF=2.67
```

Manual cross-check:
- ORB P&Ls: +50, −20, +30 → gross 60 ✓. R-multiples: 2.5, −1.0, 1.5 → avg 1.0 ✓. Wins 2/3 = 0.667 ✓. Gross wins 80, gross losses 20 → PF 4.0 ✓.
- ORB Sharpe: mean=20, var=(900+1600+100)/2=1300, std≈36.06, mean/std≈0.555, ×√252≈8.81 ✓ (matches scipy reference `np.mean/np.std(ddof=1)*sqrt(252)`).
- Max drawdown: ORB equity curve 50 → 30 → 60. Peak=60, max trough below peak = 20 ✓.

Trade-log file format (JSON-Lines, one trade per line, atomic append):
```
framework_state/trade_log_2026-05-14.jsonl
```

---

## 5. VIX regime hook (default OFF)

```
VIX=  10.0  regime=low       enabled=False:base   enabled=True:0.5x
VIX=  20.0  regime=optimal   enabled=False:base   enabled=True:1.0x
VIX=  35.0  regime=high      enabled=False:base   enabled=True:0.75x
VIX=  60.0  regime=extreme   enabled=False:base   enabled=True:0.0x (no trade)
```

Verified inert when disabled:
- `size_multiplier(60.0, 1000) == 1000` (default-disabled).
- `get_vix_value() == None` (no network call when disabled).
- No Databento import at construction time.

Manny's decision (5/17): "Build hooks, default OFF, validate from backtest." Wave 3 robustness agent (K) will A/B test VIX-on vs VIX-off and recommend an explicit flip if backtest improves ≥10%.

---

## 6. Coverage table

| Module              | Test file              | Test cases | Result    |
| ------------------- | ---------------------- | ---------- | --------- |
| `sizing.py`         | `test_sizing.py`       | 14         | 14 / 14 PASS |
| `risk.py`           | `test_risk.py`         | 14         | 14 / 14 PASS |
| `attribution.py`    | `test_attribution.py`  | 9          | 9 / 9 PASS   |
| `vix_regime.py`     | `test_vix_regime.py`   | 32         | 32 / 32 PASS |
| **Agent E total**   |                        | **69**     | **69 / 69 PASS** |

Wider framework suite (including peer agents' work in `tests/framework/`): **138 passed** in 0.40s. No regressions introduced.

What's covered:
- **Sizing** — uncapped formula, cap binds, zero/negative/NaN inputs, infinite inputs, floor rounding, short side (stop > entry), risk-pct scaling, zero-cap blocks all.
- **Risk** — each of 3 per-strategy switches + portfolio switch fires correctly; counters reset on `reset_daily`; persistence survives reload; corrupt file starts fresh without crashing; per-PID tmp suffix verified (no leftover files); NaN P&L ignored; empty strategy name ignored; consecutive losses counter resets on a winner.
- **Attribution** — long/short P&L sign, R-multiple math, hold seconds, multi-strategy aggregation matches manual calc, Sharpe matches scipy reference formula, max drawdown on equity-curve sequence, profit factor = ∞ on no-losses, daily file separation across calendar days, invalid inputs return `None`.
- **VIX regime** — 12 boundary VIX values mapped to correct regime; size_multiplier inert when disabled even at VIX=60; env var default; explicit `enabled=False` overrides env=1; custom optimal range; no Databento import when disabled.

---

## 7. Files added (all new — no existing-code touch)

```
framework/sizing.py                      114 lines
framework/risk.py                        288 lines
framework/attribution.py                 309 lines
framework/vix_regime.py                  131 lines

tests/framework/test_sizing.py           102 lines
tests/framework/test_risk.py             167 lines
tests/framework/test_attribution.py      200 lines
tests/framework/test_vix_regime.py       139 lines
```

Plus a minor edit to `framework/__init__.py` to re-export the new symbols.

State directory: `framework_state/` is created on first persist (gitignored via existing patterns).

---

## 8. Wiring notes for downstream agents

- Agents F-I (Phase 1 strategies) instantiate `HalfKellySizer` from each YAML's `risk_per_trade_pct`. Default cap 5% per research §3.
- Agent J (portfolio backtest) wraps a single `RiskManager` across all strategies — its `record_trade` aggregates portfolio P&L automatically.
- Agent J also reads `StrategyAttribution.strategy_attribution_summary(date)` for the daily breakdown.
- Agent K (robustness) toggles `WB_USE_VIX_REGIME=1` to A/B-test the VIX overlay; no code change required.
- All four modules are import-only — they do **not** auto-instantiate or read state on import. The `framework/__init__.py` exports are pure class references.

---

## 9. What I did NOT change

Per directive §7 and the critical rule at the top of the brief:
- No edits to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`, `force_exit.py`, `tape_quality.py`, any engine code, scanners, or `.env`.
- No `framework_state/risk_state.json` committed (created on first write at runtime; matches `wb_persistence.txt` pattern).
- No squeeze migration; no live integration; VIX regime stays OFF.

Wave 1 acceptance for Agent E: complete.
