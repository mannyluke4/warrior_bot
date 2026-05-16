"""Shared fixtures for framework tests.

Adds the repo root to sys.path so `import framework` resolves to
`/Users/duffy/warrior_bot_v2/framework/` regardless of how pytest is
invoked. Tests should never modify existing live code; the framework
lives entirely under framework/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
