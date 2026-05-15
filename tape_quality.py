"""Dead-tape gate — Cowork directive 2026-05-15 (DIRECTIVE_WB_DEAD_TAPE_GATE.md).

Replaces the original 'absolute bar-volume floor' proposal with a smarter
per-stock detector: measure bar-emptiness rate over the prior 30-min
window of 1m bars. If most bars in the window have negligible volume,
the tape is dead — no pattern can be trusted, no entry should fire.

The ATRA 2026-05-15 13:21 ET misfire is the canonical case: avg bar vol
~1,090 sh, half the prior bars 0-200 shares. WB scoring's relative-
volume bounce ratio (4.33×) looked like a surge but was a single thin-
tape print.

Public API:
  is_dead_tape(bars_1m) -> (alive: bool, reason: str, telemetry: dict)
    bars_1m: list of dict-like bars with .volume or ["volume"] accessible.
    Returns (alive=True, "tape_check_disabled", {}) when env-disabled.

Position in gate stack: AFTER score floor + R% floor, BEFORE CG3 sub-gates.
"""
from __future__ import annotations

import os
from typing import Any, Optional

# Env-driven config (read once at import — wb-style)
ENABLED = os.environ.get("WB_DEAD_TAPE_GATE_ENABLED", "1") == "1"
LOOKBACK_MIN = int(os.environ.get("WB_DEAD_TAPE_LOOKBACK_MIN", "30"))
BAR_VOL_FLOOR = int(os.environ.get("WB_DEAD_TAPE_BAR_VOL_FLOOR", "500"))
MAX_DEAD_RATE = float(os.environ.get("WB_DEAD_TAPE_MAX_DEAD_RATE", "0.5"))
MIN_BARS = int(os.environ.get("WB_DEAD_TAPE_MIN_BARS", "20"))


def _bar_volume(bar: Any) -> int:
    """Best-effort volume access — supports dict bars (detector internal
    state) and namedtuple/Bar instances (raw)."""
    if hasattr(bar, "volume"):
        try:
            return int(bar.volume)
        except Exception:
            pass
    try:
        return int(bar["volume"])
    except Exception:
        return 0


def is_dead_tape(bars_1m: list) -> tuple[bool, str, dict]:
    """Returns (alive, reason, telemetry).

    `alive=True` → tape is OK to trade. `alive=False` → veto.

    The contract is intentionally inverted from is_dead_tape's name so
    callers can write `if not alive: return  # veto` like other gates.
    """
    if not ENABLED:
        return True, "tape_check_disabled", {"enabled": False}

    if not bars_1m:
        # Defensive: no bars at all = treat as dead (won't fire anyway
        # since detector wouldn't ARM on empty history)
        return False, "no_bars", {"n_bars": 0}

    lookback = bars_1m[-LOOKBACK_MIN:] if len(bars_1m) > LOOKBACK_MIN else list(bars_1m)
    n = len(lookback)
    if n < MIN_BARS:
        return False, f"insufficient_bars({n}<{MIN_BARS})", {
            "n_bars": n, "min_bars": MIN_BARS,
        }

    dead_bars = sum(1 for b in lookback if _bar_volume(b) < BAR_VOL_FLOOR)
    dead_rate = dead_bars / n

    if dead_rate > MAX_DEAD_RATE:
        return False, (
            f"dead_tape(dead_rate={dead_rate:.2f},"
            f"dead_bars={dead_bars}/{n},floor={BAR_VOL_FLOOR})"
        ), {
            "n_bars": n, "dead_bars": dead_bars, "dead_rate": dead_rate,
            "bar_vol_floor": BAR_VOL_FLOOR, "max_dead_rate": MAX_DEAD_RATE,
        }

    return True, f"tape_alive(dead_rate={dead_rate:.2f})", {
        "n_bars": n, "dead_bars": dead_bars, "dead_rate": dead_rate,
        "bar_vol_floor": BAR_VOL_FLOOR, "max_dead_rate": MAX_DEAD_RATE,
    }


def env_summary() -> str:
    return (
        f"dead_tape: enabled={ENABLED} lookback={LOOKBACK_MIN}m "
        f"floor={BAR_VOL_FLOOR}sh max_dead_rate={MAX_DEAD_RATE} "
        f"min_bars={MIN_BARS}"
    )
