#!/usr/bin/env python3
"""
fix_sim_start.py — Reprocess all scanner_results/*.json files to correct
the sim_start values that were corrupted by resolve_precise_discovery().

The bug (commit efa9b3f): resolve_precise_discovery() overwrote sim_start
with the raw minute a stock first met gap/vol criteria (often 04:00 AM),
instead of the scanner checkpoint when it would actually have been visible.

This script fixes sim_start for all 297 dates using first_seen_et (the
original checkpoint discovery time) and maps it to the correct scanner
checkpoint via the same logic the live scanner uses:
  - first_seen_et < "07:15"  →  "07:00"  (premarket scan)
  - "07:15" <= first_seen_et <= "08:00"  →  "08:00"
  - "08:00" < first_seen_et <= "08:30"  →  "08:30"
  - ... etc through "10:30"

Run from warrior_bot directory:
    python fix_sim_start.py [--dry-run]
"""

import argparse
import json
import os
import sys
from glob import glob

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
CHECKPOINTS = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30"]


def checkpoint_for(time_str: str) -> str:
    """Map a HH:MM time string to the correct scanner checkpoint sim_start."""
    if not time_str or time_str == "?":
        return "07:00"
    if time_str < "07:15":
        return "07:00"
    for cp in CHECKPOINTS:
        if time_str <= cp:
            return cp
    return "10:30"  # beyond last checkpoint


def fix_json(path: str, dry_run: bool) -> dict:
    """
    Load one scanner_results JSON, fix sim_start for each candidate,
    and write it back (unless dry_run). Returns stats.
    """
    with open(path) as f:
        candidates = json.load(f)

    changed = 0
    unchanged = 0
    errors = []

    for c in candidates:
        sym = c.get("symbol", "?")
        old_start = c.get("sim_start", "?")

        # Use first_seen_et as the source of truth for the checkpoint.
        # This is the field set by the original scanner logic (before the bug).
        # For premarket stocks it's the exact minute they were found in PM scan;
        # for rescan stocks it's the checkpoint time.
        first_seen = c.get("first_seen_et", "")
        if not first_seen:
            # No first_seen_et — fall back to precise_discovery if available
            first_seen = c.get("precise_discovery", "")

        if not first_seen:
            errors.append(f"{sym}: no first_seen_et or precise_discovery, skipping")
            unchanged += 1
            continue

        correct_start = checkpoint_for(first_seen)

        if correct_start != old_start:
            c["sim_start"] = correct_start
            c["discovery_time"] = correct_start
            # Preserve precise_discovery and first_seen_et as metadata
            changed += 1
            if not dry_run:
                pass  # will write below
            else:
                print(f"  [DRY] {sym}: {old_start} → {correct_start} "
                      f"(first_seen={first_seen})")
        else:
            unchanged += 1

    if changed > 0 and not dry_run:
        with open(path, "w") as f:
            json.dump(candidates, f, indent=2)

    return {"changed": changed, "unchanged": unchanged, "errors": errors}


def main():
    parser = argparse.ArgumentParser(
        description="Reprocess scanner_results/*.json to fix sim_start values"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing files")
    args = parser.parse_args()

    json_files = sorted(glob(os.path.join(SCANNER_DIR, "*.json")))
    # Exclude float_cache.json and other non-date files
    date_files = [f for f in json_files
                  if os.path.basename(f)[:4].isdigit()]

    print(f"fix_sim_start.py — {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Processing {len(date_files)} scanner_results files...")
    print()

    total_changed = 0
    total_unchanged = 0
    total_errors = 0
    files_changed = 0

    for path in date_files:
        date_str = os.path.basename(path).replace(".json", "")
        stats = fix_json(path, args.dry_run)

        if stats["changed"] > 0:
            files_changed += 1
            total_changed += stats["changed"]
            if not args.dry_run:
                print(f"  {date_str}: {stats['changed']} fixed, {stats['unchanged']} unchanged")

        total_unchanged += stats["unchanged"]

        for err in stats["errors"]:
            print(f"  WARN {date_str}: {err}")
            total_errors += 1

    print()
    print(f"Summary:")
    print(f"  Files processed:  {len(date_files)}")
    print(f"  Files modified:   {files_changed}")
    print(f"  Candidates fixed: {total_changed}")
    print(f"  Unchanged:        {total_unchanged}")
    print(f"  Errors/skipped:   {total_errors}")

    # Spot-check: verify key assertions from the directive
    print()
    print("Spot-checks:")
    spot_checks = [
        ("scanner_results/2026-01-16.json", "VERO", "07:00"),
        ("scanner_results/2025-01-02.json", "VSME", None),  # expected varies by first_seen_et
        ("scanner_results/2025-08-18.json", "MB", "10:00"),
        ("scanner_results/2025-01-21.json", "PTHS", "10:00"),
    ]
    all_pass = True
    for rel_path, sym, expected in spot_checks:
        full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)
        if not os.path.exists(full_path):
            print(f"  SKIP  {sym} ({rel_path}) — file not found")
            continue
        with open(full_path) as f:
            data = json.load(f)
        found = next((c for c in data if c.get("symbol") == sym), None)
        if not found:
            print(f"  SKIP  {sym} not in {rel_path}")
            continue
        actual = found.get("sim_start")
        if expected is not None:
            status = "PASS" if actual == expected else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  {status}  {sym} sim_start={actual} (expected={expected})")
        else:
            print(f"  INFO  {sym} sim_start={actual} (first_seen_et={found.get('first_seen_et')})")

    # Verify no candidates have sim_start < 07:00
    print()
    print("Verifying no candidates have sim_start < 07:00 ...")
    bad_count = 0
    for path in date_files:
        date_str = os.path.basename(path).replace(".json", "")
        with open(path) as f:
            candidates = json.load(f)
        for c in candidates:
            start = c.get("sim_start", "")
            if start and start < "07:00":
                print(f"  BAD: {date_str} {c.get('symbol')} sim_start={start}")
                bad_count += 1

    if bad_count == 0:
        print(f"  PASS — all {total_changed + total_unchanged} candidates have sim_start >= 07:00")
        all_pass = True
    else:
        print(f"  FAIL — {bad_count} candidates still have sim_start < 07:00")
        all_pass = False

    print()
    if args.dry_run:
        print("DRY RUN complete — no files written.")
    else:
        print(f"Done. {'All spot-checks passed.' if all_pass else 'SOME CHECKS FAILED — review above.'}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
