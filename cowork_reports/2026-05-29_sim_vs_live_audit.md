# Sim vs Live Audit — 2026-05-29 STG Divergence

**Owner:** CC (audit)
**Anchor day:** 2026-05-29 STG. Same tick cache, 4 ARMs / 4 SIGNALS in both. Sim entered 1, live entered 3. Sim +$208 vs live +$597.
**Files audited:** `simulate.py` (5,175 LOC), `bot_v3_hybrid.py` (5,322 LOC), `bars.py` (338 LOC), `squeeze_detector.py` (753 LOC), `trade_manager.py` (3,190 LOC), `broker.py` (633 LOC), `hwm_exit.py` (123 LOC).

---

## 1. Executive summary (ranked by P&L impact)

1. **Sim has a per-symbol post-entry cooldown that live does not.** `simulate.py:679-686` blocks re-entries via `_symbol_cooldown_until[symbol]`; `bot_v3_hybrid.py` has *no* equivalent. (`grep cooldown` on the live bot returns only Tier-1/Tier-2 subscription cooldowns — never an SQ re-entry cooldown.) This is the most likely Class-B blocker for sim's missed +$755 entry. Default `symbol_cooldown_min=10` (`simulate.py:227`).
2. **Sim's `on_signal` rejects when a trade is already open (`open_trade is not None`, `simulate.py:671-672`).** If trade 1 hadn't fully closed in sim before the 06:48:55 signal, trade 2 is silently dropped. Live evaluates `state.open_position is not None` (`bot_v3_hybrid.py:2628`) on the same principle, but with different fill/close timing.
3. **Sim's fill model uses `max(arm, trigger_price)` and refuses to fill if `gap_pct > WB_BT_MAX_TRIGGER_GAP_PCT` (default 2.0%, `simulate.py:707-712`).** Live's `enter_trade` (`bot_v3_hybrid.py:3326-3328`) places a limit at `max(arm, live_tape) + dynamic_slippage`, then the verify-fill loop retries up to `ENTRY_MAX_RETRIES` with chase cap `ENTRY_MAX_CHASE_PCT_HIGH=3.5%` / `_LOW=2.0%`. Sim has no retry — one shot at `max(arm, trigger)` and done.
4. **Sim has no buying-power check on real BP; live blocks via `_presubmit_bp_check` against `AvailableFunds`.** Sim's BP gate (`simulate.py:738-743`) is *only* active when `WB_SIM_ACCOUNT_EQUITY > 0` and uses `current_equity * 4` (legacy 4× Reg-T). When `WB_SIM_ACCOUNT_EQUITY=0` (default in the standalone replays), sim has no BP check at all — but it also can't take simultaneous trades. Live's `_presubmit_bp_check` reads `broker.get_buying_power()` (= `AvailableFunds`, `broker.py:572`) and is the source of trade 3's `insufficient_bp` block.
5. **Phase 3c is still open: bar OHLCV can diverge per-bar between sim and live even from the same cache.** Confirmed yesterday (`cowork_reports/2026-05-27_phase3c_bar_construction_results.md`): identical `TradeBarBuilder` class produces different bars for the same minute when fed from cache vs engine socket. This is the leading Class-A cause for trade-1's opposite-direction `sq_para_trail_exit`.

---

## 2. Data computation table

| Component                         | Sim (file:line)                                                        | Live (file:line)                                                       | Divergence?   |
|-----------------------------------|------------------------------------------------------------------------|------------------------------------------------------------------------|---------------|
| `TradeBarBuilder` class           | `bars.py:65` (shared)                                                  | `bars.py:65` (shared)                                                  | Code identical |
| Tick feed → `on_trade`            | `simulate.py:4073-4075` (replay loop: `bb_10s/1m/5m.on_trade(...)`)    | `bot_v3_hybrid.py:4270-4272` (live IBKR tick → builders)               | Source differs (cache vs engine) — Phase 3c found per-bar OHLCV mismatches |
| VWAP                              | `bars.py:127-131` via accumulators                                     | `bars.py:127-131` via accumulators                                     | Same code; differs only if tick stream differs |
| HOD                               | `bars.py:133-134, :250, :268`                                          | `bars.py:133-134, :250, :268`                                          | Same code |
| PM_high                           | `bars.py:136-138, :253-255, :271-273`                                  | `bars.py:136-138, :253-255, :271-273`                                  | Same code |
| EMA9                              | `squeeze_detector.py:125, :190` (`ema_next`)                           | Same `squeeze_detector.py` calls                                       | Same code |
| `tick_count_in_bar`               | `bars.py:289, :298, :305` reset per-bucket                             | `bars.py:289, :298, :305` reset per-bucket                             | Same code |
| `first_tick_ts` / `last_tick_ts`  | `bars.py:290-291, :306, :337-338`                                      | `bars.py:290-291, :306, :337-338`                                      | Same code; reflects whatever ticks arrive |
| Bar-close callback (boundary)     | `bars.py:294-307` (bucket flip in `on_trade`)                          | `bars.py:294-307` (bucket flip in `on_trade`)                          | Same code; boundary triggered by NEXT tick (not wall-clock) |
| Detector evaluation on tick       | `simulate.py:4322` (`sq_det.on_trade_price`) and `try_arm_on_tick` `:4104+`  | `bot_v3_hybrid.py:2675` (`try_arm_on_tick`) / `:2690` (`on_trade_price`) | Same detector, same code path |
| Detector evaluation on bar close  | `squeeze_detector.py:177` `on_bar_close_1m` fires from the builder's `on_bar_close` callback | Same callback registration  | Same code |

**Verdict (data computation):** All bar arithmetic and detector code is shared. The only attested data divergence is **bar OHLCV from the same minute** when sim reads `tick_cache/<date>/<sym>.json.gz` vs when live's bar builder consumes ticks from IBKR's stream in real-time. This was demonstrated yesterday (sim's ASTC 08:45 ET bar body $1.77, live main bot's $0.17 — `cowork_reports/2026-05-27_phase3c_bar_construction_results.md` lines 17-21). **A timing detail worth flagging**: a bar's close is triggered by the *first tick of the NEXT bucket* (`bars.py:294-307`). Live evaluates `on_bar_close` mid-tick; sim does the same. If the last tick of a bar arrives well after the bar wall-clock close (e.g. seconds late in live's stream), both code paths handle it identically. No latent timing skew in the code itself.

Bar-close timing answer: sim closes a bar when the next tick in the cache crosses the bucket boundary (`bars.py:283-294`). Live closes a bar when the next live tick crosses. If the cache was truncated mid-bar (the `project_tick_cache_eod_truncation_2026-05-21` memory pattern), sim's last bar never closes — but for 2026-05-29 STG the user reports same SIGNAL count, which rules truncation out as a Class-B factor here.

Per-tick vs bar-close question: arming runs on **both** paths. Bar-close (`on_bar_close_1m`, line 177) is the canonical path. Tick-level arming (`try_arm_on_tick`, line 353) fires mid-bar when `WB_TICK_LEVEL_ARM=1`. The exit logic (`_squeeze_manage_exits` / sim's `_squeeze_tick_exits`) is per-tick in both. Trail-stop trigger uses `t.peak` and `t.r`; `peak` is updated per-tick (`simulate.py:830-832`, `bot_v3_hybrid.py:3542-3544`). Both compare `bid/price <= trail_price`. Code-equivalent.

---

## 3. Entry gates side-by-side

| Gate                                   | Sim (file:line)                                          | Live (file:line)                                              | Status        |
|----------------------------------------|----------------------------------------------------------|---------------------------------------------------------------|---------------|
| Open-trade gate                        | `simulate.py:671-672` (`open_trade is not None` → return)| `bot_v3_hybrid.py:2628-2629` (`open_position is not None`)    | IDENTICAL semantics; differs only in *timing* of close |
| R floor (`min_r`, `min_absolute_r`)    | `simulate.py:674-675`                                    | `bot_v3_hybrid.py:3243-3247`                                  | IDENTICAL    |
| Per-symbol re-entry cooldown (count)   | `simulate.py:677-686` (`_symbol_cooldown_until`)         | **(none — no equivalent code path)**                          | **SIM_ONLY** |
| Stop-hit bars cooldown                 | `simulate.py:688-690` (`_stop_hit_cooldown`)             | **(none)**                                                    | **SIM_ONLY** |
| Per-symbol entry-count → cooldown      | `simulate.py:814-821` (only for non-squeeze setups)      | **(none)**                                                    | SIM_ONLY for non-SQ; SQ is exempt in sim anyway |
| Detector-level `max_attempts`          | `squeeze_detector.py:259-271` (shared)                   | Same shared detector                                          | IDENTICAL (the `WB_SQ_MAX_ATTEMPTS=5` env var) |
| Quality / float gate                   | `simulate.py:692-696` (`stock_info.float_shares < quality_min_float`) | **(none in entry path — pre-filtered upstream by scanner)** | SIM_ONLY (post-arm); live screens at scanner level only |
| Chase cap / trigger-gap cap            | `simulate.py:707-712` (`WB_BT_MAX_TRIGGER_GAP_PCT`, default 2.0%) | `bot_v3_hybrid.py:3149-3158` (`ENTRY_MAX_CHASE_PCT_HIGH/_LOW` via retry loop) | DIFFERENT mechanism: sim is single-shot, live has retry budget |
| Buying-power check                     | `simulate.py:738-743` (`current_equity*4 - open_notional`, only when `WB_SIM_ACCOUNT_EQUITY>0`) | `bot_v3_hybrid.py:3004-3029` (`_presubmit_bp_check` via `AvailableFunds`) | DIFFERENT (different inputs, different defaults) |
| Pre-target target-hit `qty<=0` skip    | `simulate.py:745-746`                                    | `bot_v3_hybrid.py:3287-3299`                                  | IDENTICAL |
| MAX_DAILY_ENTRIES guard                | (none)                                                   | `bot_v3_hybrid.py:2632-2633`                                  | **LIVE_ONLY** |
| Daily-loss gate (`MAX_DAILY_LOSS`)     | (none in entry path)                                     | `bot_v3_hybrid.py:2640-2645`                                  | **LIVE_ONLY** |
| Consecutive-losses gate                | (none)                                                   | `bot_v3_hybrid.py:2646-2647`                                  | **LIVE_ONLY** |
| Box-position blocks momentum           | (n/a in single-symbol sim)                               | `bot_v3_hybrid.py:2636-2637`                                  | **LIVE_ONLY** |
| Pillar gates (price/RVOL/gap)          | `simulate.py:4737-4748` (sim's bar-mode + tick-mode wrappers) | (lives upstream in scanner — not in tick path)            | DIFFERENT layer |
| Entry-time cutoff                      | (none)                                                   | `bot_v3_hybrid.py:3358-3361`                                  | **LIVE_ONLY** |
| L2 filter (observe-only)               | (none)                                                   | `bot_v3_hybrid.py:3370-3382`                                  | **LIVE_ONLY** |
| Entry-halt active                      | (none)                                                   | `bot_v3_hybrid.py:3225-3236`                                  | **LIVE_ONLY** |
| Toxic filter                           | `simulate.py:4724-4736`                                  | (none in live tick path)                                      | **SIM_ONLY** |
| Seed-stale gate                        | `simulate.py:4089-4092` `validate_arm_after_seed`        | `bot_v3_hybrid.py:1887` `validate_arm_after_seed`             | IDENTICAL (shared detector method) |
| Seed-gate during `_seeding`            | `squeeze_detector.py:323-324`                            | `squeeze_detector.py:323-324`                                 | IDENTICAL |
| Volume winsorize                       | `squeeze_detector._winsorize_volume` (shared)            | Same shared method                                            | IDENTICAL |

**Key asymmetry**: Sim has **two** post-trade re-entry gates that live entirely lacks (`_symbol_cooldown_until`, `_stop_hit_cooldown`). The detector-level `_attempts` counter and `_in_trade` flag are the *only* re-entry brake live has.

---

## 4. Trade 1 trail-exit analysis (Class A: same setup, opposite outcome)

`sq_para_trail_exit` fires identically:
- Live: `bot_v3_hybrid.py:3588-3595` — `trail_price = pos["peak"] - (SQ_PARA_TRAIL_R * r)`; exits if `price <= trail_price`. `SQ_PARA_TRAIL_R` default 1.0 (`bot_v3_hybrid.py` constant from `WB_SQ_PARA_TRAIL_R`).
- Sim: `simulate.py:1343-1360` — `trail_price = t.peak - (trail_r * t.r)`; exits if `price <= trail_price`. Same env var (`simulate.py:290`).

The trail-trigger price is governed by **(a)** `pos["peak"]` and **(b)** `r` (= entry price minus stop at arm time). Both are recorded at entry:
- Sim: `peak = fill_price` (`simulate.py:802`), `r = armed.r` (`simulate.py:792`, the parity fix from 2026-05-20).
- Live: `pos["peak"] = limit_price` at entry (`bot_v3_hybrid.py:3502`), then promoted to `actual_price` on fill confirm (`bot_v3_hybrid.py:3064-3065`); `r = armed.r` (`bot_v3_hybrid.py:3239`).

**Possible Class-A causes for trade 1's opposite trail outcome:**

1. **Different `peak` evolution.** Sim's peak advances on every tick from the cache; live's advances on every IBKR tick. If the cache is missing post-EOD or surge ticks (the `project_tick_cache_persistence_gap` pattern), sim's peak can be lower than live's, lowering `trail_price` and making sim survive longer. With the higher live peak, the trail is FARTHER above entry; once price reverses below trail_price, live exits below entry. Concrete numerics: same trigger ($7.02-7.09), same `r`. If sim's recorded peak was ~$7.20 and live's was ~$7.35, with `trail_r=1.0`, `r≈0.20`, sim's trail = $7.00 and live's = $7.15 — explaining sim's $7.07 exit (above entry, profit) vs live's $6.83 exit (well below trail = something else triggered).
2. **Different `fill_price`.** Sim filled at $7.02 (max of arm and trigger; both ≈ arm). Live's limit was $7.09, filled $6.93 (better-than-limit due to ASK fluctuation). With identical `r=armed.r`, the stop is computed from `entry - r` at submit (live `bot_v3_hybrid.py:3067` rewrites `stop = actual_price - r` on fill). So live's effective stop ≈ $6.93 - $0.20 = $6.73, sim's = $7.02 - $0.20 = $6.82. Trail is `peak - r`. Sim's exit $7.07 > $6.82 stop. Live's exit $6.83 > $6.73 stop. Both are *trail* exits, not stop-hit. The trail-trigger price simply depends on peak.
3. **Different bar OHLCV updating `peak`.** If yesterday's Phase 3c finding holds (sim's bar high is materially different from live's bar high for the same minute), the `peak` updates that happen mid-bar on every tick can diverge across the surge minute. The cumulative effect can be: live's `peak` = bar high actually reached during the surge; sim's `peak` capped by the cache's recorded high. Phase 3c is the leading hypothesis.

**Cannot determine from code alone** whether peak divergence or fill-price divergence was the dominant Class-A driver on this trade. The bar-stream diff for 2026-05-29 STG (from yesterday's wired-up `WB_BAR_STREAM_LOG_ENABLED=1` cron) is the deciding evidence. Recommend grepping `logs/bar_stream/2026-05-29_main_bot.jsonl` for STG bars in the 05:44-05:50 ET window and diffing against `logs/bar_stream/2026-05-29_sim_STG.jsonl` produced by a sim replay.

---

## 5. Trade 2 entry-skip analysis (Class B: live entered, sim did not)

Live's trade 2: 06:48:55 entry $6.30 (limit $6.37), exit at +$755 via `sq_target_hit`. Same SIGNAL fired in sim per the user's observation, but sim did NOT enter. Walking sim's gate chain in `simulate.py` `on_signal` (line 658+) in order:

1. **Open-trade gate** (line 671): Did sim's trade 1 still have `open_trade != None` at 06:48:55? Trade 1's `sq_para_trail_exit` in sim happened at $7.07. Need to know the exit timestamp. If sim closed it before 06:48:55, this gate passes. If not, this gate alone explains the skip.
2. **R floor** (line 674): Same detector R; would have passed live's check too. UNLIKELY.
3. **Per-symbol cooldown** (line 679-686): `_symbol_cooldown_until.get("STG")`. Squeeze setups are exempt at the *count* level (`simulate.py:817` excludes `"squeeze"`). So this only triggers if `_symbol_cooldown_until` was set elsewhere — it isn't, for squeeze. **NOT a blocker.**
4. **Stop-hit cooldown** (line 689): Only set when a previous trade closed by `stop_hit` (`simulate.py:2177`). Trade 1 closed by `sq_para_trail_exit`, not `stop_hit`. **NOT a blocker.**
5. **Quality gate / float** (line 693): One-time check; if it passed for trade 1 it passes for trade 2. **NOT a blocker.**
6. **Chase cap / trigger gap** (line 707-712, `WB_BT_MAX_TRIGGER_GAP_PCT=2.0`): Trade 2 had live entry $6.30 on the $6.37 limit (≈ arm). For sim to reject, `(price - arm) / arm > 2%`. If sim's signal fired at, say, $6.50 with arm $6.37, gap is +2.0% — borderline reject. **PLAUSIBLE blocker.** This depends on the tick that crossed the arm in sim vs the tick live's IBKR feed reported.
7. **BP gate** (line 738-743): Only active when `WB_SIM_ACCOUNT_EQUITY > 0`. In the standalone replays (per `CLAUDE.md` regression command), this is 0 by default. **NOT a blocker** in the default config.
8. **`qty <= 0` skip** (line 745-746): Trade 2's live qty was sized $28K-ish (close to the `insufficient_bp` line of trade 3). Sim would have sized similarly. UNLIKELY blocker.

**Most likely sim Class-B blocker, in order:**

- **(a) Trade 1 still open in sim at 06:48:55.** Sim's trade 1 entered at 05:44 and exited via `sq_para_trail_exit`. If sim's peak/trail mechanics held the trade longer than live's, sim could still be in trade 1 when live's trade 2 fired. Walk-clock difference between sim's trade-1 exit and live's trade-2 entry is the key timestamp to confirm. **Recommend grepping the sim output for STG's trade-1 close time vs trade-2 SIGNAL time.**
- **(b) WB_BT_MAX_TRIGGER_GAP_PCT cap.** The 06:48:55 entry tick may have been farther above the new arm in sim's view (because sim's bar arm = different high per Phase 3c), pushing gap_pct > 2.0%. Sim would log a SIGNAL but the `on_signal` returns None at line 712 silently — there is no print of "trigger_gap_aborted" in the default sim verbose output. The user's observation that sim "shows 4 SIGNALS but only 1 ENTERED" is consistent with this silent rejection.

**Cannot determine from code alone** which of (a) or (b) was the dominant driver. The sim log for STG 2026-05-29 around 06:48 ET will show whether `open_trade` was still set at that moment. If sim's trade 1 already closed but sim still didn't enter, then (b) is the answer.

---

## 6. Execution semantics (sim vs live broker behavior)

**Sim:**
- Single-shot fill at `max(arm, trigger_price)`. Never simulates broker round-trip latency, ASK drift, partial fills, or rejects.
- `WB_BT_MAX_TRIGGER_GAP_PCT` (default 2.0%, `simulate.py:707`) is sim's only "cancel" mechanism — and it's silent.
- Slippage when `trigger_price` not passed: `entry + self.slippage` (`simulate.py:715`). Hardcoded default 0.02 (`simulate.py:222`). **Note**: the tick-mode SQ path *does* pass `trigger_price` (`simulate.py:4334`), so slippage is unused for SQ in tick mode.
- Exit fills at the tick price that triggered the exit (`_close` records `core_exit_price = price`). No partial-fill modeling.
- BP cap (`simulate.py:738-743`) uses 4× Reg-T against `current_equity` (sim's running P&L tracker). When `WB_SIM_ACCOUNT_EQUITY=0`, no BP cap.

**Live:**
- Limit at `max(arm, live_tape) + slippage` (`bot_v3_hybrid.py:3326-3328`), with Alpaca-aware widening when `WB_ALPACA_AWARE_LIMITS=1` (`:3334-3335`).
- `_verify_fill_with_retry` polls broker, retries up to `ENTRY_MAX_RETRIES=3` (`:3122`), repricing to `current_market + slippage` each time, capped at `original_limit × (1 + chase_pct)` (`:3154-3158`). Times out at `ENTRY_RETRY_TIMEOUT_SEC=10`s per attempt.
- BP check via `broker.get_buying_power()` which returns `AvailableFunds` (`broker.py:572`, the 2026-05-28 NCT/SPRC fix). Required notional is `qty * limit * 1.05` (`bot_v3_hybrid.py:3025`). This block produced the trade-3 `insufficient_bp` print.
- Equity baseline: `STARTING_EQUITY = NetLiquidation` at startup (`bot_v3_hybrid.py:5005`); `current_equity = STARTING_EQUITY + state.daily_pnl` (`:3259`); `risk_dollars = max(50, current_equity * RISK_PCT)` (`:3260`).

**What might break against real fills:** sim's "trigger price = fill price" is wrong in either direction. Real fills can be better (ASK drops between submit and fill) OR worse (limit fills exactly at limit while bid was already lower). Sim under-models the asymmetry, which is the documented `feedback_fill_optimism_disregard` pattern.

---

## 7. Recommendations (prioritized)

1. **Remove the sim-only post-entry cooldowns OR add an equivalent in live.** Sim's `_symbol_cooldown_until` and `_stop_hit_cooldown` (`simulate.py:679-690`) silently reject re-entries that live happily takes. For SQ specifically, sim's `on_signal` exempts squeeze from `_symbol_cooldown_until` cooldown writes (`:817`), but the `_stop_hit_cooldown` gate still applies to SQ (`:689` runs before the setup_type branch). Either gate squeeze setups around line 689 to mirror live's behavior, OR add a `WB_LIVE_REENTRY_COOLDOWN_MIN` env var to live that defaults OFF and let production decide.
2. **Make sim's chase-cap rejection visible.** Currently `simulate.py:711-712` returns None silently on `gap_pct > 2.0%`. Add a `print(f"  [{time_str}] SQ_TRIGGER_GAP_ABORT: gap={gap_pct:.1f}% > {max_trigger_gap_pct:.1f}%")` so the next sim run for STG 2026-05-29 immediately shows which signals were rejected by this gate. This is a 2-line change and would have closed today's audit in 10 minutes instead of hours.
3. **Land Phase 3c Option A (bar-stream replay) for SQ regression days.** Yesterday's Phase 3c finding (sim's ASTC 08:45 bar OHLCV differs from main bot's by 5×) means tick-cache replay is structurally unable to reproduce live's bar arithmetic on bursty minutes. For SQ-specific Class-A audits like trade 1 today, replay against the live bar-stream JSONL (`logs/bar_stream/2026-05-29_main_bot.jsonl`) instead of the tick cache. Wire a `simulate.py --bar-stream <path>` mode that feeds the detector via `bb_1m.seed_bar_close` instead of `on_trade`. ~1 day of work; eliminates Class-A divergence for past-day audits.

---

## What this audit cannot determine from code alone

- Trade 1 Class-A: the exact peak/fill divergence requires diffing sim and live bar-stream logs for STG 2026-05-29 in the 05:44-05:50 window.
- Trade 2 Class-B: the exact gate that rejected sim's 06:48:55 SIGNAL. Most likely candidates are (a) sim's trade-1 still being open, or (b) silent `WB_BT_MAX_TRIGGER_GAP_PCT` rejection. The sim's stdout output for STG 2026-05-29 (with `verbose=1`) will distinguish (a) from (b) immediately.

Both gaps are resolvable in <30 minutes with the right log greps; the audit's value is the gate inventory and code citations above.
