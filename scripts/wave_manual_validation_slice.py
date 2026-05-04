"""wave_manual_validation_slice.py — prepare a CSV slice for Manny's
manual review of the wave detector.

Per Stage 2 directive: Manny picks 5 of his best wave-scalp days from
TradingView paper P&L log. We filter the wave detail CSV to those
(date, symbol) combinations and present them in a review-friendly form.

Usage:
  python scripts/wave_manual_validation_slice.py 2026-04-22:KIDZ 2026-04-23:CRWG ...

Each arg is `YYYY-MM-DD:SYMBOL`. We pull from the V8b/V2-trailing wave
detail (the recommended config's view of the day). Output CSV columns:

  date, symbol, wave_id, direction, score, start_time_et, start_price,
  end_time_et, end_price, duration_minutes, magnitude_pct,
  manual_TP_FP_FN, comments

Last two columns are blank — Manny fills them in.

The Stage-2 acceptance gate cares about:
  - TP rate ≥ 70% — algorithm catches Manny's actual trades
  - FP rate ≤ 50% — fewer than half of algorithm's flags would be ones
    Manny wouldn't take
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from typing import List, Tuple

import pytz

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = pytz.timezone("US/Eastern")


def parse_pairs(args: List[str]) -> List[Tuple[str, str]]:
    out = []
    for a in args:
        if ":" not in a:
            print(f"Skipping malformed arg: {a} (expected YYYY-MM-DD:SYMBOL)",
                  file=sys.stderr)
            continue
        date_str, sym = a.split(":", 1)
        out.append((date_str.strip(), sym.strip().upper()))
    return out


def load_waves(detail_csv: str) -> List[dict]:
    if not os.path.exists(detail_csv):
        print(f"Wave detail CSV not found: {detail_csv}", file=sys.stderr)
        sys.exit(2)
    with open(detail_csv) as f:
        return list(csv.DictReader(f))


def to_et_time(utc_iso: str) -> str:
    """Convert ISO UTC timestamp to ET HH:MM:SS for review readability."""
    try:
        dt = datetime.fromisoformat(utc_iso)
        return dt.astimezone(ET).strftime("%H:%M:%S")
    except Exception:
        return utc_iso


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExample:")
        print("  python scripts/wave_manual_validation_slice.py "
              "2026-04-22:KIDZ 2026-04-23:CRWG 2026-04-29:SKYQ "
              "2026-04-30:HTZ 2026-05-01:CERS")
        return 1

    pairs = parse_pairs(sys.argv[1:])
    if not pairs:
        print("No valid (date, symbol) pairs given", file=sys.stderr)
        return 2

    # Pull from the recommended V8b config's view of waves (waves are
    # detection-side; identical across variants, so v0 detail is fine).
    detail_csv = os.path.join(REPO, "wave_research", "v0_baseline",
                              "v0_baseline_waves_detail.csv")
    waves = load_waves(detail_csv)

    # Index by (date, symbol) for fast filter
    pair_set = set(pairs)
    matched: List[dict] = []
    for w in waves:
        if (w.get("date"), w.get("symbol", "").upper()) in pair_set:
            matched.append(w)

    if not matched:
        print(f"No waves matched the {len(pairs)} (date, symbol) pairs given.",
              file=sys.stderr)
        print("Check that the dates are in tick_cache/ AND that the symbols "
              "produced waves on those days.", file=sys.stderr)
        return 3

    out_path = os.path.join(REPO, "wave_research", "manual_validation_slice.csv")

    fields = [
        "date", "symbol", "wave_id", "direction",
        "start_time_et", "start_price", "end_time_et", "end_price",
        "duration_minutes", "magnitude_pct", "score",
        "score_near_recent_low", "score_macd_rising", "score_higher_low",
        "score_volume_confirm", "score_green_bounce",
        # Manny-fillable columns
        "manual_label_TP_FP_FN_skip",
        "manual_comment",
    ]

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in sorted(matched, key=lambda r: (r.get("date"), r.get("symbol"),
                                                  int(r.get("wave_id") or 0))):
            row = {
                "date": m.get("date"),
                "symbol": m.get("symbol"),
                "wave_id": m.get("wave_id"),
                "direction": m.get("direction"),
                "start_time_et": to_et_time(m.get("start_time_utc", "")),
                "start_price": m.get("start_price"),
                "end_time_et": to_et_time(m.get("end_time_utc", "")),
                "end_price": m.get("end_price"),
                "duration_minutes": m.get("duration_minutes"),
                "magnitude_pct": m.get("magnitude_pct"),
                "score": m.get("score") or "",
                "score_near_recent_low": m.get("score_near_recent_low") or "",
                "score_macd_rising": m.get("score_macd_rising") or "",
                "score_higher_low": m.get("score_higher_low") or "",
                "score_volume_confirm": m.get("score_volume_confirm") or "",
                "score_green_bounce": m.get("score_green_bounce") or "",
                "manual_label_TP_FP_FN_skip": "",
                "manual_comment": "",
            }
            w.writerow(row)

    by_pair = {}
    for m in matched:
        k = (m.get("date"), m.get("symbol"))
        by_pair[k] = by_pair.get(k, 0) + 1
    print(f"Wrote {len(matched)} waves across {len(by_pair)} (date, symbol) pairs:")
    for k, n in sorted(by_pair.items()):
        print(f"  {k[0]} {k[1]:<6}  {n} waves")
    print(f"\n→ {out_path}")
    print()
    print("Manny: open in a spreadsheet. For each row, fill manual_label_TP_FP_FN_skip with one of:")
    print("  TP   = algorithm flagged a wave I traded (correct)")
    print("  FP   = algorithm flagged a wave I would NOT take (false alarm)")
    print("  skip = wave irrelevant to my play (e.g., late-day or wrong direction)")
    print()
    print("After labeling, also list any waves you DID trade that the algorithm")
    print("MISSED (false negatives) at the bottom of the CSV with FN in the label column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
