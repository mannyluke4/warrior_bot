# DIRECTIVE: Two Correctness Fixes Before Monday

**Date:** May 8, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — bug fixes only, no strategy tuning  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md`

---

## Scope (Strict)

This directive ships exactly **two correctness fixes** that surfaced in today's session. Strategy tuning waits until we have 5+ sessions of data, per Manny's plan. Anything outside these two scopes is out of scope for this directive.

In particular, do **not** in this PR:
- Touch trailing-stop logic
- Touch chop-gate thresholds
- Touch VWAP distance gating
- Touch R% requirements per score tier
- Touch the marketability-buffer slippage logic
- Add new tuning env vars beyond what's specified below

If a "while we're in here" temptation appears, write it down for the May 15-16 tuning review and move on.

---

## Fix 1: Silent Pyramid Trigger (BUG)

### Problem

Today's logs from `2026-05-08_subbot_alpaca.log` show two pyramid trigger events:

```
[15:03:55 ET] SST WB_PYRAMID: leg2_entry=4.0400 R=0.0499
[19:21:20 ET] ATRA WB_PYRAMID: leg2_entry=8.8400 R=0.1213
```

**Neither produced an actual Alpaca order.** The trigger logic fires inside the WaveBreakout detector / strategy code, prints a log line, but never calls `place_wave_breakout_entry()` for the second leg. CC verified by checking Alpaca's order history for both timestamps — no order was submitted.

This is dangerous in two ways:
- **Misleading signal:** logs look like a feature is active when it isn't
- **Latent risk:** if the missing wiring gets accidentally connected without thought, leg2 would have entered SST at $4.04 right before reversal (doubling that loss). The pyramid logic was designed but never properly tested in production.

### The Fix

**Disable the pyramid trigger event entirely.** Do NOT attempt to wire it up. Remove the noise from logs.

Specifically:

1. **Locate the pyramid trigger code path** in `bot_alpaca_subbot.py` (and `bot_v3_hybrid.py` if mirrored). The phrase to grep for is `WB_PYRAMID` or `pyramid_trigger` or similar.

2. **Add a hard-disable env var:**
   ```python
   PYRAMID_ENABLED = os.getenv("WB_WB_PYRAMID_ENABLED", "0") == "1"
   ```

3. **Wrap the pyramid detection logic in the env-var check.** When `WB_WB_PYRAMID_ENABLED=0` (the default and only-supported value for now), the detector must NOT:
   - Log `WB_PYRAMID` events
   - Compute `leg2_entry` or `R`
   - Call into any leg2 placement function (even a stub)

   The check should short-circuit at the entry point of pyramid-related logic.

4. **In `.env.example`, set the var explicitly off** with a comment explaining why:
   ```bash
   # Pyramid second-leg entries — DISABLED (logic exists but Alpaca order
   # placement wiring is missing). Enabling without wiring leg2 in
   # place_wave_breakout_entry() produces silent log noise. Will be
   # re-enabled after order placement is wired and tested.
   WB_WB_PYRAMID_ENABLED=0
   ```

5. **Do NOT remove the pyramid code itself** — only gate it. The code is the design we'll need when we wire leg2 properly. Just stop it from firing in production.

### Verification

After deploying:

1. Run the bot in paper for one full session (Monday)
2. `grep -c WB_PYRAMID logs/2026-05-XX_subbot_alpaca.log` should be **0**
3. No log noise about leg2 entries on any score-10 bypass winner

### Future

The Monday after the May 15 tuning review (i.e., week of May 18), we'll write a separate directive to **properly wire pyramid leg2 to Alpaca**. That directive will:
- Place an actual leg2 LIMIT BUY when the trigger fires
- Use the same fill verification, slippage handling, and notional-cap logic as leg1
- Be backtested against the existing wave_research data with pyramid enabled vs disabled
- Have its own paper validation period before live activation

For now, just silence it.

---

## Fix 2: Per-Position Notional Cap Tied to Equity (BUG)

### Problem

Today's TRAW rejection at 17:45 ET:

```
TRAW score=10, planned: entry $2.20, qty 20,381, notional $44,838
Alpaca response: code 40310000 — insufficient buying power
  Buying power available: $17,142.78
  Cost basis required: $45,857.25
  Gap: -$28,714
```

**Why was BP only $17K when account equity was $28,500?** ATRA was already open. ATRA notional consumed: 5,813 × $8.65 = **$50,283**. With 4× margin on $28,500 equity, total BP was ~$114K. After ATRA, only $64K was free. Subtract reserve and unrealized fluctuation → ~$17K available.

The current sizing logic uses a hard-coded `WB_WB_MAX_NOTIONAL=$50,000` per position. With $30K equity, that's **1.67× equity per position**. Math:
- 4× margin = $120K total BP on $30K equity
- $50K cap per position
- Therefore: at most 2 concurrent positions of $50K each, with $20K left over (not enough for a third $50K position)

Today's session had **5 score-10 bypass triggers** — only 3 fit. TRAW (the 4th) was rejected; CLNN (the 5th) didn't fill for unrelated reasons. **The bot is structurally too greedy on per-position size.**

### The Fix

Change the per-position notional cap from a fixed dollar amount to **min(equity × multiplier, hard floor)**.

1. **Add new env vars:**
   ```bash
   # Per-position notional cap — tied to current equity
   WB_WB_NOTIONAL_PER_POSITION_PCT=1.0    # max 1.0× equity per position
   WB_WB_NOTIONAL_FLOOR=10000              # min $10K notional regardless of equity
   WB_WB_MAX_NOTIONAL=50000                # hard ceiling regardless of equity
   ```

2. **Update the sizing logic in `compute_wb_position_size()`** (or wherever `MAX_NOTIONAL` is currently consulted). Replace:
   ```python
   max_notional = float(os.getenv("WB_WB_MAX_NOTIONAL", "50000"))
   ```
   With:
   ```python
   max_notional = min(
       float(os.getenv("WB_WB_MAX_NOTIONAL", "50000")),  # hard ceiling
       max(
           float(os.getenv("WB_WB_NOTIONAL_FLOOR", "10000")),  # min floor
           current_equity * float(os.getenv("WB_WB_NOTIONAL_PER_POSITION_PCT", "1.0"))
       )
   )
   ```

3. **Where does `current_equity` come from?** In `bot_alpaca_subbot.py`, the bot already polls Alpaca's `TradingClient.get_account()` for equity at startup and (presumably) periodically. If that value is cached on bot state (e.g., `state.account_equity` or similar), use it. If it's not cached, **add a single helper** that fetches it on-demand:
   ```python
   def get_current_equity(broker) -> float:
       """Returns current Alpaca account equity. Falls back to STARTING_EQUITY on failure."""
       try:
           account = broker.client.get_account()
           return float(account.equity)
       except Exception as e:
           log.warning(f"get_current_equity failed: {e}, using fallback")
           return float(os.getenv("STARTING_EQUITY", "30000"))
   ```

4. **Apply the cap consistently:**
   - At ARM time when sizing is computed
   - At the place-order step as a final sanity check
   - Log the active cap on every entry: `[WB] sizing: equity=$28500, cap=$28500, computed_notional=$28500, qty=12931`

### Why 1.0× equity (not 0.75× or 1.5×)?

Today's data:
- Equity ≈ $28,500
- 4× margin BP ≈ $114K
- 1.0× equity = $28,500 cap per position
- That allows ~3.5 concurrent positions of $28,500 each, fully utilizing margin
- Leaves headroom for slippage and partial fills
- Doesn't push the bot into using overnight margin (which would create T+1 settlement risk)

If `0.75×`: too conservative, only 2.6 concurrent positions fit. We had 5 triggers today; 2.6 is barely better than today's actual 2.

If `1.5×`: too aggressive, only 2.3 concurrent fit, no improvement.

**1.0× is the sweet spot for our $30K-$50K equity window.** It scales naturally as the account grows.

### Hard ceiling stays at $50K

Even when the account hits $100K+, individual position notional shouldn't exceed $50K. Reasons:
- Slippage math gets ugly above $50K on small-cap names ($3-$10 stocks with 50K-200K daily volume)
- Spread crossing on a $50K position is already 5-15 cents on these names
- $50K is a comfortable ceiling that lets us stay in liquidity-friendly territory

When the account is large enough that 1.0× equity > $50K, the hard ceiling kicks in.

### Verification

After deploying:

1. Add a startup log line: `[WB] notional cap: equity=$X, equity_cap=$Y, hard_ceiling=$Z, effective_cap=$W`
2. On every entry, log: `[WB] sizing: equity=$X, effective_cap=$Y, planned_notional=$Z`
3. On Monday, if 3+ score-bypass entries fire concurrently, verify all 3 fit within available BP

### Risk

The cap change is bounded: it can only make per-position size **smaller**, never larger. That means the worst case is "fewer winners by leaving capital on the table on small-cap moves" (acceptable), not "blow through margin and get a Reg-T call" (not acceptable).

---

## What NOT to Do (Repeat for Emphasis)

This is a **two-fix correctness PR**. Do NOT include:

- ❌ Trailing-stop tuning (#3, #4 in trade breakdown report)
- ❌ VWAP-bypass blocking (#1)
- ❌ Score-tier R% requirements (#2)
- ❌ Marketability buffer changes (#6)
- ❌ Entry timeout extension (#8)
- ❌ Liquidity prefilter (#9)
- ❌ Strategy tuning of any kind

Those are queued for the May 15-16 review **after we have 5 sessions of data**. Do not pre-tune.

---

## Files Touched

```
bot_alpaca_subbot.py             # Both fixes
bot_v3_hybrid.py                  # Mirror Fix 1 if pyramid logic is present (Fix 2 may already be there since main bot has IBKR sizing)
.env.example                      # New env vars + comments
cowork_reports/                   # Brief verification report after Monday session
  2026-05-XX_correctness_fixes_verification.md
```

---

## Acceptance Criteria

After Monday's session:

| # | Check | How to verify |
|---:|---|---|
| 1 | No `WB_PYRAMID` log lines anywhere in subbot or main bot logs | `grep -c WB_PYRAMID logs/2026-05-XX_*.log` returns 0 |
| 2 | Notional cap log line appears at every entry | `grep "sizing: equity=" logs/2026-05-XX_subbot_alpaca.log` shows one line per WB entry |
| 3 | Notional cap is correctly 1.0× equity (capped at $50K) | Cross-check the cap math against equity at trade time |
| 4 | If 3+ score-10 entries fire concurrently, all 3 should fit within BP (no insufficient_buying_power rejections) | Audit Alpaca's order history for any 40310000 errors during the session |
| 5 | No regressions to existing chop-gate behavior | Daily trade count, WB_ARMED count, and CHOP_REJECT count should be in line with recent days |

If criterion 4 doesn't get tested (because <3 score-10 bypasses fired), that's fine — we'll see it on a future busy day.

---

## Reversal Path

If something goes wrong:

```bash
# Disable both fixes by reverting env vars (if env-driven only):
WB_WB_PYRAMID_ENABLED=0   # already off, no rollback needed for fix 1
WB_WB_NOTIONAL_PER_POSITION_PCT=999  # effectively disables the cap

# OR git revert the commit if structural changes break things
git revert <commit-sha>
```

Both fixes are designed to be reversible without code changes.

---

*Two fixes. Both bugs. Ship Monday-ready. Strategy tuning waits for data.*
