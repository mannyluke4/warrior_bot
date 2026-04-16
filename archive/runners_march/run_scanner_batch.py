#!/usr/bin/env python3
"""Batch re-scan all trading days for YTD backtest."""
import subprocess
import time
import os
import json

DATES = [
    # January
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
    # February
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
    # March
    "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
    "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12",
]

STATE_FILE = "scanner_batch_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def main():
    state = load_state()
    completed = set(state["completed"])
    remaining = [d for d in DATES if d not in completed]

    print(f"Scanner batch: {len(completed)}/{len(DATES)} done, {len(remaining)} remaining")

    for i, date in enumerate(remaining):
        print(f"\n[{len(completed)+i+1}/{len(DATES)}] Scanning {date}...", flush=True)
        start = time.time()
        try:
            r = subprocess.run(
                ["python", "scanner_sim.py", "--date", date],
                capture_output=True, text=True, timeout=600,
                cwd="/Users/mannyluke/warrior_bot"
            )
            elapsed = time.time() - start
            # Extract candidate count
            cnt_line = [l for l in r.stdout.split("\n") if "Total candidates" in l]
            cnt = cnt_line[0].strip() if cnt_line else "unknown"
            print(f"  Done in {elapsed:.0f}s — {cnt}", flush=True)
            if r.returncode != 0:
                print(f"  WARNING: exit code {r.returncode}", flush=True)
                if r.stderr:
                    print(f"  stderr: {r.stderr[-200:]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 600s", flush=True)
            continue
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue

        state["completed"].append(date)
        save_state(state)

    print(f"\nAll {len(DATES)} dates scanned!")

if __name__ == "__main__":
    main()
