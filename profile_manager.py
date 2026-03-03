"""
Profile Manager — Multi-Profile Trading System

Each stock on the watchlist can carry a profile tag (e.g., APVO:A, ANPA:B).
Each profile has its own env var overrides that are applied before detector
creation and restored after, so profiles are fully isolated.

Profile codes:
  A — Micro-Float Pre-Market Runner (PROVEN, default)
  B — Mid-Float L2-Assisted (CANDIDATE)
  C — Fast Mover (EARLY CANDIDATE)
  X — Unknown/Conservative (CATCH-ALL)
"""

import json
import os
from pathlib import Path

PROFILES_DIR = Path(__file__).parent / "profiles"


def parse_symbol_profile(entry: str) -> tuple[str, str]:
    """
    Parse 'APVO:A' into ('APVO', 'A'). Default to 'A' if no tag.

    >>> parse_symbol_profile('APVO:A')
    ('APVO', 'A')
    >>> parse_symbol_profile('GWAV')
    ('GWAV', 'A')
    >>> parse_symbol_profile('ANPA:b')
    ('ANPA', 'B')
    """
    if ":" in entry:
        sym, profile = entry.split(":", 1)
        return sym.strip(), profile.strip().upper()
    return entry.strip(), "A"


def load_profile(profile_code: str) -> dict:
    """
    Load profile JSON from profiles/{code}.json.
    Falls back to Profile A if the requested profile file doesn't exist.
    Returns dict of env var name -> value.
    """
    path = PROFILES_DIR / f"{profile_code.upper()}.json"
    if not path.exists():
        fallback = PROFILES_DIR / "A.json"
        if fallback.exists():
            path = fallback
        else:
            return {}
    with open(path) as f:
        return json.load(f)


def apply_profile_env(profile_code: str) -> dict:
    """
    Apply profile env var overrides to os.environ.
    Returns a dict of {key: original_value} for use with restore_env().

    Call BEFORE MicroPullbackDetector() or any os.getenv() reads that
    should be affected by the profile.
    """
    overrides = load_profile(profile_code)
    saved = {}
    for key, value in overrides.items():
        saved[key] = os.environ.get(key)  # None if not currently set
        os.environ[key] = str(value)
    return saved


def restore_env(saved: dict):
    """
    Restore env vars to their pre-profile state.
    Always call this in a finally block after apply_profile_env().
    """
    for key, original in saved.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
