"""Round-trip tests for session_state.py. No bot imports — pure state IO.

Run: python test_session_state.py
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone

import session_state as ss


# Redirect session dirs under a temp root for every run so we never touch
# the real session_state/ or tick_cache/ while testing.
def _patch_root(tmp_root: str) -> None:
    ss._ROOT = tmp_root


def _sample_open_trade(symbol: str = "FCUV") -> dict:
    return {
        "symbol": symbol,
        "setup_type": "squeeze",
        "entry_price": 8.47,
        "entry_time": "2026-04-15T13:27:14Z",
        "qty": 4000,
        "r": 0.14,
        "stop": 8.33,
        "target_r": 1.5,
        "target_price": 8.68,
        "peak": 8.61,
        "trail_mode": "pre_target",
        "partial_filled_at": None,
        "partial_filled_qty": 0,
        "bail_timer_start": "2026-04-15T13:27:14Z",
        "exit_mode": "signal",
        "order_id": "abc-123",
        "fill_confirmed": True,
        "score": 7.2,
        "is_parabolic": False,
        "stop_order_id": "xyz-456",
        "target_order_id": "xyz-789",
        "partial_target_order_id": None,
    }


def run():
    tmp = tempfile.mkdtemp(prefix="wb_session_test_")
    try:
        _patch_root(tmp)

        # 1. Marker round-trip + age
        assert not ss.marker_exists()
        ss.write_marker()
        assert ss.marker_exists()
        age = ss.marker_age_seconds()
        assert age is not None and age < 5
        print(f"✓ marker round-trip (age={age:.2f}s)")

        # 2. Watchlist round-trip
        wl = [{"symbol": "FCUV", "subscribed_at": "2026-04-15T13:00:00Z"},
              {"symbol": "ROLR", "subscribed_at": "2026-04-15T13:05:00Z"}]
        ss.write_watchlist(wl)
        assert ss.read_watchlist() == wl
        print("✓ watchlist round-trip")

        # 3. Risk round-trip + closed_trades cap
        big = [{"sym": f"T{i}", "pnl": i} for i in range(100)]
        ss.write_risk(1234.56, 12, 2, big)
        r = ss.read_risk()
        assert r["daily_pnl"] == 1234.56
        assert r["daily_trades"] == 12
        assert r["consecutive_losses"] == 2
        assert len(r["closed_trades"]) == ss.CLOSED_TRADES_CAP
        assert r["closed_trades"][0]["sym"] == f"T{100 - ss.CLOSED_TRADES_CAP}"
        assert r["closed_trades"][-1]["sym"] == "T99"
        print(f"✓ risk round-trip (cap={ss.CLOSED_TRADES_CAP}, kept last N)")

        # 4. Open trades round-trip + schema validation
        t1 = _sample_open_trade("FCUV")
        t2 = _sample_open_trade("ROLR")
        ss.write_open_trades([t1, t2])
        out = ss.read_open_trades()
        assert len(out) == 2 and out[0]["symbol"] == "FCUV"
        print("✓ open_trades round-trip")

        # 5. Schema validation rejects missing fields
        bad = _sample_open_trade()
        del bad["stop_order_id"]
        try:
            ss.write_open_trades([bad])
            raise AssertionError("expected ValueError on missing stop_order_id")
        except ValueError as e:
            assert "stop_order_id" in str(e)
        print("✓ schema rejects missing stop_order_id")

        # 6. Corrupt-file read returns defaults
        with open(ss._path("risk.json"), "w") as f:
            f.write("{not json")
        r = ss.read_risk()
        assert r["daily_pnl"] == 0.0 and r["daily_trades"] == 0
        print("✓ corrupt risk.json → defaults")

        # 7. Malformed open_trades entry filtered on read
        import json
        with open(ss._path("open_trades.json"), "w") as f:
            json.dump([t1, {"symbol": "BAD"}], f)  # second entry is malformed
        out = ss.read_open_trades()
        assert len(out) == 1 and out[0]["symbol"] == "FCUV"
        print("✓ malformed open_trades entries filtered on read")

        # 8. decide_boot_mode — cold when no marker
        # (wipe & re-patch to simulate fresh state)
        shutil.rmtree(tmp)
        tmp2 = tempfile.mkdtemp(prefix="wb_session_test_")
        _patch_root(tmp2)
        mode, reason = ss.decide_boot_mode()
        assert mode == "cold" and reason == "no_marker"
        print(f"✓ no marker → cold ({reason})")

        # 9. decide_boot_mode — --fresh flag
        ss.write_marker()
        mode, reason = ss.decide_boot_mode(fresh=True)
        assert mode == "cold" and reason == "fresh_flag"
        print(f"✓ --fresh → cold ({reason})")

        # 10. decide_boot_mode — empty-state fallback (marker only)
        # marker exists but no ticks, no risk, no watchlist
        mode, reason = ss.decide_boot_mode()
        assert mode == "cold" and reason == "empty_state"
        print(f"✓ marker only (no durable state) → cold ({reason})")

        # 11. decide_boot_mode — marker + watchlist → resume
        ss.write_watchlist([{"symbol": "FCUV", "subscribed_at": "x"}])
        mode, reason = ss.decide_boot_mode()
        assert mode == "resume" and reason == "marker_present"
        print(f"✓ marker + watchlist → resume ({reason})")

        # 12. decide_boot_mode — --scrub wipes and returns cold
        mode, reason = ss.decide_boot_mode(scrub=True)
        assert mode == "cold" and reason == "scrub_flag"
        assert not ss.marker_exists()
        assert ss.read_watchlist() == []
        print(f"✓ --scrub → cold + dirs wiped ({reason})")

        # 13. Atomic write: tmp file should not linger after success
        ss.write_marker()
        for name in os.listdir(ss.session_dir()):
            assert not name.endswith(".tmp") and ".tmp." not in name, \
                f"lingering tmp file: {name}"
        print("✓ atomic write leaves no tmp files")

        # Cleanup
        shutil.rmtree(tmp2, ignore_errors=True)

        print("\nALL TESTS PASSED")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


if __name__ == "__main__":
    run()
