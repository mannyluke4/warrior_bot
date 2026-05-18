# Stage A2 — Incident-Replay Regression Suite: Pre-Patch Results

**Date:** 2026-05-18
**Author:** CC (Thread 2, A2)
**Status:** Tests authored, pre-patch baseline captured. Awaiting Thread 4 patches → re-run as post-patch validation.
**Branch:** `v2-ibkr-migration`
**File:** `tests/regression/test_incident_replay.py` (7 tests, 511 lines)

---

## TL;DR

- **4 of 7 tests FAIL pre-patch in exactly the expected direction** — they capture the four production bugs the bundled deploy patches.
- **1 test PASSES pre-patch** — Test 2 confirms the already-shipped `broker.py` cache-on-failure patch (commit 27f54f8) survives the SBFM DNS-outage scenario.
- **2 tests SKIP** — VERO/ROLR control replays are skipped pending Thread 1's A1 regression inventory (the directive explicitly forbade hardcoding `+$34,479` until the inventory cross-checks). When `WB_REGRESSION_VERO_TARGET` / `WB_REGRESSION_ROLR_TARGET` env vars or literal values land, the skips lift.
- **Each FAIL emits a load-bearing error message** identifying the file:line that needs patching, so the Thread 4 author can read the test output and know exactly where to write.

---

## Run command

```bash
cd /Users/duffy/warrior_bot_v2
venv/bin/python -m pytest -v tests/regression/test_incident_replay.py
```

Wall-clock: ~0.6s. No external network, no IBKR connection, no live Alpaca calls.

---

## Per-test verdicts

### Test 1 — `test_sbfm_qty0_skip_on_bp_failure` — FAIL pre-patch (as designed)

**Setup:** real `AlpacaBroker` instance with a fake alpaca-py client whose `get_account()` raises `RuntimeError("Failed to resolve 'api.alpaca.markets'")` — simulates the 2026-05-18 07:19 ET DNS outage. SBFM-shaped `ArmedTrade` (entry $2.02, stop $1.92, R=$0.10, size_mult=0.5 for [PROBE=50%]). `enter_trade()` invoked end-to-end with mocked `state.broker.submit_limit`.

**Pre-patch observed:**
```
⚠️ BP_FETCH_FAIL: RuntimeError: Failed to resolve 'api.alpaca.markets' ... — using last_known_bp=$0.00 (age=-1s)
  Sizing: equity=$29,687 risk=$1,039 qty=0 notional=$0 (BP 50% of $0 = max $0)
🟩 ENTRY: SBFM qty=1 limit=$2.09 (slip=$0.070) stop=$1.9200 R=$0.1000 score=5.2 type=squeeze
  BROKER ORDER: <MagicMock ...> BUY 1 SBFM @ $2.09
```

Assertion fails on `submit_limit.call_count == 0` — it was called once with `qty=1`. This is the SBFM bug reproduced exactly. The `max(1, …)` floor at `bot_v3_hybrid.py:3048` rescues qty=0 → qty=1.

**Post-patch expectation:** remove the `max(1, …)` floor → the `if qty <= 0` block at 3050 catches qty=0 → return → no order submitted → assertion passes.

---

### Test 2 — `test_sbfm_uses_cached_bp_when_fetch_fails` — PASS pre-patch (already-shipped patch)

**Setup:** same broker shape as Test 1, but `_last_known_bp = 59374.0` and `_last_known_bp_ts = time.time() - 30` (primed cache, 30s old). `WB_RISK_PCT=0.025` pinned to match the directive's stated rationale.

**Pre-patch observed:**
```
⚠️ BP_FETCH_FAIL: RuntimeError: ... — using last_known_bp=$59,374.00 (age=31s)
  Sizing: equity=$29,687 risk=$742 qty=7421 notional=$14,990 (BP 50% of $59,374 = max $29,687)
🟩 ENTRY: SBFM qty=3710 limit=$2.09 ... type=squeeze
  BROKER ORDER: test-order-id BUY 3710 SBFM @ $2.09
```

`qty=3710` falls within the directive's `[3000, 4000]` band. The broker.py cache-on-failure patch (commit 27f54f8) is working as intended.

**Note:** I added `monkeypatch.setenv("WB_RISK_PCT", "0.025")` to pin the result. With the live `.env` setting (3.5%), qty would be ~5,195 — also a real trade, but outside the literal `[3000, 4000]` band the directive cited. The test docstring documents this choice.

**Post-patch expectation:** unchanged — this test is a load-bearing control, not a guard.

---

### Test 3 — `test_sle_2026_05_15_resume_boot_suppression` — FAIL pre-patch (as designed)

**Setup:** fresh `SqueezeDetector`. Hand-arm at `trigger=$5.02, stop=$4.90, R=$0.12, score=11.0` (matches the SLE 2026-05-15 16:17 ET cached arm). Call `begin_seed()` to set `_seeding=True`. Then invoke `on_trade_price(5.90)` — simulates the live ib_insync tick racing the seed-replay pipeline.

**Pre-patch observed:**
```
AssertionError: Pre-patch FAIL (expected): on_trade_price fired ENTRY SIGNAL during _seeding=True.
squeeze_detector.py:289 needs an `if self._seeding: return None` gate added before the trigger check.
Got msg='ENTRY SIGNAL @ 5.0200 (break 5.0200) stop=4.9000 R=0.1200 score=11.0 setup_type=squeeze ...'
```

Confirmed: today's `on_trade_price` only checks `_seed_just_ended` (line 295), not `_seeding`. Live tick at $5.90 fires ENTRY against an arm at $5.02 → chase-cap timeout → log spam → operator alarm. The bug repeats 6× the evening of 2026-05-15.

The test also exercises the second half of the fix (`validate_arm_after_seed` using live price): asserts `SQ_SEED_STALE_RESET` fires when the live $5.90 is passed in. This assertion passes **today** (the validator itself is correct; the call site at `bot_v3_hybrid.py:1866` is the patch surface — using `raw_ticks[-1]` instead of `state.last_tick_price[symbol]`). The test simulates the post-patch behavior by passing the live price directly to the validator and confirming it does the right thing. Thread 4 must mirror this at the call site.

A second loop simulates 6 more restart cycles (tape prices $5.85, $5.97, $6.09, $5.82, $5.88, $5.93) and asserts each one fails the same way pre-patch — confirming the bug is repeatable, not a one-off.

**Post-patch expectation:** `on_trade_price` returns `None` while `_seeding=True` → no ENTRY → arm survives → `validate_arm_after_seed` (after `end_seed()`) drops it via `SQ_SEED_STALE_RESET` → zero submitted orders for SLE 16:17 → 17:50 window.

---

### Test 4 — `test_lnks_2026_05_14_r_floor_rejection` — FAIL pre-patch (as designed)

**Setup:** `WB_MIN_ABSOLUTE_R=0.10` set; `bot_v3_hybrid` reloaded so module-level `MIN_ABSOLUTE_R` re-reads. LNKS-shaped armed: entry $2.20, stop $2.14, R=$0.06, score=12. Mocked broker with `get_buying_power()` returning $60K. `enter_trade("LNKS", armed, "squeeze")`.

**Pre-patch observed:**
```
AssertionError: Pre-patch FAIL (expected): bot_v3_hybrid.enter_trade currently only checks `r < MIN_R` (line 3014).
With WB_MIN_R=0.06 and R=$0.06, the trade is admitted. Need to add the `max(MIN_R, MIN_ABSOLUTE_R)` floor.
submit_limit was called 1× with args=[call('LNKS', 13636, 'BUY', 2.27)]. stdout:
  Sizing: equity=$29,687 risk=$1,039 qty=13636 notional=$29,999 (BP 50% of $60,000 = max $30,000)
🟩 ENTRY: LNKS qty=13636 limit=$2.27 (slip=$0.070) stop=$2.1400 R=$0.0600 score=12.0 type=squeeze
  BROKER ORDER: lnks-test BUY 13636 LNKS @ $2.27
```

Bug confirmed: R=$0.06 passes the existing `WB_MIN_R=0.06` floor (because `r < MIN_R` is strict-less-than), so the trade goes through. The R-floor patch needs `effective_floor = max(MIN_R, MIN_ABSOLUTE_R)` at line 3014.

**Post-patch expectation:** stdout contains `R_BELOW_FLOOR` (or equivalent — the test accepts any of `R_BELOW_FLOOR`, `r_below_floor`, `SUPPRESS ARM`, `abs_floor`, `MIN_ABSOLUTE_R`); `submit_limit` is never called.

---

### Test 5 — `test_runtime_broker_mismatch_assert` — FAIL pre-patch (as designed)

**Setup:** import `bot_v3_hybrid`; look for `_assert_broker_matches` callable. Pre-patch: function does not exist → `pytest.fail()` with a load-bearing message proposing the implementation shape.

**Pre-patch observed:**
```
Failed: Pre-patch FAIL (expected): bot_v3_hybrid has no `_assert_broker_matches()` function.
Thread 4 must add a boot-time runtime-broker-mismatch assert per DIRECTIVE §A2 Test 5.
Suggested shape: read WB_BROKER and WB_EXPECTED_BROKER; if both set and they differ,
print 'BROKER_MISMATCH: WB_BROKER=<x> WB_EXPECTED_BROKER=<y>' to stderr and sys.exit(1).
```

**Post-patch expectation:** Thread 4 adds `_assert_broker_matches()`. The test's PATH 2 then exercises it with `WB_BROKER=ibkr WB_EXPECTED_BROKER=alpaca` and confirms it raises `SystemExit`/`AssertionError`/`RuntimeError` with a non-zero exit code.

**Env-var design notes for Thread 4:** the test docstring proposes `WB_BROKER` (what the bot will use) and `WB_EXPECTED_BROKER` (what the operator expects, set by `daily_run_v3.sh:210` to lock the launcher's choice — the `.env`-vs-launcher drift from `2026-05-18_sbfm_qty1_incident.md §13.5`). The patch author may pick different env-var names; the test accepts either a callable `_assert_broker_matches` shape or a subprocess-observable exit. Failure mode: log `BROKER_MISMATCH: WB_BROKER=<x> WB_EXPECTED_BROKER=<y>` and `sys.exit(1)`.

---

### Test 6 — `test_vero_2026_01_16_control` — SKIP pre-patch (A1 deliverable pending)

**Status:** skipped with informative message:

> "VERO control target not yet validated by A1 regression inventory (cowork_reports/2026-05-18_regression_inventory.md). Set WB_REGRESSION_VERO_TARGET=<verified_pnl> to enable this test, or fill in the literal once Thread 1 lands its deliverable. CLAUDE.md currently states +$34,479 from 2026-04-08 X01 tuning."

Per directive: "Don't hardcode +$34,479 unless the inventory confirms it." When Thread 1 lands `cowork_reports/2026-05-18_regression_inventory.md`, Thread 5 should either (a) set `WB_REGRESSION_VERO_TARGET` in the test environment, or (b) edit the test to replace `pytest.skip` with the verified literal. A second `pytest.skip` notes that the actual replay harness (subprocess to `simulate.py`) is Thread 3's (A3) deliverable — A2 owns the assertion shape only.

---

### Test 7 — `test_rolr_2026_01_14_control` — SKIP pre-patch (same reason)

Mirror of Test 6 for ROLR 2026-01-14. `WB_REGRESSION_ROLR_TARGET` env var hook in place. CLAUDE.md target: +$54,654.

---

## Summary table

| # | Test | Pre-patch | Post-patch expectation | Patches required |
|---|------|-----------|------------------------|------------------|
| 1 | SBFM qty=0 skip | **FAIL** (qty=1 BROKER ORDER submitted) | PASS (no order) | qty=1 floor removal (`bot_v3_hybrid.py:3048`) |
| 2 | SBFM cached BP | **PASS** (qty=3,710 submitted) | PASS (unchanged) | none (already shipped, commit 27f54f8) |
| 3 | SLE resume-boot | **FAIL** (ENTRY SIGNAL fires during _seeding) | PASS (suppressed) | `_seeding` gate in `on_trade_price`; live-price call site in `seed_symbol_from_cache` |
| 4 | LNKS R-floor | **FAIL** (R=$0.06 trade submitted) | PASS (rejected) | `WB_MIN_ABSOLUTE_R` floor in `enter_trade` |
| 5 | Broker mismatch | **FAIL** (function does not exist) | PASS (exits non-zero on mismatch) | `_assert_broker_matches()` at boot |
| 6 | VERO control | **SKIP** (A1 pending) | TBD (will pass once target verified) | none expected — control |
| 7 | ROLR control | **SKIP** (A1 pending) | TBD (will pass once target verified) | none expected — control |

---

## Files modified

- `tests/regression/__init__.py` — created (empty, package marker)
- `tests/regression/test_incident_replay.py` — created, 511 lines, 7 tests

No production-code files modified. Thread 4 owns those edits in a separate worktree.

---

## What to do next (for Thread 4 / Thread 5)

1. **Thread 4 applies the four patches.** Each test's failure message identifies the file:line to patch.
2. **Thread 5 re-runs `venv/bin/python -m pytest -v tests/regression/test_incident_replay.py`.** Expected: 5 PASS, 2 SKIP (still pending A1).
3. **Thread 1 lands the regression inventory.** Once VERO/ROLR targets are validated, lift the skips on Tests 6/7 (either set the env vars before pytest or replace `pytest.skip` lines with literal values).
4. **If any post-patch test fails:** the failure message identifies what went wrong. Diagnose, don't paper over. Per directive §3: "Unexpected divergences halt the deploy."

---

## Caveats / things flagged for the audit trail

- **SBFM tick cache file is empty** (`tick_cache/2026-05-18/SBFM.json.gz` is 0 bytes — the bot zeroed it post-incident). The test does NOT depend on the tick cache; it constructs the armed signal directly from the log evidence (entry $2.02, stop $1.92, R=$0.10, size_mult=0.5). If a future test needs the actual tick replay, the cache will need to be rebuilt from `logs/2026-05-18_daily.log`.
- **WB_RISK_PCT pin in Test 2** — the directive's `[3000, 4000]` band only holds at 2.5% risk (the codebase default). Live `.env` sets 3.5%. Test docstring documents the choice. If Manny wants the test to match the live-env qty (~5,195), widen the band to `[3000, 6000]`.
- **`bot_v3_hybrid` module reload in Tests 2 and 4** — both tests rely on `importlib.reload(bot_v3_hybrid)` so that `monkeypatch.setenv` takes effect on module-level globals (`RISK_PCT`, `MIN_R`, `MIN_ABSOLUTE_R`). Test 5 also imports bot_v3_hybrid. The reload sequence runs cleanly with the existing test isolation (no cross-test leaks observed). Worth keeping an eye on if more tests start touching module globals.
- **Test 5 PATH 2 is partially unreachable today** — the `pytest.fail()` short-circuits before PATH 2 runs. Post-patch, PATH 2 (the real assertion that `_assert_broker_matches()` raises on mismatch) becomes the load-bearing check. Both paths are in the same function so the post-patch behavior emerges automatically.
- **No subprocess spin-up for Test 5** — initial design considered launching `python bot_v3_hybrid.py` as a subprocess to assert exit code. Rejected because (a) the bot has heavy boot-time dependencies (IBKR connect, scanner threads, daily_run_v3.sh state) that aren't easily isolated in a 0.6s test, (b) the test environment doesn't have a working IBKR Gateway. The in-process function shape is faster, more reliable, and gives Thread 4 the same coverage for the boot-time check.

---

## Reproducibility

Tests are idempotent and side-effect-free. No real broker connections. No tick-cache writes. No state-dir mutations. `monkeypatch` cleans up env vars after each test.

Run anytime:

```bash
cd /Users/duffy/warrior_bot_v2
venv/bin/python -m pytest -v tests/regression/test_incident_replay.py
```

Expected output today (pre-patch):

```
tests/regression/test_incident_replay.py::test_sbfm_qty0_skip_on_bp_failure FAILED
tests/regression/test_incident_replay.py::test_sbfm_uses_cached_bp_when_fetch_fails PASSED
tests/regression/test_incident_replay.py::test_sle_2026_05_15_resume_boot_suppression FAILED
tests/regression/test_incident_replay.py::test_lnks_2026_05_14_r_floor_rejection FAILED
tests/regression/test_incident_replay.py::test_runtime_broker_mismatch_assert FAILED
tests/regression/test_incident_replay.py::test_vero_2026_01_16_control SKIPPED
tests/regression/test_incident_replay.py::test_rolr_2026_01_14_control SKIPPED
============== 4 failed, 1 passed, 2 skipped ==============
```

Expected output post-Thread-4 (with all patches applied):

```
============== 5 passed, 2 skipped ==============
```

Expected output post-A1 + post-Thread-4 (full green):

```
============== 7 passed ==============
```

---

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
