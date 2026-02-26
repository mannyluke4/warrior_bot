# logger.py
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

LOG_DIR = os.getenv("WB_LOG_DIR", "logs")
RUN_ID = os.getenv("WB_RUN_ID")  # optional override

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _utc_iso(ts: Optional[datetime] = None) -> str:
    if ts is None:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()

def get_run_id() -> str:
    global RUN_ID
    if RUN_ID:
        return RUN_ID
    RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return RUN_ID

def log_event(event_type: str, symbol: Optional[str] = None, **fields: Any) -> None:
    """
    Writes one JSON object per line to logs/events_<run_id>.jsonl
    """
    _ensure_dir(LOG_DIR)
    path = os.path.join(LOG_DIR, f"events_{get_run_id()}.jsonl")

    payload: Dict[str, Any] = {
        "ts_utc": _utc_iso(),
        "event": event_type,
        "symbol": symbol,
        "run_id": get_run_id(),
        **fields,
    }

    # Keep it compact + reliable
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")