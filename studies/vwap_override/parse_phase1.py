#!/usr/bin/env python3
"""Parse Phase 1 VWAP blocked arm data from simulation output."""
import re
import os
import json

OUTDIR = "studies/vwap_override/phase1_output"

blocked_arms = []

for fname in sorted(os.listdir(OUTDIR)):
    if not fname.endswith(".txt"):
        continue
    parts = fname.replace(".txt", "").split("_")
    symbol = parts[0]
    date = "-".join(parts[1:])

    fpath = os.path.join(OUTDIR, fname)
    lines = open(fpath).readlines()

    # Get baseline P&L
    baseline_pnl = 0
    for line in lines:
        m = re.search(r'Gross P&L: \$([+\-]?[\d,]+)', line)
        if m:
            baseline_pnl = int(m.group(1).replace(",", "").replace("+", ""))

    # Parse BLOCKED lines and their post_block lines
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "BLOCKED:" in line and "VWAP_BLOCKED_ARM" in line:
            # Parse the blocked arm
            time_m = re.search(r'time=(\d+:\d+)', line)
            score_m = re.search(r'score=([\d.]+)', line)
            entry_m = re.search(r'entry=([\d.]+)', line)
            stop_m = re.search(r'stop=([\d.]+)', line)
            r_m = re.search(r'R=([\d.]+)', line)
            detail_m = re.search(r'detail=(.+?) close=', line)
            close_m = re.search(r'close=([\d.]+)', line)
            vwap_m = re.search(r'vwap=([\d.]+)', line)

            arm = {
                "symbol": symbol,
                "date": date,
                "time": time_m.group(1) if time_m else "",
                "score": float(score_m.group(1)) if score_m else 0,
                "entry": float(entry_m.group(1)) if entry_m else 0,
                "stop": float(stop_m.group(1)) if stop_m else 0,
                "R": float(r_m.group(1)) if r_m else 0,
                "detail": detail_m.group(1).strip() if detail_m else "",
                "close_at_block": float(close_m.group(1)) if close_m else 0,
                "vwap_at_block": float(vwap_m.group(1)) if vwap_m else 0,
                "baseline_pnl": baseline_pnl,
            }

            # Look for post_block line
            if i + 1 < len(lines) and "post_block:" in lines[i + 1]:
                pb = lines[i + 1].strip()
                m5 = re.search(r'max_5m=([\d.]+)', pb)
                m10 = re.search(r'max_10m=([\d.]+)', pb)
                m30 = re.search(r'max_30m=([\d.]+)', pb)
                arm["max_high_5m"] = float(m5.group(1)) if m5 else 0
                arm["max_high_10m"] = float(m10.group(1)) if m10 else 0
                arm["max_high_30m"] = float(m30.group(1)) if m30 else 0
                i += 1

            # Calculate hypothetical P&L if entered at arm price with stop
            # Using $1000 risk, qty = risk / R
            risk = 1000
            if arm["R"] > 0:
                qty = int(risk / arm["R"])
                # Hypothetical exit at max_high_30m (best case)
                if arm.get("max_high_30m", 0) > 0:
                    hyp_pnl_30m = (arm["max_high_30m"] - arm["entry"]) * qty
                    arm["hyp_pnl_30m"] = hyp_pnl_30m
                    arm["hyp_qty"] = qty
                    # Would the stop have been hit? (close at block was below entry)
                    arm["would_stop"] = arm["close_at_block"] <= arm["stop"]
                    # Did price recover above entry?
                    arm["recovered_5m"] = arm.get("max_high_5m", 0) >= arm["entry"]
                    arm["recovered_10m"] = arm.get("max_high_10m", 0) >= arm["entry"]
                    arm["recovered_30m"] = arm.get("max_high_30m", 0) >= arm["entry"]
                    # VWAP % at block
                    if arm["vwap_at_block"] > 0:
                        arm["pct_below_vwap"] = (arm["vwap_at_block"] - arm["close_at_block"]) / arm["vwap_at_block"] * 100

            # Extract tags from detail
            tags = []
            if "bull_struct" in arm["detail"]:
                tags.append("ABCD")
            if "vol_surge" in arm["detail"]:
                tags.append("VOLUME_SURGE")
            if "r2g" in arm["detail"]:
                tags.append("RED_TO_GREEN")
            if "whole" in arm["detail"]:
                tags.append("WHOLE_DOLLAR_NEARBY")
            arm["tags"] = tags

            blocked_arms.append(arm)
        i += 1

# Sort by score descending
blocked_arms.sort(key=lambda x: x["score"], reverse=True)

# Output as JSON for further processing
print(json.dumps(blocked_arms, indent=2))
