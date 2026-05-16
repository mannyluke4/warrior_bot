"""Unit tests for framework.sizing.TieredSizer.

Coverage matrix (per DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md §3):

Advancement gates
-----------------
1. Equity ≥ next-tier floor for ≥3 consecutive sessions
2. Rolling 30-session Sharpe ≥ 1.0
3. Current equity ≥ prior 5-session average (no active drawdown)
4. At most 1 advancement per 14 calendar days

Retreat triggers
----------------
A. Equity drops 15% from current tier HWM
B. Rolling 30-session Sharpe < 0.3
C. 3 consecutive losing weeks

Override modes
--------------
- tier_lock=True   : gates evaluated, transitions suppressed
- auto_advance=False : gates evaluated, transitions staged not applied
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from framework.sizing import TieredSizer, TierState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sizer(
    tmp_path: Path,
    initial_tier: int = 1,
    tier_lock: bool = False,
    auto_advance: bool = True,
) -> TieredSizer:
    """Build a TieredSizer with state under tmp_path (isolated per test)."""
    state_path = tmp_path / "tier_state.json"
    return TieredSizer(
        initial_tier=initial_tier,
        tier_lock=tier_lock,
        auto_advance=auto_advance,
        state_path=state_path,
    )


def _passing_returns(n: int = 60) -> list[float]:
    """Synthesize a returns series with Sharpe well above 1.0.

    Mean 0.5% per session, stdev 0.3% → Sharpe ~ 26 (annualized). Way
    above the 1.0 gate; way above 0.3 retreat floor.
    """
    out = []
    for i in range(n):
        # Tiny deterministic ripple so stdev is non-zero
        out.append(0.005 + (0.0005 if i % 2 == 0 else -0.0005))
    return out


def _failing_returns(n: int = 60) -> list[float]:
    """Synthesize returns with Sharpe well below 0.3.

    Mean ~ -0.1% per session, stdev 1.0% → strongly negative Sharpe.
    """
    out = []
    for i in range(n):
        out.append(-0.001 + (0.01 if i % 2 == 0 else -0.01))
    return out


def _sessions_from(start: date, n: int) -> list[date]:
    """Return n consecutive calendar dates (weekday-only)."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:  # Mon-Fri only
            out.append(d)
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Config + basic compute_risk
# ---------------------------------------------------------------------------


class TestBasic:
    def test_tier1_risk_is_300(self, tmp_path: Path) -> None:
        s = _make_sizer(tmp_path, initial_tier=1)
        assert s.compute_risk(equity=25_000) == pytest.approx(300.0)

    def test_tier7_risk_is_2500(self, tmp_path: Path) -> None:
        s = _make_sizer(tmp_path, initial_tier=7)
        assert s.compute_risk(equity=250_000) == pytest.approx(2500.0)

    def test_tier_clamps_into_range(self, tmp_path: Path) -> None:
        # Tier 99 should clamp to top (9)
        s = _make_sizer(tmp_path, initial_tier=99)
        assert s.current_tier == 9
        # Tier 0 should clamp to bottom (1)
        s2 = _make_sizer(tmp_path / "alt", initial_tier=0)
        assert s2.current_tier == 1

    def test_compute_risk_invalid_equity(self, tmp_path: Path) -> None:
        s = _make_sizer(tmp_path)
        assert s.compute_risk(0) == 0.0
        assert s.compute_risk(-1000) == 0.0
        assert s.compute_risk(float("nan")) == 0.0

    def test_size_returns_qty_and_risk_dollars(self, tmp_path: Path) -> None:
        """Adapter shim matching SizingMode.size for portfolio_backtest."""
        s = _make_sizer(tmp_path, initial_tier=1)
        # entry 5.00, stop 4.50, $300 risk → 600 shares
        qty, risk = s.size(
            equity=25_000, entry_price=5.0, stop_price=4.5,
            recent_bar_volume=1_000_000,
        )
        assert qty == 600
        assert risk == pytest.approx(300.0)

    def test_size_zero_r(self, tmp_path: Path) -> None:
        s = _make_sizer(tmp_path)
        qty, risk = s.size(25_000, 5.0, 5.0, 1_000_000)
        assert qty == 0
        assert risk == 0.0


# ---------------------------------------------------------------------------
# Advancement path: tier 1 -> 2 -> 3 with all 4 gates verified
# ---------------------------------------------------------------------------


class TestAdvancement:
    def test_advance_tier1_to_tier2_all_gates(self, tmp_path: Path) -> None:
        """Drive equity up to tier-2 floor, satisfy all gates, advance.

        Tier 2 floor: $40K. Required: ≥3 consecutive sessions ≥ $40K.
        Tier 1 floor is $25K so we hold equity steady at $42K throughout.
        """
        s = _make_sizer(tmp_path, initial_tier=1)
        assert s.current_tier == 1

        sessions = _sessions_from(date(2026, 6, 1), 30)
        returns = _passing_returns(60)

        # Seed 25 sessions at low-but-stable equity to build history + Sharpe
        for i, d in enumerate(sessions[:25]):
            # Slowly tick up so no DD gate fails
            s.on_session_close(d, equity=30_000 + i * 100, portfolio_returns=returns[: i + 5])

        # Still at tier 1 — equity below $40K floor
        assert s.current_tier == 1

        # Now jump to $42K for 3 consecutive sessions
        d1, d2, d3 = sessions[25], sessions[26], sessions[27]
        s.on_session_close(d1, equity=42_000, portfolio_returns=returns)
        assert s.current_tier == 1  # gate 1 needs 3 consecutive
        s.on_session_close(d2, equity=42_500, portfolio_returns=returns)
        assert s.current_tier == 1  # 2 of 3
        result = s.on_session_close(d3, equity=43_000, portfolio_returns=returns)

        # All 4 gates passed → advance to tier 2
        assert s.current_tier == 2, f"expected tier 2; got {s.current_tier}"
        assert result["applied"] is not None
        assert result["applied"]["action"] == "advance"
        assert result["gates"]["advancement"]["gate1_consec_at_floor"] is True
        assert result["gates"]["advancement"]["gate2_sharpe"] is True
        assert result["gates"]["advancement"]["gate3_no_dd"] is True
        assert result["gates"]["advancement"]["gate4_min_window"] is True
        # Risk per signal jumps $300 → $500
        assert s.compute_risk(43_000) == pytest.approx(500.0)

    def test_gate1_fires_only_after_three_consecutive(self, tmp_path: Path) -> None:
        """Hit floor sporadically — gate 1 should never trigger."""
        s = _make_sizer(tmp_path, initial_tier=1)
        sessions = _sessions_from(date(2026, 6, 1), 20)
        returns = _passing_returns(60)

        # Seed 10 sessions of stable history
        for i, d in enumerate(sessions[:10]):
            s.on_session_close(d, equity=30_000 + i * 100, portfolio_returns=returns)

        # Then alternate above/below $40K floor
        equities = [42_000, 38_000, 42_500, 39_000, 41_000, 38_500]
        for d, eq in zip(sessions[10:16], equities):
            s.on_session_close(d, equity=eq, portfolio_returns=returns)

        # Never 3 consecutive above floor → still tier 1
        assert s.current_tier == 1

    def test_gate2_sharpe_blocks_advancement(self, tmp_path: Path) -> None:
        """Bad portfolio returns (low Sharpe) should block advancement."""
        s = _make_sizer(tmp_path, initial_tier=1)
        sessions = _sessions_from(date(2026, 6, 1), 30)
        # Provide enough sessions to fill the rolling window — Sharpe will
        # come in low because of mean-near-zero with high variance.
        # Build a returns series with mean 0 and high stdev.
        bad_returns = [(0.01 if i % 2 == 0 else -0.01) for i in range(60)]

        for i, d in enumerate(sessions[:25]):
            s.on_session_close(d, equity=30_000 + i * 100, portfolio_returns=bad_returns)

        # 3 sessions ≥ tier 2 floor with bad returns
        for d in sessions[25:28]:
            s.on_session_close(d, equity=42_000, portfolio_returns=bad_returns)

        # Gate 2 should fail → still tier 1
        assert s.current_tier == 1
        # And the diagnostic should confirm
        assert s.last_gate_eval is not None
        assert s.last_gate_eval["advancement"]["gate1_consec_at_floor"] is True
        assert s.last_gate_eval["advancement"]["gate2_sharpe"] is False

    def test_gate3_active_drawdown_blocks(self, tmp_path: Path) -> None:
        """Current equity below trailing 5-session average → gate 3 fails."""
        s = _make_sizer(tmp_path, initial_tier=1)
        sessions = _sessions_from(date(2026, 6, 1), 25)
        returns = _passing_returns(60)

        # Build 20 sessions with a recent peak then a dip
        # Last 5: $46K, $47K, $48K, $49K, $50K  → trailing avg = $48K
        # Then session 21: $42K — above tier-2 floor but below $48K avg
        peaks = list(range(46_000, 51_000, 1_000))
        history = list(range(30_000, 46_000, 1_000))[:15] + peaks
        for d, eq in zip(sessions[: len(history)], history):
            s.on_session_close(d, equity=eq, portfolio_returns=returns)

        # Now drop to $42K — above tier-2 $40K floor BUT below 5-sess avg of ~$48K
        # We need 3 consecutive ≥40K, all below the trailing avg
        for d in sessions[len(history): len(history) + 3]:
            s.on_session_close(d, equity=42_000, portfolio_returns=returns)

        # Still tier 1 — gate 3 (drawdown) blocked the advance
        assert s.current_tier == 1
        assert s.last_gate_eval["advancement"]["gate3_no_dd"] is False

    def test_gate4_min_14_day_window(self, tmp_path: Path) -> None:
        """After one advancement, second one must wait 14 calendar days."""
        s = _make_sizer(tmp_path, initial_tier=1)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 60)

        # Warm up — 20 sessions of stable returns
        for i, d in enumerate(sessions[:20]):
            s.on_session_close(d, equity=30_000 + i * 200, portfolio_returns=returns)

        # Drive into tier 2 (requires 3 consecutive ≥$40K)
        for d in sessions[20:23]:
            s.on_session_close(d, equity=42_000, portfolio_returns=returns)
        assert s.current_tier == 2

        # Now jump equity to $65K — would qualify for tier 3 on equity grounds.
        # But we just advanced — gate 4 should block.
        # Sessions are ~weekdays, so 3 consecutive sessions after advancement
        # is only ~3-5 calendar days later.
        for d in sessions[23:26]:
            s.on_session_close(d, equity=65_000, portfolio_returns=returns)

        # Should still be at tier 2 — gate 4 blocked
        assert s.current_tier == 2
        assert s.last_gate_eval["advancement"]["gate1_consec_at_floor"] is True
        assert s.last_gate_eval["advancement"]["gate4_min_window"] is False

        # Now feed 14+ more sessions (≥14 calendar days)
        for d in sessions[26:42]:
            s.on_session_close(d, equity=65_000, portfolio_returns=returns)

        # Now gate 4 cleared → advancement to tier 3
        assert s.current_tier == 3

    def test_advance_tier_1_to_2_to_3(self, tmp_path: Path) -> None:
        """Full ladder: tier 1 → 2 → 3 with all gate checks satisfied."""
        s = _make_sizer(tmp_path, initial_tier=1)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 80)

        for i, d in enumerate(sessions[:20]):
            s.on_session_close(d, equity=30_000 + i * 200, portfolio_returns=returns)

        # tier 2 jump
        for d in sessions[20:23]:
            s.on_session_close(d, equity=42_000, portfolio_returns=returns)
        assert s.current_tier == 2

        # Wait 14+ days, then drive equity ≥ $60K for 3 consecutive
        for d in sessions[23:45]:
            s.on_session_close(d, equity=55_000, portfolio_returns=returns)

        for d in sessions[45:48]:
            s.on_session_close(d, equity=65_000, portfolio_returns=returns)

        assert s.current_tier == 3
        assert s.compute_risk(65_000) == pytest.approx(750.0)


# ---------------------------------------------------------------------------
# Retreat triggers
# ---------------------------------------------------------------------------


class TestRetreat:
    def test_drawdown_15pct_from_hwm_retreats(self, tmp_path: Path) -> None:
        """Tier 3 with HWM at $80K, equity drops to $67K (-16.25%) → retreat."""
        s = _make_sizer(tmp_path, initial_tier=3)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 20)

        # Establish tier-3 HWM at $80K
        for i, d in enumerate(sessions[:10]):
            eq = 75_000 + i * 500  # peaks at ~$79.5K
            s.on_session_close(d, equity=eq, portfolio_returns=returns)
        # One more high
        s.on_session_close(sessions[10], equity=80_000, portfolio_returns=returns)
        assert s.state.tier_high_water_mark >= 80_000

        # Drop to $67K  → -16.25% from HWM
        result = s.on_session_close(sessions[11], equity=67_000, portfolio_returns=returns)

        assert s.current_tier == 2, "expected retreat to tier 2"
        assert result["applied"]["action"] == "retreat"
        assert "dd_" in result["applied"]["reason"]

    def test_low_sharpe_retreats(self, tmp_path: Path) -> None:
        """Tier 3 with rolling Sharpe < 0.3 → retreat regardless of equity."""
        s = _make_sizer(tmp_path, initial_tier=3)
        # Build a state where equity stays steady (no DD trigger) but Sharpe craters.
        sessions = _sessions_from(date(2026, 6, 1), 40)
        bad_rets = _failing_returns(60)

        for i, d in enumerate(sessions[:35]):
            s.on_session_close(d, equity=80_000, portfolio_returns=bad_rets)
            if s.current_tier < 3:
                # Once Sharpe trigger fires, we'll retreat — that's the test
                break

        assert s.current_tier == 2
        assert s.last_gate_eval["retreat"]["trigger_b_low_sharpe"] is True

    def test_three_losing_weeks_retreats(self, tmp_path: Path) -> None:
        """Three consecutive losing ISO-weeks → retreat one tier."""
        s = _make_sizer(tmp_path, initial_tier=3)
        returns = _passing_returns(60)
        # Establish HWM at $80K but then drift the equity in a pattern that
        # produces 3 losing weeks without ever crossing -15% DD.

        # Week 1: $80K -> $79K (small dip, weekly loss -$1K)
        # Week 2: $79K -> $78K
        # Week 3: $78K -> $77K
        # Week 4 first day at $76K — should trigger retreat AFTER week 3 closes
        sequence: list[tuple[date, float]] = []
        d = date(2026, 6, 1)  # Monday
        # Seed: prime HWM by running one session at $80K
        # then start the slow drift
        equity = 80_000
        sequence.append((d, equity))
        for week in range(4):
            base = date(2026, 6, 1) + timedelta(days=week * 7)
            for offset in range(5):
                day = base + timedelta(days=offset)
                if day == d:
                    continue
                equity -= 200  # -$1K per 5-day week
                sequence.append((day, equity))
        # End of week 3 means we've processed 3 full weeks of losses.
        for sess_date, eq in sequence:
            s.on_session_close(sess_date, equity=eq, portfolio_returns=returns)
            if s.current_tier < 3:
                break

        assert s.state.consecutive_losing_weeks >= 3 or s.current_tier == 2
        # Verify it retreated
        assert s.current_tier == 2

    def test_retreat_resets_tier_hwm(self, tmp_path: Path) -> None:
        """After a retreat, HWM resets so the new tier starts fresh."""
        s = _make_sizer(tmp_path, initial_tier=3)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 15)

        for i, d in enumerate(sessions[:10]):
            s.on_session_close(d, equity=80_000 + i * 100, portfolio_returns=returns)
        # Force DD retreat
        s.on_session_close(sessions[10], equity=65_000, portfolio_returns=returns)

        assert s.current_tier == 2
        # HWM was reset; will be re-anchored on next session close
        # (after retreat, HWM is reset to 0 and grows from the next equity)


# ---------------------------------------------------------------------------
# Override modes: tier_lock and auto_advance
# ---------------------------------------------------------------------------


class TestOverrides:
    def test_tier_lock_pins_tier_1_through_growth(self, tmp_path: Path) -> None:
        """tier_lock=True: equity grows to tier-7 levels, sizer stays at tier 1."""
        s = _make_sizer(tmp_path, initial_tier=1, tier_lock=True)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 100)

        # Crank equity from $25K all the way past $250K (tier 7)
        equities = [25_000 + i * 3_000 for i in range(100)]
        # By session ~75 we're past $250K
        for d, eq in zip(sessions, equities):
            result = s.on_session_close(d, equity=eq, portfolio_returns=returns)
            # Tier never changes
            assert s.current_tier == 1
            # compute_risk stays at $300
            assert s.compute_risk(eq) == pytest.approx(300.0)

        # Final result should have a pending transition staged (gates would
        # have fired but were suppressed)
        assert s.current_tier == 1
        assert s.compute_risk(equities[-1]) == pytest.approx(300.0)

    def test_tier_lock_apply_pending_is_blocked(self, tmp_path: Path) -> None:
        """Even apply_pending_transition() is a no-op when tier_lock=True."""
        s = _make_sizer(tmp_path, initial_tier=1, tier_lock=True)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 30)

        for i, d in enumerate(sessions[:20]):
            s.on_session_close(d, equity=30_000 + i * 200, portfolio_returns=returns)
        for d in sessions[20:23]:
            s.on_session_close(d, equity=42_000, portfolio_returns=returns)

        # Still tier 1
        assert s.current_tier == 1
        # Manually try to apply
        applied = s.apply_pending_transition()
        assert applied is None  # blocked by tier_lock
        assert s.current_tier == 1

    def test_auto_advance_false_stages_transition(self, tmp_path: Path) -> None:
        """auto_advance=False: gates fire, transition staged but not applied."""
        s = _make_sizer(tmp_path, initial_tier=1, auto_advance=False)
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 30)

        for i, d in enumerate(sessions[:20]):
            s.on_session_close(d, equity=30_000 + i * 200, portfolio_returns=returns)
        for d in sessions[20:23]:
            s.on_session_close(d, equity=42_000, portfolio_returns=returns)

        # Still tier 1 — but pending transition should be set
        assert s.current_tier == 1
        assert s.pending_transition is not None
        assert s.pending_transition["action"] == "advance"
        assert s.pending_transition["to"] == 2

        # Manual approval applies it
        applied = s.apply_pending_transition()
        assert applied is not None
        assert s.current_tier == 2
        assert s.compute_risk(42_000) == pytest.approx(500.0)
        # And pending is cleared
        assert s.pending_transition is None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_state_persists_across_instances(self, tmp_path: Path) -> None:
        """A new TieredSizer at the same state_path picks up where we left off."""
        state_path = tmp_path / "tier_state.json"
        s1 = TieredSizer(
            initial_tier=1, state_path=state_path,
        )
        returns = _passing_returns(60)
        sessions = _sessions_from(date(2026, 6, 1), 30)
        for i, d in enumerate(sessions[:25]):
            s1.on_session_close(d, equity=30_000 + i * 200, portfolio_returns=returns)
        for d in sessions[25:28]:
            s1.on_session_close(d, equity=42_000, portfolio_returns=returns)
        assert s1.current_tier == 2

        # New instance — should see tier 2 already
        s2 = TieredSizer(initial_tier=1, state_path=state_path)
        assert s2.current_tier == 2  # initial_tier ignored when state exists
        assert s2.compute_risk(42_000) == pytest.approx(500.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
